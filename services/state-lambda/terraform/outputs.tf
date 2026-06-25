output "aws_account_id" { value = data.aws_caller_identity.current.account_id }
output "lambda_function_name" { value = aws_lambda_function.state.function_name }
output "lambda_function_arn" { value = aws_lambda_function.state.arn }
output "lambda_role_arn" { value = aws_iam_role.state_lambda.arn }
output "idempotency_bucket_name" { value = aws_s3_bucket.idempotency.bucket }
output "idempotency_bucket_arn" { value = aws_s3_bucket.idempotency.arn }
output "cloudwatch_log_group_name" { value = aws_cloudwatch_log_group.state_lambda.name }
