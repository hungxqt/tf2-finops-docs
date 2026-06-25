# FinOps Watch CDO - Tài liệu tổng hợp kiến thức trọng tâm

Tài liệu này là điểm bắt đầu duy nhất để nắm toàn bộ hệ thống Task Force 2 FinOps Watch CDO mà không phải đọc lại tất cả tài liệu mỗi lần. Nội dung được tổng hợp từ client brief, ba integration contracts, bộ tài liệu CDO, ADRs và AWS Component Details tại baseline Git hiện tại.

Khi cần chi tiết hoặc bằng chứng chính xác, quay lại tài liệu nguồn được liên kết ở cuối mỗi phần.

## 1. Bài toán cần giải quyết

Khách hàng là CFO của công ty chạy AWS multi-account, khoảng 80 kỹ sư thuộc 12 squad. Hóa đơn AWS từng tăng từ khoảng 180.000 USD lên 420.000 USD trong một tháng. Một training cluster non-production bị bỏ quên đã tiêu tốn khoảng 400 USD/ngày trong 18 ngày, gây lãng phí khoảng 7.000 USD.

FinOps Watch phải thực hiện vòng lặp:

```text
Thu thập dữ liệu chi phí
→ Chuẩn hóa và kiểm tra chất lượng
→ Phát hiện bất thường
→ Giải thích và định tuyến cảnh báo
→ Đề xuất hoặc thực hiện containment an toàn
→ Xác minh kết quả
→ Lưu bằng chứng kiểm toán
→ Hiển thị cho Finance và Engineering
```

CDO không xây thuật toán AI. CDO xây và vận hành control plane xung quanh AI Engine.

Nguồn: [TF2_FINOPS_LEARNER.md](TF2_FINOPS_LEARNER.md), [01_requirements_analysis.md](docs/tf2-finops/01_requirements_analysis.md).

## 2. Những yêu cầu tuyệt đối không được quên

### 2.1 Hard boundaries

- AWS only, region ví dụ chính là `ap-southeast-1`.
- Chỉ sử dụng synthetic data nếu chưa được cấp quyền truy cập bill thực.
- Cadence chính thức: 24 giờ.
- NEVER terminate prod, NEVER delete data, NEVER modify IAM.
- Production chỉ được `tag`, `suggest` hoặc `dry-run`.
- `dry-run` bắt buộc cho mọi containment path.
- Phải triển khai ít nhất một containment pattern và thiết kế ít nhất hai pattern khác.
- Mọi containment proposal hoặc action phải có audit trail.
- Audit containment phải được lưu ít nhất 90 ngày.
- Dashboard phải Finance-readable và không yêu cầu SQL.
- Demo phải có: inject synthetic anomaly → detect → alert → containment trigger.

### 2.2 Chỉ tiêu AI

Các chỉ tiêu này thuộc AIOps; CDO chỉ lưu và trình bày như integration evidence:

- Precision tối thiểu 80%.
- False-positive rate tối đa 10%.
- Backtest trên ba tháng dữ liệu synthetic historical.
- Phải bắt được ít nhất hai anomaly types.

### 2.3 Audit schema bắt buộc

Mỗi containment action phải truy vết được:

- Actor.
- Timestamp.
- Correlation ID.
- Idempotency key.
- Anomaly ID.
- Resource, account và squad owner.
- Before state.
- Proposed hoặc applied after state.
- Execution mode: `dry-run` hoặc `apply`.
- Rollback path.
- Approval status.
- Retention location và retention period.

## 3. Kiến trúc chính thức cần nhớ

Kiến trúc được chọn là lakehouse-centric FinOps control plane kết hợp serverless orchestration và một AI Engine Lambda container do CDO host.

```text
AWS Member Accounts
├─ CUR/Data Exports trong S3
├─ Cost Explorer API
└─ CloudWatch resource utilization metrics
             │
             ▼
EventBridge Scheduler, cadence 24h
             │
             ▼
Step Functions Standard
├─ State Lambda → S3 idempotency store
├─ Ingestion Lambda → S3 raw
├─ Normalization/Validation Lambda → S3 curated
├─ Glue Data Catalog + Athena
├─ AI Engine Lambda, synchronous direct invoke
├─ Alert Routing Lambda → Finance/Engineering channels
├─ Containment Lambda → policy guardrails
└─ Audit Writer → S3 Object Lock + DynamoDB read cache
             │
             ▼
S3 + CloudFront Finance Dashboard
```

### 3.1 Các quyết định kiến trúc hiện hành

- EventBridge Scheduler kích hoạt Step Functions mỗi 24 giờ.
- AI Engine là một Lambda container duy nhất từ image ECR do AIOps cung cấp.
- Step Functions gọi AI Engine Lambda trực tiếp và đồng bộ.
- Không có Request Lambda/Worker Lambda tách riêng trong baseline mới.
- Không có SQS trong detection path.
- SQS/DLQ chỉ dùng làm retry buffer cho alert routing.
- S3 là authoritative store cho audit và idempotency.
- DynamoDB chỉ là read cache/materialized view cho dashboard và các truy vấn nhanh.
- Dashboard MVP dùng S3 static assets + CloudFront + Cognito/Lambda@Edge authentication.
- Chỉ AI Engine Lambda có Function URL dưới CloudFront `/v1/*` để phục vụ contract operations tương tác.
- State, Ingestion và Containment Lambdas là internal functions, chỉ Step Functions gọi.

Nguồn: [02_infra_design.md](docs/tf2-finops/02_infra_design.md), [ADR-015 đến ADR-018](docs/tf2-finops/08_adrs.md).

## 4. Luồng chạy E2E

### Bước 1 - Trigger

EventBridge Scheduler bắt đầu workflow theo cadence 24 giờ.

### Bước 2 - Idempotency

State Lambda kiểm tra S3 authoritative idempotency store.

Canonical key:

```text
{tenant_id}:{billing_period_date}:{batch_type}
```

Canonical path:

```text
s3://company-cdo-telemetry/idempotency/{idempotency_key}
```

Quy tắc:

- Không có object: tạo lock và tiếp tục.
- Có cùng key, cùng payload hash: duplicate, không xử lý lại.
- Có cùng key nhưng payload hash khác: fail với `ERR_IDEMPOTENCY_MISMATCH`.
- Lock hết hạn sau 24 giờ bằng S3 Lifecycle.
- `is_ad_hoc=true` bypass scheduled key nhưng giới hạn tối đa năm lần mỗi tenant/ngày.

### Bước 3 - Ingestion

Ingestion Lambda:

- Đọc CUR/Data Exports từ S3.
- Gọi Cost Explorer API.
- Thu thập CloudWatch resource utilization metrics.
- Ghi bản raw vào S3 raw zone.
- Cache Cost Explorer response trong DynamoDB để tránh vượt giới hạn 5 requests/second.

### Bước 4 - Normalization và lakehouse

Normalization/Validation Lambda:

- Chuẩn hóa account, service, region, resource, owner, environment, cost center và USD amount.
- Kiểm tra schema và data quality.
- Ghi dữ liệu curated dạng query-efficient, ưu tiên Parquet.
- Glue Data Catalog cung cấp metadata cho Athena.

### Bước 5 - AI detect

Step Functions gọi trực tiếp AI Engine Lambda với logical operation `POST /v1/detect`.

Đây là synchronous invocation. Response chính gồm:

- `success`.
- `correlation_id`.
- `anomalies_detected`.
- `anomalies_list`.
- `error_message` nếu có.

Không dùng `/v1/status/{correlation_id}` để polling detection. `/v1/status/{id}` chỉ dành cho trạng thái remediation hoặc self-healing.

### Bước 6 - Decide

Với từng anomaly, CDO gọi logical `POST /v1/decide` để nhận:

- Root Cause Analysis.
- Confidence và severity.
- Finance dashboard data.
- Engineering technical context.
- Recommended route.
- Recommended containment/action plan.
- Dry-run và rollback payload.

CDO vẫn phải áp policy deterministic trước khi thực thi. Không được tin tưởng mù quáng raw command từ AI.

### Bước 7 - Alert routing

Alert Routing Lambda tách hai đối tượng:

- Finance: spend delta, projected waste, owner, confidence, business impact, trạng thái containment.
- Engineering: resource ID, AWS service, usage pattern, technical RCA, action plan, rollback path.

SQS/DLQ chỉ được sử dụng khi alert delivery thất bại hoặc cần retry/backoff.

### Bước 8 - Containment

Containment Lambda kiểm tra:

- Environment.
- Execution mode.
- Allowlist action.
- Approval requirement.
- Resource ownership.
- Hard boundaries.

Production không được auto-shutdown. Non-production chỉ được apply khi policy cho phép; mọi path vẫn phải hỗ trợ dry-run.

### Bước 9 - Audit trước và sau action

Audit Writer ghi authoritative record vào S3 Object Lock trước khi thực hiện action và cập nhật kết quả sau action. DynamoDB chỉ giữ read cache cho dashboard.

### Bước 10 - Verify và rollback

- `POST /v1/verify`: đánh giá kết quả containment bằng post-action telemetry.
- `GET /v1/status/{id}`: xem trạng thái remediation/self-healing.
- `POST /v1/audit/{audit_id}/rollback`: kích hoạt rollback.

AI unavailable hoặc response sai schema phải fail closed: không apply containment, alert operator và giữ bằng chứng failed run.

## 5. CDO và AIOps sở hữu gì

| Năng lực | CDO | AIOps |
|---|---|---|
| CUR, Cost Explorer, CloudWatch ingestion | Sở hữu | Không sở hữu |
| Data normalization và quality metadata | Sở hữu | Tiêu thụ |
| Scheduling, workflow và idempotency | Sở hữu | Không sở hữu |
| S3 lakehouse, Glue và Athena | Sở hữu | Không sở hữu |
| AI model code và detection logic | Không sở hữu | Sở hữu |
| Model version, confidence calibration và explanation | Lưu evidence | Sở hữu |
| ECR image build, model weights và configs | Kiểm tra/deploy digest | Cung cấp |
| Lambda hosting, VPC, IAM, concurrency và monitoring | Sở hữu | Cung cấp runtime requirements |
| Alert routing | Sở hữu | Chỉ recommend route |
| Containment policy và approval | Sở hữu | Chỉ recommend action |
| IAM role selection và AWS action execution | Sở hữu | Không được tự quyết định |
| Audit evidence và rollback orchestration | Sở hữu | Cung cấp decision metadata |
| Precision/FPR/backtest | Lưu integration evidence | Sở hữu |

Nguyên tắc nhớ nhanh:

```text
AIOps quyết định bằng mô hình.
CDO quyết định liệu kết quả đó có được sử dụng an toàn hay không.
```

## 6. Ba integration contracts

### 6.1 Cost data pull contract

Owner: CDO.

Nguồn:

- CUR/Data Exports trong S3.
- Cost Explorer API.
- CloudWatch resource utilization metrics.

Fields chính:

- Account, service, region và resource ID.
- Owner, environment và cost center.
- Usage date và billing period.
- Cost amount, USD.
- Estimated/final flag.
- Resource utilization metrics.

### 6.2 AI decision output contract

Owner: AIOps.

CDO phải validate, persist evidence và áp policy.

Fields cần chú ý:

- Run/correlation/model version.
- Anomaly ID và type.
- Confidence và severity.
- Expected spend, actual spend và delta.
- Evidence window và explanation.
- Recommended Finance/Engineering route.
- Recommended containment mode.
- Evidence URI.

### 6.3 Alert and containment contract

Owner: CDO.

Fields chính:

- Anomaly ID.
- Route target.
- Approval requirement.
- Action type.
- Execution mode.
- Before/after state.
- Rollback path.
- Audit record ID.

## 7. Telemetry và fallback

Detection input kết hợp:

- CUR resource-level cost facts.
- Cost Explorer daily aggregates.
- CloudWatch metrics: CPU, memory, network, disk, database connections và GPU utilization.

Nếu CloudWatch metrics thiếu:

```text
AI vẫn chạy CUR-only detection
→ confidence *= 0.5
→ containment bị khóa về dry-run/alert-only
```

Các context optional như deployment lineage, business events, migration/load-test marker giúp giảm false positive nhưng không được làm mất core CUR/Cost Explorer path.

## 8. Lakehouse, Athena DDL và Terraform IaC

Quyết định ADR-014:

```text
Athena SQL DDL
→ dùng trong thiết kế và validation schema ban đầu
→ thử với synthetic CUR files

Terraform aws_glue_catalog_table
→ source of truth lâu dài
→ version-controlled và code-reviewed

Athena Partition Projection
→ tự ánh xạ partition
→ không cần Glue Crawler
→ không cần MSCK REPAIR TABLE
→ không cần ALTER TABLE thêm partition thủ công
```

S3 partitioning nên hỗ trợ account, year, month/billing period và các window truy vấn cần thiết. Athena queries phải prune partition và có query scan limits.

## 9. State Lambda hiện phải làm gì

State Lambda là internal CDO Lambda do Step Functions gọi.

Nhiệm vụ:

- Acquire scheduled run lock trong S3.
- Kiểm tra duplicate.
- Kiểm tra payload hash mismatch.
- Quản lý trạng thái `IN_PROGRESS`, `COMPLETED`, `FAILED`, `FAILED_CONTRACT_CHECK` nếu workflow cần.
- Hỗ trợ explicit redrive từ failed state.
- Giới hạn ad-hoc scans.
- Trả idempotency decision cho Step Functions.

Không thuộc State Lambda:

- AI model execution.
- Alert routing.
- Containment execution.
- Audit ledger Object Lock 90 ngày.
- DynamoDB dashboard/read cache.
- Public Function URL.

## 10. S3 và DynamoDB khác nhau như thế nào

### S3 authoritative store

Dùng cho:

- Idempotency locks.
- Audit evidence.
- Decision evidence.
- Durable compliance records.

Audit prefix phải dùng Object Lock và retention ít nhất 90 ngày. Idempotency prefix dùng lifecycle 24 giờ và không phải compliance audit record.

### DynamoDB read cache

Dùng cho:

- Dashboard materialized views.
- Low-latency anomaly/run summaries.
- Cost Explorer response cache.
- Audit indexes và lookup nhanh.

DynamoDB không phải authoritative audit/idempotency source theo ADR-016.

## 11. Security model

### 11.1 IAM

- Least privilege theo từng Lambda.
- Step Functions chỉ được invoke đúng functions.
- Ingestion role chỉ đọc CUR, gọi Cost Explorer và ghi raw data.
- State role chỉ truy cập S3 idempotency prefix.
- Containment role dùng allowlist và explicit deny destructive actions.
- AI Engine role chỉ đọc curated data, gọi dependencies cần thiết và ghi cache/evidence đúng prefix.
- Không dùng IAM User static credentials.
- CI/CD dùng GitHub OIDC assume-role.

### 11.2 Network

- Lambda chạy trong private VPC subnets khi cần.
- Sử dụng VPC endpoints cho S3, DynamoDB, ECR, Logs, KMS và Secrets Manager.
- AI Engine không public trực tiếp; interactive `/v1/*` đi qua CloudFront behavior và lớp authentication.

### 11.3 Encryption

- S3, DynamoDB, secrets và logs được mã hóa at rest.
- TLS cho in-transit.
- Audit bucket dùng KMS và Object Lock.
- S3 Bucket Key được ưu tiên để giảm KMS request cost.

### 11.4 Secret handling

- Secrets Manager là source chính.
- Không bake credentials vào image.
- Không lưu secret trong Git/Terraform plaintext.
- Gitleaks và secret scanning phải block merge.
- Log phải redact token, webhook và dữ liệu nhạy cảm.

## 12. Containment patterns

### Implemented hoặc MVP candidate

`tag-for-review`:

- Gắn tag để đánh dấu resource cần review.
- An toàn trên mọi environment.
- Dễ dry-run, audit và rollback.

### Designed patterns

- `time-gated-countdown`: tag + thông báo owner + countdown trước action.
- `auto-shutdown`: chỉ dev/sandbox/research, không production.
- Application/service-specific concurrency cap.

Lưu ý: `quota-cap` không nên được tuyên bố đã implement nếu chưa có AWS API thật có thể giảm/cap quota và rollback rõ ràng. `RequestServiceQuotaIncrease` không phải API giảm quota.

## 13. Dashboard Finance-friendly

Dashboard phải trả lời bốn câu hỏi:

1. Điều gì đã thay đổi?
2. Account hoặc squad nào sở hữu?
3. Hệ thống tin cậy bao nhiêu?
4. Hành động nào được phép hoặc đã thực hiện?

Views chính:

- Spend trend với anomaly overlay.
- Anomaly detail: severity, confidence, explanation và evidence window.
- Top accounts/services/squads bị ảnh hưởng.
- Containment status và execution mode.
- Link tới audit evidence.

Finance không chạy Athena SQL. Athena tạo summaries ở backend; frontend đọc JSON hoặc DynamoDB materialized records.

## 14. Alert routing

### Finance channel

Nội dung ưu tiên:

- Cost impact và projected waste.
- Account/squad owner.
- Confidence được giải thích bằng ngôn ngữ thường.
- Trạng thái approval và containment.
- Link dashboard/audit.

### Engineering channel

Nội dung ưu tiên:

- Resource ID và service.
- Usage metrics và anomaly type.
- Technical RCA.
- Recommended action.
- Execution mode và rollback path.

Không nhúng raw CUR tables hoặc dữ liệu nhạy cảm trực tiếp trong Slack/email.

## 15. Deployment và CI/CD

### Infrastructure

Terraform quản lý:

- Networking và endpoints.
- S3 buckets và lifecycle/Object Lock.
- Glue/Athena definitions.
- Step Functions và Lambdas.
- IAM roles.
- ECR, concurrency, aliases và alarms.
- DynamoDB caches.

### Pipeline gates

- `terraform fmt` và `terraform validate`.
- TFLint/Checkov hoặc tương đương.
- Trivy image scanning.
- Dependency scanning.
- Gitleaks.
- CRITICAL CVE phải block deployment nếu không có exception được phê duyệt.
- Terraform destructive change review.
- AI contract schema compatibility test.
- ECR image phải pin bằng digest, không dùng mutable tag làm production source.

### Lambda deployment

- Publish version.
- Alias/canary routing.
- Reserved concurrency để giới hạn blast radius.
- Provisioned Concurrency chỉ bật nếu benchmark cho thấy cần thiết.
- Rollback bằng previous image digest/Lambda version.

## 16. Observability và SLO

CDO theo dõi:

- Step Functions success/failure.
- Lambda duration, error, timeout, throttle và cold start.
- Reserved concurrency exhaustion.
- SQS queue depth/age chỉ cho alert routing.
- S3 request/error và stale partition.
- Athena scanned bytes và query failures.
- Dashboard freshness.
- Alert delivery latency.
- Audit write failures.

Targets quan trọng:

- Scheduled run success: mục tiêu 99.9%.
- Platform/AI hosting availability: khoảng 99.5%.
- Dashboard refresh: trong vòng năm phút sau pipeline completion.
- Alert delivery: trong vòng 30 phút sau detection.
- Data freshness: trong 24 giờ từ lúc CUR khả dụng.

Mọi measured value chưa có bằng chứng production phải giữ marker `Evidence needed`.

## 17. Failure handling

| Failure | Hành vi bắt buộc |
|---|---|
| CUR delay | Wait/retry; alert nếu quá 24 giờ |
| Cost Explorer throttling | Exponential backoff + jitter; dùng cache |
| Duplicate run | Abort trước AI call và alert/containment |
| Payload mismatch | `ERR_IDEMPOTENCY_MISMATCH`, block run |
| AI timeout/unavailable | Fail closed, không containment apply, alert operator |
| Invalid AI schema/version | `FAILED_CONTRACT_CHECK`, block workflow |
| Alert delivery failure | SQS retry → DLQ → SES fallback |
| Containment AccessDenied | Audit `DENIED`, alert security |
| Dashboard stale | Alarm nếu partition/summary quá 26 giờ |
| Audit write failure | Không thực hiện containment apply |

## 18. Test strategy

### Unit tests

- Handler validation.
- Idempotency key generation.
- S3 conditional lock.
- Payload mismatch.
- Status transitions/redrive.
- Policy allowlist và dry-run.

### Integration tests

- S3 authoritative writes.
- CUR/Cost Explorer ingestion adapters.
- Glue/Athena partition projection.
- AI contract request/response schemas.
- SQS/DLQ alert retry.
- SNS/SES/Slack routing.

### Contract tests

- `/v1/detect` synchronous response.
- `/v1/decide` action plan.
- `/v1/verify` result.
- `/v1/status/{id}` remediation status.
- Rollback operation.
- `409` duplicate semantics.
- `400 ERR_IDEMPOTENCY_MISMATCH`.
- `403 ERR_CROSS_TENANT_DENIED`.
- Timeout/fallback.

### Security tests

- S3 bucket public access blocked.
- Lambda invocation denied without IAM permission.
- Finance users cannot trigger actions.
- Cognito token expiration/tampering rejected.
- Containment roles cannot modify IAM, delete data hoặc terminate prod.

### E2E demo test

```text
Synthetic CUR anomaly
→ EventBridge trigger
→ State lock
→ Ingestion and normalization
→ synchronous AI detect
→ dashboard update
→ Finance + Engineering alerts
→ dry-run containment
→ S3 audit evidence
→ rollback simulation
```

## 19. Cost model cần hiểu

Chi phí chính:

- Lambda invocations và GB-seconds.
- Step Functions state transitions.
- S3 storage và requests.
- Athena scanned bytes.
- Glue catalog metadata.
- DynamoDB cache reads/writes.
- ECR storage.
- CloudWatch Logs/X-Ray.
- SQS/SNS/SES alerting.
- VPC endpoints, thường là fixed-cost lớn nhất của serverless baseline.
- Bedrock inference, cần budget/circuit breaker riêng.

Cost optimizations:

- S3 lifecycle và partitioning.
- Parquet + Athena partition pruning.
- Athena query limits/cache.
- Glue Partition Projection thay crawler.
- DynamoDB on-demand cho workload không đều.
- Log retention tiering.
- Lambda right-sizing và arm64 khi image hỗ trợ.
- Reserved concurrency.
- Không dùng NAT nếu VPC endpoints đáp ứng được traffic.

Không được coi forecast trong docs là measured actual nếu chưa có AWS evidence.

## 20. ADR map cần nhớ

| ADR | Quyết định | Trạng thái cần hiểu |
|---|---|---|
| ADR-001 | Chọn cadence 24h | Accepted |
| ADR-002 | Lakehouse-centric control plane | Accepted |
| ADR-003 | CDO/AIOps ownership boundary | Accepted |
| ADR-004 | CUR S3 + Cost Explorer API | Accepted |
| ADR-005 | Dry-run-first containment | Accepted |
| ADR-006 | DynamoDB + S3 audit | Partially superseded bởi ADR-016 |
| ADR-007 | ECS Fargate AI hosting | Superseded bởi ADR-010 |
| ADR-008 | Always-on + Spot Fargate | Superseded bởi ADR-010 |
| ADR-009 | Shared AI endpoint | Superseded bởi ADR-010 |
| ADR-010 | Per-CDO Lambda container hosting | Accepted |
| ADR-011 | Private API Gateway | Superseded |
| ADR-012 | Direct Lambda/SQS model cũ | Superseded bởi ADR-018 |
| ADR-013 | S3 + CloudFront dashboard MVP | Accepted |
| ADR-014 | Athena DDL → Terraform Glue + Partition Projection | Accepted |
| ADR-015 | Synchronous detect, bỏ async polling | Accepted |
| ADR-016 | S3 authoritative audit + idempotency | Accepted |
| ADR-017 | Function URLs cho nhiều backend Lambdas | Superseded bởi ADR-018 |
| ADR-018 | Một AI Engine Lambda container duy nhất | Accepted và mới nhất |

Quy tắc đọc ADR: không xóa quyết định cũ; luôn xem `Status` và ADR superseding mới nhất.

## 21. Điểm dễ nhầm và nội dung stale trong docs

Bộ docs hiện có một số đoạn chưa được đồng bộ hoàn toàn. Khi triển khai, ưu tiên ADR mới nhất và Infra Design thay vì các đoạn cũ sau:

1. `AWS_Component_details.md` phần State Lambda vẫn nhắc DynamoDB table và key `account_id:billing_period:execution_date`. Baseline mới là S3 và key `{tenant_id}:{billing_period_date}:{batch_type}`.
2. `AWS_Component_details.md` phần DynamoDB Run State And Audit vẫn mô tả DynamoDB như authoritative state. ADR-016 đã hạ DynamoDB xuống read cache.
3. `NOTES.md` vẫn nói lấy measured run logs từ DynamoDB. Với baseline mới, authoritative run/idempotency evidence nằm trong S3; DynamoDB chỉ có cache nếu triển khai.
4. Telemetry contract có đoạn cũ nói idempotency TTL trong DynamoDB và key `tenant_id:YYYY-MM-DD`. AI API contract và ADR-016 mới hơn sử dụng S3 cùng key tenant/date/batch.
5. Một số test/demo wording còn nhắc async SQS hoặc worker Lambda. ADR-015 và ADR-018 đã loại chúng khỏi AI detection path.
6. ADR-017 đã superseded. Chỉ AI Engine Lambda có Function URL; State Lambda không public.
7. Một số docs nói CloudWatch metrics không gửi cho AI, trong khi requirements và telemetry contract mới yêu cầu hybrid metrics. Baseline sử dụng CloudWatch enrichment với CUR-only fallback.
8. Contract vẫn chứa raw AWS CLI command trong AI output. CDO không nên thực thi trực tiếp; phải validate/mapping qua deterministic allowlist và AWS SDK.

Nếu hai nguồn mâu thuẫn, dùng thứ tự:

```text
Client hard requirements
→ User/client update hiện tại
→ ADR Accepted mới nhất
→ Infra/Security/Deployment Design
→ Contracts mới nhất
→ Component Details/Notes
```

## 22. Demo narrative ngắn để trình bày

"FinOps Watch chạy mỗi 24 giờ. CDO thu thập CUR, Cost Explorer và CloudWatch metrics vào S3 lakehouse, dùng State Lambda tạo S3 idempotency lock để không xử lý trùng. Step Functions gọi AI Engine Lambda do AIOps cung cấp một cách đồng bộ. AIOps trả anomaly, confidence và explanation; CDO chịu trách nhiệm định tuyến Finance/Engineering, áp guardrail, thực hiện dry-run containment và ghi audit evidence vào S3 Object Lock. Production không bao giờ bị terminate, dữ liệu không bị xóa và IAM không bị sửa. Dashboard S3 + CloudFront trình bày spend trend, anomaly, owner, confidence và containment status mà Finance không cần SQL."

## 23. Checklist trước khi nói hệ thống hoàn thành

- [ ] Cadence 24h được cấu hình và giải thích.
- [ ] CUR, Cost Explorer và CloudWatch ingestion hoạt động.
- [ ] S3 raw/curated, Glue và Athena query được.
- [ ] Athena DDL đã được chuyển thành Terraform Glue definitions.
- [ ] S3 idempotency lock chặn duplicate và payload mismatch.
- [ ] AI Engine image được pin bằng ECR digest.
- [ ] Synchronous detect contract test pass.
- [ ] Reserved concurrency và alarms tồn tại.
- [ ] Finance và Engineering routing tách biệt.
- [ ] Dry-run containment hoạt động.
- [ ] Production hard boundaries được enforce bằng policy/IAM.
- [ ] Audit ghi trước và sau containment.
- [ ] S3 Object Lock retention ít nhất 90 ngày.
- [ ] Dashboard Finance-readable và không cần SQL.
- [ ] E2E synthetic demo pass.
- [ ] Không trình bày forecast như measured result.
- [ ] Các `Evidence needed` được giữ nguyên nếu chưa có bằng chứng thật.

## 24. Tài liệu nguồn nên đọc khi cần đào sâu

- Client brief: [TF2_FINOPS_LEARNER.md](TF2_FINOPS_LEARNER.md)
- Requirements: [01_requirements_analysis.md](docs/tf2-finops/01_requirements_analysis.md)
- Infrastructure: [02_infra_design.md](docs/tf2-finops/02_infra_design.md)
- Security: [03_security_design.md](docs/tf2-finops/03_security_design.md)
- Deployment: [04_deployment_design.md](docs/tf2-finops/04_deployment_design.md)
- Cost: [05_cost_analysis.md](docs/tf2-finops/05_cost_analysis.md)
- Dashboard and alerting: [06_dashboard_alerting_design.md](docs/tf2-finops/06_dashboard_alerting_design.md)
- Test and evaluation: [07_test_eval_report.md](docs/tf2-finops/07_test_eval_report.md)
- ADRs: [08_adrs.md](docs/tf2-finops/08_adrs.md)
- Demo pack: [09_demo_and_presentation_pack.md](docs/tf2-finops/09_demo_and_presentation_pack.md)
- AWS components: [AWS_Component_details.md](docs/tf2-finops/AWS_Component_details.md)
- AI API contract: [ai-api-contract.md](docs/contracts/ai-api-contract.md)
- Telemetry contract: [telemetry-contract.md](docs/contracts/telemetry-contract.md)
- Deployment contract: [deployment-contract.md](docs/contracts/deployment-contract.md)
- Implementation hiện tại: [State Lambda README](services/state-lambda/README.md)
