# GitHub Actions roles (OIDC, no stored AWS keys) and the CI secret.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  github_sub_main = "repo:${var.github_repository}:ref:refs/heads/main"
  github_sub_pr   = "repo:${var.github_repository}:pull_request"
  ecr_repository_arns = [
    aws_ecr_repository.api.arn,
    aws_ecr_repository.safety.arn,
    aws_ecr_repository.llm_gateway.arn,
    aws_ecr_repository.mcp_server.arn,
    aws_ecr_repository.web.arn,
    aws_ecr_repository.orchestrator.arn,
  ]
}

resource "aws_secretsmanager_secret" "ci" {
  name                    = "${var.project}/${var.environment}/ci"
  description             = "Evals Groq key for CI's red-team canary (copied by make ci-secret)"
  recovery_window_in_days = 0
}

data "aws_iam_policy_document" "ci_build_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_sub_main]
    }
  }
}

resource "aws_iam_role" "ci_build" {
  name                 = "${local.name_prefix}-ci-build"
  assume_role_policy   = data.aws_iam_policy_document.ci_build_assume.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "ci_push_images" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:CompleteLayerUpload",
      "ecr:DescribeImages", "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload",
      "ecr:PutImage", "ecr:UploadLayerPart",
    ]
    resources = local.ecr_repository_arns
  }
}

resource "aws_iam_role_policy" "ci_build_push_images" {
  name   = "${local.name_prefix}-ci-push-images"
  role   = aws_iam_role.ci_build.id
  policy = data.aws_iam_policy_document.ci_push_images.json
}

data "aws_iam_policy_document" "ci_evals_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_sub_main, local.github_sub_pr]
    }
  }
}

resource "aws_iam_role" "ci_evals" {
  name                 = "${local.name_prefix}-ci-evals"
  assume_role_policy   = data.aws_iam_policy_document.ci_evals_assume.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "ci_read_ci_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.ci.arn]
  }
}

resource "aws_iam_role_policy" "ci_evals_read_secret" {
  name   = "${local.name_prefix}-ci-read-secret"
  role   = aws_iam_role.ci_evals.id
  policy = data.aws_iam_policy_document.ci_read_ci_secret.json
}
