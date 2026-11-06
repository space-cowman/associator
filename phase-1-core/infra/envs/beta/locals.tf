# Shared names and fixed values.
locals {
  name_prefix = "${var.project}-${var.environment}"

  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  database_name       = "platform_v2"
  database_admin_user = "platform_v2_admin"
  database_owner_user = "platform_v2_owner"
  database_app_user   = "platform_v2_app"

  redis_app_user   = "platform_v2_app"
  redis_admin_user = "platform_v2_admin"

  postgres_cluster_ip = "10.43.0.50"
  redis_cluster_ip    = "10.43.0.51"
}
