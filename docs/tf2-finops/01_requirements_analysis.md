# Requirements Analysis - Task Force 2 - CDO06

<!-- Chủ tài liệu: CDO06
     Trạng thái: Draft W11 Pack #1, cập nhật sau khi contract AI-CDO được freeze
     Phạm vi: Yêu cầu hạ tầng/platform cho TF2 FinOps Watch, căn theo thiết kế 02_infra_design_vi.md -->

## 1. Context and Problem Statement

Task Force 2 xây dựng **FinOps Watch system** cho CFO của một công ty mid-size đang vận hành nhiều AWS account. Tháng trước AWS bill tăng 2.3 lần, từ baseline khoảng 180k USD lên 420k USD. Finance mất gần một tuần mới truy ra nguyên nhân: một training cluster bị quên tắt, đốt khoảng 400 USD/ngày trong 18 ngày.

Vấn đề khách hàng cần giải quyết không phải là forecasting, billing platform hay RI/Savings Plans recommendation engine. Khách hàng cần một hệ thống guardrail chạy liên tục theo chu kỳ rõ ràng để nạp dữ liệu chi phí, phát hiện bất thường, cảnh báo đúng người, và kích hoạt containment an toàn khi pattern đủ rõ như idle resource, mis-tagged spend hoặc runaway training.

Từ góc nhìn CDO06, platform cần đóng vai trò **FinOps control plane dạng lakehouse-centric** trên AWS. CDO sở hữu ingestion pipeline, data lakehouse, orchestration, idempotency, dashboard materialization, alert routing, containment guardrails, observability và audit evidence. AIOps sở hữu AI Engine, logic phát hiện bất thường, model version, confidence score, explanation và backtest metric.

## 2. Business Goals and Success Criteria

| Mục tiêu | Tiêu chí thành công | Owner |
|---|---|---|
| Phát hiện bất thường chi phí sớm hơn quy trình manual | Backtest 3 tháng đạt precision >= 80% và false positive <= 10% | AIOps + CDO |
| Cho Finance đọc được tình hình cost mà không cần SQL | Dashboard có spend trend, anomaly overlay, confidence, owner/action và audit link | CDO |
| Cảnh báo đúng người | Alert routing tách Finance và Engineering, dựa trên anomaly type, severity, owner tag và account/environment | CDO |
| Tự động hóa containment an toàn | >=1 containment pattern implemented, >=2 designed, tất cả có dry-run và rollback path | CDO |
| Chứng minh được vận hành end-to-end | Demo synthetic anomaly inject -> detect -> alert -> containment -> audit evidence | AIOps + CDO |

## 3. Scope

### 3.1 In Scope

- AWS-only platform trong region mặc định `ap-southeast-1`.
- Scheduled batch workflow với cadence mặc định **24h**.
- Synthetic cost data là nguồn chính nếu không có quyền truy cập hóa đơn AWS thật.
- Hỗ trợ nguồn dữ liệu AWS Data Exports/CUR 2.0 hoặc CUR files trong S3, kết hợp Cost Explorer API để đối chiếu/tóm tắt.
- Lakehouse gồm S3 raw zone, S3 curated zone, Glue Data Catalog và Athena views.
- Orchestration bằng EventBridge Scheduler và Step Functions Standard.
- Lambda adapters/workers cho cost pull, normalization, AI contract client, routing policy và containment policy.
- DynamoDB cho run state, idempotency key, anomaly records, routing status, containment audit index và dashboard materialized views.
- Tích hợp AI Engine do AIOps sở hữu qua endpoint hoặc queue contract được version hóa.
- Dashboard Finance-friendly bằng QuickSight hoặc dashboard nội bộ nhẹ.
- Alert routing tối thiểu cho Finance và Engineering qua SNS/email/Slack/ticket tùy contract cuối.
- Audit evidence append-only trên S3, retention tối thiểu 90 ngày.

### 3.2 Out of Scope

- Multi-cloud.
- Multi-region active-active; single-region demo, DR design-only.
- Real-time sub-second streaming detection.
- Forecasting future cost hoặc budget planning 3 tháng.
- RI/Savings Plans recommendation engine, trừ right-sizing suggestion nhẹ.
- Auto-trade RI/Savings Plans.
- Cost showback/chargeback billing platform.
- Self-service tenant onboarding UI.
- Auto-retrain pipeline cho AI model.
- Auto-act destructive trên production.
- Delete data, terminate prod resource, modify IAM.
- Integration CloudHealth, Apptio, Vantage.
- Multi-currency; scope chỉ USD.

## 4. Hard Requirements

| Yêu cầu | Mục tiêu | Ghi chú |
|---|---:|---|
| Precision | >= 80% | AIOps cung cấp backtest, CDO lưu evidence tích hợp |
| False positive rate | <= 10% | Cần confusion matrix và per-anomaly-type breakdown |
| Cadence | 12h, 24h hoặc 48h | CDO06 chọn 24h và defend trade-off |
| Data source | CUR/Data Exports + Cost Explorer API, synthetic nếu cần | CDO pull theo cadence, không phải telemetry realtime |
| Idempotency | 100% duplicate run không xử lý lại | Dùng DynamoDB conditional write |
| Dashboard | Finance-readable | Không yêu cầu Finance biết SQL |
| Alert routing | >=2 routes | Finance route và Engineering route |
| Containment implemented | >=1 pattern | Có dry-run mode |
| Containment designed | >=2 patterns | Có boundary, approval và rollback path |
| Production safety | 3 NEVER | Never terminate prod, never delete data, never modify IAM |
| Audit retention | >=90 ngày | Audit mọi proposal/action containment |

## 5. Non-functional Requirements

| NFR | Target | Justification |
|---|---|---|
| Availability | >= 99.5% cho scheduled workflow và dashboard | Đủ tin cậy cho guardrail vận hành liên tục |
| Batch cadence | 24h mặc định | Cân bằng CUR/CE lag, chi phí vận hành và false positive risk |
| Batch run success rate | >= 95% trong demo/test window | Chứng minh workflow có retry, trạng thái lỗi và evidence |
| AI timeout behavior | Retry lỗi tạm thời, circuit breaker khi lỗi lặp lại | AI unavailable thì CDO fail closed cho containment |
| Error rate | < 0.5% cho request đã validate | Giữ độ tin cậy của alert và audit evidence |
| Idempotency | Duplicate run không gọi AI, không alert, không containment | Tránh double-run cùng cost period |
| Auditability | Append-only evidence, retention >=90 ngày | Phục vụ compliance, mentor review và rollback |
| Tenant/account isolation | Không leak dữ liệu giữa account/tenant | Phù hợp bối cảnh multi-account AWS |
| Cost control | Low fixed cost, serverless/managed-first | Hợp capstone 2 tuần và workload batch |
| Observability | CloudWatch logs, metrics, alarms cho workflow/API/dashboard stale | Phát hiện lỗi vận hành và chứng minh SLO |

## 6. Differentiation Angle

**Angle chọn:** Lakehouse-centric scheduled FinOps control plane.

CDO06 không chọn hướng cluster-heavy hoặc realtime streaming vì đề TF2 là bài toán FinOps batch theo cadence, dữ liệu cost có độ trễ tự nhiên, và khách hàng cần guardrail/auditability hơn là xử lý sub-second. Hướng lakehouse-centric đặt S3, Glue, Athena và DynamoDB làm nền tảng bằng chứng; EventBridge, Step Functions và Lambda điều phối workflow; QuickSight hoặc dashboard nội bộ phục vụ Finance.

Lý do lựa chọn:

- **Auditability:** raw cost data, curated data, AI decisions, routing và containment evidence đều có thể lưu bền vững và truy vấn lại.
- **Cost efficiency:** compute chỉ chạy theo scheduled batch, giảm chi phí cố định so với EKS/ECS always-on.
- **Operational clarity:** Step Functions cho thấy từng bước pull, normalize, call AI, route alert, containment và audit.
- **Finance readability:** Athena views và dashboard materialized views phục vụ dashboard mà Finance không cần đọc raw CUR.
- **Safe automation:** DynamoDB run state + audit append-only + policy worker giúp containment có kiểm soát.

Trade-off chấp nhận:

- Không tối ưu cho realtime sub-second anomaly detection.
- 24h phát hiện chậm hơn 12h, nhưng giảm nhiễu và phù hợp hơn với CUR/Cost Explorer lag.
- Lambda phù hợp tác vụ ngắn; nếu AI contract yêu cầu kết nối dài hoặc batch nặng, ECS Fargate chỉ là fallback, không phải default.

## 7. Comparison with Other CDO Angles

Mục này sẽ được cập nhật sau khi có tài liệu thiết kế chính thức từ CDO còn lại trong cùng Task Force. Ở thời điểm hiện tại, CDO06 chỉ khóa rõ angle của nhóm mình là **lakehouse-centric scheduled FinOps control plane**; không giả định chi tiết compute, storage hay trade-off của nhóm khác khi chưa có evidence.

Bảng so sánh tạm thời:

| Aspect | CDO06 hiện tại | CDO khác | Ghi chú cần cập nhật |
|---|---|---|---|
| Architecture angle | Lakehouse-centric scheduled FinOps control plane | TBD | Chờ docs thiết kế từ CDO khác |
| Compute pattern | EventBridge + Step Functions + Lambda | TBD | So sánh sau theo service thực tế họ chọn |
| Storage/query | S3 raw/curated + Glue + Athena + DynamoDB | TBD | Cần xem họ dùng lakehouse, database, warehouse hay cluster storage |
| Cost profile | Low fixed cost, pay-per-use/managed-first | TBD | Cần estimate hoặc measured cost từ mỗi nhóm |
| Ops complexity | Managed-first, ít vận hành server/cluster | TBD | So sánh dựa trên CI/CD, observability, rollback, failure handling |
| Audit evidence | S3 append-only evidence + DynamoDB audit index | TBD | Cần xem audit trail và retention design của nhóm khác |
| Win axis dự kiến | Auditability, cost efficiency, Finance-friendly analytics | TBD | Chỉ chốt final sau khi có docs của CDO khác |

## 8. AI-CDO Dependency Analysis

CDO06 có thể build lakehouse, orchestration, idempotency, dashboard skeleton và containment policy trước. Tuy nhiên các điểm sau cần AIOps chốt để tránh contract mismatch:

| Dependency từ AIOps | Vì sao CDO cần | Deadline mong muốn |
|---|---|---|
| AI Engine contract là endpoint hay queue | Quyết định Lambda AI client, timeout, retry và network/auth | W11 T5 |
| Input schema | CDO map CUR/CE/synthetic data sang payload hoặc `data_location` đúng format | W11 T4 |
| Response schema | CDO cần severity, confidence, anomaly type, routing target, suggested action, model version | W11 T4 |
| Anomaly definition | Quyết định synthetic anomaly, dashboard label và containment policy | W11 T4 |
| Cadence compatibility | Xác nhận 24h có phù hợp backtest/model hay không | W11 T4-T5 |
| Auth/network | CDO cần IAM role, secret, allowlist hoặc queue permission | W11 T5 |
| Backtest/eval output | CDO cần precision, FP, confusion matrix, per-anomaly-type evidence | W12 T3-T4 |

Nếu AI Engine không khả dụng, CDO workflow phải **fail closed** cho containment: lưu trạng thái `ai_unavailable`, cảnh báo operator, không tự động apply action mới, và vẫn ghi audit evidence.

## 9. Data Requirements

Một bản ghi cost sau khi chuẩn hóa cần tối thiểu các trường sau:

| Trường | Bắt buộc | Ghi chú |
|---|---|---|
| `tenant_id` hoặc `account_scope` | Có | Nhóm tenant/account logic cho demo multi-account |
| `account_id` hoặc `linked_account` | Có | AWS account scope |
| `service` | Có | AWS service name |
| `region` | Có | Region cụ thể hoặc `global` |
| `usage_type` | Có | Giúp giải thích anomaly |
| `cost_amount` | Có | Decimal, đơn vị USD |
| `currency` | Có | Bắt buộc USD |
| `tags` hoặc `owner_metadata` | Có | Dùng cho owner routing và containment policy |
| `environment` | Có nếu xác định được | Prod/staging/dev/sandbox quyết định boundary |
| `cost_period_start` / `cost_period_end` | Có | Dùng cho cadence và idempotency |
| `source` | Có | CUR, Data Exports, Cost Explorer hoặc synthetic |
| `source_data_version` | Có | ETag/manifest/synthetic dataset version để chống trùng |
| `ingested_at` | Có | Audit/debug |

Quy tắc dữ liệu:

- Raw data lưu ở S3 raw zone và không sửa trực tiếp.
- Normalized data lưu ở S3 curated zone, có schema version.
- Athena/Glue phục vụ query và dashboard.
- DynamoDB không thay thế data lake; chỉ lưu run state, metadata, anomaly/routing/containment records và dashboard materialized views.
- Malformed records đi vào dead-letter path hoặc failed validation evidence.
- Không gửi PII sang AI Engine.

## 10. Safe Containment Boundary

Containment là guardrail có kiểm soát, không phải auto-remediation tự do. Boundary production là tuyệt đối:

- Không bao giờ terminate prod.
- Không bao giờ delete data.
- Không bao giờ modify IAM.
- Prod chỉ được tag, suggest, alert hoặc dry-run nếu chưa có phê duyệt rõ ràng.

Containment patterns:

| Pattern | Trạng thái | Phạm vi | Ghi chú |
|---|---|---|---|
| Tag-for-review | Implemented design pattern | Dev, sandbox, staging; prod chỉ tag/suggest/dry-run | Gắn hoặc đề xuất tag như `FinOpsWatch=ReviewRequired` kèm anomaly context |
| Schedule shutdown | Designed pattern | Dev/sandbox sau approval | Không terminate resource; rollback bằng gỡ lịch tắt |
| Quota cap | Designed pattern | Dev/sandbox sau approval | Không sửa IAM; chỉ dùng cơ chế quota/budget guardrail đã được duyệt |

Mọi containment proposal/action phải ghi `actor`, `timestamp`, `correlation_id`, `idempotency_key`, `anomaly_id`, owner, before state, proposed/applied after state, execution mode, rollback path, approval status, evidence URI và retention policy.

## 11. Constraints and Assumptions

| Loại | Giả định/ràng buộc | Ý nghĩa với thiết kế |
|---|---|---|
| Cloud | AWS only | Không thiết kế multi-cloud |
| Region | `ap-southeast-1` mặc định | Infra design, logs, S3, Athena, Lambda cùng region demo |
| Dataset | Synthetic-first nếu không có real billing access | Cần synthetic seed có version ổn định |
| Currency | USD only | Reject hoặc normalize ngoài USD nằm ngoài scope |
| Cadence | 24h baseline | ADR cần defend trade-off 12h/24h/48h |
| Runtime | Scheduled batch | Không xây realtime streaming sub-second |
| AI ownership | AIOps-owned AI Engine | CDO chỉ consume contract và lưu evidence tích hợp |
| Dashboard | Finance-first | Tránh technical dump, không yêu cầu SQL |
| Audit | >=90 ngày | S3 append-only evidence và query/index phục vụ review |
| Code freeze | W12 trước final pitch | Docs/infra/evidence phải ổn định trước demo |

## 12. Risks and Mitigation

| Rủi ro | Tác động | Hướng giảm thiểu |
|---|---|---|
| AI contract đổi muộn | CDO integration vỡ | Freeze contract W11 T5, giữ AI client adapter và contract version |
| Không có CUR/CE thật | Không demo được real cost | Dùng synthetic dataset cùng normalized schema và source_data_version |
| CUR/Data Exports trễ | Batch thiếu data | Retry, ghi run status, không containment khi data confidence thấp |
| Cost Explorer throttling | Pull summary lỗi | Backoff có giới hạn, ưu tiên CUR/synthetic evidence khi đủ |
| AI Engine timeout/unavailable | Không có decision | Retry transient, circuit breaker, fail closed containment |
| Duplicate scheduled run | Double alert/action | DynamoDB conditional write cho idempotency key |
| Dashboard stale | Finance đọc dữ liệu cũ | Dashboard refresh status + CloudWatch alarm |
| Containment bị xem là nguy hiểm | Mentor/client reject automation | Dry-run-first, prod boundary, approval gate và audit rollback |
| Audit write fail | Mất bằng chứng | Fail closed, không apply containment nếu không ghi được audit |

## 13. Open Questions

- [ ] AIOps: AI Engine contract cuối là endpoint hay queue, auth method là gì?
- [ ] AIOps: Response schema cuối gồm những field nào cho severity, confidence, explanation, routing target và suggested action?
- [ ] AIOps + CDO: Cadence 24h có được chấp nhận cho model/backtest không?
- [ ] Mentor/client: Synthetic dataset versioning format chính thức là gì?
- [ ] Mentor/client: Mapping owner/squad/account/environment được cung cấp ở đâu?
- [ ] Mentor/client: Dev/sandbox containment apply có cần human approval không, ai approve?
- [ ] CDO: Dashboard chọn QuickSight hay dashboard nội bộ nhẹ cho evidence nhanh nhất?
- [ ] CDO: Alert destination cuối cho Finance và Engineering là email, Slack, SNS hay ticket?

