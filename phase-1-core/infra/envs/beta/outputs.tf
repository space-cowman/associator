# Values other tools read from Terraform.
output "database_secret_name" {
  description = "Secrets Manager secret holding the Postgres and Redis passwords"
  value       = aws_secretsmanager_secret.database.name
}

output "postgres_tunnel_command" {
  description = "Run on the Mac; Postgres is then at 127.0.0.1:15432"
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.data.id} --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters host=${local.postgres_cluster_ip},portNumber=5432,localPortNumber=15432"
}

output "redis_tunnel_command" {
  description = "Run on the Mac; Redis is then at 127.0.0.1:16379"
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.data.id} --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters host=${local.redis_cluster_ip},portNumber=6379,localPortNumber=16379"
}

output "api_repository_url" {
  description = "ECR repository for the api image"
  value       = aws_ecr_repository.api.repository_url
}

output "safety_repository_url" {
  description = "ECR repository for the safety image"
  value       = aws_ecr_repository.safety.repository_url
}

output "llm_gateway_repository_url" {
  description = "ECR repository for the llm-gateway image"
  value       = aws_ecr_repository.llm_gateway.repository_url
}

output "user_keys_kms_arn" {
  description = "KMS key that encrypts users' model API keys"
  value       = aws_kms_key.user_keys.arn
}

output "mcp_server_repository_url" {
  description = "ECR repository for the mcp-server image"
  value       = aws_ecr_repository.mcp_server.repository_url
}

output "attachments_bucket" {
  description = "Private S3 bucket for attachments"
  value       = aws_s3_bucket.attachments.bucket
}

output "attachments_origin" {
  description = "Origin browsers upload to and load attachments from (CSP)"
  value       = "https://${aws_s3_bucket.attachments.bucket_regional_domain_name}"
}

output "web_repository_url" {
  description = "ECR repository for the web image"
  value       = aws_ecr_repository.web.repository_url
}

output "nameservers" {
  description = "Put these 4 nameservers at the domain registrar"
  value       = aws_route53_zone.public.name_servers
}

output "public_ip" {
  description = "Fixed public IP of the node (Traefik on 80/443)"
  value       = aws_eip.node.public_ip
}

output "domain" {
  description = "Public domain of the site"
  value       = var.domain
}

output "data_server_instance_id" {
  description = "New data node (k3s server, Postgres, Redis; private): target for SSM tunnels"
  value       = aws_instance.data.id
}

output "tier_nodes" {
  description = "Instance id and private IP of each tier node"
  value = merge(
    { data = { id = aws_instance.data.id, ip = aws_instance.data.private_ip } },
    { for k, n in aws_instance.agent : k => { id = n.id, ip = n.private_ip } },
  )
}

output "orchestrator_repository_url" {
  description = "ECR repository for the orchestrator image (Phase 2)"
  value       = aws_ecr_repository.orchestrator.repository_url
}

output "ci_build_role_arn" {
  description = "Role GitHub Actions assumes to push images to ECR (main only)"
  value       = aws_iam_role.ci_build.arn
}

output "ci_evals_role_arn" {
  description = "Role GitHub Actions assumes to read the CI secret for the red-team canary"
  value       = aws_iam_role.ci_evals.arn
}
