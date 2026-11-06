# Private bucket for attachments and chat files.
resource "random_id" "attachments" {
  byte_length = 4
}

resource "aws_s3_bucket" "attachments" {
  bucket        = "${local.name_prefix}-attachments-${random_id.attachments.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "attachments" {
  bucket                  = aws_s3_bucket.attachments.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "attachments" {
  bucket = aws_s3_bucket.attachments.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id
  rule {
    id     = "drop-unchecked-uploads"
    status = "Enabled"
    filter {
      prefix = "pending/"
    }
    expiration {
      days = 1
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id
  cors_rule {
    allowed_methods = ["POST", "GET"]
    allowed_origins = var.web_origins
    allowed_headers = ["*"]
    max_age_seconds = 600
  }
}

data "aws_iam_policy_document" "attachments_bucket" {
  statement {
    sid       = "HttpsOnly"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.attachments.arn, "${aws_s3_bucket.attachments.arn}/*"]
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

resource "aws_s3_bucket_policy" "attachments" {
  bucket     = aws_s3_bucket.attachments.id
  policy     = data.aws_iam_policy_document.attachments_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.attachments]
}

data "aws_iam_policy_document" "api_attachments" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.attachments.arn}/pending/*"]
  }
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.attachments.arn}/files/*"]
  }
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.attachments.arn}/e2e/*"]
  }
}

resource "aws_iam_user_policy" "api_attachments" {
  name   = "${local.name_prefix}-api-attachments"
  user   = aws_iam_user.service["api"].name
  policy = data.aws_iam_policy_document.api_attachments.json
}
