# Architecture Decision Records - FinOps Watch CDO · Task Force 2

<!-- Doc owner: CDO Team
     Status: Ongoing log W11-W12
     Format: 1 ADR per major decision. Append-only - do not delete old ADRs. -->

> **Safety Boundary**: All architectural decisions and system design patterns must uphold the absolute safety boundaries: **NEVER terminate prod, delete data, or modify IAM**.


> **What is an ADR**: An Architecture Decision Record (ADR) is a log of important architectural decisions made along with the context and rationale behind them. The goal is to ensure that future developers understand why a particular path was chosen over alternatives.
>
> **When to write an ADR**:
> - The decision involves real trade-offs (selecting Option X has a cost, selecting Option Y has a benefit).
> - The decision has a high reversal cost (e.g., changing the compute target requires rebuilding the infrastructure).
> - The decision is likely to be questioned during architectural reviews or defenses.
>
> **Do not write an ADR for**: Minor decisions without trade-offs (resource naming, minor coding conventions, etc.).
>
> **When an old ADR is no longer applicable**: Mark it as `Status: Superseded by ADR-NNN`. Do not delete the old ADR. The log is append-only.

---

## ADR-001 - 24h cadence over 12h/48h

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: The platform requires a scheduled data processing cadence to detect cost anomalies. The team must balance the speed of detection with AWS billing export latency (CUR), API costs (Cost Explorer), compute resource consumption, and the risk of false positives from transient hourly spend spikes.
- **Decision**: Select a 24-hour processing cadence for the scheduled FinOps pipeline, triggered daily by EventBridge Scheduler.
- **Consequence**:
  - Pro: Aligns perfectly with the 24-hour update cycles of AWS CUR and cost explorer aggregates, avoiding unnecessary duplicate runs.
  - Pro: Dramatically reduces query costs and compute time compared to 12-hour or hourly cadences.
  - Pro: Minimizes false alarms from transient intraday resource scaling that naturally resolves within a business day.
  - Trade-off: Maximum time to detect an anomaly is 24 hours, which may result in higher cost leakage for sudden, massive spend spikes.
- **Alternatives considered**:
  - 12h cadence: Rejected because AWS billing data (CUR) is not updated frequently enough to justify doubling the API cost and compute runs.
  - 48h cadence: Rejected because a 2-day detection delay exposes the organization to excessive financial waste before containment policies can be proposed.

---

## ADR-002 - Lakehouse-centric FinOps control plane architecture

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: The platform must ingest, partition, analyze, and report large volumes of AWS cost data. The data store must be scale-invariant, cost-effective for long-term storage, and support ad-hoc SQL queries without requiring permanent database server compute.
- **Decision**: Implement a lakehouse-centric data plane using Amazon S3 for raw and curated data storage, AWS Glue Data Catalog for metadata mapping, and Amazon Athena for serverless SQL querying.
- **Consequence**:
  - Pro: Serverless model means zero idle infrastructure costs for the query layer.
  - Pro: S3 lifecycle policies can automatically archive historical CUR partitions to Glacier, minimizing long-term storage costs.
  - Pro: Highly scalable, supporting analytical queries across millions of cost records.
  - Trade-off: Athena queries have a query start latency (cold start) of a few seconds, making them unsuitable for real-time transactional web queries (mitigated by using DynamoDB for dashboard and transactional lookups).
- **Alternatives considered**:
  - Relational Database (RDS PostgreSQL): Rejected due to high running cost for always-on database instances and complex scaling of storage when processing massive historical billing data.
  - NoSQL only (DynamoDB): Rejected due to lack of complex analytical capabilities, joining functions, and partitioning tools for CUR analysis.

---

## ADR-003 - CDO/AIOps responsibility boundary

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: Clear division of labor is needed between the CDO team (platform and pipeline operators) and the AIOps team (AI engine developers) to prevent duplicate efforts, establish ownership, and define operational SLAs.
- **Decision**: Establish a strict contract-based integration. CDO owns cost data ingestion, scheduled workflows, alerting, containment enforcement, and the hosting platform infrastructure (Lambda container functions, ECR digest deployment, execution roles, reserved concurrency, SQS/DLQ, DynamoDB/S3 stores, networking, and SLOs) for the AI Engine. AIOps owns the AI Engine logic, container image software, model parameters, confidence scoring, and backtesting metrics.
- **Consequence**:
  - Pro: Independent release cycles and isolation of responsibilities. Clear ownership for incident triage.
  - Pro: Standardized contract prevents breaking changes when the AI model is updated.
  - Trade-off: Requires maintaining a versioned integration contract and mock endpoints for local testing.
- **Alternatives considered**:
  - Monolithic team model: Rejected because it blurs technical domains and makes it difficult to scale separate platform operations and model tuning tracks.
  - AIOps hosting their own service: Rejected because CDO needs tight control over networking, IAM security, and containment integration within the primary cloud landing zone.

---

## ADR-004 - CUR S3 plus Cost Explorer API data access

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: The platform requires both detailed resource-level cost metrics (which are highly structured) and daily cost data queries to catch anomaly patterns.
- **Decision**: Combine AWS Data Exports (CUR 2.0) delivered to S3 with direct queries to the AWS Cost Explorer API. CUR is used for historical deep dives, partition analysis, and dashboard trends, while Cost Explorer API serves as the primary daily querying mechanism for scheduled runs. To prevent exceeding the strict **5 requests/second** Cost Explorer rate limit, CDO caches query results in DynamoDB; the AI Engine consumes this cached cost data for its 7-day and 30-day baseline requirements instead of querying the Cost Explorer API directly.
- **Consequence**:
  - Pro: CUR provides granular resource-level records for audit and dashboard visibility.
  - Pro: Cost Explorer API provides low-latency data for the last 24-hour period, bypassing CUR export delays.
  - Pro: Caching cost data in DynamoDB avoids rate-limiting issues and guarantees stable offline access for the AI Engine.
  - Trade-off: Introduces minor discrepancies between final CUR records and real-time Cost Explorer API outputs due to AWS reconciliation delays.
- **Alternatives considered**:
  - CUR only: Rejected because CUR exports have an inherent lag of 8 to 24 hours, violating data freshness requirements for daily detection.
  - Cost Explorer API only: Rejected because querying large volumes of historical resource-level data via the API is highly expensive and subject to strict rate limits.

---

## ADR-005 - Dry-run-first containment guardrail

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: Unintended automated containment actions in production environments (like stopping nodes, changing quotas, or modifying security settings) can cause massive business downtime.
- **Decision**: Implement a "dry-run-first" containment policy across all environments. In production, containment is strictly limited to dry-runs (simulations, tagging for review, or suggestions). In development and sandbox environments, automated actions (like resource shutdown) may be applied only after policy verification and record generation.
- **Consequence**:
  - Pro: Zero risk of automated outages in production workloads due to false positive detections.
  - Pro: Still provides complete visibility into what the system would have done.
  - Trade-off: Requires human intervention to execute actual remediation steps in production, slightly extending the time-to-remediate.
- **Alternatives considered**:
  - Full automation everywhere: Rejected due to unacceptable risk of business disruption.
  - Manual notifications only: Rejected because development and sandbox environments benefit from automated containment to prevent budget waste.

---

## ADR-006 - DynamoDB/S3 audit trail with >=90 days retention

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: Financial compliance requires a tamper-proof, durable record of all automated and proposed containment actions, which must be retained for audit purposes.
- **Decision**: Implement a dual-layer audit trail storing containment log records in DynamoDB (for low-latency dashboard query) and S3 with Object Lock enabled (for long-term compliance storage), enforcing a minimum retention period of 90 days.
- **Consequence**:
  - Pro: Complete traceability of automated decisions for financial audits.
  - Pro: S3 Object Lock prevents accidental deletion or modification of records.
  - Trade-off: Slightly higher storage complexity and code footprint to write to two database targets.
- **Alternatives considered**:
  - DynamoDB only: Rejected because DynamoDB tables do not natively support Object Lock (Write Once Read Many - WORM) compliance features.
  - CloudWatch Logs only: Rejected because parsing CloudWatch logs is slow and unsuitable for direct rendering on user-facing finance dashboards.

---

## ADR-007 - ECS Fargate for AI Engine hosting over serverless functions

- **Status**: Superseded by ADR-010
- **Date**: 2026-06-24
- **Context**: The AI Engine provided by the AIOps team is packaged as a containerized python application requiring CPU/memory flexibility, isolated execution, and network security.
- **Decision**: Deploy and host the AI Engine container workloads on AWS ECS (Elastic Container Service) with Fargate.
- **Consequence**:
  - Pro: Serverless compute model eliminates the need to manage EC2 instances or K8s nodes.
  - Pro: Task-level IAM roles isolate permissions, and tasks are run in private subnets behind an internal ALB.
  - Trade-off: Cold start times are higher compared to always-on VMs (mitigated by using always-on capacity providers for the API/explainer tasks).
- **Alternatives considered**:
  - AWS Lambda: Rejected because the AI model library size (e.g., pandas, scikit-learn, PyTorch) exceeds Lambda deployment package limits and run times can exceed Lambda's 15-minute execution limit.
  - Amazon EKS (Kubernetes): Rejected due to high operational complexity and minimum cluster running cost, which is unjustified for this single workload.

---

## ADR-008 - Always-on plus Spot Fargate task separation

- **Status**: Superseded by ADR-010
- **Date**: 2026-06-24
- **Context**: The AI Engine executes both low-latency API tasks (health checks, explaining anomalies for dashboards) and interruptible, computationally intensive batch workloads (daily anomaly scoring, model retraining).
- **Decision**: Separate the ECS task execution across Fargate capacity providers. Use standard Fargate always-on for the API explainer tasks, and Fargate Spot capacity providers for batch analysis, retraining, and feature engineering tasks.
- **Consequence**:
  - Pro: Reduces compute costs by up to 70% for batch and retraining tasks by using Fargate Spot.
  - Pro: Always-on capacity provider ensures the dashboard API is highly available and responsive.
  - Trade-off: Batch jobs must implement checkpoints and retry logic to handle Fargate Spot task interruption events gracefully.
- **Alternatives considered**:
  - Fargate always-on for all tasks: Rejected because it leads to excessive idle compute costs during large batch jobs or model retraining runs.
  - Fargate Spot for all tasks: Rejected because spot interruptions on the API/explainer tasks would disrupt dashboard availability and real-time alerting SLOs.

---

## ADR-009 - Shared Task Force AI Engine endpoint

- **Status**: Superseded by ADR-011
- **Date**: 2026-06-24
- **Context**: Task Force 2 runs two separate FinOps CDO platforms (CDO-01 and CDO-02) representing different business units. To minimize operational costs and simplify model management, we need a deployment architecture for the AIOps AI Engine that hosts it once while serving both CDO platforms securely and efficiently.
- **Decision**: Deploy a single, shared Task Force AI Engine endpoint hosted on ECS Fargate within a shared VPC, accessible internally via `https://ai-engine.tf-2.internal/` using IAM SigV4 authentication. Multi-tenant isolation is maintained using the `X-Tenant-Id` request header to partition data and requests.
- **Responsibility Split**:
  - **CDO** owns the hosting infrastructure deployment: VPC networking (subnets, route tables, VPC endpoints), Internal Application Load Balancer (ALB), DNS record configuration, ECS cluster configuration, task scaling policies, Security Groups, ECS Task Execution and IAM Roles, SQS processing queues, and DynamoDB execution/idempotency state stores.
  - **AIOps** owns the application logic inside the container: the AI model code, container image build and publishing (ECR image payload), Root Cause Analysis (RCA) and remediation recommendation logic, local fallback rules engine execution, internal API contract enforcement, and evaluation baseline tracking.
- **Consequence**:
  - Pro: Dramatically reduces runtime costs by hosting only a single shared ECS Fargate cluster instead of separate clusters for each CDO platform.
  - Pro: Simplifies release management and model updates for AIOps since they publish a single version of the container image.
  - Pro: Direct endpoint access using AWS private DNS (`https://ai-engine.tf-2.internal/`) ensures traffic never traverses the public internet, satisfying security NFRs.
  - Trade-off: Requires coordination between CDO and AIOps for task sizing and autoscaling configurations, as well as strict tenant headers configuration to avoid cross-tenant data leakage.
- **Alternatives considered**:
  - Separate AI Engine per CDO Platform: Rejected due to duplicate resource costs and high maintenance overhead for model versioning and container deployments.
  - Public HTTP Endpoint with API Gateway: Rejected because IAM SigV4-based authentication over private internal load balancers provides stronger transport security and lower latency without exposing endpoints to the internet.

---

## ADR-010 - AWS Lambda container image hosting for AI Engine inference

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: The AI Engine provided by the AIOps team is packaged as a containerized python application requiring CPU/memory flexibility, isolated execution, and network security. The previous decision to use ECS Fargate (ADR-007) and Fargate Spot capacity providers (ADR-008) introduced shared fixed platform costs (idle compute, load balancing) and operational complexity (checkpointing, Spot interruptions).
- **Decision**: Deploy and host a dedicated, per-CDO instance of the AI Engine container workloads on AWS Lambda using container images, rather than sharing a single host ONCE across the Task Force. This CDO hosts its own endpoint/platform utilizing Lambda Container images built from the ECR repository provided by the AIOps team. The deployment utilizes ECR image digest pinning (pinning specific image SHA digests in Terraform) to guarantee execution immutability. CDO implements SQS buffering for reliable asynchronous execution and configures Lambda reserved concurrency limits (capped to a safe execution ceiling) to prevent scaling spikes from throttling other resources, maintain private network boundaries, and control the operational blast radius.
- **Consequence**:
  - Pro: Pay-per-request billing model reduces shared platform idle cost to zero compared to ECS Fargate.
  - Pro: High availability and automatic scaling are handled natively by AWS.
  - Pro: SQS queue buffering handles invocation spikes without losing execution payloads.
  - Pro: ECR digest pinning ensures code changes require an explicit Terraform change-set, preventing drift.
  - Trade-off: Potential container cold start latency (mitigated by Provisioned Concurrency if production latency metrics breach threshold).
  - Trade-off: Container size must stay within the 10 GB Lambda limit; model retraining must be executed offline.
- **Alternatives considered**:
  - ECS Fargate always-on + Spot: Rejected due to high idle compute cost and complex checkpoint/retry requirements.
  - Standard AWS Lambda zip packages: Rejected because the AI model libraries (e.g. pandas, scikit-learn, PyTorch) exceed the 250MB unzipped Lambda deployment package size limit.

---

## ADR-011 - Private REST API Gateway over internal ALB

- **Status**: Superseded by ADR-012
- **Date**: 2026-06-24
- **Context**: The AI Engine API must be accessed securely and privately by multiple CDO platforms within the private network. The previous decision used an internal ALB (ADR-009). However, migrating to AWS Lambda container hosting makes REST API Gateway with Lambda integrations a more natural and secure choice for private API exposure.
- **Decision**: Expose the shared AI Engine endpoints using a Private REST API Gateway with IAM SigV4 authentication and Lambda proxy/container integrations. Multi-tenant isolation is maintained using the `X-Tenant-Id` request header to partition data and requests.
- **Responsibility Split**:
  - **CDO** owns the hosting infrastructure deployment: VPC networking, Private REST API Gateway resources, staging/deployment parameters, IAM execution roles, SQS processing queues, and DynamoDB execution/idempotency state stores.
  - **AIOps** owns the application logic inside the Lambda container: the AI model code, container image build and publishing (ECR image payload), Root Cause Analysis (RCA) and remediation recommendation logic, local fallback rules engine execution, internal API contract enforcement, and evaluation baseline tracking.
- **Consequence**:
  - Pro: Secure private endpoint communication via VPC endpoints, avoiding ALB hourly compute costs.
  - Pro: Native IAM SigV4 integration for robust authentication.
  - Pro: Out-of-the-box support for API throttling, stage deployment variables, and routing.
  - Pro: Integrates natively with API Gateway Resource Policies to enforce multi-tenant isolation.
  - Trade-off: Private API Gateway requires VPC Endpoint provisioning, but these endpoints are shared across other platform services.
- **Alternatives considered**:
  - Internal ALB routing: Rejected because API Gateway provides superior endpoint management, rate limiting, and native Lambda proxy integration for serverless runtimes.
  - Public HTTP Endpoint with API Gateway: Rejected because IAM SigV4-based authentication over private endpoints ensures traffic never traverses the public internet, satisfying security NFRs.

---

## ADR-012 - Direct Lambda/SQS AI Engine invocation over Private API Gateway

- **Status**: Accepted
- **Date**: 2026-06-24
- **Context**: The current CDO flow is a scheduled batch workflow driven by EventBridge Scheduler and Step Functions. The AI API contract v1.1 requires `/v1/detect`, `/v1/status/{id}`, `/v1/decide`, `/v1/verify`, and `/v1/audit/{audit_id}/rollback` logical contract semantics, but the architecture does not need a separate Private REST API Gateway when Step Functions is the only orchestrating caller.
- **Decision**: Avoid deploying a physical Private REST API Gateway for the default scheduled batch workflow, since Step Functions acts as the sole orchestrating caller. Instead, the contract's `/v1/detect`, `/v1/status/{id}`, `/v1/decide`, and `/v1/verify` interfaces are implemented purely as logical contract semantics. Under the hood, Step Functions invokes the AI Engine Request Lambda directly for `/v1/detect`, which validates the payload and queues it in SQS, returning a fast execution token. The AI Engine Worker Lambda processes the queue asynchronously, storing findings in DynamoDB and S3. The Step Functions workflow polls `/v1/status/{correlation_id}` until completed, then invokes `/v1/decide` to generate the remediation plan, executes any approved containment actions, and invokes `/v1/verify` to validate the outcome. The rollback endpoint `/v1/audit/{audit_id}/rollback` is called for manual reversions. Private API Gateway is rejected in the baseline CDO platform to reduce unnecessary overhead, remaining only as an optional design choice for future multi-client deployments.
- **Consequence**:
  - Pro: Eliminates infrastructure provisioning costs and maintenance overhead of API Gateway stages, usage plans, custom resource policies, and dedicated VPC Endpoints.
  - Pro: Keeps the scheduled 24h batch workflow fully serverless, direct, and secure.
  - Pro: Preserves the logical contract and image boundaries of the AIOps AI Engine container.
  - Trade-off: Other internal systems cannot query the AI Engine via HTTP REST requests by default.
  - Trade-off: Throttling, request validation, and environment routing are moved to the Lambda application layer and AWS IAM permissions.
- **Alternatives considered**:
  - Keep Private REST API Gateway: rejected for the default path because it adds infrastructure without clear value when Step Functions is the only caller.
  - Public API Gateway: rejected because the AI Engine must remain private and internal.
  - Internal ALB: rejected because it is heavier than needed for Lambda container hosting and scheduled batch invocation.

---

## ADR-013 - S3 + CloudFront dashboard over QuickSight for MVP

- **Status**: Accepted
- **Date**: 2026-06-25
- **Context**: The platform requires a user interface for Finance stakeholders to monitor spend trends, view cost anomalies, and review containment actions. The architecture needs to determine whether to use a managed BI service (Amazon QuickSight) or a custom static website hosted on Amazon S3 and distributed via Amazon CloudFront for the Minimum Viable Product (MVP).
- **Decision**: Use a private Amazon S3 static dashboard delivered through Amazon CloudFront, authenticated with Amazon Cognito (Hosted UI with Authorization Code Flow + PKCE) and protected with S3 Origin Access Control (OAC) and Lambda@Edge viewer-request token validation. Amazon QuickSight remains a potential future BI option but is not selected for the MVP baseline.
- **Consequence**:
  - Pro: Lower recurring infrastructure cost by avoiding QuickSight Enterprise baseline charges.
  - Pro: Eliminates per-reader BI seat license fees, allowing unlimited scaling of finance dashboard users at zero licensing cost.
  - Pro: Integrates seamlessly with precomputed JSON cost summaries generated by the daily CDO pipeline, requiring zero SQL execution for dashboard users.
  - Pro: Enables tight control over action visibility, Extend/Rollback buttons, and console interactions via custom frontend logic, which is complex or restricted in native BI tools.
  - Trade-off: Less native BI functionality, ad-hoc data exploration, or user-driven custom chart generation compared to QuickSight. Advanced business unit requirements may later justify integrating QuickSight Enterprise.
- **Alternatives considered**:
  - Amazon QuickSight (Enterprise edition): Rejected as the MVP default due to per-user seat fees, higher baseline configuration costs, and the complexity of embedding custom interactive rollback action triggers within standard dashboards.

---

## ADR-014 - Athena DDL validation to Terraform Glue schema with Partition Projection

- **Status**: Accepted
- **Date**: 2026-06-25
- **Context**: The lakehouse-centric data plane requires cataloging S3-based Cost and Usage Report (CUR) datasets. The architecture needs to define a reliable schema management workflow and a partition update strategy that handles dynamically generated billing-period directories (e.g., year and month) without introducing latency, manual overhead, or unnecessary runtime costs.
- **Decision**: Use Athena SQL DDL during initial schema design and validation because it gives fast feedback against real/synthetic CUR files. After validation, promote the schema into Terraform-managed AWS Glue Data Catalog definitions (using `aws_glue_catalog_table` resources) as the durable source of truth. Use Athena Partition Projection for CUR/Data Exports billing-period partitions so scheduled ingestion does not depend on Glue Crawler, MSCK REPAIR TABLE, or manual ALTER TABLE partition registration.
- **Consequence**:
  - Pro: Eliminates all runtime ingestion costs ($0.44/DPU-hour) and execution lag (1-3 minutes) associated with running Glue Crawlers.
  - Pro: Ensures deterministic schema structures in the Glue Data Catalog, eliminating the risk of Crawler heuristic type mismatch or schema drift.
  - Pro: Removes database-write credentials or Glue metadata write permissions from runtime ingestion Lambdas, aligning with the principle of least privilege.
  - Trade-off: Schema updates require a deployment pipeline execution rather than automated runtime discovery, which matches our stable production engineering gates.
- **Alternatives considered**:
  - Glue Crawler for routine operations: Rejected due DPU cost, run latency, and heuristic schema risk.
  - Athena SQL DDL as permanent management: Rejected because manual schema creation introduces drift and is harder to version-control or code-review than IaC.
  - Manual partition repair (MSCK REPAIR TABLE or Lambda-triggered ALTER TABLE): Rejected because it adds operational latency, API call costs, and scheduled-run fragility compared to client-side partition projection.

