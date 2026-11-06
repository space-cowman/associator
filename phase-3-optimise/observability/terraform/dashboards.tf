# The Grafana dashboards, from the JSON files.
data "grafana_data_source" "metrics" {
  name = var.metrics_data_source
}

resource "grafana_folder" "associator" {
  title = "Associator"
}

locals {
  req = "http_server_request_duration_seconds"
  out = "http_client_request_duration_seconds"

  dashboard_files = fileset("${path.module}/../dashboards", "*.json")
}

resource "grafana_dashboard" "this" {
  for_each    = { for f in local.dashboard_files : trimsuffix(f, ".json") => f }
  folder      = grafana_folder.associator.uid
  config_json = replace(file("${path.module}/../dashboards/${each.value}"), "__METRICS_UID__", data.grafana_data_source.metrics.uid)
  overwrite   = true
}
