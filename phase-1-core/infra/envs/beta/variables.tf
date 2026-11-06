# Settings for this environment.
variable "project" {
  description = "Project name used in resource names and tags"
  type        = string
  default     = "platform-v2"
}

variable "environment" {
  description = "Environment name used in resource names and tags"
  type        = string
  default     = "beta"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-south-1"
}

variable "budget_email" {
  description = "Email address that receives budget alerts"
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly budget limit in USD"
  type        = number
  default     = 50
}

variable "data_node_instance_type" {
  description = "EC2 instance type for the data node (free-plan eligible)"
  type        = string
  default     = "t4g.small"
}

variable "k3s_version" {
  description = "Pinned k3s release"
  type        = string
  default     = "v1.33.13+k3s2"
}

variable "postgres_image" {
  description = "Postgres image with pgvector (multi-arch)"
  type        = string
  default     = "pgvector/pgvector:0.8.2-pg16"
}

variable "redis_image" {
  description = "Redis image (multi-arch)"
  type        = string
  default     = "redis:7.2.16-alpine"
}

variable "ecr_credential_provider_version" {
  description = "Kubernetes ECR credential provider (official build on artifacts.k8s.io)"
  type        = string
  default     = "v1.31.0"
}

variable "ecr_credential_provider_sha256" {
  description = "Published SHA-256 of the linux/arm64 credential provider binary for that version"
  type        = string
  default     = "fa0061361d21cbad70a4cd6576f69366ae863a004ec6f59cba7ddbc71ba7106e" # pragma: allowlist secret
}

variable "web_origins" {
  description = "Browser origins allowed to upload attachments straight to S3"
  type        = list(string)
  default     = ["http://localhost:3000"]
}

variable "domain" {
  description = "Public domain of the site (its DNS zone is created in Route 53)"
  type        = string
  default     = "associator.space"
}

variable "github_repository" {
  description = "GitHub repository whose Actions may assume the CI roles, as owner@id/name@id: the repository uses GitHub's immutable OIDC subject (gh api repos/OWNER/REPO/actions/oidc/customization/sub), so a deleted and re-created repository of the same name cannot match"
  type        = string
  default     = "space-cowman@289791280/associator-private@1435650951"
}
