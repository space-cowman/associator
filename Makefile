# Developer commands. Run make help to list them.
SHELL := /bin/bash
.DEFAULT_GOAL := help

export PRE_COMMIT_HOME   := .cache/pre-commit

BUILDER   := desktop-linux
PLATFORMS := linux/arm64,linux/amd64

AWS_REGION  := ap-south-1
WEB_NODE    := node:24.22.1-alpine
WEB_RUN     := docker run --rm -e NPM_CONFIG_UPDATE_NOTIFIER=false -v $(CURDIR)/phase-1-core/web:/app -v platform-v2-web-modules:/app/node_modules -w /app $(WEB_NODE)
TF_DIR      := phase-1-core/infra/envs/beta
DB_SECRET   := platform-v2/beta/database
LLM_SECRET  := platform-v2/beta/llm
CI_SECRET   := platform-v2/beta/ci
REDTEAM_KEY = export GROQ_API_KEY="$${GROQ_API_KEY:-$$(aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(LLM_SECRET) --query SecretString --output text | python3 -c 'import json,sys; c=json.load(sys.stdin); print(c.get("eval_groq_api_key") or c["groq_api_key"])')}"
OAUTH_SECRET := platform-v2/beta/oauth
GRAFANA_SECRET := platform-v2/beta/grafana
OBS_DIR     := phase-3-optimise/observability/k8s
SECRET_MERGE = python3 -c 'import json,os,subprocess,sys; \
cur=subprocess.run(["aws","secretsmanager","get-secret-value","--region","$(AWS_REGION)","--secret-id","$(1)","--query","SecretString","--output","text"],capture_output=True,text=True); \
data=json.loads(cur.stdout) if cur.returncode==0 and cur.stdout.strip().startswith("{") else {}; \
data.update({k: os.environ[v].strip() for k, v in json.loads(sys.argv[1]).items()}); \
subprocess.run(["aws","secretsmanager","put-secret-value","--region","$(AWS_REGION)","--secret-id","$(1)","--secret-string","file:///dev/stdin"],input=json.dumps(data),text=True,check=True,stdout=subprocess.DEVNULL)'
GRAFANA_MERGE = $(call SECRET_MERGE,$(GRAFANA_SECRET))
SVC_SECRET  := platform-v2/beta/services
DB_URL_SYNC := postgresql+psycopg://platform_v2_owner@127.0.0.1:15432/platform_v2
ALEMBIC     := uv run alembic -c phase-1-core/api/alembic.ini
GIT_SHA     := $(shell git rev-parse --short HEAD)
NODE        ?= data_server_instance_id
DB_IMAGE    := pgvector/pgvector:0.8.2-pg16
BACKUP_DIR  := .secrets/backups
export KUBECONFIG := $(CURDIR)/.secrets/kubeconfig

define build_push
	@test -z "$$(git status --porcelain -- $(or $(3),phase-1-core)/$(1) pyproject.toml uv.lock)" \
	  || { echo "Commit the $(1) changes first: the image tag is the git commit"; exit 1; }
	@repo=$$(terraform -chdir=$(TF_DIR) output -raw $(2)); \
	  aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $${repo%%/*} >/dev/null && \
	  docker buildx build --builder $(BUILDER) --platform $(PLATFORMS) --provenance=false \
	    -f $(or $(3),phase-1-core)/$(1)/Dockerfile -t $$repo:$(GIT_SHA) --push . && \
	  echo "Pushed $$repo:$(GIT_SHA)"
endef

read_secret = $$(aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(DB_SECRET) \
  --query SecretString --output text | python3 -c 'import json,sys; print(json.load(sys.stdin)["$(1)"])')

.PHONY: evals-experiment loadgen loadgen-clean db-orchestrator-role orchestrator-image orchestrator-k8s-secret orchestrator-deploy help test lint fmt check hooks buildx-setup buildx-check db-tunnel db-migrate redis-tunnel api-dev dev-token typecheck kubeconfig kube-tunnel api-image k8s-secrets api-deploy api-tunnel safety-dev safety-image safety-deploy my-model my-model-delete llm-secret llm-k8s-secret gateway-dev gateway-image gateway-deploy mcp-image mcp-deploy mcp-tunnel mcp-connect oauth-secret oauth-k8s-secret e2e backup-deploy backup-now tunnels-close db-backup db-restore nodes-stop nodes-start web-install web-up web-down web-logs web-check web-image web-deploy traefik-deploy routes-deploy

publish: ## Publish the code (no .md files or decision records) to the public repository space-cowman/associator
	@phase-3-optimise/cicd/publish.sh

help: ## List all commands
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

test: ## Run all tests (tests against AWS run only when both tunnels are open)
	@if nc -z 127.0.0.1 15432 2>/dev/null && nc -z 127.0.0.1 16379 2>/dev/null; then \
	  export PGPASSWORD=$(call read_secret,postgres_app_password) REDIS_PASSWORD=$(call read_secret,redis_password) \
	    TEST_OWNER_PASSWORD=$(call read_secret,postgres_owner_password); fi; \
	  uv run pytest || [ $$? -eq 5 ]

e2e: ## Phase 1 end-to-end tests against the live site (needs make db-tunnel; throwaway users, cleaned up)
	@nc -z 127.0.0.1 15432 || { echo "Open the database tunnel first: make db-tunnel"; exit 1; }
	@export E2E_BASE_URL=https://$$(terraform -chdir=$(TF_DIR) output -raw domain) \
	  PGPASSWORD=$(call read_secret,postgres_app_password) TEST_OWNER_PASSWORD=$(call read_secret,postgres_owner_password) \
	  JWT_SIGNING_KEY=$(call read_secret,jwt_signing_key); \
	  uv run pytest phase-1-core/tests/e2e -v -p no:randomly

reports: ## Open reports from private chats, summary only (needs make db-tunnel)
	@PGPASSWORD=$(call read_secret,postgres_owner_password) uv run --project phase-1-core/api python phase-1b-private-chat/moderation.py reports

report: ## One report in full: make report id=<uuid> (it contains personal data; needs make db-tunnel)
	@test -n "$(id)" || { echo "usage: make report id=<uuid>"; exit 1; }
	@PGPASSWORD=$(call read_secret,postgres_owner_password) uv run --project phase-1-core/api python phase-1b-private-chat/moderation.py report $(id)

report-close: ## Close a report: make report-close id=<uuid> status=actioned|dismissed
	@test -n "$(id)" -a -n "$(status)" || { echo "usage: make report-close id=<uuid> status=actioned|dismissed"; exit 1; }
	@PGPASSWORD=$(call read_secret,postgres_owner_password) uv run --project phase-1-core/api python phase-1b-private-chat/moderation.py close $(id) $(status)

report-remove: ## Hide a reported public post and close the report: make report-remove id=<uuid>
	@test -n "$(id)" || { echo "usage: make report-remove id=<uuid>"; exit 1; }
	@PGPASSWORD=$(call read_secret,postgres_owner_password) uv run --project phase-1-core/api python phase-1b-private-chat/moderation.py remove $(id)

e2e-files-sweep: ## Old end-to-end encrypted chat files (unused since 2026-11-06); add confirm=1 to delete them
	@PGPASSWORD=$(call read_secret,postgres_owner_password) ATTACHMENTS_BUCKET=$$(terraform -chdir=$(TF_DIR) output -raw attachments_bucket) \
	  uv run --project phase-1-core/api python phase-1b-private-chat/moderation.py sweep $(if $(confirm),--confirm)

typecheck: ## Type-check the Python services (mypy, strict)
	uv run mypy phase-1-core/api/src
	uv run mypy phase-1-core/safety/src
	uv run mypy phase-1-core/llm-gateway/src
	uv run mypy phase-1-core/mcp-server/src
	uv run mypy phase-2-agentic/orchestrator/src

lint: ## Check code style and common bugs (no changes)
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Auto-fix style: format code and apply safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

check: ## Run every pre-commit check on all files (style, secrets, private keys, YAML)
	uv run pre-commit run --all-files

hooks: ## Install the git pre-commit hook (uses the project-local cache)
	@printf '%s\n' '#!/bin/sh' \
	  '# Installed by `make hooks`: runs pre-commit on staged files, cache kept in the project.' \
	  'cd "$$(git rev-parse --show-toplevel)" || exit 1' \
	  'PRE_COMMIT_HOME=.cache/pre-commit exec uv run --quiet pre-commit run' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Installed .git/hooks/pre-commit"

buildx-setup: ## Confirm Docker's builder supports arm64 + amd64
	@plats=$$(docker buildx inspect $(BUILDER) 2>/dev/null | grep -m1 '^Platforms:'); \
	  echo "$(BUILDER) $$plats"; \
	  echo "$$plats" | grep -q 'linux/arm64' && echo "$$plats" | grep -q 'linux/amd64' \
	  || { echo "Builder $(BUILDER) lacks arm64/amd64 — enable the containerd image store in Docker Desktop settings"; exit 1; }

buildx-check: buildx-setup ## Prove the builder makes arm64 + amd64 images (builds a tiny test image, pushes nothing)
	@set -o pipefail; \
	  out=$$(printf '%s\n' 'FROM python:3.12-slim' 'RUN python -c "import platform; print(\"built for:\", platform.machine())"' \
	    | docker buildx build --builder $(BUILDER) --platform $(PLATFORMS) --output type=cacheonly \
	        --progress plain --no-cache - 2>&1) \
	  || { echo "$$out" | grep -E 'ERROR' | tail -3; echo "buildx-check FAILED"; exit 1; }; \
	  echo "$$out" | grep -E '^#[0-9]+ [0-9.]+ built for:' ; echo "buildx-check OK"

db-tunnel: ## Open the SSM tunnel: Postgres on 127.0.0.1:15432 (keep it running; Ctrl+C closes it)
	aws ssm start-session --region $(AWS_REGION) \
	  --target $$(terraform -chdir=$(TF_DIR) output -raw $(NODE)) \
	  --document-name AWS-StartPortForwardingSessionToRemoteHost \
	  --parameters host=10.43.0.50,portNumber=5432,localPortNumber=15432

db-migrate: ## Apply all database migrations (needs `make db-tunnel` running in another terminal)
	@PGPASSWORD=$(call read_secret,postgres_owner_password) DATABASE_URL=$(DB_URL_SYNC) $(ALEMBIC) upgrade head

db-orchestrator-role: ## One-time: the orchestrator's own Postgres role + schema (needs make db-tunnel; admin, no access to people's tables)
	@PG_ADMIN_PASSWORD=$(call read_secret,postgres_admin_password) PG_ORCHESTRATOR_PASSWORD=$(call read_secret,postgres_orchestrator_password) \
	  uv run python phase-2-agentic/orchestrator/scripts/db_role.py

backup-deploy: ## Install the nightly database backup (02:00 IST) with its upload-only key (needs make kube-tunnel)
	@aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id platform-v2/beta/backup --query SecretString --output text \
	  | python3 -c 'import json,sys; c=json.load(sys.stdin); print("aws-access-key-id=" + c["access_key_id"]); print("aws-secret-access-key=" + c["secret_access_key"])' \
	  | kubectl -n data create secret generic backup-credentials --from-env-file=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
	@sed "s#__BUCKET__#$$(terraform -chdir=$(TF_DIR) output -raw backups_bucket)#" phase-1-core/infra/k8s/backup.yaml | kubectl apply -f -

backup-now: ## Run the database backup once now and show the result
	@job=postgres-backup-manual-$$(date +%s); kubectl -n data create job $$job --from=cronjob/postgres-backup >/dev/null && \
	  kubectl -n data wait --for=condition=complete job/$$job --timeout=300s && kubectl -n data logs job/$$job -c upload

tunnels-close: ## Close every local SSM tunnel (by the process holding each port, not just the aws command)
	@for p in 15432 16379 16443 18000 18001; do lsof -tiTCP:$$p -sTCP:LISTEN 2>/dev/null; done | sort -u | xargs kill 2>/dev/null; \
	  pkill -f "ssm start-session" 2>/dev/null; sleep 1; \
	  for p in 15432 16379 16443 18000 18001; do ! lsof -tiTCP:$$p -sTCP:LISTEN >/dev/null 2>&1 || echo "port $$p still open"; done; echo "Tunnels closed"

db-backup: ## Dump the whole database to .secrets/backups (git-ignored; needs make db-tunnel). Runs pg_dump in Docker
	@mkdir -p $(BACKUP_DIR) && chmod 700 $(BACKUP_DIR); f=$(BACKUP_DIR)/platform-$$(date +%Y%m%d-%H%M%S).dump; \
	  PW=$(call read_secret,postgres_admin_password); \
	  docker run --rm -e PGPASSWORD="$$PW" $(DB_IMAGE) pg_dump -h host.docker.internal -p 15432 -U platform_v2_admin \
	    -d platform_v2 -Fc > $$f && chmod 600 $$f && echo "Backup: $$f ($$(du -h $$f | cut -f1))"; unset PW

db-restore: ## Restore a backup into the (empty) database: make db-restore FILE=.secrets/backups/x.dump (needs make db-tunnel)
	@test -f "$(FILE)" || { echo "FILE=... must point to a backup"; exit 1; }
	@PW=$(call read_secret,postgres_admin_password); \
	  docker run --rm -i -e PGPASSWORD="$$PW" $(DB_IMAGE) pg_restore -h host.docker.internal -p 15432 -U platform_v2_admin \
	    -d platform_v2 --exit-on-error --single-transaction < $(FILE) && echo "Restored $(FILE)"; unset PW

nodes-stop: ## Stop all cluster nodes (saves credits; the site goes offline). The NAT gateway keeps billing: see README
	@ids=$$(terraform -chdir=$(TF_DIR) output -json tier_nodes | python3 -c 'import json,sys; print(" ".join(n["id"] for n in json.load(sys.stdin).values()))'); \
	  aws ec2 stop-instances --region $(AWS_REGION) --instance-ids $$ids --query 'StoppingInstances[].InstanceId' --output text

nodes-start: ## Start all cluster nodes again (data first is not needed: agents retry until the server is up)
	@ids=$$(terraform -chdir=$(TF_DIR) output -json tier_nodes | python3 -c 'import json,sys; print(" ".join(n["id"] for n in json.load(sys.stdin).values()))'); \
	  aws ec2 start-instances --region $(AWS_REGION) --instance-ids $$ids --query 'StartingInstances[].InstanceId' --output text

redis-tunnel: ## Open the SSM tunnel: Redis on 127.0.0.1:16379 (keep it running; Ctrl+C closes it)
	aws ssm start-session --region $(AWS_REGION) \
	  --target $$(terraform -chdir=$(TF_DIR) output -raw $(NODE)) \
	  --document-name AWS-StartPortForwardingSessionToRemoteHost \
	  --parameters host=10.43.0.51,portNumber=6379,localPortNumber=16379

api-dev: ## Run the api on the Mac against beta via both tunnels (+ make safety-dev); docs at http://127.0.0.1:8000/docs
	@PGPASSWORD=$(call read_secret,postgres_app_password) REDIS_PASSWORD=$(call read_secret,redis_password) \
	  JWT_SIGNING_KEY=$(call read_secret,jwt_signing_key) \
	  DOCS_ENABLED=true uv run uvicorn api.main:app --app-dir phase-1-core/api/src --reload --port 8000 --no-server-header

dev-token: ## Print a dev token: make dev-token handle=alice [agent=1] [hours=12] (needs make db-tunnel)
	@test -n "$(handle)" || { echo "usage: make dev-token handle=alice"; exit 1; }
	@PGPASSWORD=$(call read_secret,postgres_app_password) JWT_SIGNING_KEY=$(call read_secret,jwt_signing_key) \
	  PYTHONPATH=phase-1-core/api/src uv run python -m api.dev_token $(handle) $(if $(agent),--agent) $(if $(hours),--hours=$(hours))

kubeconfig: ## Fetch k3s admin access into .secrets/kubeconfig (git-ignored); use with make kube-tunnel
	@id=$$(terraform -chdir=$(TF_DIR) output -raw $(NODE)); \
	  cmd=$$(aws ssm send-command --region $(AWS_REGION) --instance-ids $$id --document-name AWS-RunShellScript \
	    --parameters 'commands=["cat /etc/rancher/k3s/k3s.yaml"]' --query Command.CommandId --output text); \
	  sleep 4; umask 077; \
	  aws ssm get-command-invocation --region $(AWS_REGION) --command-id $$cmd --instance-id $$id \
	    --query StandardOutputContent --output text | sed 's#https://127.0.0.1:6443#https://127.0.0.1:16443#' > $(KUBECONFIG); \
	  echo "Wrote $(KUBECONFIG)"

kube-tunnel: ## Open the SSM tunnel to the k3s API on 127.0.0.1:16443 (keep it running)
	aws ssm start-session --region $(AWS_REGION) \
	  --target $$(terraform -chdir=$(TF_DIR) output -raw $(NODE)) \
	  --document-name AWS-StartPortForwardingSession \
	  --parameters portNumber=6443,localPortNumber=16443

api-image: ## Build the api image (arm64 + amd64) and push it to ECR, tagged with the git commit
	$(call build_push,api,api_repository_url)

k8s-secrets: ## Copy the api's Postgres + Redis passwords and JWT key from Secrets Manager into k8s (namespace app)
	@kubectl create namespace app --dry-run=client -o yaml | kubectl apply -f - >/dev/null
	@PG=$(call read_secret,postgres_app_password); RD=$(call read_secret,redis_password); \
	  JWT=$(call read_secret,jwt_signing_key); PEPPER=$(call read_secret,identity_pepper); \
	  AWSK=$$(aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(SVC_SECRET) --query SecretString --output text \
	    | python3 -c 'import json,sys; c=json.load(sys.stdin)["api"]; print("aws-access-key-id=" + c["access_key_id"]); print("aws-secret-access-key=" + c["secret_access_key"])'); \
	  kubectl -n app create secret generic api-credentials \
	    --from-env-file=<(printf 'postgres-password=%s\nredis-password=%s\njwt-signing-key=%s\nidentity-pepper=%s\n%s\n' "$$PG" "$$RD" "$$JWT" "$$PEPPER" "$$AWSK") \
	    --dry-run=client -o yaml | kubectl apply -f -

api-deploy: ## Deploy the api image for the current git commit to k3s (needs make kube-tunnel)
	@repo=$$(terraform -chdir=$(TF_DIR) output -raw api_repository_url); kms=$$(terraform -chdir=$(TF_DIR) output -raw user_keys_kms_arn); \
	  bucket=$$(terraform -chdir=$(TF_DIR) output -raw attachments_bucket); \
	  sed -e "s#__IMAGE__#$$repo:$(GIT_SHA)#" -e "s#__KMS_ARN__#$$kms#" -e "s#__ATTACHMENTS_BUCKET__#$$bucket#" -e "s#__DOMAIN__#$$(terraform -chdir=$(TF_DIR) output -raw domain)#" phase-1-core/infra/k8s/api.yaml | kubectl apply -f - && \
	  kubectl -n app rollout status deploy/api --timeout=180s

api-tunnel: ## Forward the deployed api to 127.0.0.1:18000 (kubectl; needs make kube-tunnel)
	kubectl -n app port-forward svc/api 18000:8000

safety-dev: ## Run the safety service on the Mac (port 8002); docs at http://127.0.0.1:8002/docs
	DOCS_ENABLED=true uv run uvicorn safety.main:app --app-dir phase-1-core/safety/src --reload --port 8002 --no-server-header

safety-image: ## Build the safety image (arm64 + amd64) and push it to ECR, tagged with the git commit
	$(call build_push,safety,safety_repository_url)

safety-deploy: ## Deploy the safety image for the current git commit to k3s (needs make kube-tunnel)
	@repo=$$(terraform -chdir=$(TF_DIR) output -raw safety_repository_url); \
	  sed "s#__IMAGE__#$$repo:$(GIT_SHA)#" phase-1-core/infra/k8s/safety.yaml | kubectl apply -f - && \
	  kubectl -n ai rollout status deploy/safety --timeout=300s

oauth-secret: ## Store the GitHub + Google sign-in client ids and secrets in Secrets Manager (hidden input)
	@read -rs -p "GitHub client ID: " GI; echo; read -rs -p "GitHub client secret: " GS; echo; \
	  read -rs -p "Google client ID: " OI; echo; read -rs -p "Google client secret: " OS; echo; \
	  test -n "$$GI$$OI" || { echo "Nothing entered"; exit 1; }; \
	  GI="$$GI" GS="$$GS" OI="$$OI" OS="$$OS" python3 -c 'import json,os; print(json.dumps({k: os.environ[e].strip() for k, e in [("github_client_id","GI"),("github_client_secret","GS"),("google_client_id","OI"),("google_client_secret","OS")]}))' \
	  | aws secretsmanager put-secret-value --region $(AWS_REGION) --secret-id $(OAUTH_SECRET) \
	      --secret-string file:///dev/stdin >/dev/null && echo "Stored in $(OAUTH_SECRET)."; unset GI GS OI OS

grafana-secret: ## Store the Grafana Cloud OTLP endpoint, instance id and write-only data token (token hidden)
	@read -r -p "OTLP endpoint [Enter = https://otlp-gateway-prod-ap-south-1.grafana.net/otlp]: " E; \
	  E="$${E:-https://otlp-gateway-prod-ap-south-1.grafana.net/otlp}"; E="$${E%/}"; \
	  case "$$E" in https://otlp-gateway-*.grafana.net/otlp) ;; *) echo "Not a Grafana Cloud OTLP endpoint: '$$E' (expected https://otlp-gateway-<region>.grafana.net/otlp)"; exit 1;; esac; \
	  read -r -p "Instance ID (the number on the OpenTelemetry page): " I; I="$$(printf '%s' "$$I" | tr -d ' ')"; \
	  case "$$I" in ''|*[!0-9]*) echo "The Instance ID must be a number, got: '$$I'"; exit 1;; esac; \
	  read -rs -p "OTLP data token (hidden): " T; echo; \
	  test -n "$$T" || { echo "No token entered"; exit 1; }; \
	  E="$$E" I="$$I" T="$$T" $(GRAFANA_MERGE) '{"otlp_endpoint": "E", "instance_id": "I", "token": "T"}' && echo "Stored in $(GRAFANA_SECRET)."; unset E I T

grafana-tf-secret: ## Store your Grafana stack URL and the 'terraform' service-account token (token hidden)
	@read -r -p "Stack URL (https://<name>.grafana.net): " U; read -rs -p "terraform service-account token (hidden): " T; echo; \
	  case "$$U" in https://*.grafana.net) ;; *) echo "That does not look like a Grafana stack URL"; exit 1;; esac; \
	  test -n "$$T" || { echo "No token entered"; exit 1; }; \
	  U="$${U%/}" T="$$T" $(GRAFANA_MERGE) '{"stack_url": "U", "tf_token": "T"}' && echo "Stored in $(GRAFANA_SECRET)."; unset U T

grafana-k8s-secret: ## Copy the Grafana OTLP endpoint + data token into k8s (namespace observability; never printed)
	@kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f - >/dev/null
	@aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(GRAFANA_SECRET) --query SecretString --output text \
	  | python3 -c 'import base64,json,sys; c=json.load(sys.stdin); print("GRAFANA_OTLP_ENDPOINT=" + c["otlp_endpoint"]); print("GRAFANA_AUTH=" + base64.b64encode((c["instance_id"] + ":" + c["token"]).encode()).decode())' \
	  | kubectl -n observability create secret generic grafana-otlp --from-env-file=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -

obs-deploy: ## Deploy the OpenTelemetry Collector: its instructions, the program, its firewall (needs make kube-tunnel)
	kubectl create configmap otel-collector -n observability --from-file=$(OBS_DIR)/collector.yaml --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -f $(OBS_DIR)/access.yaml -f $(OBS_DIR)/run.yaml -f $(OBS_DIR)/firewall.yaml
	kubectl -n observability rollout restart deploy/otel-collector
	kubectl -n observability rollout status deploy/otel-collector --timeout=120s

GRAFANA_TF_ENV = eval "$$(aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(GRAFANA_SECRET) --query SecretString --output text \
	  | python3 -c 'import json,shlex,sys; c=json.load(sys.stdin); print("export GRAFANA_URL=" + shlex.quote(c["stack_url"]) + " GRAFANA_AUTH=" + shlex.quote(c["tf_token"]))')"
OBS_TF := phase-3-optimise/observability/terraform

dashboards: ## Rebuild the Grafana dashboard JSON files from phase-3-optimise/observability/dashboards/build.py
	@uv run python phase-3-optimise/observability/dashboards/build.py

LANGSMITH_ENV = eval "$$(aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(LLM_SECRET) --query SecretString --output text \
	  | python3 -c 'import json,shlex,sys; c=json.load(sys.stdin); print("export LANGSMITH_ENDPOINT=" + shlex.quote(c["langsmith_endpoint"]) + " LANGSMITH_API_KEY=" + shlex.quote(c["langsmith_api_key"]))')"

evals-dataset: ## Upload the draft test set (phase-3-optimise/evals/questions.jsonl) to LangSmith
	@$(LANGSMITH_ENV); PYTHONPATH=phase-1-core/api/src uv run python phase-3-optimise/evals/dataset.py

evals-experiment: ## Run a LangSmith experiment: ARM=platform:v1|platform:v2|own:<model>|orchestrator DATASET=... (needs db-tunnel + kube-tunnel)
	@test -n "$(ARM)" || { echo "Set ARM, e.g. make evals-experiment ARM=platform:v2"; exit 1; }
	@kubectl -n ai port-forward svc/llm-gateway 14000:4000 >/dev/null 2>&1 & GW=$$!; \
	  kubectl -n ai port-forward svc/orchestrator 18003:8003 >/dev/null 2>&1 & OR=$$!; sleep 3; \
	  $(LANGSMITH_ENV); PG_OWNER_PASSWORD=$(call read_secret,postgres_owner_password) \
	  uv run python phase-3-optimise/evals/experiment.py "$(ARM)" --dataset "$(or $(DATASET),associator-draft-questions)" $(if $(LIMIT),--limit $(LIMIT)) $(if $(PROMPT),--prompt $(PROMPT)); \
	  kill $$GW $$OR 2>/dev/null

evals-setup: ## Create/update the LangSmith judges, automations, review queue and edited-drafts dataset (phase-3-optimise/evals/setup.py)
	@$(LANGSMITH_ENV); python3 phase-3-optimise/evals/setup.py

REDTEAM := phase-3-optimise/evals/redteam
PROMPTFOO = docker run --rm -v $(CURDIR)/$(REDTEAM):/app -w /app -e GROQ_API_KEY \
	  -e PROMPTFOO_DISABLE_REMOTE_GENERATION=true -e PROMPTFOO_DISABLE_TELEMETRY=1 \
	  -e PROMPTFOO_DISABLE_UPDATE=1 -e PROMPTFOO_DISABLE_SHARING=1 -e HOME=/tmp/home -e npm_config_cache=/npm \
	  -v platform-v2-promptfoo-npm:/npm \
	  $(WEB_NODE) npx -y promptfoo@0.124.1

redteam: ## Red-team the AI draft prompt locally (promptfoo in Docker, Groq, no remote generation); reports in $(REDTEAM)/results
	@PYTHONPATH=phase-1-core/api/src uv run python -c 'from api import prompts; open("$(REDTEAM)/system.txt","w").write(prompts.SYSTEM + "\n")'
	@mkdir -p $(REDTEAM)/results
	@$(REDTEAM_KEY); \
	  echo "== canary tests"; $(PROMPTFOO) eval -c canary.yaml --no-cache --no-progress-bar -j 1 --delay 3000 -o results/canary.json; \
	  echo "== red team: generate attacks"; $(PROMPTFOO) redteam generate -c promptfooconfig.yaml --no-cache -o redteam-generated.yaml; \
	  echo "== red team: run attacks"; $(PROMPTFOO) eval -c redteam-generated.yaml --no-cache --no-progress-bar -j 1 --delay 15000 -o results/redteam.json

redteam-eval: ## Re-run the last generated attacks (redteam-generated.yaml) without generating new ones
	@$(REDTEAM_KEY); \
	  $(PROMPTFOO) eval -c redteam-generated.yaml --no-cache --no-progress-bar -j 1 --delay 15000 -o results/redteam.json

redteam-canary: ## Only the 6 fixed must-pass tests (under a minute)
	@PYTHONPATH=phase-1-core/api/src uv run python -c 'from api import prompts; open("$(REDTEAM)/system.txt","w").write(prompts.SYSTEM + "\n")'
	@mkdir -p $(REDTEAM)/results
	@$(REDTEAM_KEY); \
	  $(PROMPTFOO) eval -c canary.yaml --no-cache --no-progress-bar -j 1 --delay 3000 -o results/canary.json

obs-plan: ## Plan the Grafana dashboards and alerts (Terraform; reads the token from Secrets Manager)
	@$(GRAFANA_TF_ENV); terraform -chdir=$(OBS_TF) init -input=false >/dev/null && terraform -chdir=$(OBS_TF) plan -input=false -out=obs.tfplan

obs-apply: ## Apply the planned Grafana dashboards and alerts (you run this)
	@$(GRAFANA_TF_ENV); terraform -chdir=$(OBS_TF) apply obs.tfplan

oauth-k8s-secret: ## Copy the sign-in client ids and secrets from Secrets Manager into k8s (namespace app)
	@aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(OAUTH_SECRET) --query SecretString --output text \
	  | python3 -c 'import json,sys; c=json.load(sys.stdin); print("\n".join(k.replace("_","-") + "=" + v for k, v in c.items() if v))' \
	  | kubectl -n app create secret generic api-oauth --from-env-file=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -

llm-secret: ## Store the Groq API key in Secrets Manager (hidden input; never shown, saved or logged)
	@read -rs -p "Groq API key: " K; echo; \
	  test -n "$$K" || { echo "No key entered"; exit 1; }; \
	  printf '%s' "$$K" | python3 -c 'import json,sys; print(json.dumps({"groq_api_key": sys.stdin.read().strip()}))' \
	  | aws secretsmanager put-secret-value --region $(AWS_REGION) --secret-id $(LLM_SECRET) \
	      --secret-string file:///dev/stdin >/dev/null && echo "Stored in $(LLM_SECRET)."; unset K

langsmith-secret: ## Add the LangSmith API key (hidden) and region to the llm secret (the gateway sends traces)
	@read -r -p "LangSmith region [us/eu/apac]: " R; R="$$(printf '%s' "$$R" | tr 'A-Z' 'a-z' | tr -d ' ')"; \
	  case "$$R" in us) E=https://api.smith.langchain.com;; eu) E=https://eu.api.smith.langchain.com;; \
	    apac) E=https://apac.api.smith.langchain.com;; *) echo "Type us, eu or apac"; exit 1;; esac; \
	  read -rs -p "LangSmith API key (hidden): " K; echo; \
	  case "$$K" in lsv2_*) ;; *) echo "That does not look like a LangSmith key (they start with lsv2_)"; exit 1;; esac; \
	  E="$$E" K="$$K" $(call SECRET_MERGE,$(LLM_SECRET)) '{"langsmith_endpoint": "E", "langsmith_api_key": "K"}' && echo "Stored in $(LLM_SECRET)."; unset E K R

ci-secret: ## Copy the evals Groq key into the CI secret (never printed); CI's red-team canary reads only this
	@set -o pipefail; aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(LLM_SECRET) --query SecretString --output text \
	  | python3 -c 'import json,sys; k=json.load(sys.stdin).get("eval_groq_api_key"); k or sys.exit("No evals Groq key: run make eval-groq-key first"); print(json.dumps({"eval_groq_api_key": k}))' \
	  | aws secretsmanager put-secret-value --region $(AWS_REGION) --secret-id $(CI_SECRET) --secret-string file:///dev/stdin >/dev/null \
	  && echo "Stored the evals key in $(CI_SECRET)."

eval-groq-key: ## Store a SEPARATE Groq key for evals (hidden): judges + red team use it, so Platform AI users keep their capacity
	@read -rs -p "Evals Groq API key (hidden): " K; echo; \
	  case "$$K" in gsk_*) ;; *) echo "That does not look like a Groq key (they start with gsk_)"; exit 1;; esac; \
	  K="$$K" $(call SECRET_MERGE,$(LLM_SECRET)) '{"eval_groq_api_key": "K"}' && echo "Stored in $(LLM_SECRET) as eval_groq_api_key."; unset K
	@$(MAKE) -s langsmith-judge-key

langsmith-judge-key: ## Copy the evals Groq key (or, without one, the Platform AI key) into LangSmith's secrets as GROQ_API_KEY, for the judges (never printed)
	@aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(LLM_SECRET) --query SecretString --output text \
	  | python3 -c 'import json,sys,urllib.request; c=json.load(sys.stdin); \
	req=urllib.request.Request(c["langsmith_endpoint"] + "/api/v1/workspaces/current/secrets", method="POST", \
	  headers={"x-api-key": c["langsmith_api_key"], "Content-Type": "application/json"}, \
	  data=json.dumps([{"key": "GROQ_API_KEY", "value": c.get("eval_groq_api_key") or c["groq_api_key"]}]).encode()); \
	print("LangSmith secret GROQ_API_KEY set: HTTP", urllib.request.urlopen(req, timeout=30).status)'

llm-k8s-secret: ## Copy the provider keys from Secrets Manager into k8s (namespace ai, needs make kube-tunnel)
	@kubectl create namespace ai --dry-run=client -o yaml | kubectl apply -f - >/dev/null
	@GROQ=$$(aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(LLM_SECRET) --query SecretString --output text \
	    | python3 -c 'import json,sys; c=json.load(sys.stdin); print("\n".join(k.replace("_","-") + "=" + c[k] for k in ("groq_api_key", "langsmith_api_key", "langsmith_endpoint") if c.get(k)))'); \
	  AWSK=$$(aws secretsmanager get-secret-value --region $(AWS_REGION) --secret-id $(SVC_SECRET) --query SecretString --output text \
	    | python3 -c 'import json,sys; c=json.load(sys.stdin)["llm-gateway"]; print("aws-access-key-id=" + c["access_key_id"]); print("aws-secret-access-key=" + c["secret_access_key"])'); \
	  kubectl -n ai create secret generic llm-credentials --from-env-file=<(printf '%s\n%s\n' "$$GROQ" "$$AWSK") \
	    --dry-run=client -o yaml | kubectl apply -f -

gateway-dev: ## Run the llm-gateway on the Mac (port 4000, fake model; Groq if GROQ_API_KEY is set)
	DOCS_ENABLED=true uv run uvicorn gateway.main:app --app-dir phase-1-core/llm-gateway/src --reload --port 4000 --no-server-header

gateway-image: ## Build the llm-gateway image (arm64 + amd64) and push it to ECR, tagged with the git commit
	$(call build_push,llm-gateway,llm_gateway_repository_url)

gateway-deploy: ## Deploy the llm-gateway image for the current git commit to k3s (needs make kube-tunnel)
	@repo=$$(terraform -chdir=$(TF_DIR) output -raw llm_gateway_repository_url); kms=$$(terraform -chdir=$(TF_DIR) output -raw user_keys_kms_arn); \
	  sed -e "s#__IMAGE__#$$repo:$(GIT_SHA)#" -e "s#__KMS_ARN__#$$kms#" phase-1-core/infra/k8s/llm-gateway.yaml | kubectl apply -f - && \
	  kubectl -n ai rollout status deploy/llm-gateway --timeout=180s

orchestrator-image: ## Build the orchestrator image (arm64 + amd64) and push it to ECR, tagged with the git commit
	$(call build_push,orchestrator,orchestrator_repository_url,phase-2-agentic)

orchestrator-k8s-secret: ## Copy the orchestrator's Postgres password from Secrets Manager into k8s (namespace ai, needs make kube-tunnel)
	@kubectl create namespace ai --dry-run=client -o yaml | kubectl apply -f - >/dev/null
	@PW=$(call read_secret,postgres_orchestrator_password); \
	  kubectl -n ai create secret generic orchestrator-credentials --from-env-file=<(printf 'postgres-password=%s\n' "$$PW") \
	    --dry-run=client -o yaml | kubectl apply -f -

orchestrator-deploy: ## Deploy the orchestrator image for the current git commit to k3s (needs make kube-tunnel)
	@repo=$$(terraform -chdir=$(TF_DIR) output -raw orchestrator_repository_url); \
	  sed -e "s#__IMAGE__#$$repo:$(GIT_SHA)#" phase-2-agentic/orchestrator/k8s/orchestrator.yaml | kubectl apply -f - && \
	  kubectl -n ai rollout status deploy/orchestrator --timeout=180s

loadgen: ## Owner's pre-launch test: generated people create clusters, threads, replies, votes and Platform AI drafts in 6 waves, 20 min apart (needs db-tunnel + kube-tunnel)
	@nc -z 127.0.0.1 15432 || { echo "Open the database tunnel first: make db-tunnel"; exit 1; }
	@kubectl -n ai port-forward svc/llm-gateway 14000:4000 >/dev/null 2>&1 & PF=$$!; trap "kill $$PF" EXIT; sleep 3; \
	  PG_OWNER_PASSWORD=$(call read_secret,postgres_owner_password) JWT_SIGNING_KEY=$(call read_secret,jwt_signing_key) \
	  uv run python phase-3-optimise/loadgen/loadgen.py

loadgen-clean: ## Delete everything make loadgen created: exactly its people and what they made (needs db-tunnel)
	@PG_OWNER_PASSWORD=$(call read_secret,postgres_owner_password) uv run python phase-3-optimise/loadgen/clean.py

my-model: ## Save your own model key (hidden input): make my-model handle=you provider=openrouter model=google/gemma-4-31b-it:free (needs db + api tunnels)
	@test -n "$(handle)" -a -n "$(provider)" -a -n "$(model)" || { echo "usage: make my-model handle=you provider=openrouter model=google/gemma-4-31b-it:free"; exit 1; }
	@read -rs -p "$(provider) API key: " K; echo; test -n "$$K" || { echo "No key entered"; exit 1; }; \
	  TOKEN=$$($(MAKE) -s dev-token handle=$(handle)); \
	  printf '%s' "$$K" | python3 -c 'import json,sys; print(json.dumps({"provider": sys.argv[1], "model": sys.argv[2], "api_key": sys.stdin.read().strip()}))' "$(provider)" "$(model)" \
	  | curl -sS -X POST http://127.0.0.1:18000/me/models -H @<(printf 'Authorization: Bearer %s\n' "$$TOKEN") -H "Content-Type: application/json" --data @- ; \
	  echo; unset K TOKEN

my-model-delete: ## Delete your saved model (and its encrypted key): make my-model-delete handle=you (needs db + api tunnels)
	@test -n "$(handle)" || { echo "usage: make my-model-delete handle=you"; exit 1; }
	@TOKEN=$$($(MAKE) -s dev-token handle=$(handle)); H=$$(printf 'Authorization: Bearer %s' "$$TOKEN"); \
	  ids=$$(curl -sS http://127.0.0.1:18000/me/models -H @<(echo "$$H") | python3 -c 'import json,sys; print(" ".join(m["id"] for m in json.load(sys.stdin)))'); \
	  test -n "$$ids" || { echo "No saved model."; exit 0; }; \
	  for id in $$ids; do curl -sS -o /dev/null -w "deleted $$id -> HTTP %{http_code}\n" -X DELETE http://127.0.0.1:18000/me/models/$$id -H @<(echo "$$H"); done; \
	  unset TOKEN H

mcp-image: ## Build the mcp-server image (arm64 + amd64) and push it to ECR, tagged with the git commit
	$(call build_push,mcp-server,mcp_server_repository_url)

mcp-deploy: ## Deploy the mcp-server image for the current git commit to k3s (needs make kube-tunnel)
	@repo=$$(terraform -chdir=$(TF_DIR) output -raw mcp_server_repository_url); \
	  sed -e "s#__IMAGE__#$$repo:$(GIT_SHA)#" -e "s#__DOMAIN__#$$(terraform -chdir=$(TF_DIR) output -raw domain)#" phase-1-core/infra/k8s/mcp-server.yaml | kubectl apply -f - && \
	  kubectl -n app rollout status deploy/mcp-server --timeout=180s

mcp-tunnel: ## Open the SSM tunnel to the deployed MCP server on 127.0.0.1:18001 (keep it running)
	aws ssm start-session --region $(AWS_REGION) \
	  --target $$(terraform -chdir=$(TF_DIR) output -raw $(NODE)) \
	  --document-name AWS-StartPortForwardingSessionToRemoteHost \
	  --parameters host=10.43.0.61,portNumber=8001,localPortNumber=18001

mcp-connect: ## Create an access token and add the MCP server to Claude Code: make mcp-connect handle=you (needs db + api + mcp tunnels)
	@test -n "$(handle)" || { echo "usage: make mcp-connect handle=you"; exit 1; }
	@command -v claude >/dev/null || { echo "Claude Code CLI ('claude') not found on PATH"; exit 1; }
	@TOKEN=$$($(MAKE) -s dev-token handle=$(handle)); \
	  SOP=$$(curl -sS -X POST http://127.0.0.1:18000/me/tokens -H @<(printf 'Authorization: Bearer %s\n' "$$TOKEN") \
	    -H "Content-Type: application/json" --data '{"name": "claude-code"}' \
	    | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])'); \
	  claude mcp add --transport http --scope user project-platform http://127.0.0.1:18001/mcp \
	    --header "Authorization: Bearer $$SOP" >/dev/null && \
	  echo "Added 'project-platform' to Claude Code (token ends ...$${SOP: -4}). Revoke anytime: DELETE /me/tokens/<id>"; \
	  unset TOKEN SOP

web-image: ## Build the production web image (arm64 + amd64) and push it to ECR, tagged with the git commit
	@test -z "$$(git status --porcelain -- phase-1-core/web)" \
	  || { echo "Commit the web changes first: the image tag is the git commit"; exit 1; }
	@repo=$$(terraform -chdir=$(TF_DIR) output -raw web_repository_url); \
	  files=$$(terraform -chdir=$(TF_DIR) output -raw attachments_origin); \
	  aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $${repo%%/*} >/dev/null && \
	  docker buildx build --builder $(BUILDER) --platform $(PLATFORMS) --provenance=false \
	    --build-arg ATTACHMENTS_ORIGIN=$$files \
	    -f phase-1-core/web/Dockerfile -t $$repo:$(GIT_SHA) --push . && \
	  echo "Pushed $$repo:$(GIT_SHA)"

web-deploy: ## Deploy the web image for the current git commit to k3s (needs make kube-tunnel)
	@repo=$$(terraform -chdir=$(TF_DIR) output -raw web_repository_url); \
	  sed "s#__IMAGE__#$$repo:$(GIT_SHA)#" phase-1-core/infra/k8s/web.yaml | kubectl apply -f - && \
	  kubectl -n app rollout status deploy/web --timeout=180s

traefik-deploy: ## Install/upgrade Traefik (public entry, HTTPS) through k3s's Helm controller
	kubectl apply -f phase-1-core/infra/k8s/traefik.yaml
	@echo "Waiting for Traefik..."; for i in $$(seq 1 60); do \
	  kubectl -n kube-system rollout status deploy/traefik --timeout=5s >/dev/null 2>&1 && break; sleep 5; done
	kubectl -n kube-system rollout status deploy/traefik --timeout=120s

routes-deploy: ## Apply the public routes (domain from Terraform) and the app namespace's inbound policy
	@domain=$$(terraform -chdir=$(TF_DIR) output -raw domain); \
	  sed "s#__DOMAIN__#$$domain#g" phase-1-core/infra/k8s/routes.yaml | kubectl apply -f -

web-install: ## Install the web app's packages (inside Docker; nothing installed on the Mac)
	$(WEB_RUN) npm install --no-audit --no-fund

web-check: ## Type-check the web app (inside Docker)
	$(WEB_RUN) npx tsc --noEmit

web-up: ## Run the web app at http://localhost:3000 in the background (needs make api-tunnel)
	@docker rm -f platform-v2-web >/dev/null 2>&1 || true
	docker run -d --name platform-v2-web -p 127.0.0.1:3000:3000 \
	  -v $(CURDIR)/phase-1-core/web:/app -v platform-v2-web-modules:/app/node_modules -w /app \
	  -e API_URL=http://host.docker.internal:18000 -e WATCHPACK_POLLING=true -e NEXT_TELEMETRY_DISABLED=1 -e NPM_CONFIG_UPDATE_NOTIFIER=false \
	  -e ATTACHMENTS_ORIGIN=$$(terraform -chdir=$(TF_DIR) output -raw attachments_origin 2>/dev/null) \
	  $(WEB_NODE) npm run dev >/dev/null && echo "Web app starting at http://localhost:3000 (make web-logs to follow)"

web-down: ## Stop the web app
	@docker rm -f platform-v2-web >/dev/null 2>&1 && echo "Web app stopped" || echo "Web app was not running"

web-logs: ## Follow the web app's logs
	docker logs -f platform-v2-web
