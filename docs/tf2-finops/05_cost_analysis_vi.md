# Phân tích Chi phí (Cost Analysis) - TF2 FinOps Watch CDO06

<!-- Chủ tài liệu: CDO06
     Trạng thái: Draft W11 Pack #1, cập nhật dữ liệu thực tế W12 T4 Pack #2
     Phạm vi: Chi phí nền tảng CDO lakehouse-centric scheduled FinOps control plane -->

## 1. Mô hình Chi phí theo Tenant (Dự báo)

"Tenant" trong ngữ cảnh TF2 FinOps Watch là một AWS member account được giám sát chi phí. Mô hình chi phí dưới đây ước tính cho chu kỳ vận hành 24h với các thành phần serverless-first.

| Thành phần | Đơn giá | Mức sử dụng trung bình/tenant | $/tenant/tháng |
|---|---|---|---|
| **Compute - Lambda** | $0.20/1M requests + $0.0000166667/GB-second | 30 lượt gọi/ngày × 5 functions × 512MB × 30s | $2.50 |
| **Orchestration - Step Functions Standard** | $0.025/1K state transitions | 1 workflow/ngày × 12 states × 30 ngày | $0.09 |
| **Orchestration - EventBridge Scheduler** | $1.00/1M invocations | 1 trigger/ngày × 30 ngày | $0.00 |
| **Storage - S3 Standard (raw/curated)** | $0.023/GB-month | 15 GB CUR data + 10 GB curated | $0.58 |
| **Storage - S3 IA (audit 30-90 days)** | $0.0125/GB-month | 5 GB audit archives | $0.06 |
| **Database - DynamoDB on-demand** | $1.25/million write + $0.25/million read | 100 writes + 500 reads/ngày | $0.48 |
| **Query - Athena** | $5.00/TB scanned | 50 GB scanned/tháng (dashboard + ad-hoc) | $0.25 |
| **Data Catalog - Glue** | $1.00/100K objects stored/month | 10K objects/month | $0.10 |
| **Data transfer - NAT Gateway** | $0.045/GB (outbound AI Engine) | 2 GB/tháng payload + response | $0.09 |
| **VPC Endpoints - Interface Endpoints** | $0.01/hour × 4 endpoints | 720 hours × 4 (KMS, SM, Athena, CloudWatch) | $28.80 |
| **Secrets Manager** | $0.40/secret/month + $0.05/10K API calls | 3 secrets + 1K calls/tháng | $1.25 |
| **KMS** | $1.00/CMK/month + $0.03/10K requests | 3 CMKs + 5K requests/tháng | $3.02 |
| **Observability - CloudWatch Logs** | $0.50/GB ingested + $0.03/GB stored | 5 GB logs/tháng | $2.65 |
| **Observability - CloudWatch Metrics** | $0.30/custom metric/month | 20 custom metrics | $6.00 |
| **Observability - X-Ray** | $5.00/1M traces + $0.50/1M scanned | 50K traces/tháng | $0.28 |
| **Dashboard - QuickSight Reader** | $5.00/reader/month (chia sẻ cho nhiều tenant) | 1/10 reader allocation | $0.50 |
| **Alerting - SNS** | $0.50/1M requests + $2.00/100K email | 60 alerts/tháng (2/ngày) + email | $0.12 |
| **AI Engine integration cost** | *Thuộc về AIOps* | *Out of scope CDO* | $0.00 |
| **Total CDO platform / tenant / tháng** | | | **$46.77** |

**Lưu ý quan trọng**:
- Chi phí trên là ước tính **CDO platform infrastructure** không bao gồm chi phí AI Engine do AIOps sở hữu.
- VPC Interface Endpoints ($28.80) là chi phí cố định lớn nhất; có thể giảm bằng cách consolidate endpoints nếu đạt quy mô.
- Chi phí thực tế sẽ được đo lường trong W12 T4 sau khi chạy synthetic workload 7-10 ngày.

---

## 2. Chi phí theo Quy mô (Cost at Scale)

Khi số lượng tenant tăng, một số chi phí cố định (VPC Endpoints, KMS CMKs, QuickSight) được phân bổ giữa nhiều tenant, giảm chi phí trung bình mỗi tenant.

| Số lượng Tenant | Chi phí cố định/tháng | Chi phí biến đổi/tháng | Tổng chi phí/tháng | Trung bình/tenant |
|---|---|---|---|---|
| **1** | $40.00 | $6.77 | $46.77 | $46.77 |
| **10** | $40.00 | $67.70 | $107.70 | $10.77 |
| **50** | $40.00 | $338.50 | $378.50 | $7.57 |
| **200** | $40.00 | $1,354.00 | $1,394.00 | $6.97 |

**Chi phí cố định bao gồm**:
- 4× VPC Interface Endpoints: $28.80
- 3× KMS CMKs: $3.00
- 1× QuickSight Reader (chia sẻ): $5.00
- CloudWatch Dashboard (chia sẻ): $3.00
- Pipeline CI/CD (CodeDeploy, GitHub Actions): $0.20

**Phân tích**:
- Với 10 tenant, chi phí giảm **77%** so với 1 tenant do phân bổ chi phí cố định.
- Với 50+ tenant, chi phí trung bình ổn định ở ~$7-8/tenant/tháng.
- Điểm hòa vốn (break-even) so với giải pháp thủ công: ~5 tenant (giả sử chi phí thủ công là $50/tenant/tháng cho 8 giờ công phân tích).

---

## 3. Tối ưu hóa Chi phí đã Áp dụng

| Biện pháp tối ưu hóa | Trạng thái | Tiết kiệm ước tính | Ghi chú |
|---|---|---|---|
| **Lambda right-sizing** |  Implemented | 15-20% chi phí compute | Chạy benchmark để chọn 512MB thay vì 1024MB cho các worker |
| **S3 Lifecycle tiering** |  Implemented | 40% chi phí storage | Raw zone: Standard 7 ngày → IA 30 ngày → Glacier 90 ngày; Audit: IA sau 30 ngày |
| **DynamoDB on-demand** |  Implemented | 20% vs provisioned | Workload batch không đều, on-demand phù hợp hơn provisioned capacity |
| **Athena partition pruning** |  Implemented | 60-80% chi phí query | Phân vùng theo cost_period_start, account_id, service |
| **VPC Gateway Endpoints (S3, DynamoDB)** |  Implemented | $0.09/GB NAT cost | Lưu lượng S3/DDB không qua NAT Gateway |
| **CloudWatch Logs retention** |  Implemented | 50% chi phí logs | Application logs: 14 ngày; Audit logs: 90 ngày rồi chuyển S3 |
| **Lambda reserved concurrency** |  Not applicable | N/A | Workload batch tần suất thấp, không cần reserve |
| **Savings Plans / Reserved Instances** |  W12 T4 evaluation | 20-40% compute | Cần baseline 2 tuần để xác định commitment; không áp dụng trong capstone 2 tuần |
| **Spot instances** |  Not applicable | N/A | Không dùng EC2/ECS always-on cluster, chỉ dùng Lambda serverless |
| **Cross-region replication** |  Out of scope | N/A | Single-region `ap-southeast-1`; DR design-only |
| **Bedrock prompt caching** |  Out of scope | N/A | AI inference cost thuộc về AIOps |

**Tổng kết**: Các biện pháp tối ưu hóa đã triển khai giúp giảm ~**35-45%** chi phí so với cấu hình baseline chưa tối ưu.

---

## 4. So sánh Chi phí với các Góc độ khác (cùng Task Force)

Phần này sẽ được cập nhật sau khi có tài liệu phân tích chi phí từ các nhóm CDO khác trong Task Force 2.

| Góc độ Kiến trúc | $/tenant/tháng (dự báo) | Lý do Khác biệt | Ghi chú |
|---|---|---|---|
| **CDO06: Lakehouse-centric scheduled** | **$46.77** (1 tenant)<br/>**$10.77** (10 tenant) | Serverless-first, chi phí cố định thấp, phù hợp batch 24h; VPC Endpoints là chi phí cố định lớn | Win axis: cost efficiency at scale, low ops overhead |
| CDO khác A: TBD | TBD | TBD | Chờ docs từ nhóm khác |
| CDO khác B: TBD | TBD | TBD | Chờ docs từ nhóm khác |

**Evidence cần thu thập để so sánh công bằng**:
- Chi phí compute pattern (EKS vs ECS vs Lambda vs EC2)
- Chi phí storage/query (RDS vs Redshift vs Athena vs EMR)
- Chi phí networking (VPC peering, Transit Gateway, NAT Gateway)
- Chi phí vận hành (managed service overhead vs self-managed cluster)

---

## 5. Chi phí Thực tế Đo được (Measured Actual - Pack #2 W12 T4)

### 5.1 Chi phí Capstone 2 tuần

Phần này sẽ được điền sau khi chạy platform thực tế trong W12 với synthetic workload.

| Dịch vụ | Dự báo (14 ngày) | Thực tế (14 ngày) | Chênh lệch | Ghi chú |
|---|---|---|---|---|
| Lambda | $1.20 | TBD | TBD | Đo từ CloudWatch Billing |
| Step Functions | $0.05 | TBD | TBD | |
| S3 | $0.30 | TBD | TBD | |
| DynamoDB | $0.25 | TBD | TBD | |
| Athena | $0.12 | TBD | TBD | |
| VPC Endpoints | $13.44 | TBD | TBD | Chi phí cố định cao nhất |
| CloudWatch | $4.00 | TBD | TBD | Logs + metrics + alarms |
| KMS | $1.40 | TBD | TBD | |
| NAT Gateway | $0.05 + transfer | TBD | TBD | |
| **Tổng cộng** | **$20.81** | **TBD** | **TBD** | |

**Phương pháp đo lường**:
1. Bật Cost Explorer với tag `Project=TF2-FinOps-CDO06` và `Environment=Sandbox`.
2. Chạy workflow synthetic 1 lượt/ngày trong 14 ngày với 3 tenant test (nhỏ, trung bình, lớn).
3. Xuất AWS Cost and Usage Report sau 14 ngày, lọc theo tag.
4. So sánh dự báo vs thực tế, phân tích các outlier.

### 5.2 Chi phí Thực tế theo Tenant

Sau khi onboard ≥3 tenant test với các mức tải khác nhau:

| Tenant test | Đặc điểm | Chi phí/ngày (thực tế) | Ngoại suy $/tháng | Ghi chú |
|---|---|---|---|---|
| Tenant-1 (Small) | 5 accounts, 20 services, 10 GB CUR | TBD | TBD | Profile: startup với spend ~$5K/tháng |
| Tenant-2 (Medium) | 20 accounts, 50 services, 50 GB CUR | TBD | TBD | Profile: mid-size với spend ~$50K/tháng |
| Tenant-3 (Large) | 50 accounts, 100 services, 200 GB CUR | TBD | TBD | Profile: enterprise với spend ~$500K/tháng |

**Expected insight**: Chi phí tăng tuyến tính với CUR data size (S3 storage + Athena scan cost), nhưng compute cost ổn định vì batch processing.

### 5.3 Chi phí mỗi Quyết định Đúng (Cost-per-Correct-Decision)

Metric này đo lường hiệu quả chi phí của nền tảng CDO + AI Engine, được tính chung với đội AIOps.

| Chỉ số | Giá trị (dự báo) | Giá trị (thực tế W12) | Ghi chú |
|---|---|---|---|
| **Tổng số lượt gọi AI Engine** | 42 calls (3 tenant × 14 ngày) | TBD | 1 call/tenant/ngày |
| **Số quyết định đúng (True Positive)** | 34 (precision 80%) | TBD | Dựa trên backtest requirement |
| **Chi phí CDO platform** | $20.81 (14 ngày) | TBD | Chỉ tính CDO, không tính AI inference |
| **Chi phí AI inference** | *Out of scope CDO* | TBD | AIOps cung cấp |
| **Chi phí tổng (CDO + AI)** | TBD | TBD | Cần dữ liệu từ AIOps |
| **Chi phí mỗi quyết định đúng** | **TBD** | **TBD** | = Total cost / True Positives |

**Benchmark so sánh**:
- Chi phí thủ công phát hiện anomaly: ~$200/anomaly (8 giờ công × $25/giờ Finance analyst)
- Mục tiêu: Cost-per-correct-decision < $10 để chứng minh ROI rõ ràng

---

## 6. Rào cản Chi phí (Cost Guardrails)

Để tránh chi phí vượt ngân sách trong quá trình capstone và demo:

| Guardrail | Ngưỡng | Hành động | Trách nhiệm |
|---|---|---|---|
| **Monthly budget alert 70%** | $30/tháng (1 tenant sandbox) | CloudWatch alarm → SNS Engineering | CDO team review usage patterns |
| **Monthly budget alert 90%** | $40/tháng | Alarm + email escalation tới mentor | CDO + Mentor review |
| **Monthly budget hard cap 100%** | $50/tháng | Lambda env var `MAX_BUDGET_EXCEEDED=true` → skip workflow | Auto fail-safe to prevent runaway cost |
| **Per-tenant S3 quota** | 100 GB/tenant curated data | S3 bucket quota + alarm | Prevent single tenant data explosion |
| **Athena query daily limit** | 200 GB scanned/ngày | Service Quotas + alarm | Cap ad-hoc query cost |
| **Lambda concurrent execution** | 10 concurrent | Reserved concurrency limit | Prevent lambda storm |
| **DynamoDB WCU/RCU burst** | Auto-scaling max 100 | DynamoDB auto-scaling cap | Limit burst cost |

**Monitoring dashboard**: CloudWatch dashboard `FinOpsWatch-CDO-CostGuardrails` hiển thị:
- Daily spend trend (7 ngày cuối)
- Forecast vs actual spend
- Top 5 cost drivers (service breakdown)
- Budget utilization %

---

## 7. Khuyến nghị Chi phí cho Sản xuất (Production Cost Recommendations)

Sau khi hoàn thành capstone 2 tuần và có baseline thực tế, các khuyến nghị sau đây nên được xem xét cho triển khai production dài hạn:

| Khuyến nghị | Thời điểm áp dụng | Tiết kiệm ước tính | Điều kiện |
|---|---|---|---|
| **Compute Savings Plans** | Sau 3 tháng baseline | 20-30% Lambda cost | Workload ổn định ≥10 tenant |
| **S3 Intelligent-Tiering** | Ngay lập tức | 10-15% storage cost | Thay thế manual lifecycle rules |
| **DynamoDB Reserved Capacity** | Sau 6 tháng baseline | 40-60% DDB cost | Khi provisioned rẻ hơn on-demand |
| **VPC Endpoint consolidation** | Khi có multi-workload | 50% endpoint cost | Dùng chung endpoints giữa nhiều platform |
| **CloudWatch Logs export to S3** | Ngay lập tức | 70% log storage cost | Logs >14 ngày export sang S3 IA |
| **Cross-region replication** | Chỉ khi yêu cầu DR | Tránh 2× storage cost | Không enable nếu không cần thiết |
| **QuickSight Enterprise** | Khi có >10 Finance users | Giảm per-user cost | $18/user/tháng vs $5 Reader |
| **Athena query result caching** | Ngay lập tức | 30-50% repeat query cost | Dashboard refresh dùng cache 24h |
| **KMS key consolidation** | Khi có compliance sign-off | 33% KMS cost | Dùng 1 CMK cho data + audit thay vì 3 keys |

**Ước tính tổng tiết kiệm khi áp dụng tất cả khuyến nghị**: 25-40% chi phí vận hành dài hạn.

---

## 8. Phân tích Rủi ro Chi phí (Cost Risk Analysis)

| Rủi ro Chi phí | Tác động | Xác suất | Biện pháp Giảm thiểu |
|---|---|---|---|
| **Athena query storm** (ad-hoc queries không tối ưu) | +$50-200/ngày | Trung bình | Query result caching, partition pruning bắt buộc, query cost alarm |
| **S3 storage explosion** (không có lifecycle) | +$10-50/tháng | Thấp | Lifecycle rules tự động, bucket quota, storage growth alarm |
| **Lambda timeout loop** (retry storm) | +$20-100/ngày | Thấp | Circuit breaker, exponential backoff, max retry limit |
| **VPC endpoint always-on cost** | $28.80/tháng cố định | Chắc chắn | Không thể giảm; chấp nhận trade-off security vs cost |
| **AI Engine outage → CDO retry storm** | +$10-50/ngày | Trung bình | Circuit breaker với backoff, max retry 3 lần, fail-closed workflow |
| **CloudWatch Logs retention không giới hạn** | +$5-20/tháng | Thấp | Auto-expire 14 ngày, critical logs export S3 |

---

## 9. Câu hỏi Mở (Open Questions)

- [ ] **Q1**: Chi phí AI inference thực tế từ AIOps là bao nhiêu để tính cost-per-correct-decision tổng thể? *Resolve với AIOps W12 T3.*
- [ ] **Q2**: Nếu có quyền truy cập AWS Organization billing real data, có thể loại bỏ synthetic data generation cost không? *Confirm với mentor W11 T5.*
- [ ] **Q3**: QuickSight Reader license có thể chia sẻ cho bao nhiêu concurrent users để ước tính chính xác per-tenant allocation? *Test thực tế W12 T2.*
- [ ] **Q4**: Chi phí measured actual có nằm trong budget capstone $50-100 không? *Verify sau 7 ngày chạy W12 T3.*

---

## Tài liệu Liên quan (Related Documents)

- [`01_requirements_analysis_vi.md`](01_requirements_analysis_vi.md) - Yêu cầu hard về precision/FP và constraint về cadence/data source ảnh hưởng chi phí
- [`02_infra_design_vi.md`](02_infra_design_vi.md) - Kiến trúc lakehouse-centric serverless quyết định cost model compute/storage
- [`03_security_design_vi.md`](03_security_design_vi.md) - VPC Endpoints, KMS CMKs, CloudTrail là các cost driver bảo mật
- [`04_deployment_design_vi.md`](04_deployment_design_vi.md) - CI/CD pipeline cost (GitHub Actions, CodeDeploy), observability stack cost
- [`07_test_eval_report.md`](../../../template-docs/07_test_eval_report.md) - Load test results sẽ validate cost assumptions trong §5 doc này

---

**Phê duyệt**: Tài liệu này cần được review bởi mentor và Finance stakeholder trước khi commit baseline cost model cho demo W12 T5.
