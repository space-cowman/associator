# Settings for the Grafana stack.
variable "alert_email" {
  description = "Where alert emails go"
  type        = string
}

variable "metrics_data_source" {
  description = "Name of the stack's Prometheus (metrics) data source"
  type        = string
  default     = "grafanacloud-redaphid51-prom"
}

variable "ai_cost_alert_usd" {
  description = "Alert when AI calls cost more than this in 24 hours (US dollars)"
  type        = number
  default     = 1
}
