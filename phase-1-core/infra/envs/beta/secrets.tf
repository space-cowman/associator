# Secrets Manager entries and generated passwords.
resource "random_password" "postgres_admin" {
  length  = 32
  special = false
}

resource "random_password" "postgres_owner" {
  length  = 32
  special = false
}

resource "random_password" "postgres_app" {
  length  = 32
  special = false
}

resource "random_password" "postgres_orchestrator" {
  length  = 32
  special = false
}

resource "random_password" "redis" {
  length  = 32
  special = false
}

resource "random_password" "redis_admin" {
  length  = 32
  special = false
}

resource "random_password" "jwt_signing_key" {
  length  = 64
  special = false
}

resource "random_password" "identity_pepper" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "database" {
  name                    = "${var.project}/${var.environment}/database"
  description             = "Postgres and Redis passwords, and the api's JWT signing key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "database" {
  secret_id = aws_secretsmanager_secret.database.id
  secret_string = jsonencode({
    postgres_admin_password        = random_password.postgres_admin.result
    postgres_owner_password        = random_password.postgres_owner.result
    postgres_app_password          = random_password.postgres_app.result
    postgres_orchestrator_password = random_password.postgres_orchestrator.result
    redis_password                 = random_password.redis.result
    redis_admin_password           = random_password.redis_admin.result
    jwt_signing_key                = random_password.jwt_signing_key.result
    identity_pepper                = random_password.identity_pepper.result
  })
}

resource "aws_secretsmanager_secret" "llm" {
  name                    = "${var.project}/${var.environment}/llm"
  description             = "LLM provider keys for the platform model (values set by the owner, not Terraform)"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "oauth" {
  name                    = "${var.project}/${var.environment}/oauth"
  description             = "Sign-in OAuth client ids and secrets (values set by the owner, not Terraform)"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret" "grafana" {
  name                    = "${var.project}/${var.environment}/grafana"
  description             = "Grafana Cloud OTLP endpoint, instance id and write token (values set by the owner, not Terraform)"
  recovery_window_in_days = 0
}
