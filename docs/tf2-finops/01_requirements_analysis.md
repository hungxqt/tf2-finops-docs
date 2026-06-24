# Requirements Analysis - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) -> Refined (W12 T4 Pack #2)
-->

## 1. Context

Task Force 2 is building the **FinOps Watch** platform for the CFO of a mid-size company operating a multi-account AWS environment (~80 engineers across 12 squads). Last month, the company experienced a 2.3× spike in its AWS bill, which surged from a baseline of ~$180k to ~$420k. The root cause was a forgotten training cluster running in a non-production account, consuming ~$400/day for 18 days (~$7k wasted). It took the Finance team nearly a week to trace and identify this waste.

The CFO wants a continuous **FinOps Watch** system running on a defined cadence that pulls cost data (CUR and Cost Explorer API), detects anomalies with measurable precision and false-positive rates, routes alerts to the correct teams (Finance vs. Engineering), and triggers safe, automated containment actions for obvious waste patterns (e.g., idle resources, mis-tagged spend, runaway training clusters).

The CDO team is responsible for the FinOps control plane, building a lakehouse-centric architecture to ingest and process cost data (S3 CUR partition pulls and Cost Explorer API calls), orchestration workflows, operational state management, dashboard views, alert routing, containment guardrails, and audit logs. The CDO team also deploys and operates the Lambda container hosting infrastructure (VPC, subnets, Lambda execution roles, reserved concurrency, SQS/DLQ async queues, and DynamoDB/S3 state stores) for hosting the AIOps-provided AI Engine. In the default scheduled batch workflow, the central Step Functions orchestrator invokes the AI Engine Request Lambda directly, which publishes the request to an SQS queue. The AI Engine Worker Lambda processes tasks from the queue asynchronously and writes results directly to DynamoDB and S3. Note that `/v1/detect` and `/v1/detect/result/{audit_id}` represent logical contract semantics for model integration, not deployed REST/HTTP routes in this baseline batch workflow, as no Private API Gateway is deployed. Workloads are run as serverless container image executions on AWS Lambda, optimized with SQS for async processing. AIOps owns the Lambda-compatible AI Engine container image, model code, detection logic, explanation text, and backtest metrics.

The AIOps team owns any synthetic historical dataset used to train, enhance, calibrate, or backtest the anomaly model. The CDO documentation treats that dataset as upstream model-quality input, not as a CDO platform sizing source or operational data source. CDO consumes the model through a signed API contract, sends strictly CUR-only cost data (excluding CloudWatch utilization signals like CPUUtilization, DatabaseConnections, or memory_mib which are reserved only for platform operational observability), persists the returned decision evidence, and proves that alerting and containment policy are applied safely.

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
| AI Engine hosting uptime | ≥99.5% availability for the hosted model functions | CDO hosted AI Engine functions (Request and Worker Lambdas) must be reliable for direct execution. |
| Cost data contract coverage | CUR-only cost data (account, service, region, resource, tag, cost period, USD amount, estimated/final flag); excludes CloudWatch utilization metrics (CPU, memory, database connections) for anomaly detection | Ensures CDO sends enough operational context to the AIOps AI Engine without owning model training data. Performance metrics are used ONLY for platform operational observability (alerts, logging, metrics, dashboard). |
| Idempotency | One accepted run per account and cost window | Prevents duplicate alerts, duplicate AI Engine calls, and double-counted dashboard materializations. |
| Alert explainability | Every anomaly alert includes confidence, severity, evidence window, owner route, and explanation | Finance and Engineering must be able to decide whether the alert is valid and what to do next. |
| Containment safety | Prod limited to tag, suggest, or dry-run; non-prod actions require policy approval | Keeps automation useful without crossing the client hard boundary. |

The NFRs are intentionally written as operational targets, not only architecture preferences. The CDO platform can pass the capstone only if it can prove that the daily workflow ran, that the AI Engine was invoked through the agreed contract, that model outputs were validated before use, and that every recommended action is auditable for at least 90 days.

## 3. Differentiation angle (KEY)

- **Angle chosen**: Lakehouse-centric FinOps control plane with serverless orchestration and CDO-hosted AI Engine on AWS Lambda container images.
- **Why this angle**: Production FinOps follows a natural 24h cadence based on CUR data export intervals. Ingesting CUR and Cost Explorer API data into a lakehouse (S3 + Glue + Athena) allows for structured historical query access, auditability, and finance-friendly materialized views. The AI Engine is hosted as a Lambda container image deployed via ECR. To optimize costs and operational overhead, the platform uses serverless compute (no idle cluster costs), SQS/DLQ queues for asynchronous worker tasks, direct Step Functions to Lambda invocation for batch jobs, and Lambda reserved concurrency as the default guardrail (with Provisioned Concurrency as an optional production optimization). This serverless container image approach minimizes fixed runtime costs while removing API Gateway overhead.
- **Trade-off accepted**: Cold-start latency of Lambda container image functions (typically 1-5 seconds during container pull and initialization), compared to always-on VMs. This is accepted because the 24h cadence does not require sub-second synchronous API response times, and asynchronous SQS integration allows the Request Lambda (representing logical `/v1/detect` semantics) to return quickly to the orchestrator while worker Lambda tasks write results to DynamoDB/S3.
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
| Lambda Container Platform hosting AI Engine (VPC integration, Execution Roles, Reserved Concurrency) | Owns | |
| Lambda concurrency controls (Reserved / Provisioned Concurrency, SQS/DLQ configuration) | Owns | |
| Deployment pipelines (ECR image digest pinning, Lambda alias routing, IaC) for AI workloads | Owns | |
| Runtime monitoring & concurrency control (Lambda reserved concurrency, CloudWatch logs, and X-Ray) | Owns | |
| AI Engine model internals, logic & code | | Owns |
| Model training, retraining & hyperparameter selection | | Owns |
| Confidence scoring & anomaly classification logic | | Owns |
| Explanatory text & natural language summaries | | Owns |
| Model versioning & artifact publishing | | Owns |
| AI model backtest performance and metrics | | Owns |
| Versioned container artifacts (images, weights, configs) | | Provides |

*Note: The CDO team consumes the AI Engine through a versioned programmatic contract via direct Lambda execution (representing logical `/v1/detect` and `/v1/detect/result/{audit_id}` semantics). The responsibility split is defined such that CDO owns the hosting infrastructure (VPC, subnets, Lambda functions, execution roles, reserved concurrency, SQS/DLQ async queues, and DynamoDB/S3 stores), while AIOps owns the Lambda-compatible AI Engine container image, model code, detection logic, explanation text, and backtest metrics. Detection telemetry is strictly CUR-only (S3 CUR partition pulls and Cost Explorer API calls) and does NOT include CloudWatch utilization metrics (CPU, memory, database connections), which are used ONLY for platform operational observability (alerts, logging, metrics, dashboard).*

*Note on Contract Wording*: The signed API contract (`ai-api-contract.md`) was established under the baseline assumption of ECS/ALB hosting. Since the platform architecture has migrated to serverless Lambda container hosting, any outdated ECS or ALB wording in the signed contract document itself requires a formal contract change request if/when that contract is later updated. For now, the contract document remains unchanged.

The boundary is enforced at runtime as well as in documentation. CDO validates the `/v1/detect` request and response schema before each compatible release, records the model version returned by AIOps, persists the evidence URI for every anomaly, and fails closed when the AI Engine is unavailable or returns an invalid payload. AIOps remains accountable for model quality metrics such as precision, recall, confidence calibration, and explanation logic, while CDO remains accountable for whether those outputs are used safely in alerting, dashboarding, and containment workflows.

The minimum AI decision output consumed by CDO is: `run_id`, `model_version`, `anomaly_id`, `tenant/account`, `anomaly_type`, `confidence`, `severity`, `expected_spend`, `actual_spend`, `delta`, `evidence_window`, `explanation`, `recommended_route`, `recommended_containment_mode`, and `evidence_uri`. Missing required fields block containment and create an operator alert.

### 4.1 Service Level Objectives (SLO) Contract Compliance

The CDO platform consumes the AI Engine API according to the Service Level Objectives (SLOs) defined in `ai-api-contract.md` §6. The integration must be verified and monitored against the following contract-mandated targets:

| SLO Metric | Contract Target | Verification Event |
|---|---|---|
| **Ingestion Latency (P99)** | < 50 ms | Roundtrip processing time of POST `/v1/detect` requests. |
| **Result Query Latency (P99)** | < 10 ms | Time to retrieve records from the DynamoDB Store. |
| **LLM Inference SLA** | < 30 seconds | Amazon Bedrock (Nova LLM) execution window and database write. |
| **System Availability** | >=99.5% | Total availability of the direct Lambda/SQS execution path. |
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
- [ ] **AIOps API contract freeze**: Has the payload structure for the `/v1/detect` API been finalized and frozen?
- [ ] **Budget ceiling**: What is the budget limit for the CDO Lambda container hosting platform (Lambda execution duration, SQS/DLQ queues, and Provisioned Concurrency options) during the capstone period?
- [ ] **Identity management**: Will the S3 + CloudFront dashboard access be integrated with the client's corporate Identity Provider (IdP) (e.g., via CloudFront + Cognito or OIDC), and when should QuickSight be introduced as a future BI integration?
- [ ] **Model retraining deployment**: How often does AIOps retrain the model, and how are new image digests communicated to CDO for deployment in ECR and Lambda digest pinning?
- [ ] **False-positive approval calendar**: Can Finance provide known migration, load-test, and flash-sale windows to AIOps for model calibration and to CDO for alert annotation?
- [ ] **Dashboard decision owner**: Which Finance role signs off on severity labels, budget thresholds, and escalation wording used in executive-facing views?
- [ ] **Containment approval owner**: For non-prod apply-mode actions, does approval come from the squad owner, platform owner, or Finance owner?
- [ ] **Evidence retention format**: Should long-term evidence be retained only as Athena-queryable S3 objects, or duplicated into DynamoDB materialized records for dashboard speed?
