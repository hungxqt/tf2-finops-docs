# Telemetry Contract — Task Force 2 (FinOps Watch)

<!-- Owner: Nhóm AI 2
     Signed by: AI Lead + CDO Leads × 2 (CDO-01, CDO-02) + Reviewer panel
     Date signed: 2026-06-25 (W11 T5)
     🔒 FREEZE — no change without formal Change Request
     Word target: 2000-3000 từ (Contract tier)
     Cross-ref: ai-api-contract.md · deployment-contract.md · docs/02_solution_design.md -->

---

## 1. Mục đích và Phạm vi

Hợp đồng này định nghĩa **các tín hiệu (signals) dữ liệu chi phí và hiệu năng** mà nhóm CDO phải thu thập từ AWS Infrastructure → chuẩn hóa → truyền tải cho AI Engine.

**Nguyên tắc cốt lõi**: CDO Platform là **source-of-truth** duy nhất. CDO **PULL** dữ liệu từ AWS CUR (S3), Cost Explorer API, và CloudWatch theo chu kỳ cố định — AI Engine không trực tiếp gọi AWS APIs.

**Phạm vi phát hiện**: Contract phục vụ 5 loại bất thường chính (reference: TF2_FINOPS_LEARNER.md):

| # | Anomaly Type | Tín hiệu chính |
|---|---|---|
| 1 | `runaway_usage` | Compute chạy 24/7, `usage_density_24h ≈ 1.0`, không giảm cuối tuần |
| 2 | `idle_resource` | Cost đều đặn, `CPUUtilization ≈ 0%`, `DatabaseConnections ≈ 0` |
| 3 | `untagged_spend` | `resource_tags_user_team` rỗng, cost lớn |
| 4 | `sudden_spike` | Cost nhảy bậc thang, `cost_ratio_to_7d_avg > 3.0` |
| 5 | `gradual_drift` | Trend tăng chậm nhiều tuần, chỉ visible trên `rolling_30d_avg` |

---

## 2. Schema Governance Layer

Áp dụng OpenTelemetry Schema System để quản lý tính tương thích khi CDO và AI nâng cấp không đồng bộ.

| Rule | Value |
|---|---|
| **Schema version** | `3.0.0` |
| **Schema URL** | `telemetry://finops-watch/v3` |
| **Backward compatible** | `true` — CDO upgrade pipeline trước AI — OK |
| **Deprecation window** | 30 ngày hỗ trợ version cũ song song |
| **Action on expiry** | `reject_request` — Từ chối payload version cũ sau grace period |
| **Change request channel** | Task Force WhatsApp + Meeting |
| **Approval** | AI Lead + CDO Leads đồng thuận |
| **Bump rule** | Breaking change → version major. Add field → minor |

> **WHY backward compatibility**: CDO-01 và CDO-02 có thể deploy pipeline khác nhau. Nếu không backward-compatible, AI Engine buộc phải hỗ trợ 2 schema cùng lúc — phức tạp không cần thiết (reference: ADR-003).

---

## 3. Request Integrity Layer

Bảo vệ chống giả mạo payload (anti-tampering) và chống tấn công phát lại (anti-replay). Khớp với `X-Payload-SHA256` và `X-Request-Timestamp` đã define trong ai-api-contract.md §4.

**JSON Schema**:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "RequestIntegrity",
  "description": "AI Engine sẽ log lại các trường này để verify integrity cho mỗi request từ CDO",
  "type": "object",
  "properties": {
    "payload_sha256": {
      "type": "string",
      "description": "SHA256 hash của JSON body — verify integrity",
      "pattern": "^[a-f0-9]{64}$"
    },
    "request_timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "Thời điểm CDO tạo request (UTC ISO 8601 RFC3339)"
    },
    "signature_verified": {
      "type": "boolean",
      "description": "true nếu AWS IAM SigV4 hợp lệ"
    },
    "replay_window_seconds": {
      "type": "integer",
      "default": 300,
      "description": "Cửa sổ chấp nhận: 5 phút"
    }
  },
  "required": ["payload_sha256", "request_timestamp", "signature_verified"]
}
```

**Rule**: Nếu `abs(now - request_timestamp) > 300s` → Reject `400 Bad Request` + log `ERR_REPLAY_DETECTED`.

> **WHY 300s**: Tradeoff giữa độ trễ CDO pipeline (~30s bình thường) và cửa sổ tấn công replay. 5 phút đủ headroom cho network jitter mà không mở quá rộng cho replay attack.

---

## 4. Tenant Context & Idempotency

Khớp 1:1 với `X-Tenant-Id` và `X-Idempotency-Key` trong ai-api-contract.md §4.

**JSON Schema**:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TenantContext",
  "description": "CDO PHẢI gửi kèm các trường này trong mỗi request để AI Engine routing multi-tenant",
  "type": "object",
  "properties": {
    "tenant_id": {
      "type": "string",
      "format": "uuid",
      "description": "Linked Account ID ánh xạ → UUID"
    },
    "account_id": {
      "type": "string",
      "pattern": "^[0-9]{12}$",
      "description": "AWS Linked Account ID (e.g. 200000000012)"
    },
    "account_name": {
      "type": "string",
      "description": "e.g. prod-core, staging, ml-research"
    },
    "correlation_id": {
      "type": "string",
      "format": "uuid",
      "description": "Trace ID xuyên suốt E2E request chain"
    },
    "idempotency_key": {
      "type": "string",
      "pattern": "^[0-9a-f-]{36}:[0-9]{4}-[0-9]{2}-[0-9]{2}$",
      "description": "Format: tenant_id:YYYY-MM-DD (reference: API Contract §4)"
    },
    "ttl_expiry": {
      "type": "string",
      "format": "date-time",
      "description": "Hết hạn sau 24h trong DynamoDB"
    }
  },
  "required": ["tenant_id", "account_id", "account_name", "correlation_id", "idempotency_key"]
}
```

**Idempotency Rules** (khớp API Contract §4 quy tắc nâng cao):
- Trùng key + cùng hash → `200 OK` kèm kết quả cũ
- Trùng key + khác hash → `400 ERR_IDEMPOTENCY_MISMATCH`
- Trùng key + đang chạy → `409 Conflict`

> **WHY composite key**: `tenant_id:YYYY-MM-DD` đảm bảo mỗi tenant chỉ có 1 batch/ngày. `is_ad_hoc = true` bypass key này cho quét khẩn cấp (tối đa 5 lần/ngày — xem Deployment Contract §7).

---

## 5. Hybrid Ingestion Contract

Giải quyết giới hạn **10MB** của API Gateway/ALB. Khớp với `data_source_type` trong ai-api-contract.md §5.1.

**JSON Schema**:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "HybridIngestion",
  "description": "CDO chọn data_source_type phù hợp per-batch. RAW_JSON cho CE data nhỏ, S3_POINTER cho CUR data lớn",
  "type": "object",
  "properties": {
    "data_source_type": {
      "type": "string",
      "enum": ["RAW_JSON", "S3_POINTER"],
      "description": "RAW_JSON: gửi trực tiếp JSON body (≤10MB). S3_POINTER: upload file lên S3 rồi gửi URI"
    },
    "s3_bucket_uri": {
      "type": "string",
      "pattern": "^s3://company-cdo-telemetry/.+\\.json\\.gz$",
      "description": "Bắt buộc khi data_source_type = S3_POINTER"
    },
    "s3_object_checksum": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$",
      "description": "SHA256 checksum file S3 — verify trước khi extract"
    }
  },
  "required": ["data_source_type"],
  "if": {
    "properties": { "data_source_type": { "const": "S3_POINTER" } }
  },
  "then": {
    "required": ["s3_bucket_uri", "s3_object_checksum"]
  }
}
```

**Constraints**:

| Parameter | Value |
|---|---|
| `raw_json_max_size_mb` | 10 |
| `s3_allowed_buckets` | `company-cdo-telemetry` |
| `s3_allowed_extensions` | `.json.gz` |
| `s3_max_object_size_mb` | 500 |
| `s3_encryption` | `aws-kms` |

> **WHY Hybrid**: Cost Explorer data nhỏ (~50KB, 6 cột × 100 records) → RAW_JSON đủ. CUR data lớn (~5-50MB, 24K+ line items) → S3_POINTER tránh timeout. CDO chọn mode phù hợp per-batch.

---

## 6. Signal 1: `aws_cost_explorer_daily` — Macro Layer (Trends)

Dữ liệu tổng hợp vĩ mô. Map trực tiếp với schema cost_explorer_daily.csv trong dataset TF2.

| Attribute | Value |
|---|---|
| **Type** | Tabular aggregate (daily grain) |
| **Frequency** | PULL 1 lần/ngày lúc 02:00 AM (EventBridge cron) |
| **Emit point** | CDO gọi `aws ce get-cost-and-usage` → normalize → đóng gói JSON |
| **Retention** | 7 ngày hot (DynamoDB cache), 30 ngày cold (S3) |
| **Used for** | Trend detection, account-level anomaly, baseline calculation |
| **Emit SLA** | p99 < 60s từ CE API response → AI consumable |
| **Volume SLA** | ~100-500 records/batch (6 accounts × ~20 services × 1 day) |
| **Cost estimate** | $0.01/request × 2 requests/day = $0.60/month |

### 6.1 JSON Schema — CDO PHẢI trả về đúng format này

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CostExplorerDailySignal",
  "description": "Mỗi record = 1 dịch vụ × 1 ngày × 1 region. CDO gọi aws ce get-cost-and-usage → normalize → gửi array các objects theo schema này",
  "type": "object",
  "properties": {
    "unblended_cost": {
      "type": "number",
      "minimum": 0,
      "description": "Chi phí ngày hiện tại (USD)"
    },
    "service_code": {
      "type": "string",
      "description": "Mã ngắn CUR: AmazonEC2, AmazonRDS, AmazonSageMaker, etc."
    },
    "service": {
      "type": "string",
      "description": "Tên hiển thị Cost Explorer: 'Amazon Elastic Compute Cloud - Compute'"
    },
    "region": {
      "type": "string",
      "description": "AWS Region code, e.g. us-east-1, ap-southeast-1"
    },
    "cost_ratio_to_7d_avg": {
      "type": "number",
      "minimum": 0,
      "description": "unblended_cost / rolling_7d_avg. Giá trị > 3.0 = sudden_spike suspect"
    },
    "day_of_week": {
      "type": "integer",
      "minimum": 0,
      "maximum": 6,
      "description": "0=Mon, 1=Tue, ..., 6=Sun"
    },
    "is_weekend": {
      "type": "boolean",
      "description": "Derived từ day_of_week: true nếu day_of_week ∈ {5,6}"
    },
    "is_estimated": {
      "type": "boolean",
      "description": "true cho 2 ngày cuối (CUR chưa finalized). AI Engine sẽ hạ confidence khi true"
    }
  },
  "required": [
    "unblended_cost", "service_code", "service", "region",
    "cost_ratio_to_7d_avg", "day_of_week", "is_weekend", "is_estimated"
  ]
}
```

> [!WARNING]
> **Naming Mismatch (đã verify với AWS thật)**: CUR dùng `service_code` (e.g. `AmazonEC2`), Cost Explorer dùng `service` (e.g. `Amazon Elastic Compute Cloud - Compute`). CDO **bắt buộc** cung cấp **cả hai trường** để tránh lỗi khi join dữ liệu — đây là cái bẫy thật ngoài production (reference: TF2 Dataset README line 79).

> [!IMPORTANT]
> **Dữ liệu ước tính**: Khi `is_estimated = true` ở 2 ngày gần nhất, AI Engine **PHẢI** hạ confidence score và **KHÔNG** kích hoạt auto-containment. CDO gửi kèm `telemetry_delay_event = true` khi CUR chưa finalized → AI Engine tạm hoãn batch, kiểm tra lại mỗi 1h (reference: 01_requirements.md §7 Q3).

> **WHY cache DynamoDB**: Cost Explorer API rate limit 5 requests/second. CDO cache kết quả vào DynamoDB tránh vượt limit. AI Engine đọc cache khi cần baseline 7d/30d thay vì gọi CE trực tiếp (reference: ADR-003).

---

## 7. Signal 2: `aws_cur_line_items` — Micro Layer (Facts)

Dữ liệu vi mô cấp tài nguyên. Map trực tiếp với schema cur_line_items.csv. **Đây là nguồn sự thật (source of truth) cho detection** (reference: TF2 Dataset README line 63).

| Attribute | Value |
|---|---|
| **Type** | Tabular CUR 2.0 resource-level (daily grain) |
| **Frequency** | PULL 1 lần/ngày sau CE signal |
| **Emit point** | CDO đọc S3 CUR manifest → Athena query → JSON/gz → truyền qua S3_POINTER |
| **Retention** | 7 ngày hot, 90 ngày cold (compliance) |
| **Used for** | Resource-level anomaly detection, drill-down RCA, containment targeting |
| **Emit SLA** | p99 < 300s (Athena query + compress + upload) |
| **Volume SLA** | ~500-25K records/batch (TF2 dataset: 24,533 line items / 92 days ≈ 267/day) |

### 7.1 JSON Schema — CDO PHẢI trả về đúng format này

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CURLineItemSignal",
  "description": "Mỗi record = 1 tài nguyên AWS cụ thể × 1 ngày. Nguồn sự thật cho anomaly detection",
  "type": "object",
  "properties": {
    "line_item_resource_id": {
      "type": "string",
      "description": "ARN hoặc Instance ID cụ thể, e.g. arn:aws:ec2:us-east-1:200000000012:instance/i-0abc123"
    },
    "line_item_usage_type": {
      "type": "string",
      "description": "Loại sử dụng chi tiết, e.g. BoxUsage:p3.2xlarge"
    },
    "line_item_usage_amount": {
      "type": "number",
      "minimum": 0,
      "description": "Khối lượng hoạt động vật lý (hours, GB, requests)"
    },
    "pricing_unit": {
      "type": "string",
      "enum": ["Hrs", "GB", "GB-Mo", "Requests", "Queries"],
      "description": "Đơn vị tính giá"
    },
    "line_item_unblended_cost": {
      "type": "number",
      "minimum": 0,
      "description": "*** Nguồn sự thật cho detection *** Chi phí thực tế (USD)"
    },
    "line_item_unblended_rate": {
      "type": "number",
      "minimum": 0,
      "description": "Đơn giá (e.g. $3.06/hr cho p3.2xlarge)"
    },
    "line_item_operation": {
      "type": "string",
      "description": "e.g. RunInstances, CreateDBInstance, CreateNotebookInstance"
    },
    "usage_density_24h": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Mật độ chạy liên tục trong 24h. 1.0 = chạy 24/24. CDO tự tính = usage_hours/24"
    },
    "resource_tags_user_environment": {
      "type": "string",
      "enum": ["prod", "prod-core", "prod-payments", "staging", "dev", "sandbox", "ml-research", "data-analytics"],
      "description": "Tag môi trường. Quyết định chiến lược containment (xem Deployment Contract §6.2)"
    },
    "resource_tags_user_owner": {
      "type": ["string", "null"],
      "description": "Người sở hữu tài nguyên. null = chưa gán owner"
    },
    "resource_tags_user_team": {
      "type": ["string", "null"],
      "description": "Squad quản lý. null/empty = untagged_spend signal → anomaly type 3"
    },
    "resource_tags_user_cost_center": {
      "type": ["string", "null"],
      "description": "Mã trung tâm chi phí, e.g. CC-2001, CC-3001"
    }
  },
  "required": [
    "line_item_resource_id", "line_item_usage_type", "line_item_usage_amount",
    "pricing_unit", "line_item_unblended_cost", "line_item_unblended_rate",
    "line_item_operation", "usage_density_24h", "resource_tags_user_environment"
  ]
}
```

### 7.2 Athena Query tối ưu (CDO bắt buộc partition + chỉ quét window cần thiết)

```sql
SELECT bill_billing_period_start_date, line_item_usage_start_date,
       line_item_usage_account_id, line_item_product_code,
       line_item_resource_id, line_item_unblended_cost,
       resource_tags_user_team, resource_tags_user_environment
FROM "cur2_database"."cur2_table"
WHERE bill_billing_period_start_date = DATE_FORMAT(CURRENT_DATE, '%Y-%m-01 00:00:00')
  AND line_item_usage_start_date >= DATE_ADD('day', -2, CURRENT_DATE)
```

> **WHY `unblended_cost` not `usage_amount`**: Daily `usage_amount` dao động nhẹ quanh 24h do nhiễu — bình thường trong CUR. `unblended_cost` là tín hiệu ổn định hơn cho detection (reference: README line 68).

---

## 8. Signal 3: `resource_utilization_metrics` — CloudWatch Layer

Tín hiệu hiệu năng vật lý. **Bắt buộc** để phát hiện `idle_resource` (cost cao + utilization thấp) và `runaway_usage` (cost cao + utilization cao liên tục).

| Attribute | Value |
|---|---|
| **Type** | CloudWatch Metrics |
| **Frequency** | PULL 1 lần/ngày (aggregate 24h period) |
| **Used for** | Xác nhận anomaly, giảm false positive, confidence scoring |
| **Fallback** | Nếu CloudWatch không available → AI Engine vẫn chạy CUR-only detection nhưng `confidence *= 0.5` |

### 8.1 JSON Schema — CDO PHẢI trả về đúng format này

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ResourceUtilizationMetrics",
  "description": "CDO tổng hợp CloudWatch metrics theo resource_id → aggregate 24h → gửi kèm CUR data. Nếu thiếu → AI Engine chạy CUR-only mode",
  "type": "object",
  "properties": {
    "resource_id": {
      "type": "string",
      "description": "Khớp với line_item_resource_id trong CUR signal"
    },
    "cpu_percent": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "CPUUtilization avg 24h (EC2/RDS/ECS)"
    },
    "memory_mib": {
      "type": "number",
      "minimum": 0,
      "description": "MemoryUtilization (MiB) — chỉ có nếu CloudWatch Agent installed"
    },
    "network_in_bytes": {
      "type": "number",
      "minimum": 0,
      "description": "NetworkIn tổng 24h (bytes)"
    },
    "network_out_bytes": {
      "type": "number",
      "minimum": 0,
      "description": "NetworkOut tổng 24h (bytes)"
    },
    "disk_io_ops": {
      "type": "number",
      "minimum": 0,
      "description": "DiskReadOps + DiskWriteOps tổng 24h"
    },
    "database_connections": {
      "type": ["integer", "null"],
      "minimum": 0,
      "description": "RDS DatabaseConnections avg 24h. null nếu không phải RDS"
    },
    "gpu_utilization": {
      "type": ["number", "null"],
      "minimum": 0,
      "maximum": 100,
      "description": "GPU Core usage % (SageMaker ml-research). null nếu không có GPU"
    },
    "idle_hours_continuous": {
      "type": ["integer", "null"],
      "minimum": 0,
      "description": "Số giờ liên tục utilization < 5%. CDO tự tính từ CloudWatch 1h-period data"
    }
  },
  "required": ["resource_id", "cpu_percent", "network_in_bytes", "network_out_bytes"]
}
```

> **WHY fallback khi mất CloudWatch**: Reliability principle — CUR data là "đủ" để detect, CloudWatch chỉ "tăng confidence". Không block detection vì thiếu metric phụ (reference: 02_solution_design.md §5 Risk mitigation).

---

## 9. Resource Identity Contract

Chuẩn hóa định danh tài nguyên theo OpenTelemetry semantic conventions. Dùng cho multi-tenant routing + RCA drill-down.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ResourceIdentity",
  "description": "CDO chuẩn hóa resource identity từ CUR + CloudTrail → gửi kèm theo mỗi batch",
  "type": "object",
  "properties": {
    "resource_id":    { "type": "string", "description": "line_item_resource_id (ARN hoặc instance ID)" },
    "resource_type":  { "type": "string", "description": "e.g. aws:ec2:instance, aws:rds:db, aws:sagemaker:notebook" },
    "aws_service":    { "type": "string", "description": "line_item_product_code" },
    "account_id":     { "type": "string", "pattern": "^[0-9]{12}$" },
    "account_name":   { "type": "string" },
    "region":         { "type": "string" },
    "environment":    { "type": "string", "enum": ["prod", "prod-core", "prod-payments", "staging", "dev", "sandbox", "ml-research", "data-analytics"] },
    "owner":          { "type": ["string", "null"] },
    "team":           { "type": ["string", "null"] },
    "cost_center":    { "type": ["string", "null"] }
  },
  "required": ["resource_id", "resource_type", "aws_service", "account_id", "region", "environment"]
}
```

---

## 10. Resource Lineage Contract

Truy vết nguồn gốc tài nguyên. Hỗ trợ RCA nhân quả: `Cost spike → deployment abc123 → commit 84fd2a → team-ml`.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ResourceLineage",
  "description": "CDO lấy từ CloudTrail/CloudFormation/CI-CD pipeline → optional nhưng tăng chất lượng RCA",
  "type": "object",
  "properties": {
    "deployment_id":    { "type": ["string", "null"], "description": "CloudFormation StackId hoặc ECS deployment ID" },
    "git_sha":          { "type": ["string", "null"], "description": "Commit hash tạo tài nguyên" },
    "pipeline_run_id":  { "type": ["string", "null"], "description": "CI/CD pipeline execution ID" },
    "created_by":       { "type": ["string", "null"], "description": "IAM User/Role ARN" },
    "created_at":       { "type": "string", "format": "date-time", "description": "CloudTrail CreateTime" },
    "ttl_expiry":       { "type": ["string", "null"], "format": "date-time", "description": "Ngày hết hạn theo kế hoạch" }
  },
  "required": ["created_at"]
}
```

> **WHY lineage**: Khi AI Engine phát hiện anomaly, nếu biết `created_by: team-ml, deployment_id: sagemaker-training-job-42`, RCA reasoning sẽ chính xác hơn so với chỉ biết "resource X tốn tiền" (reference: Google Cloud SRE lineage patterns).

---

## 11. Business Context Signals — False Positive Reduction

Loại bỏ **3 bẫy False Positive** trong dataset: flash-sale, migration, load test (reference: TF2 Dataset README §Bẫy FP).

Logic: `cost ↑ + traffic ↑ = normal growth` | `cost ↑ + traffic flat = anomaly`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "BusinessContext",
  "description": "CDO gửi kèm nếu có event đặc biệt. Giúp AI Engine tránh false positive",
  "type": "object",
  "properties": {
    "active_users":   { "type": "integer", "minimum": 0, "description": "Concurrent active users" },
    "orders_count":   { "type": "integer", "minimum": 0, "description": "Transaction count 24h" },
    "traffic_volume": { "type": "number",  "minimum": 0, "description": "Request volume aggregate 24h" },
    "campaign_flag":  { "type": "boolean", "description": "true = đang có marketing campaign" },
    "load_test_flag": { "type": "boolean", "description": "true = đang chạy performance test" },
    "migration_flag": { "type": "boolean", "description": "true = đang migration data" }
  },
  "required": ["campaign_flag", "load_test_flag", "migration_flag"]
}
```

> **WHY business context**: Dataset TF2 có 3 sự kiện benign trông y anomaly nhưng **hợp lệ**. Detector không có business context sẽ vỡ ngưỡng FP ≤10% (reference: README line 119).

---

## 12. Time Integrity Contract

Bảo vệ quan hệ nhân quả (causality) trong hệ thống phân tán. **Reject nếu clock skew > 10s**.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TimeIntegrity",
  "description": "AI Engine validate time integrity — reject nếu skew > 10s",
  "type": "object",
  "properties": {
    "source_timestamp":    { "type": "string", "format": "date-time", "description": "Thời điểm AWS agent sinh dữ liệu" },
    "collector_timestamp": { "type": "string", "format": "date-time", "description": "Thời điểm CDO Collector thu thập" },
    "ingestion_timestamp": { "type": "string", "format": "date-time", "description": "Thời điểm AI Engine nhận dữ liệu (AI tự gán)" },
    "clock_skew_ms":       { "type": "integer", "description": "abs(ingestion - source) in milliseconds" },
    "max_allowed_skew_ms": { "type": "integer", "default": 10000, "description": "10 giây threshold" }
  },
  "required": ["source_timestamp", "collector_timestamp"]
}
```

---

## 13. Telemetry Quality Contract

AI Engine tự đánh giá dữ liệu trước khi ra quyết định. **Nếu `completeness_score < 0.8` → AI forced into DRY-RUN.**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TelemetryQuality",
  "description": "AI Engine tự tính các score này SAU KHI nhận data từ CDO. Không yêu cầu CDO gửi",
  "type": "object",
  "properties": {
    "cur_status":              { "type": "string", "enum": ["HEALTHY", "DELAYED", "MISSING"] },
    "cloudwatch_status":       { "type": "string", "enum": ["HEALTHY", "DEGRADED", "MISSING"] },
    "cost_explorer_status":    { "type": "string", "enum": ["HEALTHY", "STALE"] },
    "completeness_score":      { "type": "number", "minimum": 0, "maximum": 1, "description": "Tỷ lệ trường bắt buộc có giá trị hợp lệ" },
    "freshness_score":         { "type": "number", "minimum": 0, "maximum": 1, "description": "1.0 - (data_age_hours / 24)" },
    "integrity_score":         { "type": "number", "minimum": 0, "maximum": 1, "description": "SHA256 checksum match rate" },
    "delay_score":             { "type": "number", "minimum": 0, "maximum": 1, "description": "Điểm phạt nếu CUR bị trễ > 12h" },
    "is_forced_dry_run":       { "type": "boolean", "description": "true nếu forced into DRY-RUN → map sang API response is_dry_run" }
  },
  "required": ["completeness_score", "is_forced_dry_run"]
}
```

> **WHY forced DRY-RUN**: Nếu AI Engine detect trên dữ liệu thiếu → sinh False Positive → trigger auto-containment sai → tắt resource production → outage. Forced dry-run là safety net (reference: 01_requirements.md §4 Constraints — NEVER terminate prod). AI Engine sẽ trả về `is_dry_run: true` trong API response để thông báo trạng thái này cho CDO Platform.

---

## 14. Quota Telemetry Contract

Hệ thống can thiệp `quota-cap` cần biết headroom trước khi áp trần.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "QuotaSignals",
  "description": "CDO gọi AWS Service Quotas API → aggregate → gửi kèm batch",
  "type": "object",
  "properties": {
    "service_code":    { "type": "string", "description": "e.g. AmazonEC2, AmazonSageMaker" },
    "current_quota":   { "type": "number", "minimum": 0, "description": "AWS Service Quotas current limit" },
    "current_usage":   { "type": "number", "minimum": 0, "description": "Actual usage hiện tại" },
    "utilization_pct": { "type": "number", "minimum": 0, "maximum": 100, "description": "(usage / quota) × 100" },
    "headroom_pct":    { "type": "number", "minimum": 0, "maximum": 100, "description": "100 - utilization_pct" }
  },
  "required": ["service_code", "current_quota", "current_usage", "utilization_pct", "headroom_pct"]
}
```

---

## 15. Human Feedback Contract — Active Learning Loop

Continual Learning: SRE/Engineer xác nhận qua Slack → AI cập nhật pattern memory.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "HumanFeedback",
  "description": "CDO/SRE gửi qua POST /v1/feedback — AI Engine dùng để calibrate detection",
  "type": "object",
  "properties": {
    "anomaly_id": {
      "type": "string",
      "pattern": "^ANM-[0-9]{4}-[0-9]{4}[A-Z]$",
      "description": "Format: ANM-YYYY-MMDD[A-Z] (khớp API Contract §5.2)"
    },
    "reviewer_id":  { "type": "string", "description": "Email hoặc Slack User ID" },
    "verdict":      { "type": "string", "enum": ["TRUE_POSITIVE", "FALSE_POSITIVE", "BENIGN_EVENT"] },
    "reason":       { "type": "string", "description": "Giải trình lý do đánh giá" },
    "reviewed_at":  { "type": "string", "format": "date-time" }
  },
  "required": ["anomaly_id", "reviewer_id", "verdict", "reason", "reviewed_at"]
}
```

> **WHY feedback loop**: Dataset TF2 chỉ có 3 nhãn mẫu (mentor giữ đáp án). Feedback loop cho phép hệ thống calibrate sau deployment từ phản hồi thực tế (reference: Arize AI observability patterns).

---

## 16. Audit Chain — Tamper-evident Integrity

Chuỗi hash bảo vệ tính toàn vẹn kiểm toán. Audit trail lưu ≥90 ngày (reference: 01_requirements.md §4).

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AuditChain",
  "description": "AI Engine tự generate — append-only chain. CDO không cần gửi",
  "type": "object",
  "properties": {
    "audit_id":       { "type": "string", "format": "uuid" },
    "event_hash":     { "type": "string", "pattern": "^[a-f0-9]{64}$", "description": "sha256(current_payload + previous_hash)" },
    "previous_hash":  { "type": "string", "pattern": "^[a-f0-9]{64}$", "description": "Hash bản ghi trước đó (append-only chain)" },
    "signature":      { "type": "string", "description": "Chữ ký KMS" },
    "retention_days": { "type": "integer", "default": 90 }
  },
  "required": ["audit_id", "event_hash", "previous_hash", "signature"]
}
```

---

## 17. Prometheus PromQL Queries — AI Engine Runtime Metrics

AI Engine expose metrics qua `/metrics` endpoint (OpenTelemetry Prometheus exporter, port 9090). CDO/SRE dùng các PromQL queries sau để giám sát runtime:

### 17.1 Request Throughput & Latency

```promql
# Tổng số request/phút theo endpoint
rate(http_server_requests_total{service="ai-engine"}[5m])

# P99 latency cho detection endpoint (phải < 30s)
histogram_quantile(0.99, rate(http_server_request_duration_seconds_bucket{service="ai-engine", endpoint="/v1/detect"}[5m]))

# P95 latency cho result query (phải < 10ms)
histogram_quantile(0.95, rate(http_server_request_duration_seconds_bucket{service="ai-engine", endpoint="/v1/detect/result"}[5m]))
```

### 17.2 Error Rate & Availability

```promql
# Error rate (phải < 0.5%)
rate(http_server_requests_total{service="ai-engine", status=~"5.."}[5m])
  /
rate(http_server_requests_total{service="ai-engine"}[5m])

# Availability SLI (phải >= 99.5%)
1 - (
  sum(rate(http_server_requests_total{service="ai-engine", status=~"5.."}[30m]))
  /
  sum(rate(http_server_requests_total{service="ai-engine"}[30m]))
)
```

### 17.3 AI Model Performance

```promql
# Bedrock inference latency P99 (phải < 10s, nếu > 10s → fallback)
histogram_quantile(0.99, rate(ai_model_inference_duration_seconds_bucket{service="ai-engine", model="nova-pro"}[5m]))

# Model fallback rate (bao nhiêu % request phải fallback)
rate(ai_model_fallback_total{service="ai-engine"}[1h])
  /
rate(ai_model_inference_total{service="ai-engine"}[1h])

# Token usage per day (budget guardrail: < 500K tokens/day)
sum(increase(ai_model_tokens_total{service="ai-engine"}[24h]))
```

### 17.4 Telemetry Quality

```promql
# Completeness score trung bình (phải > 0.8, nếu < 0.8 → forced DRY-RUN)
avg(ai_telemetry_completeness_score{service="ai-engine"})

# Forced dry-run rate (phải = 0% trong điều kiện bình thường)
rate(ai_detection_forced_dry_run_total{service="ai-engine"}[24h])

# Data freshness — latency từ source → ingestion
histogram_quantile(0.99, rate(ai_telemetry_ingestion_delay_seconds_bucket{service="ai-engine"}[1h]))
```

### 17.5 Detection & Containment

```promql
# Anomalies detected per day
sum(increase(ai_anomalies_detected_total{service="ai-engine"}[24h]))

# Containment success rate (phải > 95%)
sum(rate(ai_containment_success_total{service="ai-engine"}[7d]))
  /
sum(rate(ai_containment_triggered_total{service="ai-engine"}[7d]))

# False positive rate (target ≤ 10% — track qua human feedback)
sum(increase(ai_feedback_total{service="ai-engine", verdict="FALSE_POSITIVE"}[30d]))
  /
sum(increase(ai_feedback_total{service="ai-engine"}[30d]))
```

### 17.6 ECS Container Health

```promql
# CPU utilization per task (scale-up trigger: > 70%)
avg(aws_ecs_cpu_utilization{cluster="tf-2-aiops-cluster", service="ai-engine"}) by (task_id)

# Memory utilization per task
avg(aws_ecs_memory_utilization{cluster="tf-2-aiops-cluster", service="ai-engine"}) by (task_id)

# Running task count (min=2, max=10)
aws_ecs_running_task_count{cluster="tf-2-aiops-cluster", service="ai-engine"}
```

---

## 18. Cross-cutting Requirements

Mọi signal payload phải comply các quy tắc sau:

| Requirement | Rule | Enforcement |
|---|---|---|
| **Tenant scoping** | Mọi payload bắt buộc có `tenant_id` | AI Engine reject payload thiếu `tenant_id` → `400 ERR_INVALID_SCHEMA` |
| **Time precision** | Timestamp RFC3339 UTC, millisecond precision | Schema validation |
| **Schema validation** | AI ingestion layer validate JSON schema | Reject malformed → log to DLQ |
| **PII** | KHÔNG được chứa PII (email/phone/name) | CDO anonymize tại ingestion layer |
| **Metric units** | cost=USD, cpu=percent, memory=MiB, network=bytes, latency=ms | Tường minh trong schema |
| **Data classification** | `pii_present: false`, `sensitivity_level: internal` | CDO enforce at ingestion |

---

## 19. Telemetry Outage Recovery Matrix

| Kịch bản | Detection | Hành vi AI Engine |
|---|---|---|
| CUR trễ (chưa cập nhật S3) | CDO gửi `telemetry_delay_event = true` | Tạm hoãn batch. Kiểm tra lại mỗi 1h. Max 4 retries → alert P1. |
| Mất CloudWatch Metrics | `cloudwatch_status: MISSING` | AI chạy CUR-only detection. `confidence *= 0.5`. Containment = Dry-run/Alert-only. |
| Pipeline CDO sập hoàn toàn | Sau 26h không nhận dữ liệu | AI phát cảnh báo P1 đỏ tới Slack cả hai nhóm. |
| Dữ liệu ước tính (`is_estimated`) | `is_estimated = true` | AI giảm `confidence_score`. Không kích hoạt auto-containment. |
| Cost Explorer rate limit | `cost_explorer_status: STALE` | CDO serve từ DynamoDB cache. AI ghi nhận `stale_data_used: true`. |

---

## Open Questions (Resolved)

- [x] **Q1**: Signal nào cần exactly-once delivery?
  - *Resolved*: At-least-once OK cho tất cả. Idempotency Key xử lý dedup. Exactly-once phức tạp không cần thiết cho batch 24h.

- [x] **Q2**: Encryption ngoài TLS chuẩn?
  - *Resolved*: TLS 1.3 in-transit đủ. At-rest dùng AWS KMS (DynamoDB + S3). Không cần end-to-end encryption bổ sung.

---
