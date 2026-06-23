# Cost Analysis - TF2 FinOps Watch CDO06

<!-- Doc owner: CDO06
     Status: Draft W11 Pack #1, updated with actuals W12 T4 Pack #2
     Scope: CDO lakehouse-centric scheduled FinOps control plane cost -->

## 1. Cost Model per Tenant and Cadence Run (Forecast)

A "tenant" in the TF2 FinOps Watch context is an AWS member account under cost monitoring. The cost model separates variable per-tenant costs from shared platform costs. This distinction matters because the lakehouse and Lambda workflow scale mostly with account/data volume, while EKS, internal networking, and baseline observability create shared fixed cost that must be amortized across tenants.

CDO owns the operational hosting cost of the AIOps-provided AI Engine on EKS: control plane, managed node groups, ECR, internal service exposure, IRSA, secrets plumbing, autoscaling, and runtime monitoring. AIOps owns model development, model training design, model quality, and any synthetic historical dataset used to train, enhance, or backtest the model. If AIOps training or retraining jobs run on the CDO-hosted EKS cluster, the compute cost must be tagged and reported separately as "AI Engine workload cost hosted by CDO".

| Component | Unit Cost | Avg Usage Assumption | Cost treatment |
|---|---|---|---|
| **Compute - Lambda adapters** | $0.20/1M requests + $0.0000166667/GB-second | Puller, normalizer, router, containment, audit writer; 24h cadence | Variable per tenant; `Evidence needed: measured Lambda GB-seconds`. |
| **Orchestration - Step Functions Standard** | $0.025/1K state transitions | 1 workflow/day/account, retries included | Variable per tenant; low but must be measured with actual state count. |
| **Orchestration - EventBridge Scheduler** | $1.00/1M invocations | 1 scheduled trigger/day plus manual redrive | Shared negligible cost. |
| **Storage - S3 raw/curated** | $0.023/GB-month Standard, lower after lifecycle | CUR/Cost Explorer pulls, normalized parquet, dashboard extracts | Variable by billing data volume. |
| **Storage - S3 audit archive** | $0.0125/GB-month IA estimate | Containment and decision evidence retained at least 90 days | Variable by alert/containment volume; retention is mandatory. |
| **Database - DynamoDB on-demand** | $1.25/million write + $0.25/million read | Run state, idempotency, audit index, dashboard materialization | Variable with runs and dashboard reads. |
| **Query - Athena** | $5.00/TB scanned | Dashboard refresh, evidence lookup, operational review | Variable; controlled by partition pruning and query limits. |
| **Data Catalog - Glue** | Catalog/crawler charges by object and DPU-hour | Cost tables, partitions, schema evolution | Variable but small at capstone scale. |
| **EKS control plane** | About $0.10/hour | One private cluster for AI Engine hosting | Shared fixed cost, about $73/month before usage. |
| **EKS on-demand node group** | EC2 on-demand rate by instance type | `ai-engine-api`, `ai-engine-explainer`, monitoring, ingress/controller support | Shared fixed baseline; `Evidence needed: selected instance type and min size`. |
| **EKS spot node group** | Spot EC2 rate by instance type | `ai-engine-worker`, batch scoring, feature engineering, retraining jobs | Variable AI workload hosting cost; tag separately from CDO adapters. |
| **EKS node EBS volumes** | EBS GB-month | Root volumes and temporary job storage | Shared/variable depending on node sizing and job checkpoints. |
| **ECR repositories** | $0.10/GB-month storage | Versioned AIOps container images and Lambda containers if used | Shared fixed/variable by retained image count. |
| **Internal ALB/NLB** | Hourly + LCU/NLCU usage | Private AI Engine endpoint | Shared fixed plus request-driven variable. |
| **VPC endpoints** | Hourly endpoint charge + data processing where applicable | S3, DynamoDB, ECR, Secrets Manager, CloudWatch Logs, KMS/STS as needed | Shared fixed security cost. |
| **Secrets Manager** | $0.40/secret/month + request charges | AI Engine API key, webhooks, contract signing key, external IDs | Shared fixed plus request volume. |
| **KMS** | $1.00/CMK/month + request charges | Data, audit, secrets, optional EKS node-volume keys | Shared fixed; consolidation requires Security approval. |
| **Observability - CloudWatch/Container Insights** | Logs, metrics, dashboard, and Container Insights charges | Lambda, Step Functions, EKS control plane, node, and pod visibility | Shared and variable; can become a top cost driver. |
| **Dashboard - QuickSight Reader** | Reader/session pricing | Finance stakeholder dashboard access | Shared by Finance users, not by AI workload volume. |
| **Alerting - SNS/SES/Slack integration** | Request/message charges | Finance and Engineering alert routes | Variable but expected low. |
| **Total CDO platform forecast** | Mixed fixed and variable | CDO infra plus CDO-hosted AI Engine runtime | `Evidence needed: recalculated after EKS node size, endpoint count, and run volume are finalized`. |

**Important notes**:
- The above forecast is the estimated **CDO platform infrastructure** including the CDO-owned EKS hosting platform, but excluding AIOps-owned model development and model-quality work.
- EKS control plane, baseline on-demand nodes, VPC endpoints, ALB, KMS, and observability are the largest fixed costs.
- Actual costs must be measured from tagged AWS spend. Use `Evidence needed: CDO EKS hosting actual`, `Evidence needed: CDO pipeline per-run actual`, and `Evidence needed: AI workload hosted-on-CDO-EKS actual` until measured.

---

## 2. Cost at Scale

As tenant count grows, fixed costs such as EKS control plane, baseline on-demand nodes, VPC endpoints, KMS CMKs, internal load balancer, and QuickSight are amortized across multiple tenants, reducing average per-tenant cost. This section uses a forecast structure rather than claiming measured results.

| Tenant Count | Shared fixed platform/month | Variable CDO workflow/month | Hosted AI workload/month | Total/month | Avg/tenant |
|---|---|---|---|---|---|
| **1** | `Evidence needed: EKS baseline + endpoints` | `Evidence needed: one account run cost` | `Evidence needed: AI worker usage` | `Evidence needed` | `Evidence needed` |
| **10** | Same shared baseline | `Evidence needed: 10-account run cost` | `Evidence needed: AI worker usage` | `Evidence needed` | `Evidence needed` |
| **50** | Same shared baseline plus possible node scaling | `Evidence needed: 50-account run cost` | `Evidence needed: AI worker usage` | `Evidence needed` | `Evidence needed` |
| **200** | Shared baseline plus scale-out assumptions | `Evidence needed: 200-account run cost` | `Evidence needed: AI worker usage` | `Evidence needed` | `Evidence needed` |

**Fixed costs include**:
- 4× VPC Interface Endpoints: $28.80
- 3× KMS CMKs: $3.00
- 1× QuickSight Reader (shared): $5.00
- EKS control plane: about $73.00/month
- Baseline on-demand node group: `Evidence needed: instance type × min node count`
- Internal ALB/NLB: `Evidence needed: selected load balancer and LCU/NLCU usage`
- CloudWatch dashboard, logs, metrics, and Container Insights: `Evidence needed: retained log volume`

**Analysis**:
- EKS makes the one-tenant cost higher than a pure serverless prototype, but the same platform supports stable AI API hosting, batch workers, observability, and private networking.
- At larger tenant counts, average cost should decline because the EKS control plane, baseline nodes, endpoints, and dashboard costs are shared.
- The break-even point must be recalculated after node sizing and AI worker utilization are known; do not reuse the older serverless-only $46.77/tenant estimate.

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
| **Spot node group for AI workers** |  Implemented in design | 40-70% AI worker compute | Use only for interruptible `ai-engine-worker`, batch scoring, feature engineering, and retraining jobs with checkpoint/retry. |
| **On-demand node right-sizing** |  Evidence needed | 15-30% EKS baseline | Select the smallest stable instance family that supports `ai-engine-api`, `ai-engine-explainer`, ingress, monitoring, and core CDO pods. |
| **Karpenter or Cluster Autoscaler scale-down** |  Implemented in design | 20-50% worker capacity | Remove idle spot capacity after batch jobs complete. |
| **Cross-region replication** |  Out of scope | N/A | Single-region `ap-southeast-1`; DR design-only |
| **Bedrock prompt caching** |  Out of scope | N/A | AI inference cost belongs to AIOps |

**Summary**: Applied optimizations reduce cost compared to an unoptimized baseline, but the exact percentage is `Evidence needed: measured optimized vs unoptimized forecast`. The previous serverless-only estimate is no longer valid because CDO now owns EKS hosting infrastructure for the AIOps AI Engine runtime.

---

## 4. Cost Comparison with Other Angles (Same Task Force)

This section compares the current CDO06 direction against common alternatives. It does not claim final measured numbers for other teams; those remain evidence gaps until their documents are available.

| Architecture Angle | $/tenant/month (forecast) | Difference Reason | Notes |
|---|---|---|---|
| **CDO06: Lakehouse-centric scheduled + EKS-hosted AI Engine** | `Evidence needed: CDO platform actual after EKS sizing` | Serverless orchestration keeps CDO adapters low-cost, while EKS adds fixed hosting cost for AIOps runtime. | Win axis: traceable FinOps control plane, private AI Engine hosting, safe containment, and amortized platform cost at scale. |
| Pure serverless CDO prototype | Lower one-tenant fixed cost, but incomplete for current scenario | Avoids EKS control plane and node costs. | Rejected because current scenario requires CDO-hosted AI Engine runtime and batch workloads. |
| Always-on warehouse approach | Higher fixed data cost | Redshift/RDS-style storage can simplify some SQL workflows but creates idle cost for 24h cadence. | Rejected because S3/Glue/Athena fits daily FinOps evidence with lower idle cost. |
| Third-party FinOps SaaS | Subscription-dependent | Can reduce platform operations but weakens CDO/AIOps ownership boundary and containment guardrail control. | Not selected for capstone implementation. |

**Evidence needed for fair comparison**:
- Compute pattern cost (EKS on-demand/spot vs ECS vs Lambda vs EC2)
- Storage/query cost (RDS vs Redshift vs Athena vs EMR)
- Networking cost (VPC peering, Transit Gateway, NAT Gateway)
- Operational cost (managed service overhead vs self-managed cluster)
- AI Engine hosting split (CDO platform runtime vs AIOps model development/training)

---

## 5. Measured Actual (Pack #2 W12 T4)

### 5.1 2-Week Capstone Spend

This section must be filled only after running the platform with tagged AWS resources. CDO demo injections may be used for smoke tests, but AIOps-owned model training/backtest datasets must not be counted as CDO operational spend unless they run on the CDO-hosted EKS cluster.

| Service | Forecast (14 days) | Actual (14 days) | Delta | Notes |
|---|---|---|---|---|
| Lambda adapters | `Evidence needed: forecast from memory/runtime` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Puller, normalizer, router, containment, audit writer. |
| Step Functions | `Evidence needed: state transition count` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Include retries and manual redrives. |
| S3 raw/curated/audit | `Evidence needed: GB-month and request forecast` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Separate cost data and audit evidence prefixes. |
| DynamoDB | `Evidence needed: read/write forecast` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Run state, idempotency, audit index, dashboard materialization. |
| Athena/Glue | `Evidence needed: scanned TB and crawler usage` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Validate partition pruning. |
| EKS control plane | About $34 for 14 days | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Fixed while cluster exists. |
| EKS on-demand nodes | `Evidence needed: instance type × node count` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Stable AI API, explainer, monitoring, ingress/controller support. |
| EKS spot workers | `Evidence needed: job hours and instance type` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Batch scoring, feature engineering, retraining when hosted by CDO. |
| ECR/EBS/Internal LB | `Evidence needed: retained images, volumes, LCU/NLCU` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | AI Engine hosting support costs. |
| VPC Endpoints | `Evidence needed: endpoint count × hourly charge` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Private AWS service access. |
| CloudWatch/Container Insights | `Evidence needed: log volume and metric count` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Lambda, Step Functions, EKS, pods, nodes. |
| KMS/Secrets Manager | `Evidence needed: CMK and secret count` | `Evidence needed: Cost Explorer tag report` | `Evidence needed` | Data, audit, AI Engine secret, webhooks. |
| **Total** | `Evidence needed: forecast total` | `Evidence needed: actual total` | `Evidence needed` | Do not publish a final number until measured. |

**Measurement methodology**:
1. Enable Cost Explorer with tags `Project=TF2-FinOps-CDO06` and `Environment=Sandbox`.
2. Run CDO integration workflow 1x/day for 14 days with approved demo inputs and dry-run containment.
3. Export AWS Cost and Usage Report after 14 days, filter by tags.
4. Split costs into CDO adapters, CDO EKS hosting baseline, hosted AI workload runtime, storage/query, networking, and observability.
5. Compare forecast vs actual, analyze outliers, and mark every unmeasured value with `Evidence needed: ...`.

### 5.2 Per-Tenant Actual

After onboarding test accounts with different load levels:

| Test Account Profile | Characteristics | Cost/day (actual) | Extrapolate $/month | Notes |
|---|---|---|---|---|
| Small | Low account count, low CUR volume, few dashboard readers | `Evidence needed` | `Evidence needed` | Validates minimum viable workflow cost. |
| Medium | Moderate account count, common shared services, multiple owner tags | `Evidence needed` | `Evidence needed` | Validates expected capstone operating shape. |
| Large | Higher account count, larger CUR volume, heavier dashboard/query activity | `Evidence needed` | `Evidence needed` | Validates Athena scan limits and EKS worker scaling. |

**Expected insight**: S3, Athena, DynamoDB, and Lambda costs scale with account and data volume. EKS control plane and baseline on-demand nodes scale as shared fixed platform cost until the AI API or worker queue requires additional capacity.

### 5.3 Cost-per-Correct-Decision

This metric measures the cost efficiency of the full FinOps Watch decision loop. CDO can report CDO platform cost and CDO-hosted AI runtime cost, but AIOps must provide model-quality metrics and any model-development cost they want included.

| Metric | Value (forecast) | Value (actual W12) | Notes |
|---|---|---|---|
| **Total AI Engine calls** | `Evidence needed: planned run count × account count` | `Evidence needed` | Count only operational contract calls from CDO to the hosted AI Engine. |
| **Correct decisions** | AIOps-provided metric | `Evidence needed: AIOps evaluation result` | CDO does not derive this from the AI team's training dataset. |
| **CDO platform cost** | `Evidence needed: CDO forecast total` | `Evidence needed` | CDO adapters, lakehouse, dashboard, alerting, audit, EKS hosting baseline. |
| **Hosted AI runtime cost on CDO EKS** | `Evidence needed: worker/API node cost allocation` | `Evidence needed` | Runtime cost only, separated from AIOps model development. |
| **AIOps model development cost** | Out of CDO scope unless AIOps provides it | AIOps-provided | Optional for full task-force ROI, not a CDO claim. |
| **Cost per correct decision** | `Evidence needed` | `Evidence needed` | = agreed total cost / AIOps-provided correct decisions. |

**Benchmark comparison**:
- Manual anomaly detection cost: ~$200/anomaly (8 hours × $25/hour Finance analyst)
- Target: Cost-per-correct-decision should remain materially below manual review cost after AIOps provides correct-decision counts and CDO provides measured hosting/operations cost.

---

## 6. Cost Guardrails

To prevent cost overruns during capstone and demo:

| Guardrail | Threshold | Action | Responsibility |
|---|---|---|---|
| **Monthly budget alert 70%** | `Evidence needed: capstone EKS-aware budget × 70%` | CloudWatch alarm -> SNS Engineering | CDO team reviews usage patterns |
| **Monthly budget alert 90%** | `Evidence needed: capstone EKS-aware budget × 90%` | Alarm + email escalation to mentor | CDO + Mentor review |
| **Monthly budget hard stop 100%** | `Evidence needed: approved capstone budget` | Disable scheduler and block non-essential worker jobs | Auto fail-safe to prevent runaway cost |
| **Per-tenant S3 quota** | 100 GB/tenant curated data | S3 bucket quota + alarm | Prevent single tenant data explosion |
| **Athena query daily limit** | 200 GB scanned/day | Service Quotas + alarm | Cap ad-hoc query cost |
| **Lambda concurrent execution** | 10 concurrent | Reserved concurrency limit | Prevent lambda storm |
| **DynamoDB WCU/RCU burst** | Auto-scaling max 100 | DynamoDB auto-scaling cap | Limit burst cost |
| **EKS on-demand baseline** | `Evidence needed: min node count and max node count` | Alert on unexpected baseline growth | Prevent stable node group cost drift |
| **EKS spot worker runtime** | `Evidence needed: max worker node hours/day` | Stop new batch jobs and alert CDO/AIOps | Prevent runaway batch/retraining cost |
| **Container Insights log volume** | `Evidence needed: GB/day threshold` | Lower verbosity or shorten retention after approval | Prevent observability cost spikes |

**Monitoring dashboard**: CloudWatch dashboard `FinOpsWatch-CDO-CostGuardrails` shows:
- Daily spend trend (last 7 days)
- Forecast vs actual spend
- Top 5 cost drivers (service breakdown, including EKS/EC2, ALB, VPC endpoints, CloudWatch, Athena)
- Budget utilization %
- Hosted AI runtime cost separated from AIOps model-development cost

---

## 7. Production Cost Recommendations

After completing the 2-week capstone with actual baseline, the following recommendations should be considered for long-term production deployment:

| Recommendation | When to Apply | Estimated Savings | Conditions |
|---|---|---|---|
| **Compute Savings Plans** | After 3-month baseline | 20-30% on stable on-demand nodes | Only for predictable `ai-engine-api`, explainer, ingress, monitoring, and core CDO services. |
| **S3 Intelligent-Tiering** | Immediately | 10-15% storage cost | Replace manual lifecycle rules |
| **DynamoDB Reserved Capacity** | After 6-month baseline | 40-60% DDB cost | When provisioned is cheaper than on-demand |
| **VPC Endpoint consolidation** | When multi-workload exists | 50% endpoint cost | Share endpoints across platforms |
| **CloudWatch Logs export to S3** | Immediately | 70% log storage cost | Logs >14 days export to S3 IA |
| **Cross-region replication** | Only when DR required | Avoid 2× storage cost | Don't enable if not necessary |
| **QuickSight Enterprise** | When >10 Finance users | Reduce per-user cost | $18/user/month vs $5 Reader |
| **Athena query result caching** | Immediately | 30-50% repeat query cost | Dashboard refresh uses 24h cache |
| **KMS key consolidation** | When compliance signed-off | 33% KMS cost | Use 1 CMK for data + audit instead of 3 keys |
| **Spot diversification** | When batch workload is active | 20-50% worker cost stability | Use multiple instance families and AZs for `ai-engine-worker` capacity. |
| **Karpenter consolidation** | After workload pattern is known | 15-40% EKS worker cost | Consolidate underused nodes and expire idle capacity safely. |
| **Image retention policy** | Immediately | 10-30% ECR storage | Keep required release history but expire unreferenced build images. |

**Estimated total savings when applying all recommendations**: `Evidence needed: long-term measured baseline`. The largest likely savings areas are on-demand node right-sizing, spot worker scheduling, log retention, Athena partition pruning, and endpoint sharing.

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
| **EKS baseline oversized** | +$100-500/month | Medium | Right-size on-demand node group, review requests/limits, use autoscaling. |
| **Spot worker runaway** | +$50-300/day | Medium | Worker max node count, job TTL, checkpoint/retry limits, AIOps cost tags. |
| **Container Insights high cardinality metrics** | +$20-200/month | Medium | Limit custom labels, control scrape intervals, retention policies. |
| **Internal load balancer idle cost** | Fixed monthly cost | Certain | Share endpoint where safe, avoid public ALB, measure LCU/NLCU. |
| **Unclear AIOps/CDO cost ownership** | Budget disputes | Medium | Tag AI runtime separately from AIOps model development/training. |

---

## 9. Open Questions

- [ ] **Q1**: What EKS on-demand instance type and minimum node count are approved for `ai-engine-api`, `ai-engine-explainer`, ingress, monitoring, and core CDO services?
- [ ] **Q2**: What maximum spot worker node hours/day may AIOps consume on the CDO-hosted EKS cluster during capstone?
- [ ] **Q3**: What tag scheme separates CDO platform baseline, CDO adapter runs, hosted AI runtime, and AIOps model-development cost?
- [ ] **Q4**: What capstone budget should replace the older serverless-only $50-100 assumption now that EKS hosting is in scope?
- [ ] **Q5**: How many Finance users need QuickSight access during demo and production-readiness review?
- [ ] **Q6**: Which measured costs are required for the final presentation: 14-day actual, per-run actual, per-account actual, or cost-per-correct-decision?

---

## Related Documents

- [`01_requirements_analysis.md`](01_requirements_analysis.md) - Hard requirements on precision/FP and constraints on cadence/data source affecting cost
- [`02_infra_design.md`](02_infra_design.md) - Lakehouse-centric architecture and EKS hosting determine compute/storage/network cost model
- [`03_security_design.md`](03_security_design.md) - VPC Endpoints, KMS CMKs, CloudTrail are security cost drivers
- [`04_deployment_design.md`](04_deployment_design.md) - CI/CD pipeline cost (GitHub Actions, CodeDeploy), observability stack cost
- [`07_test_eval_report.md`](../../../template-docs/07_test_eval_report.md) - Future test evidence should validate cost assumptions in section 5 of this doc

---

**Approval**: This document needs review by mentor, Finance stakeholder, CDO platform owner, and AIOps representative before committing the baseline cost model for the W12 T5 demo.
