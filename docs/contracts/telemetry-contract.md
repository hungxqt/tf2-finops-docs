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

```yaml
schema:
  version: "3.0.0"
  schema_url: "telemetry://finops-watch/v3"
  compatibility:
    backward: true                   # CDO upgrade pipeline trước AI — OK
    deprecation_window_days: 30      # Hỗ trợ version cũ song song 30 ngày
    action_on_expiry: reject_request # Từ chối payload version cũ sau grace period
  change_request_process:
    channel: "Task Force WhatsApp + Meeting"
    approval: "AI Lead + CDO Leads đồng thuận"
    bump_rule: "Breaking change → version major. Add field → minor."
```

> **WHY backward compatibility**: CDO-01 và CDO-02 có thể deploy pipeline khác nhau. Nếu không backward-compatible, AI Engine buộc phải hỗ trợ 2 schema cùng lúc — phức tạp không cần thiết (reference: ADR-003).

---

## 3. Request Integrity Layer

Bảo vệ chống giả mạo payload (anti-tampering) và chống tấn công phát lại (anti-replay). Khớp với `X-Payload-SHA256` và `X-Request-Timestamp` đã define trong ai-api-contract.md §4.

```yaml
request_integrity:
  payload_sha256: string          # SHA256 hash của JSON body — verify integrity
  request_timestamp: rfc3339      # Thời điểm CDO tạo request (UTC ISO 8601)
  signature_verified: bool        # true nếu AWS IAM SigV4 hợp lệ
  replay_window_seconds: 300      # Cửa sổ chấp nhận: 5 phút
```

**Rule**: Nếu `abs(now - request_timestamp) > 300s` → Reject `400 Bad Request` + log `ERR_REPLAY_DETECTED`.

> **WHY 300s**: Tradeoff giữa độ trễ CDO pipeline (~30s bình thường) và cửa sổ tấn công replay. 5 phút đủ headroom cho network jitter mà không mở quá rộng cho replay attack.

---

## 4. Tenant Context & Idempotency

Khớp 1:1 với `X-Tenant-Id` và `X-Idempotency-Key` trong ai-api-contract.md §4.

```yaml
tenant_context:
  tenant_id: uuid_v4              # Linked Account ID ánh xạ → UUID
  account_id: string              # AWS Linked Account ID (e.g. 200000000012)
  account_name: string            # e.g. prod-core, staging, ml-research
  correlation_id: uuid_v4         # Trace ID xuyên suốt E2E request chain
  idempotency_key: string         # Format: tenant_id:YYYY-MM-DD (reference: API Contract §4)
  ttl_expiry: rfc3339             # Hết hạn sau 24h trong DynamoDB
```

**Idempotency Rules** (khớp API Contract §4 quy tắc nâng cao):
- Trùng key + cùng hash → `200 OK` kèm kết quả cũ
- Trùng key + khác hash → `400 ERR_IDEMPOTENCY_MISMATCH`
- Trùng key + đang chạy → `409 Conflict`

> **WHY composite key**: `tenant_id:YYYY-MM-DD` đảm bảo mỗi tenant chỉ có 1 batch/ngày. `is_ad_hoc = true` bypass key này cho quét khẩn cấp (tối đa 5 lần/ngày — xem Deployment Contract §7).

---

## 5. Hybrid Ingestion Contract

Giải quyết giới hạn **10MB** của API Gateway/ALB. Khớp với `data_source_type` trong ai-api-contract.md §5.1.

```yaml
hybrid_ingestion:
  data_source_type:
    enum: [RAW_JSON, S3_POINTER]
  raw_json_max_size_mb: 10
  s3_config:
    allowed_buckets: [company-cdo-telemetry]
    allowed_extensions: [.json.gz]
    max_object_size_mb: 500
    checksum_required: true        # SHA256 verification trước khi extract
    encryption: aws-kms
```

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

**Schema bắt buộc** (6 cột, khớp API Contract `aws_cost_explorer_daily`):

```yaml
cost_explorer_signals:
  unblended_cost: float           # Chi phí ngày hiện tại (USD)
  service_code: string            # Mã ngắn CUR: AmazonEC2, AmazonRDS
  service: string                 # Tên hiển thị CE: "Amazon Elastic Compute Cloud - Compute"
  region: string                  # e.g. us-east-1, ap-southeast-1
  cost_ratio_to_7d_avg: float     # (unblended_cost / rolling_7d_avg)
  day_of_week: int                # 0-6 (Mon-Sun)
  is_weekend: bool                # Derived from day_of_week
  is_estimated: bool              # true cho 2 ngày cuối (CE chưa final)
```

> [!WARNING]
> **Naming Mismatch (đã verify với AWS thật)**: CUR dùng `service_code` (e.g. `AmazonEC2`), Cost Explorer dùng `service` (e.g. `Amazon Elastic Compute Cloud - Compute`). CDO **bắt buộc** cung cấp **cả hai trường** để tránh lỗi khi join dữ liệu — đây là cái bẫy thật ngoài production (reference: TF2 Dataset README line 79).

> [!IMPORTANT]
> **Dữ liệu ước tính**: Khi `is_estimated = true` ở 2 ngày gần nhất, AI Engine **PHẢI** hạ confidence score và **KHÔNG** kích hoạt auto-containment. CDO gửi kèm `telemetry_delay_event = true` khi CUR chưa finalized → AI Engine tạm hoãn batch, kiểm tra lại mỗi 1h (reference: 01_requirements.md §7 Q3).

> **WHY cache DynamoDB**: Cost Explorer API rate limit 5 requests/second. CDO cache kết quả vào DynamoDB tránh vượt limit. AI Engine đọc cache khi cần baseline 7d/30d thay vì gọi CE trực tiếp (reference: ADR-003).

---

## 7. Signal 2: `daily_cur_spend_usd` — Micro Layer (Facts)

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

**Schema bắt buộc** (khớp API Contract `aws_cur_line_items`):

```yaml
cur_signals:
  line_item_resource_id: string   # ARN hoặc Instance ID cụ thể
  line_item_usage_type: string    # e.g. BoxUsage:p3.2xlarge
  line_item_usage_amount: float   # Khối lượng hoạt động vật lý
  pricing_unit: string            # e.g. Hrs, GB, Request
  line_item_unblended_cost: float # *** Nguồn sự thật cho detection ***
  line_item_unblended_rate: float # Đơn giá (e.g. $3.06/hr cho p3.2xlarge)
  line_item_operation: string     # e.g. RunInstances, CreateDBInstance
  usage_density_24h: float        # Mật độ chạy liên tục 0.0-1.0 (CDO tự tính)
  resource_tags_user_environment: string  # prod | staging | dev | sandbox | ml-research | data-analytics
  resource_tags_user_owner: string | null
  resource_tags_user_team: string | null       # null/empty = untagged_spend signal
  resource_tags_user_cost_center: string | null
```

**Athena Query tối ưu** (CDO bắt buộc partition + chỉ quét window cần thiết):

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
| **Fallback**: | Nếu CloudWatch không available → AI Engine vẫn chạy CUR-only detection nhưng `confidence *= 0.5` |

```yaml
utilization_signals:
  cpu_percent: float              # CPUUtilization (EC2/RDS/ECS) — avg 24h
  memory_mib: float               # MemoryUtilization (nếu có)
  network_in_bytes: float         # NetworkIn — aggregate 24h
  network_out_bytes: float        # NetworkOut — aggregate 24h
  disk_io_ops: float              # DiskReadOps + DiskWriteOps
  database_connections: int | null # RDS DatabaseConnections — avg 24h
  gpu_utilization: float | null   # GPU Core usage (SageMaker ml-research)
  idle_hours_continuous: int | null # Số giờ liên tục utilization < 5%
```

> **WHY fallback khi mất CloudWatch**: Reliability principle — CUR data là "đủ" để detect, CloudWatch chỉ "tăng confidence". Không block detection vì thiếu metric phụ (reference: 02_solution_design.md §5 Risk mitigation).

---

## 9. Resource Identity Contract

Chuẩn hóa định danh tài nguyên theo OpenTelemetry semantic conventions. Dùng cho multi-tenant routing + RCA drill-down.

```yaml
resource_identity:
  resource_id: string             # line_item_resource_id (ARN hoặc instance ID)
  resource_type: string           # e.g. aws:ec2:instance, aws:rds:db, aws:sagemaker:notebook
  aws_service: string             # line_item_product_code
  account_id: string              # line_item_usage_account_id
  account_name: string            # line_item_usage_account_name
  region: string                  # product_region_code
  environment:
    enum: [prod, staging, dev, sandbox, ml-research, data-analytics]
  owner: string | null            # resource_tags_user_owner
  team: string | null             # resource_tags_user_team
  cost_center: string | null      # resource_tags_user_cost_center
```

---

## 10. Resource Lineage Contract

Truy vết nguồn gốc tài nguyên. Hỗ trợ RCA nhân quả: `Cost spike → deployment abc123 → commit 84fd2a → team-ml`.

```yaml
resource_lineage:
  deployment_id: string | null    # CloudFormation StackId hoặc ECS deployment ID
  git_sha: string | null          # Commit hash tạo tài nguyên
  pipeline_run_id: string | null  # CI/CD pipeline execution ID
  created_by: string | null       # IAM User/Role ARN
  created_at: rfc3339             # CloudTrail CreateTime
  ttl_expiry: rfc3339 | null      # Ngày hết hạn theo kế hoạch
```

> **WHY lineage**: Khi AI Engine phát hiện anomaly, nếu biết `created_by: team-ml, deployment_id: sagemaker-training-job-42`, RCA reasoning sẽ chính xác hơn so với chỉ biết "resource X tốn tiền" (reference: Google Cloud SRE lineage patterns).

---

## 11. Business Context Signals — False Positive Reduction

Loại bỏ **3 bẫy False Positive** trong dataset: flash-sale, migration, load test (reference: TF2 Dataset README §Bẫy FP).

Logic: `cost ↑ + traffic ↑ = normal growth` | `cost ↑ + traffic flat = anomaly`

```yaml
business_context:
  active_users: int               # Concurrent active users (nếu có)
  orders_count: int               # Transaction count
  traffic_volume: float           # Request volume aggregate
  campaign_flag: bool             # true = đang có marketing campaign
  load_test_flag: bool            # true = đang chạy performance test
  migration_flag: bool            # true = đang migration data
```

> **WHY business context**: Dataset TF2 có 3 sự kiện benign trông y anomaly nhưng **hợp lệ**. Detector không có business context sẽ vỡ ngưỡng FP ≤10% (reference: README line 119).

---

## 12. Time Integrity Contract

Bảo vệ quan hệ nhân quả (causality) trong hệ thống phân tán. **Reject nếu clock skew > 10s**.

```yaml
time_integrity:
  source_timestamp: rfc3339       # Thời điểm AWS agent sinh dữ liệu
  collector_timestamp: rfc3339    # Thời điểm CDO Collector thu thập
  ingestion_timestamp: rfc3339    # Thời điểm AI Engine nhận dữ liệu
  clock_skew_ms: int              # abs(ingestion - source)
  max_allowed_skew_ms: 10000     # 10 giây
```

---

## 13. Telemetry Quality Contract

AI Engine tự đánh giá dữ liệu trước khi ra quyết định. **Nếu `completeness_score < 0.8` → AI forced into DRY-RUN.**

```yaml
telemetry_quality:
  cur_status:
    enum: [HEALTHY, DELAYED, MISSING]
  cloudwatch_status:
    enum: [HEALTHY, DEGRADED, MISSING]
  cost_explorer_status:
    enum: [HEALTHY, STALE]
  completeness_score: float       # Tỷ lệ trường bắt buộc có giá trị hợp lệ (0.0-1.0)
  freshness_score: float          # 1.0 - (data_age_hours / 24)
  integrity_score: float          # SHA256 checksum match rate
  delay_score: float              # Điểm phạt nếu CUR bị trễ > 12h
  is_forced_dry_run: bool         # Đánh dấu true nếu forced into DRY-RUN, map sang API response (GET /v1/detect/result/{audit_id})
```

> **WHY forced DRY-RUN**: Nếu AI Engine detect trên dữ liệu thiếu → sinh False Positive → trigger auto-containment sai → tắt resource production → outage. Forced dry-run là safety net (reference: 01_requirements.md §4 Constraints — NEVER terminate prod). AI Engine sẽ trả về `is_dry_run: true` trong API response để thông báo trạng thái này cho CDO Platform.

---

## 14. Quota Telemetry Contract

Hệ thống can thiệp `quota-cap` cần biết headroom trước khi áp trần.

```yaml
quota_signals:
  service_code: string            # e.g. AmazonEC2, AmazonSageMaker
  current_quota: float            # AWS Service Quotas current limit
  current_usage: float            # Actual usage
  utilization_pct: float          # (usage / quota) × 100
  headroom_pct: float             # 100 - utilization_pct
```

---

## 15. Human Feedback Contract — Active Learning Loop

Continual Learning: SRE/Engineer xác nhận qua Slack → AI cập nhật pattern memory.

```yaml
human_feedback:
  anomaly_id: string              # Format: ANM-YYYY-MMDD[A-Z] (khớp API Contract §5.2)
  reviewer_id: string             # Email hoặc Slack User ID
  verdict:
    enum: [TRUE_POSITIVE, FALSE_POSITIVE, BENIGN_EVENT]
  reason: string                  # Giải trình lý do đánh giá
  reviewed_at: rfc3339
```

> **WHY feedback loop**: Dataset TF2 chỉ có 3 nhãn mẫu (mentor giữ đáp án). Feedback loop cho phép hệ thống calibrate sau deployment từ phản hồi thực tế (reference: Arize AI observability patterns).

---

## 16. Audit Chain — Tamper-evident Integrity

Chuỗi hash bảo vệ tính toàn vẹn kiểm toán. Audit trail lưu ≥90 ngày (reference: 01_requirements.md §4).

```yaml
audit_chain:
  audit_id: uuid_v4
  event_hash: string              # sha256(current_payload + previous_hash)
  previous_hash: string           # Hash bản ghi trước đó (append-only chain)
  signature: string               # Chữ ký KMS
  retention_days: 90              # Minimum theo compliance
```

---

## 17. Cross-cutting Requirements

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

## 18. Telemetry Outage Recovery Matrix

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

## Related Documents

- `ai-api-contract.md` — 5 API endpoints specification, Idempotency rules, Response schema.
- `deployment-contract.md` — ECS Fargate compute, Networking, Secrets, Circuit Breaker.
- `docs/01_requirements.md` — Success criteria, hard constraints, retention requirements.
- `docs/02_solution_design.md` — Architecture overview, component breakdown, data flow.
- `docs/03_ai_engine_spec.md` — Model governance, Bedrock Guardrails, Prompt engineering.
- `docs/04_eval_report.md` — Backtest results, failure analysis, curveball impact.
- `docs/05_adrs.md` — Architecture Decision Records (ADR-001 to ADR-005).
