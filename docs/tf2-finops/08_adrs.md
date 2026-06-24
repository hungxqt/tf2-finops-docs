# Architecture Decision Records - FinOps Watch CDO · Task Force 2

<!-- Doc owner: CDO Team
     Status: Ongoing log W11-W12
     Format: 1 ADR per major decision. Append-only - do not delete old ADRs. -->

> [!IMPORTANT]
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
- **Decision**: Establish a strict contract-based integration. CDO owns cost data ingestion, scheduled workflows, alerting, containment enforcement, and the hosting platform infrastructure (Private API Gateway, Lambda container functions, networking) for the AI Engine. AIOps owns the AI Engine logic, container image software, model parameters, confidence scoring, and backtesting metrics.
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
- **Context**: The platform requires both detailed resource-level cost metrics (which are highly structured) and real-time/near-real-time cost data queries to catch anomaly patterns.
- **Decision**: Combine AWS Data Exports (CUR 2.0) delivered to S3 with direct queries to the AWS Cost Explorer API. CUR is used for historical deep dives, partition analysis, and dashboard trends, while Cost Explorer API serves as the primary near-real-time querying mechanism for daily runs. To prevent exceeding the strict **5 requests/second** Cost Explorer rate limit, CDO caches query results in DynamoDB; the AI Engine consumes this cached cost data for its 7-day and 30-day baseline requirements instead of querying the Cost Explorer API directly.
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

## ADR-007 - ECS Fargate for AI Engine hosting

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

## ADR-008 - Fargate always-on vs Fargate Spot capacity providers separation

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
- **Decision**: Deploy and host the AI Engine container workloads on AWS Lambda container image hosting. Deployed by pinning immutable ECR image digests.
- **Consequence**:
  - Pro: True serverless pay-per-request pricing, eliminating ECS Fargate always-on idle compute costs.
  - Pro: Simpler scaling and high availability handled natively by AWS.
  - Pro: No need for Spot interruption checkpointing/retry complexity. SQS buffers async requests gracefully.
  - Trade-off: Introduces potential cold start latency for container images (mitigated by Provisioned Concurrency if latency thresholds are breached in production).
  - Trade-off: Model artifacts and dependencies must fit within the Lambda container image limit (10 GB). Heavy offline model training and retraining remain outside this runtime scope.
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
- **Context**: The current CDO flow is a scheduled batch workflow driven by EventBridge Scheduler and Step Functions. The AI API contract requires /v1/detect and /v1/detect/result/{audit_id} behavior, but the architecture does not need a separate Private REST API Gateway when Step Functions is the only orchestrating caller.
- **Decision**: Private REST API Gateway is not required for the default CDO scheduled workflow. The default path should use direct AWS service integration through Lambda and SQS: Step Functions -> AI Engine Request Lambda -> SQS -> AI Engine Worker Lambda -> DynamoDB/S3 results -> Step Functions result check. Private API Gateway becomes an optional future/shared-client pattern, not the baseline architecture.
- **Consequence**:
  - Pro: Removes unnecessary API Gateway, VPC endpoint, stage deployment, usage plan, and resource policy complexity.
  - Pro: Keeps the workflow fully serverless and easier to operate for the 24h batch cadence.
  - Pro: Preserves the AIOps Docker image boundary through Lambda container image deployment.
  - Trade-off: No reusable HTTP /v1/* endpoint exists by default for other internal clients.
  - Trade-off: API-style throttling, request validation, and stage controls must be implemented through Lambda, SQS, IAM, and contract tests.
- **Alternatives considered**:
  - Keep Private REST API Gateway: rejected for the default path because it adds infrastructure without clear value when Step Functions is the only caller.
  - Public API Gateway: rejected because the AI Engine must remain private and internal.
  - Internal ALB: rejected because it is heavier than needed for Lambda container hosting and scheduled batch invocation.
