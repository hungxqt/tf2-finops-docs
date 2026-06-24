# Requirements Analysis - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) -> Refined (W12 T4 Pack #2)
-->

## 1. Context

Task Force 2 is building the **FinOps Watch** platform for the CFO of a mid-size company operating a multi-account AWS environment (~80 engineers across 12 squads). Last month, the company experienced a 2.3× spike in its AWS bill, which surged from a baseline of ~$180k to ~$420k. The root cause was a forgotten training cluster running in a non-production account, consuming ~$400/day for 18 days (~$7k wasted). It took the Finance team nearly a week to trace and identify this waste.

The CFO wants a continuous **FinOps Watch** system running on a defined cadence that pulls cost data (CUR and Cost Explorer API), detects anomalies with measurable precision and false-positive rates, routes alerts to the correct teams (Finance vs. Engineering), and triggers safe, automated containment actions for obvious waste patterns (e.g., idle resources, mis-tagged spend, runaway training clusters).

The CDO team is responsible for the FinOps control plane, building a lakehouse-centric architecture to ingest and process cost data, orchestration workflow, operational state management, dashboard views, alert routing, containment guardrails, and audit logs. The CDO team also hosts the AI Engine provided by the AIOps team on AWS ECS (specifically within the ECS cluster 'tf-2-aiops-cluster'), dividing workloads between Fargate always-on capacity provider tasks and Fargate Spot capacity provider tasks.

The AIOps team owns any synthetic historical dataset used to train, enhance, calibrate, or backtest the anomaly model. The CDO documentation treats that dataset as upstream model-quality input, not as a CDO platform sizing source or operational data source. CDO consumes the model through a signed API contract, persists the returned decision evidence, and proves that alerting and containment policy are applied safely.

For Finance stakeholders, success means the dashboard can answer four questions without SQL: what changed, which account or squad owns it, how confident the platform is, and what action is allowed. For CDO reviewers, success means every scheduled run has a traceable input window, idempotency key, AI Engine contract version, alert decision, containment mode, and audit record.

## 2. Infra non-functional requirements

The CDO platform must meet the following non-functional requirements (NFRs) to ensure operational readiness:

| NFR | Target | Justification |
|---|---|---|
| Scheduled processing cadence | 24h default | Defends trade-off between CUR/Cost Explorer data availability, operational cost, and false-positive control. |
| Availability | ≥99.5% for scheduled run workflows and dashboards | Ensures consistent execution of the cost inspection pipeline. |
| Auditability | ≥90 days retention, append-only logs for containment | Mandatory client requirement for compliance and traceback. |
| Dashboard readability | Finance-friendly UI, zero SQL knowledge required | CFO's team must understand cost anomalies without technical queries. |
| Cost per run | Minimize; tracked with `Evidence needed: CDO pipeline run costs` | Ensures the platform itself is cost-effective. |
| Security baseline | IAM least-privilege, multi-account read-only access | Core boundary: NEVER terminate prod, delete data, or modify IAM. |
| AI Engine hosting uptime | ≥99.5% availability for the hosted model API | CDO hosted AI Engine API on ECS must be reliable for synchronous inference. |
| Cost data contract coverage | Account, service, region, resource, tag, cost period, USD amount, and estimated/final flag | Ensures CDO sends enough operational context to the AIOps AI Engine without owning model training data. |
| Idempotency | One accepted run per account and cost window | Prevents duplicate alerts, duplicate AI Engine calls, and double-counted dashboard materializations. |
| Alert explainability | Every anomaly alert includes confidence, severity, evidence window, owner route, and explanation | Finance and Engineering must be able to decide whether the alert is valid and what to do next. |
| Containment safety | Prod limited to tag, suggest, or dry-run; non-prod actions require policy approval | Keeps automation useful without crossing the client hard boundary. |

The NFRs are intentionally written as operational targets, not only architecture preferences. The CDO platform can pass the capstone only if it can prove that the daily workflow ran, that the AI Engine was invoked through the agreed contract, that model outputs were validated before use, and that every recommended action is auditable for at least 90 days.

## 3. Differentiation angle (KEY)

- **Angle chosen**: Lakehouse-centric FinOps control plane with serverless orchestration and CDO-hosted AI Engine on AWS ECS (specifically within the ECS cluster 'tf-2-aiops-cluster').
- **Why this angle**: Production FinOps follows a natural 24h cadence based on CUR data export intervals. Ingesting CUR and Cost Explorer API data into a lakehouse (S3 + Glue + Athena) allows for structured historical query access, auditability, and finance-friendly materialized views. The AI Engine is deployed on a dedicated ECS cluster (tf-2-aiops-cluster), utilizing Fargate Capacity Providers to optimize costs: stable APIs (inference/explainer) run on Fargate always-on capacity provider tasks, while heavy batch workloads (batch scoring, feature engineering, model retraining) run on Fargate Spot capacity provider tasks. This hybrid design minimizes idle compute costs and guarantees platform scalability.
- **Trade-off accepted**: Operational complexity of running ECS and Terraform ECS configuration and GitHub Actions (CI/CD) deployment pipelines, compared to a pure serverless container setup. This is accepted because ECS provides granular control over workload placement (always-on vs. Spot capacity provider allocation), network isolation (security groups), and scales efficiently for large batch/training jobs.
- **Lock date**: 2026-06-23 (enforcing W11 design lock).

The differentiation is not "use AI for FinOps"; that ownership belongs to AIOps. The CDO differentiation is the control plane around the AI decision: repeatable data pulls, queryable historical evidence, versioned model invocation, safe routing, policy-enforced containment, and finance-readable reporting. A purely dashboard-centric approach would show spend but not close the loop. A purely automation-centric approach would act too aggressively without enough evidence. The chosen angle keeps the daily FinOps loop measurable and reversible.

The integration contract reinforces this angle. CDO normalizes AWS billing inputs before invoking the AI Engine, keeps the model invocation versioned, and records enough evidence for Finance and Engineering to understand the decision path. AIOps can improve the model independently, while CDO keeps the operational loop stable.

## 4. CDO vs AIOps responsibility split

The responsibility boundary between the CDO and AIOps teams is defined as follows:

| Responsibility | CDO | AIOps |
|---|---|---|
| Ingest cost data (CUR, Cost Explorer API) | Owns | |
| Normalize cost windows & schema validation | Owns | |
| Tag metadata & resource ownership resolution | Owns | |
| Orchestration workflow (Step Functions) | Owns | |
| Run state, idempotency & scheduling | Owns | |
| Finance-friendly dashboard views (S3 + CloudFront dashboard backed by Athena/DynamoDB summaries) | Owns | |
| Alert routing (Finance vs. Engineering channels) | Owns | |
| Safe containment guardrails & audit log trail | Owns | |
| ECS Cluster Hosting Platform (Cluster lifecycle, ECS Task Role, ECS Task Execution Role, VPC networking) | Owns | |
| ECS Fargate Capacity Providers (always-on/Spot configurations) | Owns | |
| Deployment pipelines (Terraform ECS configuration, GitHub Actions (CI/CD) deployment pipelines, IaC) for AI workloads | Owns | |
| Runtime monitoring & autoscaling (ECS Service Auto Scaling (using CPU target tracking 70% and SQS step scaling)) | Owns | |
| AI Engine model internals, logic & code | | Owns |
| Model training, retraining & hyperparameter selection | | Owns |
| Confidence scoring & anomaly classification logic | | Owns |
| Explanatory text & natural language summaries | | Owns |
| Model versioning & artifact publishing | | Owns |
| AI model backtest performance and metrics | | Owns |
| Versioned container artifacts (images, weights, configs) | | Provides |

*Note: The CDO team consumes the AI Engine through a versioned API contract exposed via the internal service endpoint on ECS. AIOps delivers versioned container images and model weights, while CDO manages the operational execution, scaling, and fault tolerance.*

The boundary is enforced at runtime as well as in documentation. CDO validates the `/detect` request and response schema before each compatible release, records the model version returned by AIOps, persists the evidence URI for every anomaly, and fails closed when the AI Engine is unavailable or returns an invalid payload. AIOps remains accountable for model quality metrics such as precision, recall, confidence calibration, and explanation logic, while CDO remains accountable for whether those outputs are used safely in alerting, dashboarding, and containment workflows.

The minimum AI decision output consumed by CDO is: `run_id`, `model_version`, `anomaly_id`, `tenant/account`, `anomaly_type`, `confidence`, `severity`, `expected_spend`, `actual_spend`, `delta`, `evidence_window`, `explanation`, `recommended_route`, `recommended_containment_mode`, and `evidence_uri`. Missing required fields block containment and create an operator alert.

### 4.1 Service Level Objectives (SLO) Contract Compliance

The CDO platform consumes the AI Engine API according to the Service Level Objectives (SLOs) defined in `ai-api-contract.md` §6. The integration must be verified and monitored against the following contract-mandated targets:

| SLO Metric | Contract Target | Verification Event |
|---|---|---|
| **Ingestion Latency (P99)** | < 50 ms | Roundtrip processing time of POST `/v1/detect` requests. |
| **Result Query Latency (P99)** | < 10 ms | Time to retrieve records from the DynamoDB Store. |
| **LLM Inference SLA** | < 30 seconds | Amazon Bedrock (Nova LLM) execution window and database write. |
| **System Availability** | >=99.5% | Total uptime of the internal ALB/API Gateway exposed to CDO. |
| **Error Rate** | < 0.5% | System error responses (HTTP 5xx) relative to total requests. |

Any violation of these SLA parameters triggers the fallback runbook (SRE alerting, static rules, or failing closed for containment decisions).

## 5. Constraints

- **AWS only**: No multi-cloud architectures. All services must deploy in `ap-southeast-1`.
- **Synthetic model data is AIOps-owned**: Historical synthetic datasets used for model training, enhancement, or backtesting are owned by AIOps. CDO may reference AIOps-provided metrics, but must not claim ownership of the model dataset.
- **Backtest target**: The AI Engine must achieve a precision of ≥80% and a false-positive rate of ≤10% over a 3-month historical test period. CDO stores these metrics as integration evidence.
- **Cadence**: 24h scheduled batch processing.
- **NEVER terminate prod, NEVER delete data, NEVER modify IAM**: Absolute hard safety boundaries. Any auto-containment action on production resources is strictly prohibited. Production actions are limited to: tag, suggest, or dry-run.
- **Dry-run mode**: Mandatory for all containment patterns across all environments.
- **Audit trail**: Required for every containment proposal or execution, with a minimum retention period of 90 days.
- **Dashboard accessibility**: Visual dashboard tailored for Finance stakeholders without requiring SQL knowledge.
- **Code freeze**: Wednesday W12.
- **CDO demo data**: CDO may use synthetic anomaly injections for integration smoke tests, dashboard demonstrations, and containment dry-runs only. These demo events are not AI training evidence.
- **Region**: Primary implementation target is `ap-southeast-1`.
- **Containment scope**: At least one non-prod containment path may be implemented, but prod containment remains tag/suggest/dry-run only regardless of anomaly confidence.
- **Measurement honesty**: Unmeasured run cost, dashboard latency, alert delivery latency, AI inference latency, and actual precision results must remain marked as `Evidence needed: ...` until the team captures evidence.

These constraints define what the CDO platform must not do. The system is allowed to detect, explain, route, tag, suggest, and simulate containment. It is not allowed to become an unrestricted cleanup bot, a billing-data exfiltration path, or an IAM automation tool.

## 6. Open questions

- [ ] **AWS multi-account topology**: What is the exact number of AWS accounts to onboard, and are OIDC role trusts established?
- [ ] **CUR export latency**: Is CUR 2.0 configured with parquet format and hourly partition exports in the target S3 bucket?
- [ ] **Tagging compliance baseline**: What percentage of existing resources are properly tagged with `owner` and `squad` keys?
- [ ] **Escalation SLA**: How long should a containment action wait in `dry-run` or approval state before being escalated to manual engineering review?
- [ ] **AIOps API contract freeze**: Has the payload structure for the `/detect` API been finalized and frozen?
- [ ] **Budget ceiling**: What is the budget limit for the CDO ECS hosting platform (control plane + Fargate capacity provider tasks) during the capstone period?
- [ ] **Identity management**: Will the S3 + CloudFront dashboard access be integrated with the client's corporate Identity Provider (IdP) (e.g., via CloudFront + Cognito or OIDC), and when should QuickSight be introduced as a future BI integration?
- [ ] **Spot reclamation strategy**: Is there a pre-defined checkpoint bucket and format for AIOps batch training jobs to handle Fargate Spot task interruptions?
- [ ] **False-positive approval calendar**: Can Finance provide known migration, load-test, and flash-sale windows to AIOps for model calibration and to CDO for alert annotation?
- [ ] **Dashboard decision owner**: Which Finance role signs off on severity labels, budget thresholds, and escalation wording used in executive-facing views?
- [ ] **Containment approval owner**: For non-prod apply-mode actions, does approval come from the squad owner, platform owner, or Finance owner?
- [ ] **Evidence retention format**: Should long-term evidence be retained only as Athena-queryable S3 objects, or duplicated into DynamoDB materialized records for dashboard speed?
