# One IAM user per service that needs KMS, with only that permission.
locals {
  kms_service_actions = {
    "api"         = "kms:Encrypt"
    "llm-gateway" = "kms:Decrypt"
  }
}

resource "aws_iam_user" "service" {
  for_each = local.kms_service_actions
  name     = "${local.name_prefix}-${each.key}"
  path     = "/service/"
}

data "aws_iam_policy_document" "service_kms" {
  for_each = local.kms_service_actions
  statement {
    actions   = [each.value]
    resources = [aws_kms_key.user_keys.arn]
    condition {
      test     = "StringEquals"
      variable = "kms:EncryptionContext:purpose"
      values   = ["user-model-key"]
    }
  }
}

resource "aws_iam_user_policy" "service_kms" {
  for_each = local.kms_service_actions
  name     = "${local.name_prefix}-${each.key}-kms"
  user     = aws_iam_user.service[each.key].name
  policy   = data.aws_iam_policy_document.service_kms[each.key].json
}

data "aws_iam_policy_document" "api_memory_kms" {
  statement {
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [aws_kms_key.user_keys.arn]
    condition {
      test     = "StringEquals"
      variable = "kms:EncryptionContext:purpose"
      values   = ["memory", "chat"]
    }
  }
}

resource "aws_iam_user_policy" "api_memory_kms" {
  name   = "${local.name_prefix}-api-memory-kms"
  user   = aws_iam_user.service["api"].name
  policy = data.aws_iam_policy_document.api_memory_kms.json
}

resource "aws_iam_access_key" "service" {
  for_each = local.kms_service_actions
  user     = aws_iam_user.service[each.key].name
}

resource "aws_secretsmanager_secret" "services" {
  name                    = "${var.project}/${var.environment}/services"
  description             = "AWS access keys of the service IAM users (KMS only)"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "services" {
  secret_id = aws_secretsmanager_secret.services.id
  secret_string = jsonencode({
    for name, _ in local.kms_service_actions : name => {
      access_key_id     = aws_iam_access_key.service[name].id
      secret_access_key = aws_iam_access_key.service[name].secret
    }
  })
}
