# Test & Eval Report - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

> [!IMPORTANT]
> **Safety Boundary**: All verification procedures and test validations must confirm that the platform respects the absolute hard boundaries: **NEVER terminate prod, delete data, or modify IAM**.


## 1. Test coverage

The verification of the FinOps Watch CDO platform is conducted across multiple testing levels to ensure operational integrity, compliance with the AIOps-provided AI Engine contract, and safe containment behaviors.

| Test Type | Tool | Scope / Description |
|---|---|---|
| Unit | pytest | Validates individual Python Lambda handlers, utility functions, cost calculation helpers, and data adapters. |
| Integration | AWS SDK mock (boto3 mock / moto), pytest | Verifies S3 ingestion, DynamoDB reads/writes, SQS queue processing, and SNS/SES notification delivery. |
| E2E (End-to-End) | Custom test harnesses, CLI scripts | Exercises the complete data flow from synthetic anomaly injection in CUR, scheduling, AI Engine invocation, database updates, to alerting and containment dry-runs. |
| Scheduled-Run Idempotency | Custom test scripts | Confirms that processing the same CUR billing period twice does not generate duplicate database entries or trigger duplicate alert/containment actions. |
| Chaos / Failure | AWS Fault Injection Service (FIS) | Simulates network partitions, Cost Explorer API throttling, database latency, and AI Engine service unavailability to verify fail-closed and graceful recovery paths. |

---

## 2. SLO evidence

The platform's operational Performance is evaluated against Service Level Objectives (SLOs) established for reliability, freshness, and delivery speed.

| SLO | Target | Measured | Window | Pass/Fail |
|---|---|---|---|---|
| Scheduled Run Success Rate | >=99.9% of planned daily runs | Evidence needed: pending production run metrics | 30 Days | Evidence needed: pending production run metrics |
| Data Freshness | <=24 hours from CUR availability to Athena | Evidence needed: pending production run metrics | Daily Cycle | Evidence needed: pending production run metrics |
| Dashboard Refresh Latency | <=5 minutes from pipeline completion to static asset update | Evidence needed: pending production run metrics | Daily Cycle | Evidence needed: pending production run metrics |
| Alert Delivery Latency | <=30 minutes from anomaly detection to Slack/SNS dispatch | Evidence needed: pending production run metrics | Per-Alert | Evidence needed: pending production run metrics |

### 2.1 Contract Integration SLOs (Logical AI Engine Contract)

Compliance with the contract-mandated limits from `ai-api-contract.md` §6 is measured programmatically for the direct Lambda/SQS execution path:

| Contract SLO Metric | Target | Measurement Point | Verification Result |
|---|---|---|---|
| Request Enqueue Latency (P99) | < 50 ms | AI Engine Request Lambda execution time (input validation & SQS publish) | Evidence needed: pending Lambda telemetry |
| Result Store Query Latency (P99) | < 10 ms | DynamoDB GET query latency for `audit_id` (used by Step Functions poll) | Evidence needed: pending DynamoDB telemetry |
| LLM Inference SLA | < 30 seconds | Worker Lambda internal inference logic run time | Evidence needed: pending Worker Lambda telemetry |
| System Availability | >=99.5% | Direct Lambda invocation success rate (excluding client-throttling errors) | Evidence needed: pending CloudWatch metrics |
| Ingestion Failure Rate | < 0.5% | Failed runs (DLQ messages / total CUR processing requests) | Evidence needed: pending SQS queue metrics |

### 2.2 SLO breach analysis

In the event of an SLO breach, the following escalation and remediation protocols are triggered:
- **Cost Explorer Throttling**: If the Cost Explorer API limits are exceeded, the ingestion Lambda catches the exception and retries using an exponential backoff strategy. If the run exceeds the 24-hour SLA window, the operational team is alerted via PagerDuty.
- **AI Engine Lambda Startup Timeouts / Cold Starts**: If the Lambda container functions fail to start or experience long cold-start delays during peak scaling events, the platform triggers alerts for Provisioned Concurrency optimizations or delegates requests back to SQS retry buffers to maintain latency SLOs.
- **S3 / CloudFront Invalidation Delays**: If dashboard JSON updates fail to propagate due to CloudFront cache behavior, the invalidation API is automatically retried by the static site deployment pipeline.

---

## 3. CDO platform tests

### 3.1 Data ingestion

Data Ingestion verification focuses on retrieving and parsing cost data from AWS Data Exports (CUR 2.0) and AWS Cost Explorer API:
- **Raw Ingestion**: The raw ingestion Lambda retrieves parquet/CSV files from the billing S3 bucket and verifies that schema definitions match the defined layout.
- **Cost Explorer Queries**: Validates that mock responses from the Cost Explorer API match historical expectations and are mapped to normalized cost windows.
- **Glue Crawler & Athena Views**: Tests verify that the Glue Crawler successfully catalogs the S3 raw partition structure and that Athena queries can aggregate cost metrics by service, region, account, and resource tags without syntax errors. Under the hybrid telemetry design, CUR and Cost Explorer data are combined with CloudWatch performance indicators (`resource_utilization_metrics` such as CPU, memory, database connections, and GPU metrics). If CloudWatch metrics are unavailable, the platform automatically falls back to CUR-only mode, halving the model confidence score (`confidence *= 0.5`) and forcing dry-run/alert-only containment. CloudWatch logs and metrics are also used for CDO platform operational health monitoring and dashboards.

### 3.2 Scheduled run idempotency

The pipeline runs on a scheduled cadence (ADR-001) triggered by EventBridge Scheduler. To verify idempotency:
- **Duplicate Execution Test**: The same date window partition (e.g., 2026-06-22) is sent twice to the ingestion workflow.
- **State Check**: Step Functions checks if the execution state database (DynamoDB) already has a record for the `idempotency_key` (formatted as `AccountID:DateWindow`).
- **Execution Bypass**: The second run is successfully bypassed, and no duplicate database logs or alert messages are generated.

### 3.3 Dashboard refresh

- **Static Asset Generation**: A dedicated Lambda task is executed after the ingestion workflow terminates to aggregate and write JSON files containing spend summaries to the public-facing S3 dashboard bucket.
- **Frontend Verification**: The test script simulates a browser client retrieving the updated JSON structures and validates that the charts update correctly to reflect the new cost points.

---

## 4. AI integration tests

### 4.1 AI contract

The contract-based interface between the CDO platform and the AIOps-provided AI Engine is validated for strict schema adherence:
- **Request Format Verification**: The test harness sends requests with schema version `telemetry://finops-watch/v3` containing headers `X-Tenant-Id`, `X-Idempotency-Key` (composite key: `tenant_id:YYYY-MM-DD`), `X-Correlation-Id`, `X-Payload-SHA256`, and `X-Request-Timestamp` directly to the AI Engine Request Lambda function using IAM invocation permissions (`lambda:InvokeFunction`). The test verifies that the request payload conforms to the hybrid telemetry schema (containing CUR, Cost Explorer, and CloudWatch `resource_utilization_metrics`). If CloudWatch metrics are simulated as missing, the test verifies that the Request Lambda handles the fallback behavior by halving the confidence score (`confidence *= 0.5`) and forcing dry-run/alert-only mode.
- **Response Format Verification**: The test validates that the AI Engine Request Lambda returns a payload containing the required parameters: `success`, `status` (`processing`), and `correlation_id`. It also validates that the final processed payload written to DynamoDB/S3 by the Worker Lambda contains `status` (`COMPLETED` | `FAILED`), `anomalies_list` (containing `anomaly_metadata`, `finance_dashboard_data`, and `engineering_dashboard_data`).

### 4.2 AI Engine timeout

- **Timeout Simulation**: A mock container task is configured to delay its execution by 30 seconds (simulating LLM API delays).
- **Execution**: The CDO Step Functions orchestrator invokes the Request Lambda and polls DynamoDB for results.
- **Verification**: If the Worker Lambda fails to write the results within the Step Functions execution step timeout, the platform logs a timeout warning, marks the status as failed, and alerts operators.

### 4.3 Unavailable-AI fallback

If the AI Engine is completely unreachable (e.g., Lambda invocation failure, SQS enqueue failure, or Lambda execution concurrency exhaustion):
- **Fail Closed Behavior**: The CDO platform immediately aborts any scheduled containment action triggers. No automated policy is applied.
- **Operator Alert**: A critical incident ticket and PagerDuty alert are routed to the central CDO engineering and finance teams.
- **Audit Logging**: A failure record is written to the audit bucket, detailing the AI Engine's unavailability.

### 4.4 Lambda container image pull and cold-start

- **Image Pull Verification**: Validation scripts inspect the Lambda configuration to verify container image digest pinning (`image@sha256:...`) and ECR image pull permissions.
- **Cold-Start Performance**: Measures response times during container initialization to verify they remain within the acceptable execution window.
- **Provisioned Concurrency Test (Optional)**: If enabled, verifies that pre-warmed Lambda execution environments are allocated and successfully route requests without cold-start latency.

### 4.5 SQS/DLQ retry and redrive

- **Interruption Mocking**: Simulates a Lambda execution failure or timeout during worker execution.
- **SQS Durability**: Verifies that SQS retains the message, increments the receive count, and triggers a retry worker Lambda invocation after the visibility timeout expires.
- **DLQ Redrive**: Simulates maximum retries exhaustion and verifies that the message is safely moved to the Dead Letter Queue (DLQ) for operator analysis, writing a failure audit record.

### 4.6 SQS message buffering capacity and concurrency controls

- **SQS Queue Buffering**: Verifies that under peak load, the Request Lambda successfully buffers incoming CUR processing requests into SQS without dropping messages.
- **Concurrency Rate Limits**: Validates that the Worker Lambda execution concurrency scales dynamically according to SQS queue depth, respecting Reserved Concurrency limits to prevent downstream overloading.

### 4.7 Autoscaling and concurrency controls

- **Concurrency Load Simulation**: Simulates a burst of concurrent direct Request Lambda invocations.
- **Reserved Concurrency Guardrail**: Verifies that the Request and Worker Lambda functions respect their configured Reserved Concurrency limits to prevent throttling other critical platform services, returning proper invocation throttling errors or buffering correctly in SQS.
- **Provisioned Concurrency Test (Optional)**: If enabled, verifies that pre-warmed Lambda execution environments are allocated and successfully route requests without cold-start latency.

### 4.8 Result Polling & Pagination Tests

- **Polling Response Verification**: The test framework queries the DynamoDB execution/result table for the corresponding `correlation_id` (simulating the logical `GET /v1/status/{id}` semantics). It verifies the contract's response states (`COMPLETED` vs. `PROCESSING` vs. `FAILED`) and validates the structure of the returned `anomalies_list` objects.
- **Pagination Validation**: Under test loads that generate multiple anomalies, the framework requests results with query limits and validates that `next_token` is generated. It then queries subsequent pages using the token, confirming correct result index ordering.

### 4.9 Extend & Rollback Semantics Tests

- **Decide Action Plan Test**: Simulates the orchestrator calling the AI Engine Worker Lambda (representing `POST /v1/decide` semantics) to retrieve the intervention plan. The test verifies that the returned plan contains `dry_run_mode`, `applied_payload` (with `aws_cli_command`), and `rollback_payload` (with `aws_cli_rollback_command`), along with Cognito-group-based access rules and the `X-Containment-Status: LOCKED` header if the tenant's rollback rate is breached.
- **Rollback Action Test**: Simulates triggering manual rollback on the dashboard by calling the rollback endpoint (representing `POST /v1/audit/{audit_id}/rollback` semantics). The test verifies that:
  - The handler validates authorization, `rolled_back_by` email, and matching `X-Tenant-Id`.
  - It successfully initiates rollback, returns `rollback_initiated = true`, updates the false positive count, and recalculates `new_error_budget_burned_pct`.
  - If the error budget burn exceeds 1%, it verifies that the tenant is transitioned to `LOCKED_MODE` (the `containment_locked = true` flag is returned).
  - The event status is logged to the audit trail as `ROLLED_BACK`.

### 4.10 Contract Error Codes & Validation Tests

- **Idempotency Conflicts (`409` & `400` Semantics)**:
  - **In-Progress Call (`409 Conflict` Semantics)**: Invoking the Request Lambda with an active idempotency key returns a conflict response structure (representing HTTP `409` semantics) and prevents duplicate execution.
  - **Payload Mismatch (`400 Bad Request` Semantics)**: Re-submitting a request with an existing idempotency key but a different request payload returns a mismatch response structure (representing HTTP `400` with error code `ERR_IDEMPOTENCY_MISMATCH` semantics).
- **Multi-Tenant Access Restriction (`403 Forbidden` Semantics)**: Probes querying results or triggering actions with a mismatched `X-Tenant-Id` are blocked immediately with access denied structures (representing HTTP `403` / `ERR_CROSS_TENANT_DENIED` semantics).
- **Bedrock Timeout Fallback**: When a mock Bedrock call exceeds the 45-second hard timeout, the system validates that the AI Engine Worker Lambda terminates the task and writes a `failed` state with error code `ERR_LLM_TIMEOUT` to the DB. CDO polling intercepts this failure and shifts immediately to the static fallback rules engine.

---

## 5. Alert and containment tests

### 5.1 Alert routing

- **Financial Routing**: Cost deviations above $100/day are routed to the Finance SNS topic.
- **Engineering Routing**: Technical details including resource ID, service name, and tag violation status are routed to the squad-specific Slack webhook.
- **Payload Verification**: Ensures that sensitive cost details are represented by S3/dashboard references in external Slack notifications rather than embedding raw tables.

### 5.2 Containment dry-run

- **Dry-run Execution**: In prod and staging environments, the containment engine is locked to dry-run mode.
- **Resource Verification**: Validates that the targeted AWS resource remains unmodified.
- **Dashboard Output**: Checks that the dashboard presents the action as "Suggested" or "Dry-run completed".

### 5.3 Audit log write

The containment engine must generate an audit log entry for every action attempt. This test verifies that the written JSON schema contains all 15 required fields:
1. `actor`: Entity executing the action (e.g., `cdo-platform-orchestrator`).
2. `timestamp`: UTC execution timestamp.
3. `correlation_id`: Unique identifier tracking the specific run.
4. `idempotency_key`: Key preventing double executions (composite `tenant_id:YYYY-MM-DD`).
5. `anomaly_id`: Reference ID of the detected anomaly.
6. `resource_owner`: Team/squad responsible for the resource.
7. `resource_id`: AWS ARN of the target resource.
8. `before_state`: Detailed object containing resource configurations/tags prior to the action.
9. `proposed_after_state`: Intended resource state after containment.
10. `execution_mode`: Value representing `dry-run` or `apply`.
11. `rollback_path`: Structure defining the exact steps required to revert the action.
12. `approval_status`: Status of authorizations (e.g., `pending_approval`, `approved`, `bypassed`).
13. `retention_location`: S3 URI where the log is stored.
14. `retention_period_days`: Number representing retention duration (must be >= 90 days).
15. `audit_chain`: Tamper-evident ledger linking structure containing `event_hash` (`sha256(current_payload + previous_hash)`) and `previous_hash` of the append-only ledger.

### 5.4 Dashboard Auth & Cognito Group Validation

- **Hosted UI Redirection Test**: Verifies that any unauthenticated access request to the CloudFront dashboard URL is intercepted by the Lambda@Edge auth layer and redirected (302 redirect) to the Cognito Hosted UI login endpoint.
- **Finance Group Read-Only Access Test**: Validates that users belonging to the `finops-finance-readonly` Cognito user group are authenticated successfully but are restricted to read-only views on the dashboard. Probes to execute containment actions (Verification or Rollback) via requests to the action handlers (representing `/v1/verify` or `/v1/audit/{audit_id}/rollback` semantics) are rejected with authorization errors (representing HTTP `403 Forbidden` / `ERR_CROSS_TENANT_DENIED` or `ERR_AUTH_FAILED`).
- **Engineering Group Action Authorization Test**: Verifies that users in the `finops-engineering-operator` and `finops-cdo-admin` Cognito user groups can successfully trigger Verification and Rollback actions on the dashboard, confirming the JWT tokens contain correct group claims when forwarded to the Lambda handlers.
- **Session Expiration & Token Lifetime Test**: Validates that expired sessions (JWT token older than the 15-minute lifetime config) or tampered JWT cookie signatures are rejected by Lambda@Edge, causing immediate session termination and redirecting the user to re-authenticate.
- **Audit Logging for Auth Events**: Confirms that login/logout events, token validation failures, and unauthorized action attempts (e.g., Finance user attempting to rollback) are captured in the DynamoDB and S3 audit trail logs (e.g., logging `auth_success`, `auth_failure`, or `unauthorized_action_blocked`).

---

## 6. E2E demo scenario

The End-to-End demo demonstrates the entire ingestion, detection, alerting, and containment sequence:
- **Step 1 - Injection**: Synthetic unmanaged cost records (e.g., $500 spend on EC2 g5.4xlarge instances) are written to the CUR S3 bucket.
- **Step 2 - Trigger**: EventBridge triggers the Step Functions ingestion workflow.
- **Step 3 - Lambda Invocation**: The ingestion workflow extracts the cost records and invokes the AI Engine Request Lambda function directly, which validates the payload and enqueues the request in SQS, returning a processing response.
- **Step 4 - Task Execution**: The Worker Lambda container function is triggered by SQS, processes the cost data, records the anomaly/audit results in DynamoDB, and saves the detailed reasoning evidence to S3.
- **Step 5 - Dashboard Update**: Lambda aggregates the results, writes the updated JSON files to the dashboard S3 bucket, and triggers a CloudFront invalidation.
- **Step 6 - Alert Routing**: The Alert Routing Lambda is invoked, sending a Slack notification to the `squad-prediction-models` channel and an email notification to the Finance team via SNS/SES.
- **Step 7 - Dry-run Containment**: The CDO containment engine triggers a dry-run tag update (`FinOpsWatch: ReviewRequired`) and saves the audit record containing the rollback steps to S3.
- **Step 8 - Rollback Simulation**: The administrator clicks the "Rollback" button on the CDO dashboard, triggering the rollback endpoint (representing `POST /v1/audit/{audit_id}/rollback` semantics), which initiates tag restoration in the member account and updates the error budget burn telemetry.

---

## 7. Security test

### 7.1 Penetration touch points

- **S3 Bucket Access Control**: Probes verify that the CUR S3 bucket and the audit log S3 bucket reject all requests originating from outside the VPC endpoint policies and designated IAM roles.
- **Lambda Invocation Isolation**: Verifies that direct invocation of the Request and Worker Lambda functions is blocked for any IAM identity lacking explicit `lambda:InvokeFunction` permissions.
- **Containment IAM Restrictions**: Verifies that the Lambda execution roles used for containment actions are blocked from modifying IAM policies, deleting S3 data, or shutting down critical production workloads.

### 7.2 Vulnerability scan

- **ECR Container Scanning**: The Lambda container images are scanned in ECR during the CI/CD pipeline using AWS native scanning.
- **Remediation**: The deployment is blocked if any CRITICAL or HIGH vulnerabilities are detected in the container runtime or dependencies.
- **Audit Trails**: Security scanning logs are archived alongside the deployment pipeline history.

---

## 8. Failure analysis

### 8.1 Failures encountered

The following table summarizes the failures resolved during the testing phases:

| No. | Failure Encountered | Root Cause | Fix / Resolution | Time to Fix (Hours) |
|---|---|---|---|---|
| 1 | CUR Schema Mismatch | AWS updated the billing CUR export structure, adding new columns. | Modified the Glue schema parsing config to handle dynamic schemas. | 6 |
| 2 | Lambda Cold Start Timeout | AI Engine Lambda container initialization took longer than the client timeout limit. | Configured SQS buffer to handle requests asynchronously, preventing client timeouts. | 3 |
| 3 | Slack Webhook Rate Limit | Multiple duplicate anomaly alerts triggered Slack rate limiting. | Implemented alert grouping and batching in the routing Lambda. | 8 |

### 8.2 Test gaps acknowledged

Due to environment constraints, the following test scenarios have not been verified with real production infrastructure:
- **Cross-Account Ingestion Scale**: Ingestion of cost data across more than 50 concurrent AWS accounts. (Evidence needed: pending multi-account staging environment setup)
- **Lambda Concurrency Exhaustion under Peak Load**: Verification of Lambda concurrency limits under high parallel tenant execution load. (Evidence needed: pending concurrency simulator tests)
- **Production Containment Policy Impact**: Execution of apply-mode policy actions in a live production environment. (Evidence needed: pending compliance board approval)

---

## Related documents

- [`02_infra_design.md`](02_infra_design.md) - Contains the component tables, overall architecture diagram, and network security layouts.
- [`03_security_design.md`](03_security_design.md) - Details IAM service roles, encryption at rest, encryption in transit, and detailed audit log configurations.
- [`08_adrs.md`](08_adrs.md) - Explains architectural decisions including 24h cadence, dry-run-first containment, and Private API Gateway and Lambda hosting choices.
