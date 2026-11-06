# ruff: noqa: E501
"""Builds the Grafana dashboards as JSON (run: make dashboards; Terraform uploads the files)."""

import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "__METRICS_UID__"}
USAGE = {"type": "prometheus", "uid": "grafanacloud-usage"}
REQ = "http_server_request_duration_seconds"
OUT = "http_client_request_duration_seconds"
GREEN, AMBER, RED, BLUE = "green", "#EAB839", "red", "blue"


class Board:
    def __init__(self, uid: str, title: str, description: str, variables: list[dict] | None = None):
        """Start an empty dashboard."""
        self.uid, self.title, self.description = uid, title, description
        self.variables = variables or []
        self.panels: list[dict] = []
        self.y = 0
        self.x = 0
        self.row_h = 0

    def _place(self, w: int, h: int) -> dict:
        """The next free spot for a panel."""
        if self.x + w > 24:
            self.x, self.y, self.row_h = 0, self.y + self.row_h, 0
        pos = {"x": self.x, "y": self.y, "w": w, "h": h}
        self.x += w
        self.row_h = max(self.row_h, h)
        return pos

    def section(self, title: str) -> None:
        """Add a section title."""
        if self.x:
            self.x, self.y, self.row_h = 0, self.y + self.row_h, 0
        self.panels.append(
            {
                "type": "row",
                "title": title,
                "collapsed": False,
                "panels": [],
                "gridPos": {"x": 0, "y": self.y, "w": 24, "h": 1},
                "id": len(self.panels) + 1,
            }
        )
        self.y += 1

    def _panel(
        self,
        kind: str,
        title: str,
        desc: str,
        targets: list[tuple[str, str]],
        w: int,
        h: int,
        unit: str,
        steps: list[tuple[str, float | None]],
        options: dict,
        custom: dict | None = None,
        instant: bool = False,
        decimals: int | None = None,
        max_: float | None = None,
        ds: dict = DS,
    ) -> None:
        """Add a panel."""
        defaults: dict = {
            "unit": unit,
            "min": 0,
            "thresholds": {
                "mode": "absolute",
                "steps": [{"color": c, "value": v} for c, v in steps],
            },
            "color": {"mode": "thresholds" if kind in ("stat", "bargauge") else "palette-classic"},
        }
        if decimals is not None:
            defaults["decimals"] = decimals
        if max_ is not None:
            defaults["max"] = max_
        if custom:
            defaults["custom"] = custom
        self.panels.append(
            {
                "id": len(self.panels) + 1,
                "type": kind,
                "title": title,
                "description": desc,
                "datasource": ds,
                "gridPos": self._place(w, h),
                "fieldConfig": {"defaults": defaults, "overrides": []},
                "options": options,
                "targets": [
                    {
                        "refId": chr(65 + i),
                        "datasource": ds,
                        "expr": e,
                        "legendFormat": legend,
                        "instant": instant,
                        "range": not instant,
                    }
                    for i, (e, legend) in enumerate(targets)
                ],
            }
        )

    def stat(
        self,
        title: str,
        desc: str,
        expr: str,
        unit: str,
        steps: list,
        legend: str = "",
        w: int = 6,
        h: int = 4,
        decimals: int | None = None,
        ds: dict = DS,
    ) -> None:
        """Add a single number."""
        self._panel(
            "stat",
            title,
            desc,
            [(expr, legend)],
            w,
            h,
            unit,
            steps,
            {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "colorMode": "value",
                "graphMode": "area",
                "textMode": "value_and_name" if legend else "value",
                "justifyMode": "center",
                "orientation": "auto",
            },
            decimals=decimals,
            ds=ds,
        )

    def graph(
        self,
        title: str,
        desc: str,
        targets: list[tuple[str, str]],
        unit: str,
        w: int = 12,
        h: int = 8,
        bars: bool = False,
        stack: bool = False,
        max_: float | None = None,
        steps: list | None = None,
    ) -> None:
        """Add a chart over time."""
        custom = {
            "drawStyle": "bars" if bars else "line",
            "lineWidth": 2,
            "fillOpacity": 60 if bars else 12,
            "gradientMode": "opacity",
            "showPoints": "never",
            "spanNulls": True,
            "lineInterpolation": "smooth",
            "stacking": {"mode": "normal" if stack else "none"},
            "thresholdsStyle": {"mode": "dashed" if steps else "off"},
            "axisSoftMin": 0,
        }
        self._panel(
            "timeseries",
            title,
            desc,
            targets,
            w,
            h,
            unit,
            steps or [(GREEN, None)],
            {
                "legend": {
                    "displayMode": "table",
                    "placement": "bottom",
                    "calcs": ["mean", "max", "lastNotNull"],
                    "showLegend": True,
                },
                "tooltip": {"mode": "multi", "sort": "desc"},
            },
            custom=custom,
            max_=max_,
        )

    def ranking(
        self,
        title: str,
        desc: str,
        expr: str,
        legend: str,
        unit: str,
        steps: list,
        w: int = 12,
        h: int = 8,
        max_: float | None = None,
    ) -> None:
        """Add a ranked bar list."""
        self._panel(
            "bargauge",
            title,
            desc,
            [(expr, legend)],
            w,
            h,
            unit,
            steps,
            {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "orientation": "horizontal",
                "displayMode": "gradient",
                "showUnfilled": True,
                "valueMode": "color",
                "namePlacement": "left",
                "sizing": "auto",
            },
            instant=True,
            max_=max_,
        )

    def json(self) -> dict:
        """The dashboard as JSON."""
        return {
            "uid": self.uid,
            "title": self.title,
            "description": self.description,
            "tags": ["associator"],
            "timezone": "browser",
            "refresh": "1m",
            "schemaVersion": 39,
            "time": {"from": "now-6h", "to": "now"},
            "graphTooltip": 1,
            "templating": {"list": self.variables},
            "panels": self.panels,
        }


SERVICE_VAR = {
    "name": "service",
    "label": "Service",
    "type": "query",
    "datasource": DS,
    "query": {"query": "label_values(target_info, service_name)", "refId": "service"},
    "definition": "label_values(target_info, service_name)",
    "includeAll": True,
    "multi": True,
    "current": {"text": "All", "value": "$__all"},
    "refresh": 2,
    "sort": 1,
}
S = 'service_name=~"$service"'


def rate(metric: str, sel: str, window: str = "5m") -> str:
    """A per-second rate query."""
    return f"rate({metric}{{{sel}}}[{window}])"


def p95(metric: str, sel: str, by: str = "") -> str:
    """A 95th percentile query."""
    group = f"le, {by}" if by else "le"
    return f"histogram_quantile(0.95, sum by ({group}) ({rate(metric + '_bucket', sel)}))"


def status_class(sel: str) -> str:
    """A query part for 2xx, 4xx or 5xx."""
    return f'sum by (class) (label_replace({rate(REQ + "_count", sel)}, "class", "${{1}}xx", "http_response_status_code", "([0-9]).*")) * 60'


def error_ratio(sel: str, by: str = "") -> str:
    """5xx share of requests, only where there is traffic, never above 100%."""
    g = f"sum by ({by}) " if by else "sum "
    total = f"{g}({rate(REQ + '_count', sel)})"
    errors = f"{g}({rate(REQ + '_count', sel + ', http_response_status_code=~"5.."')})"
    return f"clamp_max(({errors} or {total} * 0) / ({total} > 0), 1)"


SERVICES = 'service_name!~"kubelet|postgres-backup"'
GW = "associator_gateway_call_duration_seconds"
COMPLETE = 'service_name="llm-gateway", http_route="/complete"'
DEC = "associator_drafts_decided_total"
EV = "associator_evals_feedback"
JUDGES = 'judge!="human_decision"'
ORCH = "associator_orchestrator"


def act(sel: str) -> str:
    """Last-24-h counts per feature; max: one value even with two api pods."""
    return f"max by (feature, kind) (associator_activity_last_24h{{{sel}}})"


def health() -> Board:
    """The Platform Health dashboard."""
    b = Board(
        "associator-health",
        "Platform Health",
        "Is the site up, fast and inside its limits? Services (RED), servers (USE), data, backups and free-plan limits.",
        [SERVICE_VAR],
    )
    b.section("At a glance")
    b.stat(
        "Services up",
        "Our services that sent telemetry in the last 5 minutes (6 expected: api, web front door, gateway, safety, MCP, orchestrator).",
        f"count(count by (service_name) (present_over_time(target_info{{{SERVICES}}}[5m])))",
        "short",
        [(RED, None), (AMBER, 5), (GREEN, 6)],
        w=4,
    )
    b.stat(
        "Requests per minute",
        "All requests reaching the site (front door).",
        f"sum({rate(REQ + '_count', 'service_name="traefik"')}) * 60",
        "reqpm",
        [(BLUE, None)],
        w=4,
        decimals=1,
    )
    b.stat(
        "Error rate",
        "Share of requests failing with a server error (5xx), last 5 minutes.",
        error_ratio('service_name="traefik"'),
        "percentunit",
        [(GREEN, None), (AMBER, 0.01), (RED, 0.02)],
        w=4,
        decimals=2,
    )
    b.stat(
        "Response time (p95)",
        "95 of 100 requests are faster than this.",
        p95(REQ, 'service_name="traefik"'),
        "s",
        [(GREEN, None), (AMBER, 0.5), (RED, 2)],
        w=4,
        decimals=2,
    )
    b.stat(
        "Last backup",
        "Hours since the nightly database backup last reached S3 (it runs at 02:00 India time). No data: no backup for 3 days.",
        "(time() - max(last_over_time(associator_backup_last_success_seconds[3d]))) / 3600",
        "h",
        [(GREEN, None), (AMBER, 26), (RED, 30)],
        w=4,
        decimals=0,
    )
    b.stat(
        "Certificate expires in",
        "Days until the HTTPS certificate for associator.space runs out (Let's Encrypt renews it at 30 days).",
        "(min(traefik_tls_certs_not_after_seconds) - time()) / 86400",
        "d",
        [(RED, None), (AMBER, 7), (GREEN, 20)],
        w=4,
        decimals=0,
    )

    b.section("Free-plan limits")
    b.stat(
        "Grafana series used",
        "Active metric series out of the Grafana Cloud Free plan's 10,000. Above it, data is dropped.",
        "max(grafanacloud_instance_active_series) / 10000",
        "percentunit",
        [(GREEN, None), (AMBER, 0.7), (RED, 0.9)],
        w=6,
        decimals=0,
        ds=USAGE,
    )
    b.stat(
        "Platform AI requests left today",
        "Groq free plan: 1,000 requests a day per model. The lowest of Platform AI's models.",
        'min(associator_gateway_quota_remaining{unit="requests"})',
        "short",
        [(RED, None), (AMBER, 100), (GREEN, 300)],
        w=6,
        decimals=0,
    )
    b.stat(
        "Database size",
        "Postgres on the data server's disk.",
        'max(associator_datastore{store="postgres", stat="size_bytes"})',
        "bytes",
        [(BLUE, None)],
        w=6,
        decimals=1,
    )
    b.stat(
        "Backup size",
        "Size of the last nightly backup.",
        "max(last_over_time(associator_backup_size_bytes[3d]))",
        "bytes",
        [(BLUE, None)],
        w=6,
        decimals=1,
    )

    b.section("Traffic")
    b.graph(
        "Requests per minute by service",
        "How busy each service is.",
        [(f"sum by (service_name) ({rate(REQ + '_count', S)}) * 60", "{{service_name}}")],
        "reqpm",
    )
    b.graph(
        "Responses by status",
        "Front door responses grouped as 2xx (ok), 3xx (redirect), 4xx (client) and 5xx (server error).",
        [(status_class('service_name="traefik"'), "{{class}}")],
        "reqpm",
        bars=True,
        stack=True,
    )

    b.section("Errors and latency")
    b.graph(
        "Server error rate by service",
        "Share of each service's requests that failed with 5xx. Dashed line: the 2% alert.",
        [(error_ratio(S, "service_name"), "{{service_name}}")],
        "percentunit",
        max_=1,
        steps=[(GREEN, None), (RED, 0.02)],
    )
    b.graph(
        "Response time (p95) by service",
        "95 of 100 requests are faster than this.",
        [(p95(REQ, S, "service_name"), "{{service_name}}")],
        "s",
        steps=[(GREEN, None), (RED, 2)],
    )
    b.ranking(
        "Most errors by endpoint (1 hour)",
        "API endpoints with the most 4xx and 5xx responses in the last hour.",
        f'topk(10, sum by (http_route) (increase({REQ}_count{{service_name="api", http_response_status_code=~"[45]..", http_route!=""}}[1h])))',
        "{{http_route}}",
        "short",
        [(GREEN, None), (AMBER, 10), (RED, 50)],
    )
    b.ranking(
        "Slowest endpoints (p95, 15 minutes)",
        "API endpoints ranked by their 95th percentile response time.",
        f'topk(10, histogram_quantile(0.95, sum by (le, http_route) (rate({REQ}_bucket{{service_name="api", http_route!=""}}[15m]))))',
        "{{http_route}}",
        "s",
        [(GREEN, None), (AMBER, 0.5), (RED, 2)],
    )

    node = 'container="", pod=""'
    mem = f"sum by (tier) (container_memory_working_set_bytes{{{node}}}) / sum by (tier) (machine_memory_bytes)"
    disk = (
        f"max by (tier) (container_fs_usage_bytes{{{node}}} / container_fs_limit_bytes{{{node}}})"
    )
    cpu = f"sum by (tier) (rate(container_cpu_usage_seconds_total{{{node}}}[5m]))"
    b.section("Servers (edge, backend, data)")
    b.graph(
        "Memory used by server",
        "Each server has 2 GB. Dashed line: the 90% alert.",
        [(mem, "{{tier}}")],
        "percentunit",
        max_=1,
        steps=[(GREEN, None), (RED, 0.9)],
        w=8,
    )
    b.graph(
        "CPU used by server", "Cores in use (each server has 2).", [(cpu, "{{tier}}")], "short", w=8
    )
    b.graph(
        "Disk used by server",
        "Dashed line: the 85% alert.",
        [(disk, "{{tier}}")],
        "percentunit",
        max_=1,
        steps=[(GREEN, None), (RED, 0.85)],
        w=8,
    )
    b.ranking(
        "Pods closest to their memory limit",
        "A pod reaching 100% is restarted by Kubernetes. Alert at 90%.",
        'topk(8, max by (namespace, pod) (container_memory_working_set_bytes{container!=""} / (container_spec_memory_limit_bytes{container!=""} > 0)))',
        "{{namespace}}/{{pod}}",
        "percentunit",
        [(GREEN, None), (AMBER, 0.75), (RED, 0.9)],
        max_=1,
    )
    b.ranking(
        "Memory per pod",
        "The 10 pods using the most memory.",
        'topk(10, sum by (namespace, pod) (container_memory_working_set_bytes{container!=""}))',
        "{{namespace}}/{{pod}}",
        "bytes",
        [(BLUE, None)],
    )

    b.section("Data (Postgres, Redis)")
    b.graph(
        "Postgres connections",
        "Open connections to the database (api pool 5, orchestrator 4, backups).",
        [('max(associator_datastore{store="postgres", stat="connections"})', "connections")],
        "short",
        w=8,
    )
    b.graph(
        "Postgres cache hit ratio",
        "Share of reads served from memory instead of disk. Below 99% the database needs more memory.",
        [('max(associator_datastore{store="postgres", stat="cache_hit_ratio"})', "hit ratio")],
        "percentunit",
        max_=1,
        w=8,
    )
    b.graph(
        "Transactions per minute",
        "Committed and rolled back (read-only requests end in a rollback: normal).",
        [
            (
                'max(rate(associator_datastore{store="postgres", stat="commits"}[10m])) * 60',
                "commits",
            ),
            (
                'max(rate(associator_datastore{store="postgres", stat="rollbacks"}[10m])) * 60',
                "rollbacks",
            ),
            ('max(associator_datastore{store="postgres", stat="deadlocks"})', "deadlocks (total)"),
        ],
        "short",
        w=8,
    )
    b.graph(
        "Redis keys",
        "Keys in Redis (sessions, rate limits, caches). Memory and hit ratio need INFO, which the app's Redis user may not run.",
        [('max(associator_datastore{store="redis", stat="keys"})', "keys")],
        "short",
        w=8,
    )
    return b


def ai() -> Board:
    """The AI dashboard."""
    b = Board(
        "associator-ai",
        "AI",
        "Is the AI working, good and inside its quota? Errors and quota, draft quality (people and judges), the orchestrator, response time, providers, safety.",
    )
    b.section("At a glance")
    b.stat(
        "AI requests failed",
        "Share of /complete requests to the gateway that did not get an answer, last hour (after any fallback).",
        f'sum(rate({REQ}_count{{{COMPLETE}, http_response_status_code!~"2.."}}[1h])) / sum(rate({REQ}_count{{{COMPLETE}}}[1h]))',
        "percentunit",
        [(GREEN, None), (AMBER, 0.05), (RED, 0.2)],
        w=4,
        decimals=1,
    )
    b.stat(
        "Drafts kept (7 days)",
        "Share of AI drafts people published, as written or edited, rather than discarded.",
        f'sum(increase({DEC}{{outcome=~"approved|edited"}}[7d])) / sum(increase({DEC}[7d]))',
        "percentunit",
        [(RED, None), (AMBER, 0.5), (GREEN, 0.7)],
        w=4,
        decimals=0,
    )
    b.stat(
        "Answer relevance (7 days)",
        "LangSmith judge: share of drafts that address the actual question.",
        f'max({EV}{{judge="answer_relevance", stat="avg", window="7d"}})',
        "percentunit",
        [(RED, None), (AMBER, 0.7), (GREEN, 0.85)],
        w=4,
        decimals=0,
    )
    b.stat(
        "Judges that worked (24 h)",
        "Share of judge runs that produced a score (the rest failed: rate limits, bad output).",
        f'sum({EV}{{{JUDGES}, stat="scored", window="24h"}}) / (sum({EV}{{{JUDGES}, stat="scored", window="24h"}}) + sum({EV}{{{JUDGES}, stat="errors", window="24h"}}))',
        "percentunit",
        [(RED, None), (AMBER, 0.8), (GREEN, 0.95)],
        w=4,
        decimals=0,
    )
    b.stat(
        "Platform AI cap used",
        "Share of today's 300 Platform AI answers (the platform's own daily cap) already used.",
        'sum(increase(associator_ai_calls_total{source="platform", outcome="ok"}[24h])) / 300 or vector(0)',
        "percentunit",
        [(GREEN, None), (AMBER, 0.6), (RED, 0.8)],
        w=4,
        decimals=0,
    )
    b.stat(
        "AI cost, last 24 h",
        "Model cost in US dollars (Platform AI and people's own models).",
        "sum(increase(associator_ai_cost_usd_total[24h])) or vector(0)",
        "currencyUSD",
        [(GREEN, None), (AMBER, 0.5), (RED, 1)],
        w=4,
        decimals=2,
    )

    b.section("Quota and errors")
    b.graph(
        "Rate-limited share of AI requests",
        "Share of gateway requests answered 429 (quota used up) after any fallback. Dashed line: the 20% alert.",
        [
            (
                f'sum(rate({REQ}_count{{{COMPLETE}, http_response_status_code="429"}}[15m])) / sum(rate({REQ}_count{{{COMPLETE}}}[15m]))',
                "429 share",
            )
        ],
        "percentunit",
        max_=1,
        steps=[(GREEN, None), (RED, 0.2)],
    )
    b.graph(
        "Model calls by result",
        "Every model call the gateway tried, by model and cause (quota_exhausted, upstream_busy, timeout...).",
        [
            (
                f'sum by (model, reason) (increase({GW}_count{{outcome="error"}}[15m]))',
                "{{model}} · {{reason}}",
            ),
            (f'sum by (model) (increase({GW}_count{{outcome="ok"}}[15m]))', "{{model}} · ok"),
        ],
        "short",
        bars=True,
        stack=True,
    )
    b.graph(
        "Platform quota left",
        "Groq free plan per model: requests left today (of 1,000) and tokens left this minute (of 8,000).",
        [
            (
                "min by (model, unit) (associator_gateway_quota_remaining)",
                "{{model}} · {{unit}}",
            )
        ],
        "short",
    )
    b.graph(
        "Fallbacks per hour",
        "Platform AI calls answered by the backup model because the main one was rate limited.",
        [
            (
                "sum by (from_model, to_model) (increase(associator_gateway_fallbacks_total[1h]))",
                "{{from_model}} → {{to_model}}",
            )
        ],
        "short",
        bars=True,
    )

    b.section("Draft quality: people")
    b.graph(
        "Drafts kept, by path (7 days)",
        "direct: one model; single: orchestrator, one model; split: orchestrator, several models merged.",
        [
            (
                f'sum by (path) (increase({DEC}{{outcome=~"approved|edited"}}[7d])) / sum by (path) (increase({DEC}[7d]))',
                "{{path}}",
            )
        ],
        "percentunit",
        max_=1,
    )
    b.graph(
        "Draft decisions per hour",
        "What people did with AI drafts, by mode.",
        [(f"sum by (mode, outcome) (increase({DEC}[1h]))", "{{mode}} · {{outcome}}")],
        "short",
        bars=True,
        stack=True,
    )

    b.section("Draft quality: LangSmith judges")
    b.ranking(
        "Judge averages (7 days)",
        "Yes/no judges as a share (relevance, code, tone: higher is better; toxicity, bias, PII, invented: lower is better). Conciseness is 0-10.",
        f'max by (judge) ({EV}{{{JUDGES}, stat="avg", window="7d"}})',
        "{{judge}}",
        "short",
        [(BLUE, None)],
        max_=1,
    )
    b.ranking(
        "Judge failures (24 h)",
        "Judge runs that failed, per judge. Judges are spread over three Groq models so they do not share one budget.",
        f'max by (judge) ({EV}{{{JUDGES}, stat="errors", window="24h"}})',
        "{{judge}}",
        "short",
        [(GREEN, None), (AMBER, 2), (RED, 10)],
    )
    b.graph(
        "Judge success rate over time",
        "Scored / (scored + failed), all judges, last 24 h (rolling).",
        [
            (
                f'sum({EV}{{{JUDGES}, stat="scored", window="24h"}}) / (sum({EV}{{{JUDGES}, stat="scored", window="24h"}}) + sum({EV}{{{JUDGES}, stat="errors", window="24h"}}))',
                "judges that worked",
            )
        ],
        "percentunit",
        max_=1,
    )
    b.graph(
        "Answer relevance over time",
        "LangSmith judge, last 24 h and 7 days (rolling).",
        [(f'max by (window) ({EV}{{judge="answer_relevance", stat="avg"}})', "{{window}}")],
        "percentunit",
        max_=1,
    )

    b.section("Orchestrator (Ask my AI on LangGraph)")
    b.graph(
        "Runs per hour",
        "By path (single: one model; split: planned parts on several models, merged) and result.",
        [(f"sum by (path, outcome) (increase({ORCH}_runs_total[1h]))", "{{path}} · {{outcome}}")],
        "short",
        bars=True,
        stack=True,
    )
    b.graph(
        "Time per step (p95)",
        "plan (Platform AI), work (each part), merge, shorten, single, and the whole run.",
        [
            (
                f"histogram_quantile(0.95, sum by (le, step) (rate({ORCH}_step_duration_seconds_bucket[1h])))",
                "{{step}}",
            )
        ],
        "s",
    )
    b.ranking(
        "Why runs failed (7 days)",
        "all_models_failed, too_long, empty_answer...",
        f'topk(10, sum by (reason) (increase({ORCH}_runs_total{{outcome="failed"}}[7d])))',
        "{{reason}}",
        "short",
        [(GREEN, None), (AMBER, 2), (RED, 10)],
    )
    b.ranking(
        "Model tries (7 days)",
        "Calls to people's own models and Platform AI, by result (a failed try falls back to the next model).",
        f"topk(10, sum by (who, outcome) (increase({ORCH}_model_tries_total[7d])))",
        "{{who}} · {{outcome}}",
        "short",
        [(BLUE, None)],
    )
    b.ranking(
        "Parts planned (7 days)",
        "What the planner split questions into.",
        f"sum by (kind) (increase({ORCH}_parts_total[7d]))",
        "{{kind}}",
        "short",
        [(BLUE, None)],
    )
    b.ranking(
        "Runs with fallback, memory (7 days)",
        "How often a run needed another model, and how often memory was on.",
        f"sum by (fallback, memory) (increase({ORCH}_runs_total[7d]))",
        "fallback {{fallback}} · memory {{memory}}",
        "short",
        [(BLUE, None)],
    )

    b.section("Response time (what people wait for)")
    b.graph(
        "AI response time for people (p95)",
        "Platform AI and people's own models: one model call. Excludes internal tools. Target: under 3 s.",
        [
            (
                f"histogram_quantile(0.95, sum by (le, kind) ({rate(GW + '_bucket', 'kind=~"user|platform"')}))",
                "{{kind}}",
            ),
            (
                f"histogram_quantile(0.50, sum by (le) ({rate(GW + '_bucket', 'kind=~"user|platform"')}))",
                "median",
            ),
        ],
        "s",
    )
    b.graph(
        "Model response time by model (p95)",
        "Every model the gateway calls, internal tools included.",
        [
            (
                f"histogram_quantile(0.95, sum by (le, model) ({rate(GW + '_bucket', 'outcome="ok"')}))",
                "{{model}}",
            )
        ],
        "s",
    )

    b.section("Providers and tokens")
    b.graph(
        "Provider response time (p95)",
        "How long providers take to answer.",
        [(p95(OUT, 'service_name="llm-gateway"', "server_address"), "{{server_address}}")],
        "s",
    )
    b.graph(
        "Tokens per hour by model",
        "Input and output tokens (api's direct calls).",
        [
            (
                "sum by (model, direction) (increase(associator_ai_tokens_total[1h]))",
                "{{model}} · {{direction}}",
            )
        ],
        "short",
        bars=True,
        stack=True,
    )

    b.section("Safety")
    b.ranking(
        "Safety findings, 24 h",
        "What the safety checks found in content people tried to publish: blocked, asked to confirm, or warned.",
        "topk(10, sum by (kind, action) (increase(associator_safety_findings_total[24h])))",
        "{{kind}} · {{action}}",
        "short",
        [(GREEN, None), (AMBER, 5), (RED, 20)],
    )
    b.graph(
        "Safety check time (p95)",
        "How long a safety check takes.",
        [(p95(REQ, 'service_name="safety"', "http_route"), "{{http_route}}")],
        "s",
    )
    return b


def activity() -> Board:
    """The Activity dashboard."""
    b = Board(
        "associator-activity",
        "Activity",
        "Who uses what: every feature over the last 24 hours (rolling, refreshed every 5 minutes), totals, and private chats. Counts only.",
    )
    b.section("At a glance (last 24 h)")
    b.stat(
        "Active people",
        "People who posted, replied, voted or asked for an AI draft.",
        f"sum({act('feature="people", kind="active"')}) or vector(0)",
        "short",
        [(BLUE, None)],
        w=4,
        decimals=0,
    )
    for title, desc, sel in [
        ("Sign-ups", "New accounts.", 'feature="people", kind="signups"'),
        ("Questions", "New threads (people and AI apps via MCP).", 'feature="threads"'),
        ("Replies", "All replies (written, Ask my AI, Platform AI, MCP).", 'feature="replies"'),
        ("Votes", "Votes on questions and replies (people and agents).", 'feature="votes"'),
        ("AI drafts", "Drafts asked for (Ask my AI, Platform AI, MCP).", 'feature="drafts"'),
    ]:
        b.stat(
            title,
            desc,
            f"sum({act(sel)}) or vector(0)",
            "short",
            [(BLUE, None)],
            w=4,
            decimals=0,
        )

    b.section("Per feature")
    b.ranking(
        "Use per feature, last 24 h",
        "Every feature and its kind: replies by mode, votes by voter type, drafts by mode, threads by person or MCP...",
        f"sort_desc({act('feature!="people"')})",
        "{{feature}} · {{kind}}",
        "short",
        [(BLUE, None)],
        w=12,
        h=12,
    )
    b.graph(
        "Daily use over time",
        "Each line is the rolling 24 h count at that moment.",
        [
            (f"sum by (feature) ({act('feature!="people"')})", "{{feature}}"),
            (act('feature="people", kind="active"'), "active people"),
        ],
        "short",
        w=12,
        h=12,
    )

    b.section("Totals")
    tot = "max by (feature, kind) (associator_activity_total"
    for title, desc, expr, unit in [
        ("People", "All accounts.", f'sum({tot}{{feature="people"}}))', "short"),
        (
            "Questions",
            "Threads not deleted.",
            f'sum({tot}{{feature="threads", kind=""}}))',
            "short",
        ),
        (
            "Satisfied",
            "Share of questions whose asker marked a reply Satisfied.",
            f'sum({tot}{{feature="threads", kind="satisfied"}})) / sum({tot}{{feature="threads", kind=""}}))',
            "percentunit",
        ),
        ("Clusters", "Public and private clusters.", f'sum({tot}{{feature="clusters"}}))', "short"),
        (
            "People with own models",
            "People who saved at least one model for Ask my AI.",
            f'sum({tot}{{feature="people_with_models"}}))',
            "short",
        ),
        (
            "People using memory",
            "People with at least one memory item.",
            f'sum({tot}{{feature="memory_people"}}))',
            "short",
        ),
    ]:
        b.stat(title, desc, expr, unit, [(BLUE, None)], w=4, decimals=0 if unit == "short" else 1)

    route = "/conversations/{conversation_id}"
    b.section("Private chats (end-to-end encrypted)")
    for title, desc, expr, steps in [
        (
            "Messages sent, 24 h",
            "Encrypted messages posted to chats.",
            'sum(increase(associator_chat_events_total{event="message"}[24h])) or vector(0)',
            [(BLUE, None)],
        ),
        (
            "Open live connections",
            "Browser tabs connected for live updates right now.",
            "sum(associator_chat_sockets) or vector(0)",
            [(BLUE, None)],
        ),
        (
            "Files shared, 24 h",
            "Encrypted files uploaded.",
            'sum(increase(associator_chat_events_total{event="file"}[24h])) or vector(0)',
            [(BLUE, None)],
        ),
        (
            "Reports, 24 h",
            "Reports on chats and public posts (check: make reports).",
            "sum(increase(associator_reports_total[24h])) or vector(0)",
            [(GREEN, None), (AMBER, 1), (RED, 5)],
        ),
    ]:
        b.stat(title, desc, expr, "short", steps, w=6, decimals=0)
    b.graph(
        "Chat activity per hour",
        "New chats, messages, files, AI answers and reports.",
        [("sum by (event) (increase(associator_chat_events_total[1h]))", "{{event}}")],
        "short",
        bars=True,
        stack=True,
    )
    b.ranking(
        "Chat errors by endpoint (1 hour)",
        "Failed chat requests (4xx / 5xx): setup, keys, backups, messages.",
        f'topk(10, sum by (http_route, http_response_status_code) (increase({REQ}_count{{service_name="api", http_route=~"/conversations.*|/me/devices.*|/me/key-backup|/me/account-key.*", http_response_status_code=~"[45].."}}[1h])))',
        "{{http_route}} · {{http_response_status_code}}",
        "short",
        [(GREEN, None), (AMBER, 5), (RED, 20)],
    )
    b.graph(
        "Message send time (p95)",
        "How long posting an encrypted message takes on the server.",
        [
            (
                p95(
                    REQ, f'service_name="api", http_route="{route}/log", http_request_method="POST"'
                ),
                "send",
            )
        ],
        "s",
    )
    return b


if __name__ == "__main__":
    out = Path(__file__).parent
    for old in ("chats.json", "servers.json"):
        (out / old).unlink(missing_ok=True)
    for board in (health(), ai(), activity()):
        path = out / f"{board.uid.removeprefix('associator-')}.json"
        path.write_text(json.dumps(board.json(), indent=2) + "\n")
        print(f"wrote {path.name}: {len([p for p in board.panels if p['type'] != 'row'])} panels")
