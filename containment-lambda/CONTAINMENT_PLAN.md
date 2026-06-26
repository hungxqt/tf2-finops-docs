# Containment Lambda — Plan

## Scope

Lambda này xử lý bước thực thi containment trong flow:

```
Step Functions → Containment Lambda → Member Account Resources
                                    → S3 Audit Store (Object Lock)
                                    → DynamoDB Dashboard Cache
```

Không bao gồm:
- Gọi AI Engine (đã xong trước bước này)
- Alert routing (Alert Lambda làm việc đó)
- Dashboard rendering

## Flow ngang

| Bước | Thành phần | Việc làm | Input | Output |
|---|---|---|---|---|
| 1 | handler.py | Parse event từ Step Functions | Lambda event JSON | ContainmentInput |
| 2 | policy/boundary.py | Enforce hard boundaries | ContainmentInput | enforced_mode |
| 3 | aws/session.py | AssumeRole vào member account | account_id, role_name, external_id | member boto3.Session |
| 4 | aws/resource_reader.py | Đọc before_state của resource | member session, resource_id | before_state dict |
| 5 | audit/dynamo_cache.py | Cache rollback payload (TRƯỚC khi thực thi) | rollback_payload, table_name | cached = True/False |
| 6 | audit/s3_audit.py | Ghi pre-action audit record | AuditRecord, audit_bucket | audit_id, s3_uri |
| 7 | actions/* | Thực thi action theo execution_mode | member session, ContainmentInput | ActionResult |
| 8 | audit/s3_audit.py | Ghi post-action audit record | audit_id, action_result | — |
| 9 | audit/dynamo_cache.py | Cập nhật Dashboard Cache | ContainmentOutput fields | — |
| 10 | handler.py | Return ContainmentOutput | ContainmentOutput | dict cho Step Functions |

## Hard Boundaries (không thể override)

| Boundary | Điều kiện | Kết quả |
|---|---|---|
| Prod protection | environment ∈ {prod, prod-core, prod-payments} + mode = apply | Force dry-run |
| Low confidence | data_confidence = LOW (CUR delay) | Force dry-run |
| Approval denied | approval_status = denied | Return denied record, không làm gì |

## Input mẫu từ Step Functions

```json
{
  "run_id": "run-20260626-001",
  "anomaly_id": "anom-9988-7766",
  "correlation_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "model_version": "v1.4.0",
  "anomaly_type": "runaway_usage",
  "confidence": 0.92,
  "severity": "high",
  "explanation": "EC2 p3.2xlarge running 24/7 for 18 days, no traffic correlated",
  "data_confidence": "HIGH",
  "resource_id": "i-0fbgpu00000004",
  "resource_owner": "squad-ml-core",
  "account_id": "200000000012",
  "environment": "sandbox",
  "containment_role_name": "FinOpsContainmentWorkerRole",
  "external_id": "finops-external-id-seed",
  "execution_mode": "apply",
  "approval_status": "approved",
  "recommended_containment_mode": "auto-shutdown",
  "applied_payload": {
    "service": "ec2",
    "method": "stop_instances",
    "parameters": { "InstanceIds": ["i-0fbgpu00000004"] }
  },
  "rollback_payload": {
    "service": "ec2",
    "method": "start_instances",
    "parameters": { "InstanceIds": ["i-0fbgpu00000004"] }
  },
  "audit_config": {
    "audit_bucket": "company-cdo-200000000012-telemetry",
    "audit_prefix": "audit/",
    "dashboard_table": "finops-dashboard-cache-sandbox",
    "rollback_cache_table": "finops-rollback-cache"
  }
}
```

## Environment Variables (cần khai báo trong Terraform Lambda config)

| Variable | Ví dụ | Mô tả |
|---|---|---|
| `AWS_REGION` | `ap-southeast-1` | Region triển khai |

## IAM Permissions cần có (Lambda Execution Role)

### CDO Management Account

| Permission | Resource | Mục đích |
|---|---|---|
| `sts:AssumeRole` | `arn:aws:iam::*:role/FinOpsContainmentWorkerRole` | Vào member account |
| `s3:PutObject` | `arn:aws:s3:::company-cdo-*-telemetry/audit/*` | Ghi audit record |
| `dynamodb:PutItem` | `arn:aws:dynamodb:*:*:table/finops-dashboard-cache-*` | Update dashboard cache |
| `dynamodb:PutItem` `dynamodb:GetItem` | `arn:aws:dynamodb:*:*:table/finops-rollback-cache` | Cache + read rollback |
| `secretsmanager:GetSecretValue` | `arn:aws:secretsmanager:*:*:secret:finops/containment/*` | Lấy external_id |
| `logs:CreateLogGroup` `logs:PutLogEvents` | `*` | CloudWatch Logs |

### Member Account (FinOpsContainmentWorkerRole)

Theo `deployment-contract.md` Appendix B:

| Permission | Condition | Mục đích |
|---|---|---|
| `ec2:CreateTags` `ec2:StopInstances` | `StringNotEquals environment [prod, prod-core, prod-payments]` | Containment EC2 |
| `rds:AddTagsToResource` `rds:StopDBInstance` | Non-prod only | Containment RDS |
| `sagemaker:AddTags` `sagemaker:StopNotebookInstance` | Non-prod only | Containment SageMaker |
| `ec2:DescribeInstances` | All | Đọc before_state |

## DynamoDB Tables cần tồn tại

| Table | Key | TTL | Mục đích |
|---|---|---|---|
| `finops-rollback-cache` | `anomaly_id` (String) | `ttl_epoch` (90 ngày) | Cache rollback payload |
| `finops-dashboard-cache-{env}` | `anomaly_id` (String) | Không | Dashboard read cache |

## S3 Bucket cần tồn tại

| Bucket | Object Lock | Prefix | Mục đích |
|---|---|---|---|
| `company-cdo-{account_id}-telemetry` | COMPLIANCE mode | `audit/year={}/month={}/` | Audit records 90 ngày |

## Chạy tests local

```bash
# Cài dependencies
pip install -r requirements-dev.txt

# Chạy tất cả tests
pytest tests/ -v

# Chỉ chạy boundary tests (không cần moto)
pytest tests/test_boundary.py -v

# Chỉ chạy audit tests (cần moto)
pytest tests/test_audit.py -v
```

## Điều kiện hoàn thành

Lambda được xem là hoàn thành khi:

1. Tất cả unit tests pass (`pytest tests/ -v`)
2. Hard boundary: prod + low_confidence + denied đều force dry-run/denied
3. Pre-action audit được ghi S3 TRƯỚC khi thực thi action
4. Rollback payload được cache vào DynamoDB TRƯỚC khi thực thi
5. DynamoDB Dashboard Cache được update sau mỗi run
6. Return `ContainmentOutput` dict đúng schema cho Step Functions
