# State Lambda

State Lambda là service nội bộ thuộc CDO, chịu trách nhiệm quản lý trạng thái
lượt chạy và idempotency. Step Functions gọi trực tiếp Lambda này; service
không cung cấp Function URL hoặc API Gateway endpoint.

Amazon S3 là kho dữ liệu authoritative. State Lambda không sử dụng DynamoDB,
SQS, không xử lý CUR/Cost Explorer, không thực hiện containment và không chứa
logic AI thuộc AIOps.

## Luồng hoạt động

```text
Step Functions
  -> State Lambda
  -> xác thực event và action
  -> đọc/ghi có điều kiện S3 idempotency object
  -> trả về quyết định và trạng thái lượt chạy
```

AI Engine do AIOps sở hữu là một Lambda container riêng. State Lambda chỉ bảo
vệ workflow CDO khỏi xử lý trùng và chuyển trạng thái không hợp lệ.

## Actions

| Action | Kết quả |
|---|---|
| `ACQUIRE_RUN` | Tạo run lock hoặc từ chối lượt chạy trùng. |
| `GET_RUN` | Trả về run-state record hiện tại. |
| `COMPLETE_RUN` | Chuyển lượt chạy sang `COMPLETED`. |
| `FAIL_RUN` | Chuyển lượt chạy sang `FAILED`. |
| `FAIL_CONTRACT_CHECK` | Ghi nhận lỗi contract và giữ containment ở trạng thái fail-closed. |
| `REDRIVE_RUN` | Tạo lại một lượt chạy đã lỗi và giữ quan hệ với lượt chạy trước. |

## Idempotency

Scheduled run sử dụng object key:

```text
idempotency/{tenant_id}:{billing_period_date}:{batch_type}
```

Ad-hoc run sử dụng:

```text
idempotency/ad-hoc/{tenant_id}/{billing_period_date}/{run_id}
```

Mỗi tenant chỉ được chạy tối đa năm ad-hoc run trong một ngày billing.

Object mới được tạo bằng S3 `IfNoneMatch="*"`. Update và redrive sử dụng ETag
hiện tại với `IfMatch`. State Lambda không xóa object để chiếm lock. Object hết
hạn chỉ được thay thế khi ETag vẫn khớp, nhờ đó tránh hai invocation cùng ghi
đè trạng thái.

## Event mẫu

```json
{
  "action": "ACQUIRE_RUN",
  "tenant_id": "123e4567-e89b-42d3-a456-426614174001",
  "account_id": "123456789012",
  "billing_period_date": "2026-06-25",
  "batch_type": "daily-batch",
  "run_id": "run-001",
  "correlation_id": "123e4567-e89b-42d3-a456-426614174000",
  "payload_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "contract_version": "v1.3.0",
  "is_ad_hoc": false,
  "lock_ttl_seconds": 86400,
  "duplicate_run_policy": "reject_existing_run"
}
```

Acquire thành công trả về `decision=ACCEPTED` và `status=IN_PROGRESS`.
Duplicate có cùng payload trả về `decision=REJECTED_DUPLICATE`. Nếu cùng key
nhưng khác payload, Lambda trả lỗi `ERR_IDEMPOTENCY_MISMATCH`.

## Yêu cầu môi trường

- Python 3.14.
- PowerShell 7.
- Terraform 1.5 trở lên.
- AWS CLI và AWS credentials có quyền trên account đích.

Kiểm tra nhanh:

```powershell
py -0p
pwsh --version
terraform version
aws sts get-caller-identity
```

## Đóng gói Lambda

Từ thư mục `services/state-lambda`:

```powershell
.\scripts\package.ps1
```

Script tự tìm Python 3.14 từ `py -0p` hoặc `PATH`, cài boto3 đã pin và tạo:

```text
build/state-lambda.zip
```

`build/` được Git bỏ qua và không cần push lên GitHub.

## Kiểm tra Terraform sau khi clone

Các thành viên có thể kiểm tra cấu hình mà chưa cần remote backend:

```powershell
terraform -chdir=terraform init -backend=false
terraform -chdir=terraform fmt -check
terraform -chdir=terraform validate
```

File `.terraform.lock.hcl` được commit để mọi thành viên sử dụng cùng phiên bản
AWS provider. Thư mục `.terraform/` là cache local và không được commit.

## Triển khai AWS

1. Đóng gói Lambda.
2. Sao chép các file cấu hình mẫu.
3. Thay bucket backend mẫu và các biến theo môi trường.
4. Chạy plan, kiểm tra kỹ rồi mới apply.

```powershell
Copy-Item terraform/backend.tf.example terraform/backend.tf
Copy-Item terraform/development.tfvars.example terraform/development.tfvars

# Sửa bucket trong terraform/backend.tf trước khi init.
terraform -chdir=terraform init
terraform -chdir=terraform fmt -check
terraform -chdir=terraform validate
terraform -chdir=terraform plan "-var-file=development.tfvars" "-out=state-lambda.tfplan"
terraform -chdir=terraform apply state-lambda.tfplan
```

Không apply nếu plan thay thế idempotency bucket hoặc xuất hiện DynamoDB, SQS,
Function URL, public access hay quyền `s3:DeleteObject`.

`backend.tf` và `development.tfvars` là cấu hình local, đã được `.gitignore`
loại khỏi commit.

## Chạy local với S3 development

Cài dependency vào virtual environment:

Dùng đường dẫn Python 3.14 hiển thị bởi `py -0p` để tạo môi trường:

```powershell
& "C:\path\to\python3.14\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Đặt AWS profile và bucket development:

```powershell
$env:IDEMPOTENCY_BUCKET_NAME = "your-development-idempotency-bucket"
$env:AWS_PROFILE = "your-profile"
Set-Location src
@'
import json
from lambda_function import lambda_handler

event = {
    "action": "ACQUIRE_RUN",
    "tenant_id": "123e4567-e89b-42d3-a456-426614174001",
    "account_id": "123456789012",
    "billing_period_date": "2026-06-25",
    "batch_type": "daily-batch",
    "run_id": "local-run-001",
    "correlation_id": "123e4567-e89b-42d3-a456-426614174000",
    "payload_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "contract_version": "v1.3.0"
}

print(json.dumps(lambda_handler(event, None), indent=2))
'@ | python -
```

Lệnh trên ghi vào S3 thật. Chỉ sử dụng bucket development hoặc sandbox.

## Xác minh sau deploy

```powershell
aws s3api get-object --bucket <bucket> --key <object-key> run-state.json
aws logs tail /aws/lambda/<function-name> --since 10m --follow
```

CloudWatch log gồm action, tenant, run, correlation, decision, status và error
code. Service không log toàn bộ payload, tags hoặc failure reason.

## Rollback

Deploy lại ZIP gần nhất đã hoạt động ổn định. S3 object schema không thay đổi
giữa bản Go và Python nên không cần data migration.

## Lỗi thường gặp

| Lỗi | Nguyên nhân hoặc cách xử lý |
|---|---|
| Không tìm thấy Python 3.14 | Cài Python 3.14 và kiểm tra lại bằng `py -0p`. |
| `ERR_CONFIGURATION` | Thiếu `IDEMPOTENCY_BUCKET_NAME`. |
| `ERR_INVALID_SCHEMA` | Event từ Step Functions không đúng contract. |
| `ERR_IDEMPOTENCY_MISMATCH` | Cùng idempotency key nhưng payload khác nhau. |
| `ERR_CONCURRENT_UPDATE` | Invocation khác đã update object trước; đọc trạng thái mới rồi retry. |
| `ERR_RUN_NOT_FOUND` | S3 run-state object không tồn tại. |
| `ERR_STORE` | Kiểm tra IAM, bucket name, region và CloudWatch logs. |
