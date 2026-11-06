# Alerts, emailed to the owner.
resource "grafana_contact_point" "owner" {
  name = "Associator owner"
  email {
    addresses               = [var.alert_email]
    single_email            = true
    disable_resolve_message = false
  }
}

resource "grafana_notification_policy" "this" {
  contact_point   = grafana_contact_point.owner.name
  group_by        = ["alertname", "service_name"]
  group_wait      = "1m"
  group_interval  = "10m"
  repeat_interval = "12h"
}

locals {
  services = ["api", "llm-gateway", "safety", "mcp-server", "traefik", "orchestrator"]

  rules = merge(
    {
      "Errors above 2%" = {
        expr      = "sum by (service_name) (rate(${local.req}_count{http_response_status_code=~\"5..\"}[5m])) / (sum by (service_name) (rate(${local.req}_count[5m])) > 0.01)"
        threshold = 0.02
        for       = "5m"
        no_data   = "OK"
        summary   = "More than 2% of requests to {{ $labels.service_name }} are failing (5xx)."
      }
      "api is slow" = {
        expr      = "histogram_quantile(0.95, sum by (le) (rate(${local.req}_bucket{service_name=\"api\"}[10m])))"
        threshold = 2
        for       = "10m"
        no_data   = "OK"
        summary   = "1 in 20 api requests takes longer than 2 seconds."
      }
      "AI provider errors" = {
        expr      = "sum by (server_address) (rate(${local.out}_count{service_name=\"llm-gateway\", http_response_status_code=~\"(4|5)..\"}[10m])) * 60"
        threshold = 1
        for       = "10m"
        no_data   = "OK"
        summary   = "{{ $labels.server_address }} is answering the llm-gateway with errors (over 1 a minute)."
      }
    },
    {
      "Server memory above 90%" = {
        expr      = "sum by (tier) (container_memory_working_set_bytes{container=\"\", pod=\"\"}) / sum by (tier) (machine_memory_bytes)"
        threshold = 0.9
        for       = "10m"
        no_data   = "OK"
        summary   = "The {{ $labels.tier }} server has used over 90% of its memory for 10 minutes."
      }
      "Server disk above 85%" = {
        expr      = "max by (tier) (container_fs_usage_bytes{container=\"\", pod=\"\"} / container_fs_limit_bytes{container=\"\", pod=\"\"})"
        threshold = 0.85
        for       = "10m"
        no_data   = "OK"
        summary   = "The {{ $labels.tier }} server's disk is over 85% full."
      }
      "Pod near its memory limit" = {
        expr      = "max by (namespace, pod) (container_memory_working_set_bytes{container!=\"\"} / (container_spec_memory_limit_bytes{container!=\"\"} > 0))"
        threshold = 0.9
        for       = "10m"
        no_data   = "OK"
        summary   = "{{ $labels.namespace }}/{{ $labels.pod }} uses over 90% of its memory limit: it may be restarted."
      }
      "New report received" = {
        expr      = "sum by (where) (increase(associator_reports_total[15m]))"
        threshold = 0
        for       = "0s"
        no_data   = "OK"
        summary   = "A new {{ $labels.where }} report arrived: acknowledge it within 24 hours (make reports)."
      }
      "AI cost above daily budget" = {
        expr      = "sum(increase(associator_ai_cost_usd_total[24h]))"
        threshold = var.ai_cost_alert_usd
        for       = "0s"
        no_data   = "OK"
        summary   = "AI calls cost more than $${var.ai_cost_alert_usd} in the last 24 hours."
      }
      "AI requests rate limited above 20%" = {
        expr      = "sum(rate(${local.req}_count{service_name=\"llm-gateway\", http_route=\"/complete\", http_response_status_code=\"429\"}[15m])) / sum(rate(${local.req}_count{service_name=\"llm-gateway\", http_route=\"/complete\"}[15m]))"
        threshold = 0.2
        for       = "15m"
        no_data   = "OK"
        summary   = "Over 20% of AI requests are refused for quota (429) even after fallback."
      }
      "Judges failing above 20%" = {
        expr      = "1 - sum(associator_evals_feedback{judge!=\"human_decision\", stat=\"scored\", window=\"24h\"}) / (sum(associator_evals_feedback{judge!=\"human_decision\", stat=\"scored\", window=\"24h\"}) + sum(associator_evals_feedback{judge!=\"human_decision\", stat=\"errors\", window=\"24h\"}))"
        threshold = 0.2
        for       = "1h"
        no_data   = "OK"
        summary   = "Over 20% of LangSmith judge runs failed in the last 24 hours (rate limits?)."
      }
      "Orchestrator runs failing" = {
        expr      = "sum(increase(associator_orchestrator_runs_total{outcome=\"failed\"}[1h])) / (sum(increase(associator_orchestrator_runs_total[1h])) > 0)"
        threshold = 0.2
        for       = "0s"
        no_data   = "OK"
        summary   = "Over 20% of Ask my AI runs failed in the last hour."
      }
      "Backup missing" = {
        expr      = "(time() - max(last_over_time(associator_backup_last_success_seconds[3d]))) / 3600"
        threshold = 26
        for       = "0s"
        no_data   = "Alerting"
        summary   = "No database backup reached S3 for over 26 hours (check: kubectl -n data get jobs)."
      }
      "Certificate expires within 14 days" = {
        expr      = "(min(traefik_tls_certs_not_after_seconds) - time()) / 86400"
        threshold = 14
        below     = true
        for       = "0s"
        no_data   = "OK"
        summary   = "The HTTPS certificate expires in under 14 days: renewal is failing."
      }
      "Grafana series above 90%" = {
        expr      = "max(grafanacloud_instance_active_series) / 10000"
        threshold = 0.9
        for       = "30m"
        no_data   = "OK"
        ds        = "grafanacloud-usage"
        summary   = "Over 90% of the Grafana Cloud Free plan's 10,000 series are used: data is dropped above it."
      }
      "Platform AI cap above 80%" = {
        expr      = "sum(increase(associator_ai_calls_total{source=\"platform\", outcome=\"ok\"}[24h])) / 300"
        threshold = 0.8
        for       = "0s"
        no_data   = "OK"
        summary   = "Over 80% of today's 300 Platform AI answers are used."
      }
    },
    {
      for s in local.services : "${s} stopped reporting" => {
        expr      = "count(present_over_time(target_info{service_name=\"${s}\"}[10m])) or vector(0)"
        threshold = 0.5
        below     = true
        for       = "0s"
        no_data   = "Alerting"
        summary   = "${s} has sent no telemetry for 10 minutes: it may be down."
      }
    }
  )
}

resource "grafana_rule_group" "associator" {
  name             = "associator"
  folder_uid       = grafana_folder.associator.uid
  interval_seconds = 60

  dynamic "rule" {
    for_each = local.rules
    content {
      name           = rule.key
      condition      = "C"
      for            = rule.value.for
      no_data_state  = rule.value.no_data
      exec_err_state = "Error"
      annotations    = { summary = rule.value.summary }
      labels         = { project = "associator" }

      data {
        ref_id         = "A"
        datasource_uid = try(rule.value.ds, data.grafana_data_source.metrics.uid)
        relative_time_range {
          from = 900
          to   = 0
        }
        model = jsonencode({ refId = "A", expr = rule.value.expr, instant = true })
      }
      data {
        ref_id         = "C"
        datasource_uid = "__expr__"
        relative_time_range {
          from = 0
          to   = 0
        }
        model = jsonencode({
          refId      = "C"
          type       = "threshold"
          expression = "A"
          conditions = [{ evaluator = { type = try(rule.value.below, false) ? "lt" : "gt", params = [rule.value.threshold] } }]
        })
      }
    }
  }
}
