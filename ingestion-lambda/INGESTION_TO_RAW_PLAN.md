# Plan Config Ingestion Lambda to S3 Raw Zone

## Pham vi

Plan nay chi mo ta luong cau hinh va van hanh den buoc Ingestion Lambda ghi du lieu vao S3 Raw Zone.

Dung tai:

```text
EventBridge Scheduler -> Step Functions -> Ingestion Lambda -> S3 Raw Zone
```

Khong bao gom:

```text
Glue Catalog
Partition & Convert
S3 Curated Zone
Athena Query
AI Engine
```

## Luong ngang

| Buoc | Thanh phan | Viec can lam | Input | Output |
|---|---|---|---|---|
| 1 | EventBridge Scheduler | Trigger workflow ingestion hang ngay | Cron/rate schedule | Start Step Functions |
| 2 | Step Functions Workflow | Tao payload ingestion gom billing period, run_id, account list, CUR source, raw bucket va KMS key | Schedule event | `IngestionInput` |
| 3 | Ingestion Lambda | Nhan event va parse payload thanh `IngestionInput` | Lambda event JSON | Payload hop le de chay ingestion |
| 4 | Ingestion Lambda | Tao AWS session mac dinh voi region `ap-southeast-1` | Lambda IAM role/env credentials | `boto3.Session` |
| 5 | Ingestion Lambda | Lap qua tung Member Account va assume role | `account_id`, `role_arn`, `external_id` | Session trong Member Account |
| 6 | CUR Puller | List CUR files theo thang billing period trong CUR export bucket | `cur_sources.bucket`, `cur_sources.prefix`, `cost_period_start` | Danh sach CUR object hop le |
| 7 | S3Writer | Copy CUR object tu CUR export bucket sang S3 Raw Zone voi KMS encryption | CUR source object, `raw_bucket`, `raw_prefix`, `run_id`, `kms_key_arn` | CUR object trong Raw Zone |
| 8 | Cost Explorer Puller | Query Cost Explorer API theo daily granularity | `cost_period_start`, `cost_period_end`, account context | Cost Explorer JSON response |
| 9 | S3Writer | Ghi Cost Explorer JSON vao S3 Raw Zone voi KMS encryption | CE JSON bytes, `raw_bucket`, `raw_prefix`, `run_id`, `account_id` | CE JSON object trong Raw Zone |
| 10 | CloudTrail Puller, neu `v2` | Poll SQS queue nhan CloudTrail events tu EventBridge | `CLOUDTRAIL_SQS_URL` hoac `CLOUDTRAIL_SQS_URL_{account_id}` | Danh sach high-cost CloudTrail events |
| 11 | S3Writer | Ghi CloudTrail signal JSON vao S3 Raw Zone voi KMS encryption | CloudTrail events, `raw_bucket`, `raw_prefix`, `run_id` | CloudTrail JSON object trong Raw Zone |
| 12 | Ingestion Lambda | Tong hop ket qua ingest va tra ve Step Functions | CUR refs, CE refs, CloudTrail refs, errors | `IngestionOutput` |

## Input config mau

```json
{
  "run_id": "ingestion-20260625-0001",
  "api_version": "v2",
  "tenant_id": "tenant-or-org-id",
  "cost_period_start": "2026-06-01",
  "cost_period_end": "2026-07-01",
  "raw_bucket": "cdo-data-lakehouse-raw",
  "raw_prefix": "cost/raw/",
  "kms_key_arn": "arn:aws:kms:ap-southeast-1:123456789012:key/xxxx",
  "enable_cloudtrail_streaming": true,
  "retry": {
    "max_attempts": 3,
    "base_delay_ms": 500,
    "max_delay_ms": 30000
  },
  "accounts": [
    {
      "account_id": "111111111111",
      "role_arn": "arn:aws:iam::111111111111:role/CDOIngestionReadRole",
      "external_id": "optional-external-id"
    }
  ],
  "cur_sources": [
    {
      "bucket": "member-cur-export-bucket",
      "prefix": "cur-report-prefix/"
    }
  ]
}
```

## S3 Raw Zone layout

Theo code hien tai, cac object duoc ghi vao Raw Zone theo cac pattern sau:

```text
s3://{raw_bucket}/{raw_prefix}{run_id}/cur/{safe_bucket}/{original_cur_key}
s3://{raw_bucket}/{raw_prefix}{run_id}/ce/{account_id}/{timestamp}.json
s3://{raw_bucket}/{raw_prefix}{run_id}/cloudtrail/{timestamp}.json
```

Trong do:

| Field | Y nghia |
|---|---|
| `raw_bucket` | Bucket S3 dung lam raw zone |
| `raw_prefix` | Prefix raw, vi du `cost/raw/` |
| `run_id` | ID cua moi lan ingestion |
| `safe_bucket` | Ten CUR bucket da thay dau `.` bang `-` |
| `account_id` | AWS linked/member account ID |
| `timestamp` | UTC timestamp luc ghi object |

## Lambda environment variables

```text
TELEMETRY_API_VERSION=v2
AI_ENGINE_ENDPOINT_V2=https://ai-engine.tf2-finops.internal/v2/detect
AI_ENGINE_ENDPOINT_V1=https://ai-engine.tf2-finops.internal/v1/detect
CLOUDTRAIL_SQS_URL=https://sqs.ap-southeast-1.amazonaws.com/123456789012/cloudtrail-events
```

Neu moi account co queue rieng:

```text
CLOUDTRAIL_SQS_URL_111111111111=https://sqs.ap-southeast-1.amazonaws.com/111111111111/cloudtrail-events
CLOUDTRAIL_SQS_URL_222222222222=https://sqs.ap-southeast-1.amazonaws.com/222222222222/cloudtrail-events
```

## IAM can cau hinh

Lambda execution role:

| Permission | Muc dich |
|---|---|
| `sts:AssumeRole` | Assume role vao Member Accounts |
| `s3:PutObject` | Ghi CE JSON va CloudTrail JSON vao Raw Zone |
| `s3:CopyObject` | Copy CUR object vao Raw Zone |
| `s3:GetObject` | Doc CUR object nguon khi copy |
| `s3:ListBucket` | List CUR objects theo prefix |
| `kms:Encrypt` | Ghi object voi SSE-KMS |
| `kms:Decrypt` | Doc/copy object neu bucket nguon can KMS |
| `kms:GenerateDataKey` | Tao data key khi ghi object ma hoa |
| `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` | Ghi CloudWatch Logs |

Member Account role:

| Permission | Muc dich |
|---|---|
| `ce:GetCostAndUsage` | Query Cost Explorer |
| `s3:ListBucket` | List CUR export bucket |
| `s3:GetObject` | Doc CUR object |
| `sqs:ReceiveMessage` | Poll CloudTrail queue neu dung Signal 2 |
| `sqs:DeleteMessageBatch` | Xoa message da xu ly |
| `sqs:GetQueueAttributes` | Doc thong tin queue |

## Output tra ve Step Functions

Lambda tra ve `IngestionOutput` gom:

| Field | Y nghia |
|---|---|
| `run_id` | ID cua ingestion run |
| `status` | `completed`, `partial`, hoac `failed` |
| `api_version` | `v1` hoac `v2` |
| `cur_refs` | Danh sach CUR objects da copy vao Raw Zone |
| `ce_json_refs` | Danh sach CE JSON objects da ghi vao Raw Zone |
| `cloudtrail_refs` | Danh sach CloudTrail objects da ghi vao Raw Zone |
| `source_uris` | Tat ca S3 URI output |
| `account_statuses` | Trang thai tung account |
| `errors` | Loi theo account/source neu co |

## Error handling

| Error code | Nguon | Xu ly de xuat |
|---|---|---|
| `ASSUME_ROLE_FAILED` | STS assume role | Mark account failed, tiep tuc account khac |
| `CUR_DELAY` | CUR source bucket | Mark CUR delayed/error, co the retry lan sau |
| `CE_THROTTLE` | Cost Explorer API | Retry theo config backoff, neu het attempt thi mark error |
| `CLOUDTRAIL_ERROR` | SQS/CloudTrail | Non-blocking, fallback CUR + CE |
| `UNKNOWN` | Loi khong co prefix | Log va mark source error |

## Dieu kien hoan tat

Ingestion run duoc xem la hoan tat o pham vi Raw Zone khi:

```text
1. Lambda parse duoc payload Step Functions.
2. Lambda assume role vao it nhat mot Member Account thanh cong.
3. CUR objects, CE JSON hoac CloudTrail JSON duoc ghi vao S3 Raw Zone.
4. Lambda tra ve `IngestionOutput` co refs va status cho Step Functions.
```

