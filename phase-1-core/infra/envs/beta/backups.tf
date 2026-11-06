# Database backups and the Terraform state bucket.
resource "random_id" "backups" {
  byte_length = 4
}

resource "aws_s3_bucket" "backups" {
  bucket        = "${local.name_prefix}-backups-${random_id.backups.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    id     = "keep-30-days"
    status = "Enabled"
    filter {}
    expiration {
      days = 30
    }
    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.backups]
}

data "aws_iam_policy_document" "backups_bucket" {
  statement {
    sid       = "HttpsOnly"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.backups.arn, "${aws_s3_bucket.backups.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "backups" {
  bucket = aws_s3_bucket.backups.id
  policy = data.aws_iam_policy_document.backups_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.backups]
}

resource "aws_iam_user" "backup" {
  name = "${local.name_prefix}-backup"
  path = "/service/"
}

data "aws_iam_policy_document" "backup_upload" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.backups.arn}/postgres/*"]
  }
}

resource "aws_iam_user_policy" "backup_upload" {
  name   = "${local.name_prefix}-backup-upload-only"
  user   = aws_iam_user.backup.name
  policy = data.aws_iam_policy_document.backup_upload.json
}

resource "aws_iam_access_key" "backup" {
  user = aws_iam_user.backup.name
}

resource "aws_secretsmanager_secret" "backup" {
  name                    = "${var.project}/${var.environment}/backup"
  description             = "Upload-only AWS access key of the database backup job"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "backup" {
  secret_id = aws_secretsmanager_secret.backup.id
  secret_string = jsonencode({
    access_key_id     = aws_iam_access_key.backup.id
    secret_access_key = aws_iam_access_key.backup.secret
  })
}

resource "aws_s3_bucket" "tfstate" {
  bucket = "${local.name_prefix}-tfstate-${random_id.backups.hex}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

data "aws_iam_policy_document" "tfstate_bucket" {
  statement {
    sid       = "HttpsOnly"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.tfstate.arn, "${aws_s3_bucket.tfstate.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  policy = data.aws_iam_policy_document.tfstate_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.tfstate]
}

output "backups_bucket" {
  description = "Private bucket for nightly database dumps (30 days)"
  value       = aws_s3_bucket.backups.bucket
}

output "tfstate_bucket" {
  description = "Bucket for the remote Terraform state (set it in versions.tf, then init -migrate-state)"
  value       = aws_s3_bucket.tfstate.bucket
}
