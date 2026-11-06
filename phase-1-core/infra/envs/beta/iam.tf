# The servers' IAM role.
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${local.name_prefix}-node-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy_attachment" "node_ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "read_database_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.database.arn]
  }
}

resource "aws_iam_role_policy" "node_read_database_secret" {
  name   = "${local.name_prefix}-read-database-secret"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.read_database_secret.json
}

resource "aws_iam_instance_profile" "node" {
  name = "${local.name_prefix}-node-profile"
  role = aws_iam_role.node.name
}

data "aws_iam_policy_document" "pull_images" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    actions = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
    resources = [
      aws_ecr_repository.api.arn,
      aws_ecr_repository.safety.arn,
      aws_ecr_repository.llm_gateway.arn,
      aws_ecr_repository.mcp_server.arn,
      aws_ecr_repository.web.arn,
      aws_ecr_repository.orchestrator.arn,
    ]
  }
}

resource "aws_iam_role_policy" "node_pull_images" {
  name   = "${local.name_prefix}-pull-images"
  role   = aws_iam_role.node.id
  policy = data.aws_iam_policy_document.pull_images.json
}
