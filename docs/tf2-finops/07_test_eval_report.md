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

### 2.1 Contract Integration SLOs (AI Engine API)

Compliance with the contract-mandated limits from `ai-api-contract.md` §6 is measured programmatically:

| Contract SLO Metric | Target | Measurement Point | Verification Result |
|---|---|---|---|
| Ingestion Latency (P99) | < 50 ms | POST `/v1/detect` response latency | Evidence needed: pending API integration telemetry |
| Result Query Latency (P99) | < 10 ms | GET `/v1/detect/result/{audit_id}` response latency | Evidence needed: pending API integration telemetry |
| LLM Inference SLA | < 30 seconds | Async inference logic run time | Evidence needed: pending API integration telemetry |
| System Availability | >=99.5% | API Gateway health check success rate | Evidence needed: pending API Gateway uptime statistics |
| Error Rate | < 0.5% | HTTP 5xx responses / total requests | Evidence needed: pending API integration telemetry |

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
- **Glue Crawler & Athena Views**: Tests verify that the Glue Crawler successfully catalogs the S3 raw partition structure and that Athena queries can aggregate cost metrics by service, region, account, and resource tags without syntax errors. Under the CUR-only telemetry design, no utilization signals from CloudWatch (CPU, memory, database connections) are gathered or sent to the AI Engine for detection. Utilization signals are verified to be used solely for CDO platform operational health observability (alerts, logging, metrics, dashboard).

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
- **Request Format Verification**: The test harness sends requests with schema version `telemetry://finops-watch/v3` containing headers `X-Tenant-Id`, `X-Idempotency-Key` (composite key: `tenant_id:YYYY-MM-DD`), `X-Correlation-Id`, `X-Payload-SHA256`, and `X-Request-Timestamp` to the Private REST API Gateway endpoint using IAM SigV4 authentication. The test verifies that the request payload is strictly CUR-only (either `RAW_JSON` or `S3_POINTER` types) and contains no CloudWatch utilization metrics.
- **Response Format Verification**: The test validates that the AI Engine returns a response containing the required parameters: `audit_id`, `status` (`completed` | `processing` | `failed`), `anomalies_list` (containing `anomaly_metadata`, `finance_dashboard_data`, and `engineering_dashboard_data`), and `pagination` controls (`next_token` and `limit`).

### 4.2 AI Engine timeout

- **Timeout Simulation**: A mock container task is configured to delay its response by 30 seconds (exceeding the 15-second client timeout).
- **Execution**: The CDO orchestration client invokes the API.
- **Verification**: The CDO platform detects the timeout, halts the request, logs a warning, and attempts up to 3 retries before escalating.

### 4.3 Unavailable-AI fallback

If the AI Engine is completely unreachable (e.g., HTTP 503 error, API Gateway gateway/integration timeout, or Lambda execution concurrency exhaustion):
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

### 4.6 API Gateway private endpoint connectivity

- **VPC Endpoint Ingress**: Probes the Private REST API Gateway endpoint connectivity from within the private VPC subnets.
- **Metrics & Authentication**: Response time for basic health checks must remain below 50 milliseconds using IAM SigV4 signatures.

### 4.7 Autoscaling and concurrency controls

- **Concurrency Load Simulation**: Simulates a burst of concurrent `/v1/detect` requests.
- **Reserved Concurrency Guardrail**: Verifies that the Lambda function respects its configured Reserved Concurrency limit to prevent throttling other critical platform services, returning proper HTTP `429` (Too Many Requests) or buffering correctly in SQS.
- **Application Auto Scaling (Optional)**: If Provisioned Concurrency autoscaling is configured, verifies that metrics trigger the scaling of warmed executions.

### 4.8 API Result Polling & Pagination Tests

- **Polling Response Verification**: The test framework queries GET `/v1/detect/result/{audit_id}`. It verifies the contract's response states (`completed` vs. `processing` vs. `failed`) and validates the structure of the returned `anomalies_list` objects.
- **Pagination Validation**: Under test loads that generate multiple anomalies, the framework requests results with `limit=1` and validates that `next_token` is generated. It then queries subsequent pages using the token, confirming correct result index ordering.

### 4.9 Extend & Rollback Endpoints Tests

- **Extend/Snooze API Test**: Simulates an engineer action by POSTing to `/v1/action/extend` with `extend_seconds` and `reason`. The test verifies that the API updates the resource's countdown timer and returns `new_expiration_time`.
- **Rollback API Test**: Simulates clicking "Revert" on the dashboard by invoking POST `/v1/action/rollback`. The test verifies that:
  - The API checks authentication and matching `X-Tenant-Id`.
  - It successfully generates and returns the required rollback CLI command (e.g., `aws rds start-db-instance`).
  - The event status is logged to the audit trail as `rollback_initiated`.

### 4.10 Contract Error Codes & Validation Tests

- **Idempotency Conflicts (`409` & `400`)**:
  - **In-Progress Call (`409 Conflict`)**: Sending a request with an active idempotency key returns HTTP `409` and prevents duplicate executions.
  - **Payload Mismatch (`400 Bad Request`)**: Re-submitting a request with an existing idempotency key but a different request payload returns HTTP `400` with error code `ERR_IDEMPOTENCY_MISMATCH`.
- **Multi-Tenant Access Restriction (`403 Forbidden`)**: Probes calling GET `/v1/detect/result/{audit_id}` with an `audit_id` belonging to a different `X-Tenant-Id` are blocked immediately with HTTP `403` / `ERR_CROSS_TENANT_DENIED`.
- **Bedrock Timeout Fallback (`500 Internal Error`)**: When a mock Bedrock call exceeds the 45-second hard timeout, the system validates that the AI Engine terminates the task and writes a `failed` state to the DB. CDO polling intercepts HTTP `500` / `ERR_LLM_TIMEOUT` and shifts immediately to the static fallback rules engine.

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
- **Finance Group Read-Only Access Test**: Validates that users belonging to the `finops-finance-readonly` Cognito user group are authenticated successfully but are restricted to read-only views on the dashboard. Probes to execute containment actions (Extend or Rollback) via POST requests to `/v1/action/extend` or `/v1/action/rollback` are rejected with HTTP `403 Forbidden` / `ERR_INSUFFICIENT_PERMISSIONS`.
- **Engineering Group Action Authorization Test**: Verifies that users in the `finops-engineering-operator` and `finops-cdo-admin` Cognito user groups can successfully trigger Extend/Rollback actions on the dashboard, confirming the JWT tokens contain correct group claims when forwarded to the action API endpoints.
- **Session Expiration & Token Lifetime Test**: Validates that expired sessions (JWT token older than the 15-minute lifetime config) or tampered JWT cookie signatures are rejected by Lambda@Edge, causing immediate session termination and redirecting the user to re-authenticate.
- **Audit Logging for Auth Events**: Confirms that login/logout events, token validation failures, and unauthorized action attempts (e.g., Finance user attempting to rollback) are captured in the DynamoDB and S3 audit trail logs (e.g., logging `auth_success`, `auth_failure`, or `unauthorized_action_blocked`).

---

## 6. E2E demo scenario

The End-to-End demo demonstrates the entire ingestion, detection, alerting, and containment sequence:
- **Step 1 - Injection**: Synthetic unmanaged cost records (e.g., $500 spend on EC2 g5.4xlarge instances) are written to the CUR S3 bucket.
- **Step 2 - Trigger**: EventBridge triggers the Step Functions ingestion workflow.
- **Step 3 - API Invocation**: The ingestion workflow extracts the cost records, calls the Private REST API Gateway endpoint of the AI Engine API, which enqueues the request in SQS and returns a `202 Accepted` response.
- **Step 4 - Task Execution**: The Worker Lambda container function is triggered by SQS, processes the features, records the anomaly/audit results in DynamoDB, and saves the detailed reasoning evidence.
- **Step 5 - Dashboard Update**: Lambda aggregates the results, writes the updated JSON files to the dashboard S3 bucket, and triggers a CloudFront invalidation.
- **Step 6 - Alert Routing**: The Alert Routing Lambda is invoked, sending a Slack notification to the `squad-prediction-models` channel and an email notification to the Finance team via SNS/SES.
- **Step 7 - Dry-run Containment**: The CDO containment engine triggers a dry-run tag update (`FinOpsWatch: ReviewRequired`) and saves the audit record containing the rollback steps to S3.
- **Step 8 - Rollback Simulation**: The administrator clicks the "Revert" button on the CDO dashboard, executing the rollback steps defined in the audit record to return the tags to their baseline state.

---

## 7. Security test

### 7.1 Penetration touch points

- **S3 Bucket Access Control**: Probes verify that the CUR S3 bucket and the audit log S3 bucket reject all requests originating from outside the VPC endpoint policies and designated IAM roles.
- **API Gateway Resource Policy Isolation**: Verifies that direct ingress requests to the Private REST API Gateway from outside the VPC endpoint are blocked by resource policies and security group rules.
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
| 2 | Lambda Cold Start Timeout | AI Engine Lambda container initialization took longer than the API Gateway timeout limit. | Configured SQS buffer to handle requests asynchronously, preventing gateway timeouts. | 3 |
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
