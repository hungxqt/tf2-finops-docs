# Test & Eval Report - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

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
| System Availability | >=99.5% | ALB API health check success rate | Evidence needed: pending ALB uptime statistics |
| Error Rate | < 0.5% | HTTP 5xx responses / total requests | Evidence needed: pending API integration telemetry |

### 2.2 SLO breach analysis

In the event of an SLO breach, the following escalation and remediation protocols are triggered:
- **Cost Explorer Throttling**: If the Cost Explorer API limits are exceeded, the ingestion Lambda catches the exception and retries using an exponential backoff strategy. If the run exceeds the 24-hour SLA window, the operational team is alerted via PagerDuty.
- **AI Engine Container Startup Timeouts**: If the Fargate Spot container tasks fail to start or experience long provisioning delays during peak scaling events, the platform dynamically delegates request processing to the always-on Fargate capacity provider tasks to maintain latency SLOs.
- **S3 / CloudFront Invalidation Delays**: If dashboard JSON updates fail to propagate due to CloudFront cache behavior, the invalidation API is automatically retried by the static site deployment pipeline.

---

## 3. CDO platform tests

### 3.1 Data ingestion

Data Ingestion verification focuses on retrieving and parsing cost data from AWS Data Exports (CUR 2.0) and AWS Cost Explorer API:
- **Raw Ingestion**: The raw ingestion Lambda retrieves parquet/CSV files from the billing S3 bucket and verifies that schema definitions match the defined layout.
- **Cost Explorer Queries**: Validates that mock responses from the Cost Explorer API match historical expectations and are mapped to normalized cost windows.
- **Glue Crawler & Athena Views**: Tests verify that the Glue Crawler successfully catalogs the S3 raw partition structure and that Athena queries can aggregate cost metrics by service, region, account, and resource tags without syntax errors.

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
- **Request Format Verification**: The test harness sends requests containing `correlation_id`, `anomaly_id`, and `cost_window` to verify that they conform to the schema.
- **Response Format Verification**: The test validates that the AI Engine returns a response containing the required parameters: `confidence_score` (between 0.00 and 1.00) and `explanation` (non-empty string).

### 4.2 AI Engine timeout

- **Timeout Simulation**: A mock container task is configured to delay its response by 30 seconds (exceeding the 15-second client timeout).
- **Execution**: The CDO orchestration client invokes the API.
- **Verification**: The CDO platform detects the timeout, halts the request, logs a warning, and attempts up to 3 retries before escalating.

### 4.3 Unavailable-AI fallback

If the AI Engine is completely unreachable (e.g., HTTP 503 error, ALB gateway timeout, or Fargate cluster exhaustion):
- **Fail Closed Behavior**: The CDO platform immediately aborts any scheduled containment action triggers. No automated policy is applied.
- **Operator Alert**: A critical incident ticket and PagerDuty alert are routed to the central CDO engineering and finance teams.
- **Audit Logging**: A failure record is written to the audit bucket, detailing the AI Engine's unavailability.

### 4.4 ECS task configuration/placement

- **Capacity Provider Placement**: Validation scripts inspect the active ECS task deployment configuration in the target environment.
- **Always-on Services**: Confirms that API servers, monitoring tasks, and the internal ALB are placed on always-on Fargate capacity providers to handle real-time traffic.
- **Batch Services**: Confirms that batch processing, feature engineering, and model training tasks are assigned to Fargate Spot capacity providers.

### 4.5 Fargate Spot interruption/retry

- **Interruption Mocking**: A simulated ECS Task Interruption Event is sent to the ECS Cluster.
- **SQS Queue Durability**: Validates that the active batch request is not lost and is returned to the SQS queue.
- **Task Retry**: Verifies that the task scheduler launches a replacement container and resumes processing from the last checkpoint stored in S3.

### 4.6 API availability

- **ALB Ingress Verification**: Probes the internal ALB endpoint (`/health`) from within the private subnet.
- **Metrics**: Response time must remain below 100 milliseconds for simple health check calls.

### 4.7 Autoscaling

- **Load Simulation**: High concurrency traffic is directed to the explainer endpoint.
- **AWS Application Auto Scaling**: Verifies that CPU utilization triggers the addition of tasks up to the configured limit, and decreases task counts when the traffic load subsides.

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

The containment engine must generate an audit log entry for every action attempt. This test verifies that the written JSON schema contains all 14 required fields:
1. `actor`: Entity executing the action (e.g., `cdo-platform-orchestrator`).
2. `timestamp`: UTC execution timestamp.
3. `correlation_id`: Unique identifier tracking the specific run.
4. `idempotency_key`: Key preventing double executions.
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

---

## 6. E2E demo scenario

The End-to-End demo demonstrates the entire ingestion, detection, alerting, and containment sequence:
- **Step 1 - Injection**: Synthetic unmanaged cost records (e.g., $500 spend on EC2 g5.4xlarge instances) are written to the CUR S3 bucket.
- **Step 2 - Trigger**: EventBridge triggers the Step Functions ingestion workflow.
- **Step 3 - API Invocation**: The ingestion workflow extracts the cost records, calls the internal ALB endpoint of the AI Engine API, and receives an anomaly classification response.
- **Step 4 - Task Execution**: The AI Engine container task processes the features, records the anomaly in DynamoDB, and saves the detailed reasoning.
- **Step 5 - Dashboard Update**: Lambda aggregates the results, writes the updated JSON files to the dashboard S3 bucket, and triggers a CloudFront invalidation.
- **Step 6 - Alert Routing**: The Alert Routing Lambda is invoked, sending a Slack notification to the `squad-prediction-models` channel and an email notification to the Finance team via SNS/SES.
- **Step 7 - Dry-run Containment**: The CDO containment engine triggers a dry-run tag update (`FinOpsWatch: ReviewRequired`) and saves the audit record containing the rollback steps to S3.
- **Step 8 - Rollback Simulation**: The administrator clicks the "Revert" button on the CDO dashboard, executing the rollback steps defined in the audit record to return the tags to their baseline state.

---

## 7. Security test

### 7.1 Penetration touch points

- **S3 Bucket Access Control**: Probes verify that the CUR S3 bucket and the audit log S3 bucket reject all requests originating from outside the VPC endpoint policies and designated IAM roles.
- **ECS Network Isolation**: Verifies that direct ingress requests to the AI Engine tasks from the public subnets or internet gateways are blocked by security group rules.
- **Containment IAM Restrictions**: Verifies that the Lambda/ECS task roles used for containment actions are blocked from modifying IAM policies, deleting S3 data, or shutting down critical production workloads.

### 7.2 Vulnerability scan

- **ECR Container Scanning**: The container images are scanned during the CI/CD pipeline using AWS native scanning.
- **Remediation**: The deployment is blocked if any CRITICAL or HIGH vulnerabilities are detected in the container runtime or dependencies.
- **Audit Trails**: Security scanning logs are archived alongside the deployment pipeline history.

---

## 8. Failure analysis

### 8.1 Failures encountered

The following table summarizes the failures resolved during the testing phases:

| No. | Failure Encountered | Root Cause | Fix / Resolution | Time to Fix (Hours) |
|---|---|---|---|---|
| 1 | CUR Schema Mismatch | AWS updated the billing CUR export structure, adding new columns. | Modified the Glue schema parsing config to handle dynamic schemas. | 6 |
| 2 | ALB Health Check Timeout | AI Engine container initialization took longer than health check thresholds. | Adjusted the target group health check grace period from 30s to 90s. | 3 |
| 3 | Slack Webhook Rate Limit | Multiple duplicate anomaly alerts triggered Slack rate limiting. | Implemented alert grouping and batching in the routing Lambda. | 8 |

### 8.2 Test gaps acknowledged

Due to environment constraints, the following test scenarios have not been verified with real production infrastructure:
- **Cross-Account Ingestion Scale**: Ingestion of cost data across more than 50 concurrent AWS accounts. (Evidence needed: pending multi-account staging environment setup)
- **Fargate Spot AWS Interruption Event Frequency**: Verification of actual Fargate Spot reclaim events under high cluster load. (Evidence needed: pending AWS Spot reclaim simulation data)
- **Production Containment Policy Impact**: Execution of apply-mode policy actions in a live production environment. (Evidence needed: pending compliance board approval)

---

## Related documents

- [`02_infra_design.md`](02_infra_design.md) - Contains the component tables, overall architecture diagram, and network security layouts.
- [`03_security_design.md`](03_security_design.md) - Details IAM service roles, encryption at rest, encryption in transit, and detailed audit log configurations.
- [`08_adrs.md`](08_adrs.md) - Explains architectural decisions including 24h cadence, dry-run-first containment, and ECS hosting choices.
