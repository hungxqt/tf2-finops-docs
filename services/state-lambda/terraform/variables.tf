variable "aws_region" {
  description = "AWS Region for State Lambda and S3 idempotency store."
  type        = string
  default     = "ap-southeast-1"
}

variable "aws_profile" {
  description = "Optional AWS CLI profile."
  type        = string
  default     = null
  nullable    = true
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "development"
  validation {
    condition     = contains(["development", "sandbox", "staging", "prod"], var.environment)
    error_message = "environment must be development, sandbox, staging, or prod."
  }
}

variable "project" {
  description = "Project naming prefix."
  type        = string
  default     = "tf2-finops-watch"
}

variable "owner" {
  description = "Resource owner tag."
  type        = string
  default     = "finops-platform"
}

variable "idempotency_bucket_name" {
  description = "Optional globally unique S3 idempotency bucket name."
  type        = string
  default     = null
  nullable    = true
}

variable "lambda_zip_path" {
  description = "Packaged State Lambda ZIP path."
  type        = string
  default     = "../build/state-lambda.zip"
}

variable "lambda_architecture" {
  description = "Lambda CPU architecture."
  type        = string
  default     = "x86_64"
  validation {
    condition     = contains(["x86_64", "arm64"], var.lambda_architecture)
    error_message = "lambda_architecture must be x86_64 or arm64."
  }
}

variable "lambda_memory_size" {
  description = "Lambda memory in MB."
  type        = number
  default     = 128
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 15
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention."
  type        = number
  default     = 14
}

variable "additional_tags" {
  description = "Additional resource tags."
  type        = map(string)
  default     = {}
}
