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
| Integration | AWS SDK mock (boto3 mock / moto), pytest | Verifies S3 ingestion, S3 authoritative writes, SQS alert queue processing, and SNS/SES notification delivery. |
| E2E (End-to-End) | Custom test harnesses, CLI scripts | Exercises the complete data flow from synthetic anomaly injection in CUR, scheduling, AI Engine invocation, S3 updates, to alerting and containment dry-runs. |
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
| Request Latency (P99) | < 300 ms | ALB target response time (input validation & synchronous detect run) | Evidence needed: pending telemetry |
| Result Store Query Latency (P99) | < 10 ms | S3 GetObject latency for `correlation_id` / `anomaly_id` | Evidence needed: pending S3 telemetry |
| LLM Inference SLA | < 30 seconds | AI Engine Lambda internal inference logic run time | Evidence needed: pending AI Engine Lambda telemetry |
| System Availability | >=99.5% | ALB HTTPS API invocation success rate (excluding client-throttling errors) | Evidence needed: pending CloudWatch metrics |
| Ingestion Failure Rate | < 0.5% | Failed runs (failures / total CUR processing requests) | Evidence needed: pending metrics |

### 2.2 SLO breach analysis

In the event of an SLO breach, the following escalation and remediation protocols are triggered:
- **Cost Explorer Throttling**: If the Cost Explorer API limits are exceeded, the ingestion Lambda catches the exception and retries using an exponential backoff strategy. If the run exceeds the 24-hour SLA window, the operational team is alerted via PagerDuty.
- **AI Engine Lambda Startup Timeouts / Cold Starts**: If the Lambda container functions fail to start or experience long cold-start delays during peak scaling events, the platform triggers alerts for Provisioned Concurrency optimizations or delegates requests to retry handling to maintain latency SLOs.
- **S3 / CloudFront Invalidation Delays**: If dashboard JSON updates fail to propagate due to CloudFront cache behavior, the invalidation API is automatically retried by the static site deployment pipeline.

---

## 3. CDO platform tests

### 3.1 Data ingestion

Data Ingestion verification focuses on retrieving and parsing cost data from AWS Data Exports (CUR 2.0) and AWS Cost Explorer API:
- **Raw Ingestion**: The raw ingestion Lambda retrieves parquet/CSV files from the billing S3 bucket and verifies that schema definitions match the defined layout.
- **Cost Explorer Queries**: Validates that mock responses from the Cost Explorer API match historical expectations and are mapped to normalized cost windows.
- **Glue Catalog & Athena Partition Projection (ADR-014)**: Test procedures cover both phase stages. First, tests verify schema validation using Athena SQL DDL during initial schema design against synthetic CUR files. Second, tests verify that Glue Data Catalog table definitions are correctly applied via Terraform IaC, and that client-side Athena Partition Projection dynamically resolves S3 raw partitions at query execution time without runtime crawler dependencies, allowing queries to aggregate cost metrics by service, region, account, and resource tags without syntax errors. Under the hybrid telemetry design, CUR and Cost Explorer data are combined with CloudWatch performance indicators (`resource_utilization_metrics` such as CPU, memory, database connections, and GPU metrics). If CloudWatch metrics are unavailable, the platform automatically falls back to CUR-only mode, setting `data_confidence = LOW` and forcing dry-run/alert-only containment. CloudWatch logs and metrics are also used for CDO platform operational health monitoring and dashboards.

### 3.2 Scheduled run idempotency

The pipeline runs on a scheduled cadence (ADR-001) triggered by EventBridge Scheduler. To verify idempotency:
- **Duplicate Execution Test**: The same date window partition (e.g., 2026-06-22) is sent twice to the ingestion workflow.
- **State Check**: Ingestion compute attempts a DynamoDB conditional write on `finops-idempotency-{env}` using the composite key.
- **Execution Bypass**: The second write fails with `ConditionalCheckFailedException` (key already exists), causing the second run to be successfully bypassed with no duplicate S3 objects or alert messages.

### 3.3 Dashboard refresh

- **Static Asset Generation**: A dedicated Lambda task is executed after the ingestion workflow terminates to aggregate and write JSON files containing spend summaries to the public-facing S3 dashboard bucket.
- **Frontend Verification**: The test script simulates a browser client retrieving the updated JSON structures and validates that the charts update correctly to reflect the new cost points.

---

## 4. AI integration tests

### 4.1 AI contract

The contract-based interface between the CDO platform and the AIOps-provided AI Engine is validated for strict schema adherence:
- **Request Format Verification**: The test harness sends requests with schema version `telemetry://finops-watch/v3` containing headers `X-Tenant-Id`, `X-Idempotency-Key` (composite key: `tenant_id:YYYY-MM-DD:batch_type`), `X-Correlation-Id`, `X-Payload-SHA256`, and `X-Request-Timestamp` to the private internal ALB endpoint using HTTPS and SigV4 authentication. The test verifies that the request payload conforms to the hybrid telemetry schema (containing CUR, Cost Explorer, and CloudWatch `resource_utilization_metrics`). If CloudWatch metrics are simulated as missing, the test verifies that the Lambda handles the fallback behavior by setting `data_confidence = LOW` and forcing dry-run/alert-only mode.
- **Response Format Verification**: The test validates that the AI Engine ALB returns a synchronous payload containing the required parameters: `success`, `correlation_id`, `anomalies_detected`, and `anomalies_list` (containing `anomaly_id`, `anomaly_type`, `severity`, `confidence_score`, `resource_id`, `environment`, `responsible_team`, `unblended_cost_24h_usd`, `cost_ratio_to_7d_avg`, `ai_model_used`, `alert_routing`).
- **Ingest Validation with Finalized CUR-only Data**: Verifies that when the ingestion run processes finalized CUR data on-time, the request payload asserts `telemetry_delay_event = false` and the response contains `data_confidence = HIGH`.
- **Fallback Validation with CUR Delayed**: Verifies that if CUR data delivery is delayed, the request flags `telemetry_delay_event = true` (signaling that daily Cost Explorer query fallback is active) and the response returns `data_confidence = LOW`.
- **S3 Bucket URI Schema Validation**: Verifies that the `s3_bucket_uri` parameter is validated against the regex pattern `s3://company-cdo-[0-9]{12}-telemetry/.*$` (matching account-scoped naming), throwing schema validation errors for malformed URIs.
- **Raw CPU Telemetry Check**: Confirms that the CDO platform sends the raw `cpu_utilization_hourly` array without precomputing SRE metrics like `idle_hours_continuous` on the CDO backend.

### 4.2 AI Engine timeout

- **Timeout Simulation**: A mock container task is configured to delay its execution by 30 seconds (simulating LLM API delays).
- **Execution**: The CDO Step Functions orchestrator or compute task calls the private internal ALB endpoint synchronously.
- **Verification**: If the ALB request fails to return the results within the Step Functions execution step timeout, the platform logs a timeout warning and alerts operators.

### 4.3 Unavailable-AI fallback

If the AI Engine is completely unreachable (e.g., ALB routing failure or Lambda execution concurrency exhaustion):
- **Fail Closed Behavior**: The CDO platform immediately aborts any scheduled containment action triggers. No automated policy is applied.
- **Operator Alert**: A critical incident ticket and PagerDuty alert are routed to the central CDO engineering and finance teams.
- **Audit Logging**: A failure record is written to the audit bucket, detailing the AI Engine's unavailability.

### 4.4 Lambda container image pull and cold-start

- **Image Pull Verification**: Validation scripts inspect the Lambda configuration to verify container image digest pinning (`image@sha256:...`) and ECR image pull permissions.
- **Cold-Start Performance**: Measures response times during container initialization to verify they remain within the acceptable execution window.
- **Provisioned Concurrency Test (Optional)**: If enabled, verifies that pre-warmed Lambda execution environments are allocated and successfully route requests without cold-start latency.

### 4.5 Alert SQS/DLQ retry and redrive

- **Interruption Mocking**: Simulates a Lambda execution failure or timeout during alert routing execution.
- **SQS Durability**: Verifies that SQS retains the message, increments the receive count, and triggers a retry alert routing Lambda invocation after the visibility timeout expires.
- **DLQ Redrive**: Simulates maximum retries exhaustion and verifies that the message is safely moved to the Dead Letter Queue (DLQ) for operator analysis, writing a failure audit record.

### 4.6 Alert SQS message buffering capacity and concurrency controls

- **SQS Queue Buffering**: Verifies that under peak load, the Alert Routing Lambda successfully buffers incoming alert routing requests into SQS without dropping messages.
- **Concurrency Rate Limits**: Validates that the Alert Routing Lambda execution concurrency scales dynamically according to SQS queue depth, respecting Reserved Concurrency limits to prevent downstream overloading.

### 4.7 Concurrency controls

- **Concurrency Load Simulation**: Simulates a burst of concurrent direct AI Engine Lambda invocations.
- **Reserved Concurrency Guardrail**: Verifies that the AI Engine Lambda function respects its configured Reserved Concurrency limits to prevent throttling other critical platform services, returning proper invocation throttling errors.
- **Provisioned Concurrency Test (Optional)**: If enabled, verifies that pre-warmed Lambda execution environments are allocated and successfully route requests without cold-start latency.

### 4.8 Result Retrieval & Pagination Tests

- **Retrieval Response Verification**: The test framework queries the S3 Authoritative store for the corresponding `correlation_id`. It validates the structure of the returned `anomalies_list` objects.
- **Pagination Validation**: Under test loads that generate multiple anomalies, the framework requests results with query limits and validates that `next_token` is generated. It then queries subsequent pages using the token, confirming correct result index ordering.

### 4.9 Extend & Rollback Semantics Tests

- **Decide Action Plan Test**: Simulates the orchestrator calling the AI Engine Lambda (representing `POST /v1/decide` semantics) to retrieve the intervention plan. The test verifies that the returned plan contains `dry_run_mode`, `applied_payload` (with `aws_cli_command`), and `rollback_payload` (with `aws_cli_rollback_command` and `boto3_equivalent`), along with Cognito-group-based access rules and the `X-Containment-Status: LOCKED` header if the tenant's rollback rate is breached.
- **Rollback Action Test**: Simulates triggering manual rollback on the dashboard by calling the rollback endpoint (representing `POST /v1/audit/{audit_id}/rollback` semantics). The test verifies that:
  - The handler validates authorization, `rolled_back_by` email, and matching `X-Tenant-Id`.
  - It successfully initiates rollback, returns `audit_recorded = true` (instead of `rollback_initiated = true`), updates the false positive count, and recalculates `new_error_budget_burned_pct`.
  - The event status is logged to the audit trail as `ROLLED_BACK`.
- **Rollback Caching & Offline Fallback Test**: Verifies that the CDO backend caches the `rollback_payload.boto3_equivalent` configuration into the DynamoDB `finops-rollback-cache` table. The test simulates an AI Engine offline/unreachable scenario and verifies that the CDO platform backend successfully executes the rollback via standard Boto3 calls using the cached configuration, and then reports the execution results to the rollback audit endpoint.
- **Error Budget Lock Tests**: Asserts that containment lock triggers at a rollback rate of >=1% in production (prod), >=10% in staging, and never (disabled) in dev/sandbox environments, utilizing the `error_budget_exceeded_threshold` lock reason.

### 4.10 Contract Error Codes & Validation Tests

- **Idempotency Conflicts (`409` & `400` Semantics)**:
  - **In-Progress Call (`409 Conflict` Semantics)**: Invoking the AI Engine Lambda with an active idempotency key returns a conflict response structure (representing HTTP `409` semantics) and prevents duplicate execution.
  - **Payload Mismatch (`400 Bad Request` Semantics)**: Re-submitting a request with an existing idempotency key but a different request payload returns a mismatch response structure (representing HTTP `400` with error code `ERR_IDEMPOTENCY_MISMATCH` semantics).
- **Multi-Tenant Access Restriction (`403 Forbidden` Semantics)**: Probes querying results or triggering actions with a mismatched `X-Tenant-Id` are blocked immediately with access denied structures (representing HTTP `403` / `ERR_CROSS_TENANT_DENIED` semantics).
- **Bedrock Timeout Fallback**: When a mock Bedrock call exceeds the 45-second hard timeout, the system validates that the AI Engine Lambda terminates the task and returns a `failed` state with error code `ERR_LLM_TIMEOUT`. CDO intercepts this failure and shifts immediately to the static fallback rules engine.
- **Clock Skew & Telemetry Timestamp Tests**:
  - **Request Clock Skew Reject**: Verifies that requests with an API request timestamp drift (clock skew) greater than 300 seconds are rejected with error code `ERR_REPLAY_DETECTED`.
  - **CUR Data Lag Accept**: Confirms that CUR data with an ingestion timestamp delay up to 36 hours is accepted and processed successfully, as it falls within the expected daily billing latency.

### 4.11 Callback retry schedule tests

- **Retry Interval Verification**: Validates that when callback delivery fails, the platform executes a retry schedule at 0s, 30s, and 120s delay intervals.
- **Fault Isolation & Logging**: Verifies that if the retry limits are exceeded, the event is logged as `CALLBACK_EXHAUSTED` in platform telemetry, but the synchronous detection run is not failed or invalidated.

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
4. `idempotency_key`: Key preventing double executions (composite `{tenant_id}:{billing_period_date}:{batch_type}`).
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
- **Audit Logging for Auth Events**: Confirms that login/logout events, token validation failures, and unauthorized action attempts (e.g., Finance user attempting to rollback) are captured in the S3 audit trail logs (e.g., logging `auth_success`, `auth_failure`, or `unauthorized_action_blocked`).

---

## 6. E2E demo scenario

The End-to-End demo demonstrates the entire ingestion, detection, alerting, and containment sequence:
- **Step 1 - Injection**: Synthetic unmanaged cost records (e.g., $500 spend on EC2 g5.4xlarge instances) are written to the CUR S3 bucket.
- **Step 2 - Trigger**: EventBridge triggers the Step Functions ingestion workflow.
- **Step 3 - Lambda Invocation**: The ingestion workflow extracts the cost records and calls the AI Engine private ALB endpoint synchronously via HTTPS and SigV4, which returns the detection success indicator and the list of anomalies.
- **Step 4 - Task Execution**: The Step Functions workflow processes the cost data, records the anomaly/audit results in the S3 Authoritative store (with dashboard caching in DynamoDB), and saves the detailed reasoning evidence to S3.
- **Step 5 - Dashboard Update**: Lambda aggregates the results, writes the updated JSON files to the dashboard S3 bucket, and triggers a CloudFront invalidation.
- **Step 6 - Alert Routing**: The Alert Routing Lambda is invoked, sending a Slack notification (including engineering alert payload with `slack_routing`) to the `squad-prediction-models` channel and an email notification to the Finance team via SNS/SES.
- **Step 7 - Dry-run Containment**: The CDO containment engine triggers a dry-run tag update (`FinOpsWatch: ReviewRequired`) and saves the audit record containing the rollback steps to S3.
- **Step 8 - Rollback Simulation**: The administrator clicks the "Rollback" button on the CDO dashboard, triggering the rollback endpoint (representing `POST /v1/audit/{audit_id}/rollback` semantics), which initiates tag restoration in the member account by executing the cached `rollback_payload.boto3_equivalent` from the DynamoDB `finops-rollback-cache` table and updates the error budget burn telemetry.

---

## 7. Security test

### 7.1 Penetration touch points

- **S3 Bucket Access Control**: Probes verify that the CUR S3 bucket and the audit log S3 bucket reject all requests originating from outside the VPC endpoint policies and designated IAM roles.
- **Lambda Invocation Isolation**: Verifies that direct invocation of the AI Engine Lambda function is blocked for any IAM identity lacking explicit `lambda:InvokeFunction` permissions.
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
| 2 | Lambda Cold Start Timeout | AI Engine Lambda container initialization took longer than the client timeout limit. | Configured Step Functions timeout to be longer and optimized container packaging. | 3 |
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
