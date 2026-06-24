# Demo & Presentation Pack - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

## 1. Demo script

This script guides presenters through demonstrating the end-to-end FinOps Watch CDO platform capabilities, simulating a real-world synthetic cost anomaly detection and mitigation workflow.

### Step 1 - Inject synthetic cost anomaly
- **Action**: Run the synthetic injection script to insert cost records into the raw S3 billing bucket.
- **Telemetry Specifications**: The telemetry data is strictly CUR-only (S3 CUR partition pulls and Cost Explorer API calls). It excludes any CloudWatch performance telemetry (utilization signals like CPUUtilization, DatabaseConnections, or memory_mib) to keep the AI Engine detection focused purely on cost. CloudWatch metrics are used strictly by the CDO platform for operational observability.
- **Payload**: A batch of mock EC2 usage records showing a sudden 10x cost increase on an unmanaged GPU instance cluster (e.g., $500 spend on EC2 g5.4xlarge).
- **Verification**: Check S3 raw zone file path: `s3://cdo-raw-cost-bucket/exports/year=2026/month=06/`.

### Step 2 - Trigger pipeline scheduler
- **Action**: Manually invoke the EventBridge Scheduler rule or run the trigger command via the AWS CLI.
- **CLI Command**: `aws stepfunctions start-execution --state-machine-arn <State_Machine_ARN> --input "{\"Date\": \"2026-06-24\"}"` (using the rtk wrapper).
- **Verification**: Step Functions console shows a green "Running" status.

### Step 3 - Invoke shared AI Engine endpoint (POST /v1/detect)
- **Action**: Monitor the ingestion Step Functions workflow as it reaches the AI scoring state.
- **Internal Action**: The worker Lambda queries the raw partitioned cost data and performs an HTTP POST request to the single shared Task Force AI Engine endpoint via `https://ai-engine.tf-2.internal/v1/detect` using IAM SigV4 authentication.
- **Request Headers**:
  - `X-Tenant-Id`: Identifies the tenant (e.g., `CDO-01`).
  - `X-Idempotency-Key`: Composite key format `tenant_id:YYYY-MM-DD` (e.g., `CDO-01:2026-06-24`).
  - `X-Correlation-Id`: Execution tracking UUID.
  - `X-Payload-SHA256`: SHA256 integrity hash of the body payload.
  - `X-Request-Timestamp`: ISO 8601 timestamp.
- **Request Payload**:
  - Schema URL: `telemetry://finops-watch/v3`.
  - Data Ingestion Type: `RAW_JSON` for Cost Explorer API queries (<10MB) or `S3_POINTER` for CUR data in S3 (<500MB).
  - Control Flags: `is_ad_hoc` (bypasses 24h idempotency for emergency scan), `is_estimated` (CE estimated spend, lowers confidence and bypasses auto-containment), `is_forced_dry_run` (if telemetry completeness < 0.8, forces dry-run mode).
  - Telemetry Data: Cost and metadata attributes only, excluding CloudWatch performance metrics.
- **Verification**: Check Lambda execution logs for HTTP `202 Accepted` response with JSON body containing:
  - `audit_id` (tracking UUID)
  - `status`: `"processing"`
  - `retry_after_seconds`: `30`

### Step 4 - Poll results (GET /v1/detect/result/{audit_id}) & Execute AI Engine task
- **Action**: Poll the AI Engine result endpoint `GET /v1/detect/result/{audit_id}` periodically every 30 seconds.
- **Internal Action**: The AI Engine running on ECS Fargate (task size: 2 vCPU, 4 GB; cluster: `tf-2-aiops-cluster`) processes the ingestion payload. The container image (owned by AIOps) executes the AI model scoring, evaluates anomaly confidence, and compiles RCA details. Upon completion, the polling request returns HTTP `200 OK`.
- **Response Payload**:
  - `audit_id`: Matching execution UUID.
  - `anomalies_list`: Array of detected anomalies with confidence scores and explanations.
  - `pagination`: Pagination object containing `next_token` and `limit`.
- **Verification & Fail-safes**:
  - If a duplicate idempotency key is detected, the API returns HTTP `409` with `Retry-After: 30`.
  - If a duplicate key with mismatched payload is sent, the API returns HTTP `400` with `ERR_IDEMPOTENCY_MISMATCH`.
  - If Bedrock times out (45s Bedrock limit, returning `ERR_LLM_TIMEOUT`) or the service is down (`ERR_SERVICE_DOWN`), the pipeline immediately falls back to static rule execution and alerts SRE.
  - Check DynamoDB anomaly records table to verify the record has been written with a cryptographic audit trail chain link calculated as `sha256(current_payload + previous_hash)`.

### Step 5 - Update CDO dashboard
- **Action**: The aggregation Lambda is triggered to rebuild the dashboard assets.
- **Internal Action**: Aggregations are compiled into static S3 JSON files, and a CloudFront cache invalidation is executed.
- **Verification**: Open the dashboard URL in a browser and verify that the daily spend chart displays the anomalous cost peak overlay.

### Step 6 - Route alerts
- **Action**: Check the notification channels.
- **Internal Action**: The Alert Routing Lambda inspects the anomaly severity and squad ownership tags.
- **Verification**: 
  - Slack: Verify that a notification message has arrived in the `#squad-prediction-models` channel containing the resource ARN, cost delta, and dashboard link.
  - SES/SNS: Verify that the Finance mailing list received an email summary of the cost spike.

### Step 7 - Execute dry-run containment and countdown control
- **Action**: Inspect the containment audit trail and countdown controls.
- **Internal Action**: The containment engine executes policy checks on the target resource. Since the resource is marked under production rules, the engine executes in dry-run mode (Safety Value: `Never` auto-contain on production). In non-prod/dev environments, the engine may apply containment (Safety Value: `After countdown` or `Yes with policy approval`). Operators can snooze the containment countdown by invoking `POST /v1/action/extend`.
- **Verification**: Verify that the targeted AWS EC2 instance remains running, but the DynamoDB audit log table has a new record showing a proposed action `stop_instance` with `execution_mode: dry-run`.

### Step 8 - Execute rollback simulation (POST /v1/action/rollback)
- **Action**: Revert the simulated containment state from the dashboard interface or API.
- **Internal Action**: The administrator clicks the "Revert" button on the CDO dashboard, which invokes the `POST /v1/action/rollback` endpoint to execute the rollback steps defined in the audit record (e.g., restoring original tag state).
- **Verification**: Check CLI logs and DynamoDB records to confirm the audit state changes to `RollbackCompleted`.

---

## 2. Evidence checklist

This checklist outlines the specific log files, database tables, and communication logs required to verify the successful execution of the CDO platform pipeline during audits.

- **CUR logs in S3**: Ingestion files stored under `s3://cdo-raw-cost-bucket/exports/` confirming raw data format compatibility.
- **VPC Flow Logs & IAM SigV4 Verification**: Logs showing internal HTTP traffic routed safely to `https://ai-engine.tf-2.internal/` with SigV4 request signatures and no internet egress.
- **DynamoDB records**:
  - Anomalies table: Record containing `anomaly_id`, `confidence_score`, and `explanation` from the AI Engine, with pagination parameters.
  - Audit trail table: Record containing all 14 containment action fields, verifying `correlation_id` matches the Step Functions execution, and containing a cryptographic audit trail chain block calculated as `sha256(current_payload + previous_hash)`.
- **Slack webhooks**: Webhook logs from the target Slack application channel, confirming correct JSON payload delivery without exposing raw cost structures.
- **QuickSight / Dashboard screenshots**: High-resolution image references showing:
  - Daily spend trend with anomaly point overlays.
  - Active containment list detailing the dry-run mode marker (Safety Value: `Never` for production, `After countdown` or `Yes with policy approval` for dev/sandbox).
- **CLI tag logs**: CloudTrail API logs confirming `ec2:CreateTags` dry-run API calls matching the targeted instance ARN.

---

## 3. CDO pitch points

Key selling points of the serverless lakehouse-centric FinOps control plane architecture:

- **Serverless cost savings**: By selecting S3, Glue, and Athena for the data lakehouse, the platform runs at a fraction of the cost of traditional always-on databases (RDS/Redshift). Compute costs are only incurred during the query execution window, resulting in up to 90% savings for daily batch operations.
- **Shared AI hosting optimization**: Deploying a single shared AI Engine endpoint (`https://ai-engine.tf-2.internal/`) hosted on ECS Fargate (cluster `tf-2-aiops-cluster` using Fargate Spot for batch workloads) optimizes compute footprint across multiple CDO platforms while keeping tenant workloads isolated via the `X-Tenant-Id` header.
- **Complete compliance**: The dual-layer audit trail (DynamoDB for UI speed and S3 with Object Lock for immutability) guarantees that all automated and proposed actions are preserved for at least 90 days, meeting financial audit regulations. Every audit trail entry is cryptographically chained via `sha256(current_payload + previous_hash)` for tamper-proofing.
- **Risk-free operation**: Strict dry-run defaults in production and staging environments prevent accidental service outages. Automation is safely restricted to non-production/sandbox environments where policies are strictly enforced.
- **Multi-tenant isolation**: Structural S3 prefixes and Glue partitioning separate cost data by account and squad. Cross-account access relies on read-only IAM assume-role policies, preventing unauthorized lateral movements.

---

## 4. Curveball responses

Architectural justifications for common challenging questions:

- **How do you handle AWS CUR data export lag (up to 24 hours)?**
  - *Response*: While CUR exports have an inherent lag, our 24-hour scheduled cadence (ADR-001) is designed to align with this cycle. To bridge the gap for critical real-time alerts, our data plane combines CUR exports with daily calls to the AWS Cost Explorer API, which provides lower-latency cost aggregates.
- **How do you handle AI Engine false positives (normal scaling classified as anomaly)?**
  - *Response*: Our safety-first containment posture (ADR-005) ensures that no automated destructive action is ever taken on production resources. Furthermore, engineering squads receive Slack alerts with a "Snooze" button that invokes the `POST /v1/action/extend` API endpoint to snooze/extend the countdown, allowing them to mark the classification as normal scaling and suppress subsequent containment triggers for that resource. Additionally, detection telemetry is strictly CUR-only and does not send any CloudWatch utilization metrics (such as CPU, Memory, or DatabaseConnections) to the AI Engine for detection, keeping the data plane lightweight and compliant.
- **What happens if a bug triggers automated containment on production assets?**
  - *Response*: Production environment containment is hardcoded at the IAM policy and Lambda runtime levels to dry-run mode (Safety Value: `Never`). Even in the event of database corruption or code malfunction, the IAM roles assigned to the containment Lambda do not possess the permissions necessary to delete, terminate, or shut down production resources.
- **How does the platform handle AWS Cost Explorer API throttling during scaling?**
  - *Response*: The ingestion Lambda features an integrated exponential backoff and retry mechanism. In addition, query results are cached locally in S3 for the duration of the run to prevent duplicate API requests for identical date ranges.
- **What happens if the dashboard becomes out-of-sync with actual AWS resources?**
  - *Response*: The static dashboard assets are updated immediately at the end of each pipeline run. A CloudFront invalidation is triggered programmatically to clear edge caches. A manual "Sync Now" button is also provided on the interface to query DynamoDB records directly.
- **How is rollback security enforced to prevent unauthorized resource changes?**
  - *Response*: Rollback execution invokes the `POST /v1/action/rollback` API endpoint. It requires identical IAM permissions and MFA verification. Every rollback request must be tied to a valid incident ID or change ticket, and the action is fully logged to the WORM audit trail in S3.
- **Who owns the ECS Fargate deployment and operational lifecycle of the shared AI Engine?**
  - *Response*: CDO owns the hosting infrastructure deployment (VPC, subnets, internal ALB, DNS, task sizing, autoscaling, security groups, task IAM roles, queues, and DynamoDB state stores) to guarantee platform availability, security, and SigV4 authentication. AIOps owns the AI model logic, RCA/recommendation logic, local fallback rules engine execution, internal API contract enforcement, and container image builds.
- **What happens if the AI Engine fails, times out, or receives duplicate requests?**
  - *Response*: If the AI Engine detects duplicate idempotency keys, it returns HTTP `409` with a `Retry-After: 30` header, or `400` with `ERR_IDEMPOTENCY_MISMATCH` if payloads differ. If Bedrock times out (45s Bedrock hard limit, returning `ERR_LLM_TIMEOUT`) or the service is down (`ERR_SERVICE_DOWN`), the CDO pipeline immediately falls back to a static rules engine and triggers SRE alerts, ensuring a fail-safe containment posture.

---

## 5. Open questions

- [ ] **Slack Webhook Integration Security**: Should we transition from static Slack incoming webhooks to a secure Slack App utilizing AWS Secrets Manager OAuth tokens for increased routing control?
- [ ] **Cognito OIDC Custom Domain**: Will the Finance team require AWS Cognito OIDC user authentication with single sign-on (SSO) integration for dashboard access?
- [ ] **Athena Query Limits**: What hard limits should be configured on Athena query data usage per day to prevent runaway billing from ad-hoc analysis?
- [ ] **Bedrock Model Token Budget**: What token limits should be set per tenant in Secrets Manager configurations to prevent Bedrock cost overruns during massive anomaly spikes? (`Evidence needed: Bedrock cost/token model benchmarks`)
