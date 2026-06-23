# Cost Analysis - TF2 FinOps Watch CDO06

<!-- Doc owner: CDO06
     Status: Draft W11 Pack #1, updated with actuals W12 T4 Pack #2
     Scope: CDO lakehouse-centric scheduled FinOps control plane cost -->

## 1. Cost Model per Tenant (Forecast)

A "tenant" in the TF2 FinOps Watch context is an AWS member account under cost monitoring. The cost model below estimates the 24h cadence operation with serverless-first components.

| Component | Unit Cost | Avg Tenant Usage | $/tenant/month |
|---|---|---|---|
| **Compute - Lambda** | $0.20/1M requests + $0.0000166667/GB-second | 30 calls/day × 5 functions × 512MB × 30s | $2.50 |
| **Orchestration - Step Functions Standard** | $0.025/1K state transitions | 1 workflow/day × 12 states × 30 days | $0.09 |
| **Orchestration - EventBridge Scheduler** | $1.00/1M invocations | 1 trigger/day × 30 days | $0.00 |
| **Storage - S3 Standard (raw/curated)** | $0.023/GB-month | 15 GB CUR data + 10 GB curated | $0.58 |
| **Storage - S3 IA (audit 30-90 days)** | $0.0125/GB-month | 5 GB audit archives | $0.06 |
| **Database - DynamoDB on-demand** | $1.25/million write + $0.25/million read | 100 writes + 500 reads/day | $0.48 |
| **Query - Athena** | $5.00/TB scanned | 50 GB scanned/month (dashboard + ad-hoc) | $0.25 |
| **Data Catalog - Glue** | $1.00/100K objects stored/month | 10K objects/month | $0.10 |
| **Data transfer - NAT Gateway** | $0.045/GB (outbound AI Engine) | 2 GB/month payload + response | $0.09 |
| **VPC Endpoints - Interface Endpoints** | $0.01/hour × 4 endpoints | 720 hours × 4 (KMS, SM, Athena, CloudWatch) | $28.80 |
| **Secrets Manager** | $0.40/secret/month + $0.05/10K API calls | 3 secrets + 1K calls/month | $1.25 |
| **KMS** | $1.00/CMK/month + $0.03/10K requests | 3 CMKs + 5K requests/month | $3.02 |
| **Observability - CloudWatch Logs** | $0.50/GB ingested + $0.03/GB stored | 5 GB logs/month | $2.65 |
| **Observability - CloudWatch Metrics** | $0.30/custom metric/month | 20 custom metrics | $6.00 |
| **Observability - X-Ray** | $5.00/1M traces + $0.50/1M scanned | 50K traces/month | $0.28 |
| **Dashboard - QuickSight Reader** | $5.00/reader/month (shared across tenants) | 1/10 reader allocation | $0.50 |
| **Alerting - SNS** | $0.50/1M requests + $2.00/100K email | 60 alerts/month (2/day) + email | $0.12 |
| **AI Engine integration cost** | *AIOps-owned* | *Out of CDO scope* | $0.00 |
| **Total CDO platform / tenant / month** | | | **$46.77** |

**Important notes**:
- The above cost is the estimated **CDO platform infrastructure** excluding AI Engine costs owned by AIOps.
- VPC Interface Endpoints ($28.80) is the largest fixed cost; can be reduced by consolidating endpoints at scale.
- Actual costs will be measured in W12 T4 after running synthetic workload for 7-10 days.

---

## 2. Cost at Scale

As tenant count grows, some fixed costs (VPC Endpoints, KMS CMKs, QuickSight) are amortized across multiple tenants, reducing average per-tenant cost.

| Tenant Count | Fixed Cost/month | Variable Cost/month | Total Cost/month | Avg/tenant |
|---|---|---|---|---|
| **1** | $40.00 | $6.77 | $46.77 | $46.77 |
| **10** | $40.00 | $67.70 | $107.70 | $10.77 |
| **50** | $40.00 | $338.50 | $378.50 | $7.57 |
| **200** | $40.00 | $1,354.00 | $1,394.00 | $6.97 |

**Fixed costs include**:
- 4× VPC Interface Endpoints: $28.80
- 3× KMS CMKs: $3.00
- 1× QuickSight Reader (shared): $5.00
- CloudWatch Dashboard (shared): $3.00
- CI/CD pipeline (CodeDeploy, GitHub Actions): $0.20

**Analysis**:
- At 10 tenants, cost drops **77%** compared to 1 tenant due to fixed cost amortization.
- At 50+ tenants, average cost stabilizes at ~$7-8/tenant/month.
- Break-even point vs manual approach: ~5 tenants (assuming manual cost is $50/tenant/month for 8 hours of analysis work).

---

## 3. Applied Cost Optimizations

| Optimization | Status | Estimated Savings | Notes |
|---|---|---|---|
| **Lambda right-sizing** |  Implemented | 15-20% compute cost | Benchmarked to choose 512MB instead of 1024MB for workers |
| **S3 Lifecycle tiering** |  Implemented | 40% storage cost | Raw zone: Standard 7 days → IA 30 days → Glacier 90 days; Audit: IA after 30 days |
| **DynamoDB on-demand** |  Implemented | 20% vs provisioned | Batch workload is uneven, on-demand fits better than provisioned capacity |
| **Athena partition pruning** |  Implemented | 60-80% query cost | Partition by cost_period_start, account_id, service |
| **VPC Gateway Endpoints (S3, DynamoDB)** |  Implemented | $0.09/GB NAT cost | S3/DDB traffic bypasses NAT Gateway |
| **CloudWatch Logs retention** |  Implemented | 50% logs cost | Application logs: 14 days; Audit logs: 90 days then export to S3 |
| **Lambda reserved concurrency** |  Not applicable | N/A | Low-frequency batch workload, no need to reserve |
| **Savings Plans / Reserved Instances** |  W12 T4 evaluation | 20-40% compute | Need 2-week baseline to determine commitment; not applied in 2-week capstone |
| **Spot instances** |  Not applicable | N/A | No always-on EC2/ECS cluster, only serverless Lambda |
| **Cross-region replication** |  Out of scope | N/A | Single-region `ap-southeast-1`; DR design-only |
| **Bedrock prompt caching** |  Out of scope | N/A | AI inference cost belongs to AIOps |

**Summary**: Applied optimizations reduce cost by ~**35-45%** compared to unoptimized baseline configuration.

---

## 4. Cost Comparison with Other Angles (Same Task Force)

This section will be updated after receiving cost analysis documents from other CDO teams in Task Force 2.

| Architecture Angle | $/tenant/month (forecast) | Difference Reason | Notes |
|---|---|---|---|
| **CDO06: Lakehouse-centric scheduled** | **$46.77** (1 tenant)<br/>**$10.77** (10 tenant) | Serverless-first, low fixed cost, fits 24h batch; VPC Endpoints are largest fixed cost | Win axis: cost efficiency at scale, low ops overhead |
| Other CDO A: TBD | TBD | TBD | Awaiting docs from other team |
| Other CDO B: TBD | TBD | TBD | Awaiting docs from other team |

**Evidence needed for fair comparison**:
- Compute pattern cost (EKS vs ECS vs Lambda vs EC2)
- Storage/query cost (RDS vs Redshift vs Athena vs EMR)
- Networking cost (VPC peering, Transit Gateway, NAT Gateway)
- Operational cost (managed service overhead vs self-managed cluster)

---

## 5. Measured Actual (Pack #2 W12 T4)

### 5.1 2-Week Capstone Spend

This section will be filled after running the platform in W12 with synthetic workload.

| Service | Forecast (14 days) | Actual (14 days) | Delta | Notes |
|---|---|---|---|---|
| Lambda | $1.20 | TBD | TBD | Measured from CloudWatch Billing |
| Step Functions | $0.05 | TBD | TBD | |
| S3 | $0.30 | TBD | TBD | |
| DynamoDB | $0.25 | TBD | TBD | |
| Athena | $0.12 | TBD | TBD | |
| VPC Endpoints | $13.44 | TBD | TBD | Highest fixed cost |
| CloudWatch | $4.00 | TBD | TBD | Logs + metrics + alarms |
| KMS | $1.40 | TBD | TBD | |
| NAT Gateway | $0.05 + transfer | TBD | TBD | |
| **Total** | **$20.81** | **TBD** | **TBD** | |

**Measurement methodology**:
1. Enable Cost Explorer with tags `Project=TF2-FinOps-CDO06` and `Environment=Sandbox`.
2. Run synthetic workflow 1x/day for 14 days with 3 test tenants (small, medium, large).
3. Export AWS Cost and Usage Report after 14 days, filter by tags.
4. Compare forecast vs actual, analyze outliers.

### 5.2 Per-Tenant Actual

After onboarding ≥3 test tenants with different load levels:

| Test Tenant | Characteristics | Cost/day (actual) | Extrapolate $/month | Notes |
|---|---|---|---|---|
| Tenant-1 (Small) | 5 accounts, 20 services, 10 GB CUR | TBD | TBD | Profile: startup with ~$5K/month spend |
| Tenant-2 (Medium) | 20 accounts, 50 services, 50 GB CUR | TBD | TBD | Profile: mid-size with ~$50K/month spend |
| Tenant-3 (Large) | 50 accounts, 100 services, 200 GB CUR | TBD | TBD | Profile: enterprise with ~$500K/month spend |

**Expected insight**: Cost scales linearly with CUR data size (S3 storage + Athena scan cost), but compute cost remains stable due to batch processing.

### 5.3 Cost-per-Correct-Decision

This metric measures the cost efficiency of the CDO platform + AI Engine, calculated jointly with the AIOps team.

| Metric | Value (forecast) | Value (actual W12) | Notes |
|---|---|---|---|
| **Total AI Engine calls** | 42 calls (3 tenant × 14 days) | TBD | 1 call/tenant/day |
| **Correct decisions (True Positive)** | 34 (80% precision) | TBD | Based on backtest requirement |
| **CDO platform cost** | $20.81 (14 days) | TBD | CDO only, not including AI inference |
| **AI inference cost** | *Out of CDO scope* | TBD | AIOps provides |
| **Total cost (CDO + AI)** | TBD | TBD | Needs data from AIOps |
| **Cost per correct decision** | **TBD** | **TBD** | = Total cost / True Positives |

**Benchmark comparison**:
- Manual anomaly detection cost: ~$200/anomaly (8 hours × $25/hour Finance analyst)
- Target: Cost-per-correct-decision < $10 to demonstrate clear ROI

---

## 6. Cost Guardrails

To prevent cost overruns during capstone and demo:

| Guardrail | Threshold | Action | Responsibility |
|---|---|---|---|
| **Monthly budget alert 70%** | $30/month (1 tenant sandbox) | CloudWatch alarm → SNS Engineering | CDO team reviews usage patterns |
| **Monthly budget alert 90%** | $40/month | Alarm + email escalation to mentor | CDO + Mentor review |
| **Monthly budget hard cap 100%** | $50/month | Lambda env var `MAX_BUDGET_EXCEEDED=true` → skip workflow | Auto fail-safe to prevent runaway cost |
| **Per-tenant S3 quota** | 100 GB/tenant curated data | S3 bucket quota + alarm | Prevent single tenant data explosion |
| **Athena query daily limit** | 200 GB scanned/day | Service Quotas + alarm | Cap ad-hoc query cost |
| **Lambda concurrent execution** | 10 concurrent | Reserved concurrency limit | Prevent lambda storm |
| **DynamoDB WCU/RCU burst** | Auto-scaling max 100 | DynamoDB auto-scaling cap | Limit burst cost |

**Monitoring dashboard**: CloudWatch dashboard `FinOpsWatch-CDO-CostGuardrails` shows:
- Daily spend trend (last 7 days)
- Forecast vs actual spend
- Top 5 cost drivers (service breakdown)
- Budget utilization %

---

## 7. Production Cost Recommendations

After completing the 2-week capstone with actual baseline, the following recommendations should be considered for long-term production deployment:

| Recommendation | When to Apply | Estimated Savings | Conditions |
|---|---|---|---|
| **Compute Savings Plans** | After 3-month baseline | 20-30% Lambda cost | Stable workload ≥10 tenants |
| **S3 Intelligent-Tiering** | Immediately | 10-15% storage cost | Replace manual lifecycle rules |
| **DynamoDB Reserved Capacity** | After 6-month baseline | 40-60% DDB cost | When provisioned is cheaper than on-demand |
| **VPC Endpoint consolidation** | When multi-workload exists | 50% endpoint cost | Share endpoints across platforms |
| **CloudWatch Logs export to S3** | Immediately | 70% log storage cost | Logs >14 days export to S3 IA |
| **Cross-region replication** | Only when DR required | Avoid 2× storage cost | Don't enable if not necessary |
| **QuickSight Enterprise** | When >10 Finance users | Reduce per-user cost | $18/user/month vs $5 Reader |
| **Athena query result caching** | Immediately | 30-50% repeat query cost | Dashboard refresh uses 24h cache |
| **KMS key consolidation** | When compliance signed-off | 33% KMS cost | Use 1 CMK for data + audit instead of 3 keys |

**Estimated total savings when applying all recommendations**: 25-40% of long-term operating cost.

---

## 8. Cost Risk Analysis

| Cost Risk | Impact | Probability | Mitigation |
|---|---|---|---|
| **Athena query storm** (unoptimized ad-hoc queries) | +$50-200/day | Medium | Query result caching, mandatory partition pruning, query cost alarm |
| **S3 storage explosion** (no lifecycle) | +$10-50/month | Low | Automatic lifecycle rules, bucket quota, storage growth alarm |
| **Lambda timeout loop** (retry storm) | +$20-100/day | Low | Circuit breaker, exponential backoff, max retry limit |
| **VPC endpoint always-on cost** | $28.80/month fixed | Certain | Cannot reduce; accept security vs cost trade-off |
| **AI Engine outage → CDO retry storm** | +$10-50/day | Medium | Circuit breaker with backoff, max 3 retries, fail-closed workflow |
| **CloudWatch Logs unlimited retention** | +$5-20/month | Low | Auto-expire 14 days, critical logs export S3 |

---

## 9. Open Questions

- [ ] **Q1**: What is the actual AI inference cost from AIOps to calculate total cost-per-correct-decision? *Resolve with AIOps W12 T3.*
- [ ] **Q2**: If we have access to AWS Organization billing real data, can we eliminate synthetic data generation cost? *Confirm with mentor W11 T5.*
- [ ] **Q3**: How many concurrent users can share a QuickSight Reader license to estimate accurate per-tenant allocation? *Test actual W12 T2.*
- [ ] **Q4**: Does measured actual cost stay within capstone budget of $50-100? *Verify after 7 days of running W12 T3.*

---

## Related Documents

- [`01_requirements_analysis.md`](01_requirements_analysis.md) - Hard requirements on precision/FP and constraints on cadence/data source affecting cost
- [`02_infra_design.md`](02_infra_design.md) - Lakehouse-centric serverless architecture determines compute/storage cost model
- [`03_security_design.md`](03_security_design.md) - VPC Endpoints, KMS CMKs, CloudTrail are security cost drivers
- [`04_deployment_design.md`](04_deployment_design.md) - CI/CD pipeline cost (GitHub Actions, CodeDeploy), observability stack cost
- [`07_test_eval_report.md`](../../../template-docs/07_test_eval_report.md) - Load test results will validate cost assumptions in §5 of this doc

---

**Approval**: This document needs review by mentor and Finance stakeholder before committing the baseline cost model for W12 T5 demo.
