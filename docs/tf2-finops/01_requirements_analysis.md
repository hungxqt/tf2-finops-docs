# Requirements Analysis - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) → Refined (W12 T4 Pack #2)
-->

## 1. Context

Task Force 2 is building the **FinOps Watch** platform for the CFO of a mid-size company operating a multi-account AWS environment (~80 engineers across 12 squads). Last month, the company experienced a 2.3× spike in its AWS bill, which surged from a baseline of ~$180k to ~$420k. The root cause was a forgotten training cluster running in a non-production account, consuming ~$400/day for 18 days (~$7k wasted). It took the Finance team nearly a week to trace and identify this waste.

The CFO wants a continuous **FinOps Watch** system running on a defined cadence that pulls cost data (CUR and Cost Explorer API), detects anomalies with measurable precision and false-positive rates, routes alerts to the correct teams (Finance vs. Engineering), and triggers safe, automated containment actions for obvious waste patterns (e.g., idle resources, mis-tagged spend, runaway training clusters).

The CDO team is responsible for the FinOps control plane, building a lakehouse-centric architecture to ingest and process cost data, orchestration workflow, operational state management, dashboard views, alert routing, containment guardrails, and audit logs. The CDO team also hosts the AI Engine provided by the AIOps team on AWS EKS, dividing workloads between on-demand and spot node groups.

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
| AI Engine hosting uptime | ≥99.5% availability for the hosted model API | CDO hosted AI Engine API on EKS must be reliable for synchronous inference. |

## 3. Differentiation angle (KEY)

- **Angle chosen**: Lakehouse-centric FinOps control plane with serverless orchestration and CDO-hosted AI Engine on AWS EKS.
- **Why this angle**: Production FinOps follows a natural 24h cadence based on CUR data export intervals. Ingesting CUR and Cost Explorer API data into a lakehouse (S3 + Glue + Athena) allows for structured historical query access, auditability, and finance-friendly materialized views. The AI Engine is deployed on a dedicated EKS cluster, utilizing managed node groups to optimize costs: stable APIs (inference/explainer) run on on-demand nodes, while heavy batch workloads (batch scoring, feature engineering, model retraining) run on spot nodes. This hybrid design minimizes idle compute costs and guarantees platform scalability.
- **Trade-off accepted**: Operational complexity of running EKS and Helm/GitOps deployment pipelines, compared to a pure serverless container setup. This is accepted because EKS provides granular control over workload placement (on-demand vs. spot node affinity), network isolation (network policies), and scales efficiently for large batch/training jobs.
- **Lock date**: 2026-06-23 (enforcing W11 design lock).

## 4. CDO vs AIOps responsibility split

The responsibility boundary between the CDO and AIOps teams is defined as follows:

| Responsibility | CDO | AIOps |
|---|---|---|
| Ingest cost data (CUR, Cost Explorer API) | Owns | |
| Normalize cost windows & schema validation | Owns | |
| Tag metadata & resource ownership resolution | Owns | |
| Orchestration workflow (Step Functions) | Owns | |
| Run state, idempotency & scheduling | Owns | |
| Finance-friendly dashboard views (QuickSight/Athena) | Owns | |
| Alert routing (Finance vs. Engineering channels) | Owns | |
| Safe containment guardrails & audit log trail | Owns | |
| EKS Cluster Hosting Platform (Cluster lifecycle, IAM roles, VPC networking) | Owns | |
| EKS Managed Node Groups (On-demand/Spot configurations) | Owns | |
| Deployment pipelines (Helm, GitOps, IaC) for AI workloads | Owns | |
| Runtime monitoring & autoscaling (HPA/KEDA) | Owns | |
| AI Engine model internals, logic & code | | Owns |
| Model training, retraining & hyperparameter selection | | Owns |
| Confidence scoring & anomaly classification logic | | Owns |
| Explanatory text & natural language summaries | | Owns |
| Model versioning & artifact publishing | | Owns |
| AI model backtest performance and metrics | | Owns |
| Versioned container artifacts (images, weights, configs) | | Provides |

*Note: The CDO team consumes the AI Engine through a versioned API contract exposed via the internal service endpoint on EKS. AIOps delivers versioned container images and model weights, while CDO manages the operational execution, scaling, and fault tolerance.*

## 5. Constraints

- **AWS only**: No multi-cloud architectures. All services must deploy in `ap-southeast-1`.
- **Synthetic data only**: Production data is simulated using synthetic cost injection unless the client explicitly grants access to a real billing profile.
- **Backtest target**: The AI Engine must achieve a precision of ≥80% and a false-positive rate of ≤10% over a 3-month historical test period. CDO stores these metrics as integration evidence.
- **Cadence**: 24h scheduled batch processing.
- **NEVER terminate prod, NEVER delete data, NEVER modify IAM**: Absolute hard safety boundaries. Any auto-containment action on production resources is strictly prohibited. Production actions are limited to: tag, suggest, or dry-run.
- **Dry-run mode**: Mandatory for all containment patterns across all environments.
- **Audit trail**: Required for every containment proposal or execution, with a minimum retention period of 90 days.
- **Dashboard accessibility**: Visual dashboard tailored for Finance stakeholders without requiring SQL knowledge.
- **Code freeze**: Wednesday W12.

## 6. Open questions

- [ ] **AWS multi-account topology**: What is the exact number of AWS accounts to onboard, and are OIDC role trusts established?
- [ ] **CUR export latency**: Is CUR 2.0 configured with parquet format and hourly partition exports in the target S3 bucket?
- [ ] **Tagging compliance baseline**: What percentage of existing resources are properly tagged with `owner` and `squad` keys?
- [ ] **Escalation SLA**: How long should a containment action wait in `dry-run` or approval state before being escalated to manual engineering review?
- [ ] **AIOps API contract freeze**: Has the payload structure for the `/detect` API been finalized and frozen?
- [ ] **Budget ceiling**: What is the budget limit for the CDO EKS hosting platform (control plane + node groups) during the capstone period?
- [ ] **Identity management**: Will QuickSight dashboard access be integrated with the client's corporate Identity Provider (IdP) via SAML/OIDC?
- [ ] **Spot reclamation strategy**: Is there a pre-defined checkpoint bucket and format for AIOps batch training jobs to handle spot node interruptions?
