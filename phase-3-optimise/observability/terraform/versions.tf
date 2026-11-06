# Terraform and the Grafana provider.
terraform {
  required_version = ">= 1.9"
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "4.50.0"
    }
  }
  backend "s3" {
    bucket       = "platform-v2-beta-tfstate-1ced02b5"
    key          = "observability/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "grafana" {}
