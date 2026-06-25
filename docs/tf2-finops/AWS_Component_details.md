# AWS Component Details - FinOps Watch CDO

<!-- Source: 02_infra_design.md. Scope excludes AI Engine hosting platform. -->

> [!IMPORTANT]
> **Safety Boundary**: All CDO-owned infrastructure components and access controls described here must conform to the absolute hard boundaries: **NEVER terminate prod, delete data, or modify IAM**.


This document expands the AWS components described in [`02_infra_design.md`](02_infra_design.md) into role, purpose, input, and output details.

The scope is the CDO-owned FinOps control plane:

- Ingest cost data from AWS member accounts.
- Normalize and store cost evidence in a lakehouse.
- Orchestrate the daily FinOps run.
- Invoke an externally managed AI Engine through a contract boundary.
- Route alerts to Finance and Engineering.
- Apply only safe containment modes.
- Preserve audit evidence for review and dashboarding.

This document documents the CDO-owned components, including the Lambda container functions, ECR image deployment by digest, SQS queues, DynamoDB stores, Lambda execution roles, and network isolation deployed to host the AI Engine container provided by the AIOps team. It excludes the AIOps-owned AI model internals, logic, weights, and training datasets.

## Scope Boundary

| Area | Included here | Reason |
| --- | --- | --- |
| Cost ingestion | Yes | CDO owns CUR and Cost Explorer ingestion into the FinOps lakehouse. |
| Lakehouse storage | Yes | CDO owns raw, curated, Athena result, and audit evidence storage. |
| Serverless orchestration | Yes | CDO owns EventBridge Scheduler, Step Functions, and Lambda adapters. |
| State and audit database | Yes | CDO owns idempotency, run state, audit index, and dashboard materialization records. |
| Finance dashboard | Yes | CDO owns S3 + CloudFront dashboard backed by Athena/DynamoDB summaries; QuickSight is a future BI option. |
| Alert routing | Yes | CDO owns Finance and Engineering alert routing. |
| Safe containment | Yes | CDO owns dry-run, tag, suggest, and approved non-prod containment paths. |
| AI Engine API Contract | Yes | CDO calls, validates, and adheres to the versioned API and telemetry contracts. |
| AI Engine Hosting Infrastructure | Yes | CDO deploys and operates the Lambda container functions, SQS queues, DynamoDB stores, Lambda execution roles, and security configuration. |
| AI model internals & datasets | No | AIOps owns model logic, training, weights, and backtest datasets. |

## Component Summary

| # | Component | AWS service / surface | Platform role |
| --- | --- | --- | --- |
| 1 | AWS Member Accounts | AWS Organizations member accounts | Source of cost data and target scope for approved containment. |
| 2 | CUR S3 Export Buckets | Amazon S3 | Source for detailed cost and usage report files. |
| 3 | Cost Explorer API Endpoints | AWS Cost Explorer API | Source for aggregated daily cost signals. |
| 4 | CDO Management Account VPC | Amazon VPC | Private network boundary for CDO platform execution. |
| 5 | VPC Endpoints | AWS PrivateLink / Gateway Endpoints | Private access to AWS APIs and data stores. |
| 6 | EventBridge Scheduler | Amazon EventBridge Scheduler | Daily trigger for the FinOps workflow. |
| 7 | Step Functions Workflow | AWS Step Functions Standard | Main orchestrator for ingestion, validation, AI contract call, alerting, and containment. |
| 8 | Ingestion Lambda | AWS Lambda | Pulls CUR files and Cost Explorer data. |
| 9 | State Lambda | AWS Lambda | Checks and updates idempotency and run state. |
| 10 | Normalization / Validation Lambda | AWS Lambda | Converts raw cost data into contract-ready records. |
| 11 | AI Engine Lambda Function | AWS Lambda | Executes the synchronous cost anomaly detection algorithm (representing the POST `/v1/detect` contract-level semantic). |
| 12 | Alert Routing Lambda | AWS Lambda | Routes anomaly decisions to the correct notification path. |
| 13 | Containment Lambda | AWS Lambda | Executes dry-run, tag, suggest, or approved non-prod containment actions. |
| 14 | Audit Writer Lambda | AWS Lambda | Writes immutable audit records before and after policy actions. |
| 15 | S3 Raw Zone | Amazon S3 | Stores immutable CUR and Cost Explorer raw pulls. |
| 16 | S3 Curated Zone | Amazon S3 | Stores partitioned, schema-validated, query-optimized cost data. |
| 17 | S3 Audit Trail Bucket | Amazon S3 with Object Lock | Durable evidence store for containment and decision records. |
| 18 | Glue Data Catalog | AWS Glue Data Catalog | Registers schemas and partitions for Athena. |
| 19 | Athena Query Engine | Amazon Athena | Queries curated data and powers materialized views. |
| 20 | DynamoDB Run State Cache | Amazon DynamoDB | Caches dashboard materialized data and non-authoritative indexes. |
| 21 | Secrets Provider | AWS Secrets Manager | Stores secret references used by Lambda and alerting integrations. |
| 22 | IAM Cross-Account Roles | AWS IAM / STS | Allows controlled read and containment access into member accounts. |
| 23 | Finance Dashboard | Amazon S3 + CloudFront | Presents static web-based finance-readable views without SQL; assets are secured via OAC (Origin Access Control) and verified by Lambda@Edge. |
| 24 | Alert Channels | Amazon SNS, Slack API, SES | Sends Finance, Engineering, Platform, and Security notifications. |
| 25 | CloudWatch Monitoring | CloudWatch Logs, Metrics, Alarms | Observes workflow failures, stale data, and delivery failures. |
| 26 | AI Engine Lambda Execution | AWS Lambda | Runs model container synchronously to return anomalies directly. |
| 27 | ECR Repository | Amazon ECR | Stores AIOps container image artifacts deployed by digest pinning. |
| 28 | Alert Routing SQS/DLQ | Amazon SQS | Buffers failed alert messages to Slack/Email for automatic retries and logs failures to DLQ. |
| 29 | DynamoDB Dashboard Cache | Amazon DynamoDB | Caches run state, anomalies metadata, and dashboard-friendly materialized query views. |
| 30 | Dashboard Auth Gateway | Amazon Cognito | Authenticates dashboard users and provides group-based authorization (readonly Finance vs Engineering operators). |
| 31 | Viewer-Request Auth Gate | Lambda@Edge | Viewer-request handler checking secure HTTP-only cookies and validating JWT signatures against Cognito JWKS before forwarding requests to private S3 bucket. |

## Excluded Components

The following components are excluded from the CDO platform scope as they are owned and managed by AIOps:

| Excluded component | Description | Reason excluded |
| --- | --- | --- |
| AI Model Internals | Isolation Forest / Nova LLM weights & config | Owned by AIOps; provided to CDO as a containerized image artifact. |
| Model Training Logic | AI Engine retraining and tuning logic | Run inside containers but algorithms are owned and managed by AIOps. |
| Backtest datasets | Model evaluation datasets and benchmarks | AIOps maintains model metrics baseline; CDO stores only run-level integration telemetry. |

## 1. AWS Member Accounts

### Role

AWS member accounts are the source accounts monitored by the FinOps Watch platform. They contain the workloads, resources, tags, spend patterns, and cost exports that CDO evaluates.

### Purpose

They provide the real operational context for anomaly detection and containment decisions. The platform must preserve the account and environment context because the same anomaly can have different allowed actions in sandbox, staging, and prod.

### Input

- AWS account ID.
- Account alias or business name.
- Environment label, such as sandbox, staging, prod, research, or shared services.
- Owner and squad mapping.
- Approved cross-account role names.
- External ID or trust condition for role assumption.
- CUR export bucket location when the account owns its export.
- Resource tags such as `owner`, `squad`, `environment`, and cost center.

### Output

- Cost and usage source records.
- Resource ownership context.
- Account partition keys for lakehouse storage.
- Containment target metadata.
- Access results for cross-account read or containment role assumptions.
- Audit evidence showing which account was evaluated.

## 2. CUR S3 Export Buckets

### Role

CUR S3 export buckets provide detailed AWS Cost and Usage Report files from member accounts or centralized billing exports.

### Purpose

They are the most detailed cost input source for resource-level and tag-level analysis. CUR data supports historical investigation, account partitioning, and finance-grade evidence.

### Input

- CUR 2.0 export configuration.
- S3 bucket name and prefix.
- Billing period and partition path.
- Parquet or CSV report files.
- Account ID, product code, resource ID, unblended cost, usage amount, and resource tags.
- Bucket policy that allows the CDO ingestion role to read approved prefixes.

### Output

- Raw CUR objects copied or referenced by the ingestion Lambda.
- Source object URI retained as evidence.
- Cost line items written into the S3 Raw Zone.
- Missing or delayed partition signals for retry and alerting.

## 3. Cost Explorer API Endpoints

### Role

Cost Explorer API endpoints provide aggregated cost data through AWS APIs.

### Purpose

They complement CUR by giving daily service, account, region, and tag-level cost summaries. This is useful when CUR export latency exists or when the platform needs a quick aggregate view.

### Input

- Linked account ID.
- Time period.
- Granularity, usually daily.
- Metrics such as unblended cost.
- Group-by fields such as linked account, service, region, and tag.
- Read-only IAM permission such as `ce:GetCostAndUsage`.

### Output

- Daily cost summary JSON.
- Estimated or final cost status.
- API throttling signals.
- Raw Cost Explorer dumps in the S3 Raw Zone.
- Normalized cost aggregates for curated storage and AI contract payloads.

## 4. CDO Management Account VPC

### Role

The CDO Management Account VPC is the private network boundary for the CDO platform.

### Purpose

It isolates Lambda networking, VPC endpoints, private service access, and management-account resources so cost data and audit records do not need public internet transit.

### Input

- VPC CIDR block.
- Private subnet CIDR blocks.
- Availability zones in `ap-southeast-1`.
- Routing and NAT policy.
- Security group rules for Lambda and VPC endpoints.
- VPC endpoint list.

### Output

- VPC ID.
- Private subnet IDs.
- Route table IDs.
- Lambda security group ID.
- VPC endpoint security group ID.
- Private connectivity path to AWS services.

## 5. VPC Endpoints

### Role

VPC endpoints provide private network access from the CDO VPC to AWS services.

### Purpose

They reduce public internet exposure for cost data, audit data, secrets, logs, queues, and state operations.

### Input

- VPC ID and subnet IDs.
- Endpoint security group.
- Endpoint service names for S3, DynamoDB, Secrets Manager, KMS, CloudWatch Logs, SNS, SQS, Step Functions, EventBridge, and CloudWatch.
- Endpoint policies scoped to approved buckets, tables, topics, queues, and roles.

### Output

- Gateway endpoint IDs for S3 and DynamoDB.
- Interface endpoint IDs for private AWS API calls.
- Private DNS resolution for supported AWS services.
- Network path evidence for security review.

## 6. EventBridge Scheduler

### Role

EventBridge Scheduler triggers the FinOps workflow on a defined cadence.

### Purpose

It starts the daily cost inspection pipeline without running an always-on scheduler or serverless container cron workload.

### Input

- Schedule expression, usually daily.
- Target Step Functions state machine ARN.
- Scheduler execution role ARN.
- Input payload containing run window, environment, and account scope.
- Enabled or disabled state during deployment.

### Output

- Scheduled workflow invocation.
- Invocation timestamp.
- Failed invocation metrics.
- Scheduler ARN for observability and deployment evidence.

## 7. Step Functions Workflow

### Role

Step Functions is the central orchestrator for the CDO FinOps run.

### Purpose

It sequences deterministic CDO steps: idempotency check, ingestion, validation, normalization, AI contract invocation, alert routing, containment policy decision, audit writing, and failure handling.

### Input

- Scheduler event payload.
- Account scope and billing window.
- Lambda function ARNs.
- DynamoDB table names.
- Athena workgroup and query references.
- External AI contract version.
- Retry, wait, and timeout policies.
- Alert topic ARNs and failure destinations.

### Output

- Workflow execution record.
- Per-state success or failure details.
- AI decision validation result.
- Alert and containment branch decisions.
- Failure state for CloudWatch alarms.
- Audit references in DynamoDB and S3.

## 8. Ingestion Lambda

### Role

The ingestion Lambda pulls Cost Explorer data and copies or registers CUR files.

### Purpose

It turns external billing sources into raw platform inputs stored under the CDO lakehouse.

### Input

- Account list and role-assumption details.
- CUR bucket names and prefixes.
- Cost Explorer query window.
- Raw S3 bucket and prefix.
- KMS key ARN for write access.
- Retry and backoff settings.

### Output

- Raw CUR file references.
- Raw Cost Explorer JSON files.
- Source object URI evidence.
- Pull status per account and cost window.
- Error records for CUR delay or Cost Explorer throttling.

## 9. State Lambda

### Role

The state Lambda manages run locks and idempotency decisions.

### Purpose

It prevents duplicate runs for the same account and billing window, avoiding duplicate alerts, duplicate AI calls, and duplicate dashboard records.

### Input

- `account_id`.
- Billing period.
- Execution date.
- Run ID.
- DynamoDB run-state table name.
- Lock TTL and duplicate-run policy.

### Output

- Accepted or rejected run decision.
- Idempotency key, for example `account_id:billing_period:execution_date`.
- Run state record with `IN_PROGRESS`, `COMPLETED`, `FAILED`, or duplicate status.
- Duplicate attempt audit metadata.

## 10. Normalization / Validation Lambda

### Role

The normalization and validation Lambda converts raw billing inputs into a stable CDO schema.

### Purpose

It ensures CUR and Cost Explorer data can be queried, sent to the AI decision contract, and presented to Finance with consistent fields.

### Input

- Raw CUR records.
- Raw Cost Explorer records.
- Account and owner mapping.
- Required schema fields.
- Tag normalization rules.
- Curated S3 bucket and prefix.

### Output

- Normalized records with account, service, region, resource, tag, cost period, USD amount, and estimated/final flag.
- Curated files in partitioned storage.
- Validation errors for missing or malformed fields.
- Ownership fallback such as `unassigned-resources`.

## 11. AI Engine Lambda Function

### Role

Executes the synchronous cost anomaly detection algorithm (representing the POST `/v1/detect` contract-level semantic).

### Purpose

It serves as the entry point for the AI detection flow. It validates incoming request schemas, checks for idempotency conflicts, and runs the anomaly detection model synchronously.

### Input

- Normalized cost window payload.
- Run ID and idempotency key.
- Account scope.
- Contract version.
- Secrets reference for payload integrity signing.

### Output

- Success status (contract-level equivalent of HTTP `200 OK`) containing:
  - `success` (boolean)
  - `correlation_id` (UUID v4)
  - `anomalies_detected` (boolean)
  - `anomalies_list` (array of detected anomalies)
  - `error_message` (optional)
- Error codes or validation failures (contract-level equivalents of HTTP `400 Bad Request` or `409 Conflict`) if idempotency check or payload validation fails.

## 12. Alert Routing Lambda

### Role

The alert routing Lambda sends anomaly and workflow notifications to the correct channel.

### Purpose

It separates Finance, Engineering, Platform, and Security alerts so each audience receives actionable information without unnecessary sensitive detail.

### Input

- AI decision payload.
- Alert route map.
- Owner and squad metadata.
- Severity and confidence.
- Dashboard or audit link.
- SNS topic ARNs.
- Slack webhook secret reference.
- SES target configuration.
- Redaction policy.

### Output

- Finance alert event.
- Engineering alert event.
- Platform or Security escalation event.
- Alert delivery status.
- DLQ message for failed delivery.
- Audit reference linking the alert to the run.

## 13. Containment Lambda

### Role

The containment Lambda evaluates and executes safe containment actions in member accounts.

### Purpose

It turns approved policy decisions into controlled actions while preserving the hard boundary that production remains tag, suggest, or dry-run only.

### Input

- AI decision payload.
- Environment and account context.
- Containment policy map.
- Execution mode, such as dry-run, tag, suggest, or approved non-prod apply.
- Target resource ARN or ID.
- Cross-account containment role name.
- Approval status.
- Audit writer configuration.

### Output

- Dry-run result.
- Tagging result.
- Suggestion record.
- Approved non-prod containment result.
- Denied action record.
- Before and proposed-after state.
- Rollback path.
- Audit record ID.

## 14. Audit Writer Lambda

### Role

The audit writer Lambda records decision and containment evidence.

### Purpose

It creates the traceable audit trail required for Finance, Engineering, and compliance review.

### Input

- Run ID and correlation ID.
- Idempotency key.
- Anomaly ID.
- Resource owner and target resource ID.
- Before state.
- Proposed after state.
- Execution mode.
- Approval status.
- Retention location.
- Rollback path.

### Output

- DynamoDB audit index record.
- S3 audit evidence object.
- Retention metadata.
- Dashboard linkable audit record ID.
- Failure signal when audit writing fails.

## 15. S3 Raw Zone

### Role

The S3 Raw Zone stores original cost inputs.

### Purpose

It preserves immutable source evidence before transformation, supporting reprocessing and audit review.

### Input

- CUR files from member-account S3 exports.
- Cost Explorer JSON responses.
- Source account ID.
- Billing period.
- Ingestion timestamp.
- KMS encryption configuration.

### Output

- Raw objects partitioned by account and date.
- Source evidence URI.
- Input for normalization and validation.
- Recovery point when curated processing fails.

## 16. S3 Curated Zone

### Role

The S3 Curated Zone stores normalized and query-optimized cost records.

### Purpose

It provides the stable lakehouse layer for Athena queries, AI contract payload construction, and Finance dashboards.

### Input

- Validated raw records.
- Normalized service and display-name fields.
- Owner and squad tags.
- Account, year, and month partition values.
- Parquet conversion output.

### Output

- Partitioned curated objects.
- Athena-readable datasets.
- Query input for dashboard materialized views.
- Evidence window input for AI decision records.

## 17. S3 Audit Trail Bucket

### Role

The S3 audit trail bucket stores long-retention evidence for containment and decision records.

### Purpose

It acts as the durable evidence store for traceability, especially when DynamoDB contains only indexes or dashboard-friendly materialized records.

### Input

- Audit writer output.
- Containment proposal and result records.
- AI decision evidence references.
- Retention period, at least 90 days.
- Object Lock settings when enabled.

### Output

- Append-only audit objects.
- Evidence URI linked from DynamoDB and S3 + CloudFront dashboard.
- Retention proof for review.
- Recovery evidence for incident investigation.

## 18. Glue Data Catalog

### Role

Glue Data Catalog stores database and table metadata for the lakehouse.

### Purpose

It makes raw and curated S3 data queryable by Athena without moving it into a fixed data warehouse.

### Input

- Raw and curated S3 locations.
- Table schemas.
- Partition keys such as `account_id`, `year`, and `month`.
- IaC table configuration and partition projection parameters (ADR-014).
- Data type definitions.

### Output

- Glue database.
- Glue tables.
- Partition metadata.
- Schema registry for Athena queries.
- Catalog evidence for dashboard and query workflows.

## 19. Athena Query Engine

### Role

Athena runs serverless SQL queries over S3 lakehouse data.

### Purpose

It powers materialized cost views, dashboard datasets, anomaly evidence queries, and investigation workflows without requiring Finance users to write SQL directly.

### Input

- Glue database and table names.
- Curated S3 partitions.
- Athena workgroup.
- Query byte cutoff.
- Query result bucket.
- Named query definitions or dashboard view SQL.

### Output

- Query results in S3.
- Materialized dashboard inputs.
- Evidence windows for anomaly decisions.
- Stale-data signal when latest curated partition is too old.
- Query cost metrics.

## 20. DynamoDB Run State And Audit

### Role

DynamoDB stores operational state, idempotency records, audit indexes, and dashboard materialized records.

### Purpose

It provides low-latency state checks for the workflow and quick lookups for dashboards and alerts.

### Input

- Run ID.
- Idempotency key.
- Account and billing window.
- State status.
- Audit record ID.
- Dashboard materialization fields.
- TTL and retention policy.

### Output

- Run lock result.
- Run state record.
- Duplicate-run detection.
- Audit index record.
- Dashboard summary record.
- Failure state for alarms and redrive.

## 21. Secrets Provider

### Role

Secrets Manager stores secret containers and secret references required by CDO runtime components.

### Purpose

It keeps sensitive values out of Terraform variables, documentation, Lambda environment plaintext, and alert payloads.

### Input

- Secret names for AI endpoint configuration.
- Contract signing key secret name.
- Slack webhook secret name.
- Dashboard credential secret name if needed.
- External ID seed secret name.
- KMS key for secret encryption.
- Rotation policy.

### Output

- Secret ARNs passed to Lambda and IAM policies.
- Secret rotation metadata.
- Access audit through CloudTrail.
- Runtime secret retrieval path for approved execution roles.

## 22. IAM Cross-Account Roles

### Role

IAM roles and STS role assumption provide controlled access from the CDO management account into member accounts.

### Purpose

They allow CDO to read cost data and execute safe containment without broad account privileges.

### Input

- Management account role ARN.
- Member account IDs.
- External ID.
- Source account condition.
- Session tag requirements.
- Read-only CUR and Cost Explorer permissions.
- Containment permissions scoped by environment and action type.

### Output

- Assumed-role session for ingestion.
- Assumed-role session for containment.
- Access denied signal when policy conditions fail.
- CloudTrail audit events.
- Session tags that link actions to CDO run IDs.

## 23. Finance Dashboard

### Role

A lightweight internal web dashboard hosted as static assets in Amazon S3 and delivered through Amazon CloudFront. The dashboard reads precomputed finance-readable summaries from S3 JSON objects or DynamoDB records generated by the scheduled ingestion workflow. Athena remains behind the scenes for curated summary generation; Finance users never write SQL.

QuickSight is retained as a future BI option for larger Finance teams or executive reporting, but it is not the default MVP dashboard because the capstone prioritizes low recurring cost and no per-reader BI seat fees.

### Purpose

It answers the CFO-facing questions without SQL: what changed, who owns it, how confident the platform is, and what action is allowed.

### Input

- S3 JSON precomputed summaries.
- DynamoDB materialized run records.
- Audit record links.
- Owner and squad metadata.
- Severity and confidence fields.
- CloudFront authorized users or Cognito groups.
- Athena datasets (via manual export or future QuickSight BI integration).

### Output

- Finance dashboard views.
- S3 JSON dataset/file refresh status.
- Spend anomaly summaries.
- Owner and route breakdowns.
- Audit links for containment decisions.
- Dashboard stale-data signal when inputs lag.

## 24. Alert Channels

### Role

Alert channels deliver platform findings and failure signals to the right audience.

### Purpose

They ensure Finance, Engineering, Platform, and Security receive routed, redacted, actionable notifications.

### Input

- Alert routing decision.
- SNS topic ARNs.
- Slack webhook reference.
- SES email target.
- Severity and confidence.
- Owner and squad route.
- Dashboard or audit link.
- Redaction policy.

### Output

- Finance alert.
- Engineering alert.
- Platform or Security escalation.
- Email fallback notification.
- Failed alert DLQ message.
- Delivery metrics for monitoring.

## 25. CloudWatch Monitoring

### Role

CloudWatch records logs, metrics, and alarms for the serverless control plane.

### Purpose

It provides operational detection for failed workflows, stale dashboard data, Lambda errors, alert delivery failures, and audit write failures.

### Input

- Lambda log groups.
- Step Functions execution metrics.
- EventBridge Scheduler metrics.
- DynamoDB throttling metrics.
- Athena failure or stale partition signal.
- Alert delivery status.
- Dashboard freshness metric.

### Output

- CloudWatch logs.
- CloudWatch metrics.
- CloudWatch alarms.
- Operator alerts.
- Evidence that the platform ran, failed, retried, or recovered.

## 26. AI Engine Lambda Execution

### Role

Runs the AI model container and writes results to S3.

### Purpose

Executes model inference and anomaly analysis inside a Lambda function initialized from an AIOps-provided container image. It runs synchronously within the direct detect lifecycle, and utilizes reserved concurrency to control blast radius and throttle limits.

### Input

- Ingested cost and CloudWatch utilization features from S3.
- Pinned ECR image digest.
- S3 bucket ARNs for evidence.
- Lambda execution role ARN.
- Reserved concurrency configuration.

### Output

- Anomaly detection results and explanations returned synchronously to the Step Functions orchestrator.
- Detailed execution reasoning evidence written to the S3 bucket.
- Execution traces sent to X-Ray and logs sent to CloudWatch.

## 27. ECR Repository

### Role

Stores version-tagged AIOps AI Engine container image artifacts.

### Purpose

Acts as the single registry for deployment. Images are pinned by SHA256 digest in Lambda configuration.

### Input

- Image builds from CI/CD.
- CVE scans and compliance verification tags.

### Output

- Pinned image URI (`.dkr.ecr.ap-southeast-1.amazonaws.com/ai-engine@sha256:...`) pulled by AWS Lambda.

## 28. Alert Routing SQS/DLQ

### Role

Buffers failed alert messages to Slack/Email for automatic retries.

### Purpose

Decouples alert notification delivery from the primary workflow execution. It prevents transient Slack/Email API failures from aborting the CDO pipeline, automatically retrying failed deliveries and routing persistent failures to the DLQ.

### Input

- JSON alert payloads for Slack/Email.
- Dead Letter Queue configuration.

### Output

- Retried alerts sent to Slack/Email targets.
- DLQ messages on permanent delivery failures.

## 29. DynamoDB Dashboard Cache

### Role

Caching store for run state, anomalies, and containment execution audits.

### Purpose

Provides low-latency read views to support the S3 + CloudFront finance dashboard, caching precomputed run histories and status updates without querying the authoritative S3/Athena layer.

### Input

- Materialized views written by CDO platform Lambdas after runs.

### Output

- Low-latency status and result records retrieved by the S3 + CloudFront dashboard.

## 30. Amazon Cognito

### Role

User authentication and directory provider.

### Purpose

Authenticates dashboard users via secure Cognito Hosted UI (Authorization Code Flow with PKCE) and defines user groups (`finops-finance-readonly`, `finops-engineering-operator`, `finops-cdo-admin`) to authorize dashboard operations.

### Input

- Interactive user credentials entered in the Cognito Hosted UI.

### Output

- ID, Access, and Refresh JWT tokens containing group claims, stored as secure cookies.

## 31. Lambda@Edge Viewer Request Auth

### Role

Edge-level authorization filter.

### Purpose

Intercepts dashboard requests at the CloudFront viewer request event, parses JWT cookies, checks signatures against Cognito JWKS, and verifies session expiration. Denies access or redirects to login if the session is invalid.

### Input

- Incoming viewer request headers and cookies.

### Output

- Request forwarding to private S3 origin with OAC validation (if authorized) or 302 redirect to Cognito Hosted UI.

## Contract-Level Data Flows

### Cost Data Pull Contract

| Field | Detail |
| --- | --- |
| Responsible components | EventBridge Scheduler, Step Functions, Ingestion Lambda, S3 Raw Zone, S3 Curated Zone, Glue, Athena |
| Input | Account scope, cost window, CUR S3 location, Cost Explorer query parameters |
| Output | Source object URI, cost window, account, service, region, resource, tag owner, unblended cost, estimated/final flag |
| Failure behavior | Retry on CUR delay and Cost Explorer throttling; alert if delay exceeds the configured threshold |

### External AI Decision Contract

| Field | Detail |
| --- | --- |
| Responsible CDO components | Step Functions, AI Engine Lambda, DynamoDB, S3 audit trail, SQS |
| Excluded components | AI Engine model weights, AI training jobs, model training datasets, and AI model internal logic |
| Input | Normalized cost window, run ID, account scope, contract version, evidence window |
| Output | Model version, anomaly ID, confidence, severity, expected spend, actual spend, delta, explanation, recommended route, recommended containment mode, evidence URI |
| Failure behavior | Fail closed, block containment, alert operators, and write failed contract state in DynamoDB |

### Alert And Containment Contract

| Field | Detail |
| --- | --- |
| Responsible components | Alert Routing Lambda, Containment Lambda, DynamoDB, S3 audit trail, SNS, Slack, SES, S3 + CloudFront dashboard |
| Input | Validated AI decision, owner route, environment, resource metadata, containment policy, execution mode |
| Output | Route target, approval requirement, execution mode, before/after state, rollback path, audit record ID |
| Failure behavior | Write denied or failed audit record, route critical alert, do not retry unsafe containment actions |

## Production Safety Rules

- Production containment is limited to tag, suggest, or dry-run.
- Do not terminate production resources.
- Do not delete data.
- Do not modify IAM from containment workflows.
- Write audit evidence before attempting any apply-mode non-prod action.
- Missing owner tags must remain visible and route to the CDO infrastructure channel.
- Synthetic demo events must be labeled as `synthetic-demo` and must not be treated as AIOps model-training evidence.

## Source Traceability

| Source section in `02_infra_design.md` | Components captured here |
| --- | --- |
| `1. Architecture diagram` | Member accounts, CUR, Cost Explorer, EventBridge, Step Functions, Lambda, S3, Glue, Athena, DynamoDB, Slack, SES, S3 + CloudFront dashboard |
| `1.1 High-Level Architecture Overview` | Orchestrator, lakehouse, alerting/containment engine, dashboard/channels |
| `1.2 Ingestion & Data Lakehouse Workflow` | CUR, Cost Explorer, Scheduler, Step Functions, Ingestion Lambda, S3 Raw, S3 Curated, Glue, Athena |
| `1.4 Alerting & Containment Engine` | Alert Lambda, Containment Lambda, State Lambda, DynamoDB state/audit, member resources, Slack, SES, S3 + CloudFront dashboard |
| `2. Component table` | EventBridge Scheduler, Step Functions, Lambda, S3, Glue, Athena, DynamoDB, Secrets Manager, S3 + CloudFront dashboard, SNS/Slack, Containment Worker, Lambda container functions, ECR, SQS |
| `4. Multi-account approach` | Member accounts, cross-account CUR puller role, cross-account containment role, account onboarding, idempotency |
| `6. Scaling strategy` | Athena partitioning, DynamoDB on-demand scaling, Lambda reserved concurrency scaling |
| `7. Failure modes + recovery` | CUR delay, Cost Explorer throttling, workflow failure, duplicate run, stale dashboard, alert delivery failure, containment denial, AI contract mismatch, Lambda cold starts and async processing |
