locals {
  name_prefix = "${var.project}-${var.environment}"
  lambda_name = "${local.name_prefix}-state-lambda"
  bucket_name = coalesce(var.idempotency_bucket_name, "${local.name_prefix}-${data.aws_caller_identity.current.account_id}-idempotency")

  lambda_zip_path = abspath(var.lambda_zip_path)

  common_tags = merge({
    Project     = "TF2-FinOps-Watch"
    Environment = var.environment
    Owner       = var.owner
    Component   = "state-lambda"
    ManagedBy   = "Terraform"
  }, var.additional_tags)
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_s3_bucket" "idempotency" {
  bucket        = local.bucket_name
  force_destroy = false
  tags          = local.common_tags

  lifecycle { prevent_destroy = true }
}

resource "aws_s3_bucket_public_access_block" "idempotency" {
  bucket                  = aws_s3_bucket.idempotency.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "idempotency" {
  bucket = aws_s3_bucket.idempotency.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "idempotency" {
  bucket = aws_s3_bucket.idempotency.id
  rule {
    bucket_key_enabled = true
    apply_server_side_encryption_by_default { sse_algorithm = "aws:kms" }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "idempotency" {
  bucket = aws_s3_bucket.idempotency.id
  rule {
    id     = "expire-idempotency-locks-after-24-hours"
    status = "Enabled"
    filter { prefix = "idempotency/" }
    expiration { days = 1 }
    noncurrent_version_expiration { noncurrent_days = 1 }
  }
  depends_on = [aws_s3_bucket_versioning.idempotency]
}

data "aws_iam_policy_document" "idempotency_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.idempotency.arn, "${aws_s3_bucket.idempotency.arn}/*"]
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

resource "aws_s3_bucket_policy" "idempotency" {
  bucket = aws_s3_bucket.idempotency.id
  policy = data.aws_iam_policy_document.idempotency_bucket.json
}

resource "aws_iam_role" "state_lambda" {
  name               = "${local.lambda_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "state_lambda" {
  statement {
    sid       = "ListIdempotencyPrefix"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.idempotency.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["idempotency/*"]
    }
  }
  statement {
    sid       = "ManageIdempotencyObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.idempotency.arn}/idempotency/*"]
  }
  statement {
    sid       = "LambdaLogDelivery"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.state_lambda.arn}:*"]
  }
  statement {
    sid       = "XRayTraceDelivery"
    effect    = "Allow"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "state_lambda" {
  name   = "${local.lambda_name}-policy"
  role   = aws_iam_role.state_lambda.id
  policy = data.aws_iam_policy_document.state_lambda.json
}

resource "aws_cloudwatch_log_group" "state_lambda" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_lambda_function" "state" {
  function_name    = local.lambda_name
  description      = "CDO S3-backed run lock and idempotency decision Lambda."
  role             = aws_iam_role.state_lambda.arn
  filename         = local.lambda_zip_path
  source_code_hash = filebase64sha256(local.lambda_zip_path)
  runtime          = "python3.14"
  handler          = "lambda_function.lambda_handler"
  architectures    = [var.lambda_architecture]
  memory_size      = var.lambda_memory_size
  timeout          = var.lambda_timeout_seconds
  environment { variables = { IDEMPOTENCY_BUCKET_NAME = aws_s3_bucket.idempotency.bucket } }
  tracing_config { mode = "Active" }
  tags       = local.common_tags
  depends_on = [aws_cloudwatch_log_group.state_lambda, aws_iam_role_policy.state_lambda]
}
