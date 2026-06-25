# Demo & Presentation Pack - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

> [!IMPORTANT]
> **Safety Boundary**: The demo environment and all presentation scenarios must strictly demonstrate conformance to the absolute safety boundaries: **NEVER terminate prod, delete data, or modify IAM**.


## 1. Demo script

This script guides presenters through demonstrating the end-to-end FinOps Watch CDO platform capabilities, simulating a real-world synthetic cost anomaly detection and mitigation workflow.

### Step 1 - Inject synthetic cost anomaly
- **Action**: Run the synthetic injection script to insert cost records into the raw S3 billing bucket.
- **Telemetry Specifications**: The default telemetry ingestion source uses finalized CUR data via S3 partition pulls (Data Ingestion Type: `S3_POINTER`). If CUR data delivery is delayed (detected via platform lag checks), the CDO platform sets the request parameter `telemetry_delay_event = true` and falls back to daily AWS Cost Explorer API queries. Telemetry is hybrid, combining cost data with CloudWatch utilization telemetry (`resource_utilization_metrics` such as CPU utilization, memory, database connections, and disk I/O). If CloudWatch performance telemetry is missing, the system automatically falls back to CUR-only mode, setting `data_confidence = LOW` and forcing dry-run/alert-only containment.
- **Payload**: A batch of mock EC2 usage records showing a sudden 10x cost increase on an unmanaged GPU instance cluster (e.g., $500 spend on EC2 g5.4xlarge).
- **Verification**: Check S3 raw zone file path: `s3://cdo-raw-cost-bucket/exports/year=2026/month=06/`.

### Step 2 - Trigger pipeline scheduler
- **Action**: Manually invoke the EventBridge Scheduler rule or run the trigger command via the AWS CLI.
- **CLI Command**: `aws stepfunctions start-execution --state-machine-arn <State_Machine_ARN> --input "{\"Date\": \"2026-06-24\"}"` (using the rtk wrapper).
- **Verification**: Step Functions console shows a green "Running" status.

### Step 3 - Invoke AI Engine Lambda Synchronously (Logical POST /v1/detect semantics)
- **Action**: Monitor the ingestion Step Functions workflow as it reaches the AI scoring state.
- **Internal Action**: The CDO orchestration Step Functions workflow directly invokes the AI Engine Lambda function synchronously using IAM invocation permissions (`lambda:InvokeFunction`).
- **Request Parameters (passed in Lambda invocation payload)**:
  - `X-Tenant-Id`: Identifies the tenant (e.g., `CDO-01`).
  - `X-Idempotency-Key`: Composite key format `{tenant_id}:{billing_period_date}:{batch_type}` (e.g., `CDO-01:2026-06-24:daily_batch`).
  - `X-Correlation-Id`: Execution tracking UUID.
  - `X-Payload-SHA256`: SHA256 integrity hash of the body payload.
  - `X-Request-Timestamp`: ISO 8601 timestamp.
  - `telemetry_delay_event`: Boolean flag (`true` if CUR is delayed and daily Cost Explorer fallback is active, `false` otherwise).
- **Request Payload**:
  - Schema URL: `telemetry://finops-watch/v3`.
  - Data Ingestion Type: `S3_POINTER` pointing to CUR data in S3 (default detection source), or `RAW_JSON` containing daily Cost Explorer API query results (fallback only when CUR is delayed, i.e., `telemetry_delay_event = true`).
  - Control Flags: `is_ad_hoc` (bypasses 24h idempotency for emergency scan), `is_estimated` (CE estimated spend, lowers confidence and bypasses auto-containment), `is_forced_dry_run` (if telemetry completeness < 0.8, forces dry-run mode).
  - Telemetry Data: Cost, metadata, and CloudWatch performance metrics (with automatic fallback to CUR-only mode if performance metrics are missing).
- **Verification**: Check Lambda execution logs for a successful synchronous response containing:
  - `success`: `true`
  - `correlation_id` (tracking UUID)
  - `data_confidence`: `"HIGH"` (indicating completed CUR + utilization run) or `"LOW"` (indicating fallback mode due to CUR delay or degraded telemetry)
  - `anomalies_detected`: `true`
  - `anomalies_list` (containing detailed anomaly objects)

### Step 4 - Verify Results & Write to S3 Authoritative Store
- **Action**: Verify that the Step Functions workflow stores the returned anomalies in the S3 Authoritative store and caches them in DynamoDB for dashboard rendering.
- **Internal Action**: The CDO platform evaluates the synchronous response. If `anomalies_detected` is true, it writes execution states and audit logs to the S3 Authoritative store (under `s3://company-cdo-telemetry/`) with Object Lock enabled, and updates the DynamoDB dashboard cache.
- **Result Payload (stored in S3/DynamoDB)**:
  - `correlation_id`: Matching execution UUID.
  - `data_confidence`: Telemetry confidence level (`HIGH` or `LOW`).
  - `anomalies_list`: Array of detected cost anomalies with fields: `anomaly_id`, `anomaly_type`, `severity`, `confidence_score`, `resource_id`, `environment`, `responsible_team`, `unblended_cost_24h_usd`, `cost_ratio_to_7d_avg`, `ai_model_used`, `alert_routing`.
- **Verification & Fail-safes**:
  - If a duplicate idempotency key is detected, the AI Engine returns a conflict response structure (representing HTTP `409` semantics).
  - If a duplicate key with mismatched payload is sent, the AI Engine returns a payload mismatch response structure (representing HTTP `400` with `ERR_IDEMPOTENCY_MISMATCH` semantics).
  - If Bedrock times out (45s Bedrock limit, returning `ERR_LLM_TIMEOUT`) or the service is down (`ERR_SERVICE_DOWN`), the CDO platform synchronously falls back to the static rules engine and alerts SRE.
  - Check the S3 authoritative audit bucket to verify the record has been written with a cryptographic audit trail chain link calculated as `sha256(current_payload + previous_hash)`.

### Step 5 - Get Intervention Plan (Logical POST /v1/decide semantics)
- **Action**: Once the status is complete, Step Functions invokes the AI Engine Lambda function (representing `/v1/decide` semantics) to retrieve the Root Cause Analysis (RCA) and containment action plan.
- **Request Parameters**: `X-Correlation-Id` and `X-Tenant-Id` headers.
- **Verification**: Verify that the AI Engine returns a plan containing the exact AWS CLI commands (e.g. `aws ec2 create-tags` in dry-run mode), the corresponding rollback CLI commands, and the `rollback_payload.boto3_equivalent` configuration block.

### Step 6 - Authenticate and access CDO dashboard (Cognito Hosted UI)
- **Action**: Open the dashboard CloudFront URL in a browser. Verify you are automatically redirected to the Cognito Hosted UI login screen. Log in using a Finance user account (associated with the `finops-finance-readonly` group).
- **Internal Action**: CloudFront forwards the request after the Lambda@Edge auth layer intercepts the request, validates the Cognito JWT token, and passes the request to the private S3 bucket. The dashboard parses the JWT group claim.
- **Verification**: Confirm the daily spend trends and anomaly overlays render successfully, but the manual Action Plan execution triggers and Rollback controls are completely disabled or hidden. If the error budget lock is active (prod >1%, staging >10%, dev/sandbox disabled), verify that a prominent red warning indicates the tenant is in `LOCKED_MODE` with lock reason `error_budget_exceeded_threshold`.

### Step 7 - Route alerts
- **Action**: Check the notification channels.
- **Internal Action**: The Alert Routing Lambda inspects the anomaly severity and squad ownership tags.
- **Verification**: 
  - Slack: Verify that a notification message has arrived in the `#squad-prediction-models` channel containing the resource ARN, cost delta, data confidence, correlation ID, and dashboard link.
  - SES/SNS: Verify that the Finance mailing list received an email summary of the cost spike, data confidence explanation, and proposed action plan.

### Step 8 - Execute dry-run containment (Cognito-authorized execution)
- **Action**: Log out of the Finance session and log back in as an Engineering Operator (member of the `finops-engineering-operator` group). Locate the active anomaly on the dashboard and click the "Execute Plan" button.
- **Internal Action**: The dashboard interface triggers the containment handler Lambda. The backend validates the active Cognito JWT cookie, checks group membership, and permits the operation.
- **Verification**: Verify that the targeted AWS EC2 instance remains running, but the authoritative S3 audit store (and the DynamoDB dashboard cache) has a new record showing a proposed action `stop_instance` with `execution_mode: dry-run` and a cryptographically chained block hash.

### Step 9 - Verify containment effectiveness (Logical POST /v1/verify semantics)
- **Action**: The CDO platform (or Step Functions workflow) calls `/v1/verify` (or direct Lambda equivalent) passing the `correlation_id` and post-action telemetry.
- **Internal Action**: AI Engine compares post-remediation utilization metrics with historical baseline to evaluate containment outcome.
- **Verification**: Verify the API returns status `DONE`, `RETRY`, or `ROLLBACK` and logs the verification result.

### Step 10 - Execute manual/auto rollback (Logical POST /v1/audit/{audit_id}/rollback semantics)
- **Action**: While logged in as an Engineering Operator, click the "Revert/Rollback" button on the CDO dashboard. Try the same action while logged in as a Finance user to verify rejection.
- **Internal Action**: The dashboard triggers the rollback handler Lambda (representing `/v1/audit/{audit_id}/rollback` semantics) with the Cognito session credentials. The backend checks Cognito group claims, verifies tenant context, reads the cached `rollback_payload.boto3_equivalent` configuration from S3, executes the rollback directly via Boto3 (allowing execution even if the AI Engine is offline), and then notifies the AI Engine rollback audit endpoint.
- **Verification**: Check CLI logs and S3/DynamoDB audit records to confirm the audit state changes to `RollbackCompleted` (returning `audit_recorded = true`) with the operator's Cognito user ID logged in the `actor` field. Confirm that the Finance user's attempt yields an authorization failure (representing HTTP `403 Forbidden` semantics) and writes an `unauthorized_action_blocked` audit entry. If the manual rollback rate exceeds the environment threshold (prod 1%, staging 10%), verify the tenant is locked into `LOCKED_MODE` (forcing all future decisions to dry-run).

### Step 11 - Verify callback delivery
- **Action**: Monitor the callback receiver endpoint logs during asynchronous runs.
- **Internal Action**: When the AI Engine completes a check, it delivers updates to the CDO callback endpoint.
- **Verification**: Confirm delivery is logged as platform telemetry. Verify that if delivery fails, the platform executes a retry schedule (0s, 30s, 120s) and logs `CALLBACK_EXHAUSTED` upon final failure without disrupting the synchronous detection results.

---

## 2. Evidence checklist

This checklist outlines the specific log files, database tables, and communication logs required to verify the successful execution of the CDO platform pipeline during audits.

- **CUR logs in S3**: Ingestion files stored under `s3://cdo-raw-cost-bucket/exports/` confirming raw data format compatibility.
- **VPC Flow Logs & IAM Telemetry**: Logs showing direct Lambda invocation execution logs and VPC Endpoint traffic with no internet egress.
- **S3 Authoritative logs & DynamoDB cache**:
  - Anomalies cache: Record containing `anomaly_id`, `confidence_score`, and `explanation` from the AI Engine, with pagination parameters.
  - Audit trail (authoritative in S3, cached in DynamoDB): Record containing all 14 containment action fields, verifying `correlation_id` matches the Step Functions execution, and containing a cryptographic audit trail chain block calculated as `sha256(current_payload + previous_hash)`.
- **Slack webhooks**: Webhook logs from the target Slack application channel, confirming correct JSON payload delivery without exposing raw cost structures.
- **QuickSight / Dashboard screenshots**: High-resolution image references showing:
  - Daily spend trend with anomaly point overlays.
  - Active containment list detailing the dry-run mode marker (Safety Value: `Never` for production, `After countdown` or `Yes with policy approval` for dev/sandbox).
- **CLI tag logs**: CloudTrail API logs confirming `ec2:CreateTags` dry-run API calls matching the targeted instance ARN.

---

## 3. CDO pitch points

Key selling points of the serverless lakehouse-centric FinOps control plane architecture:

- **Serverless cost savings**: By selecting S3, Glue, and Athena for the data lakehouse, the platform runs at a fraction of the cost of traditional always-on databases (RDS/Redshift). Compute costs are only incurred during the query execution window, resulting in up to 90% savings for daily batch operations.
- **Shared AI hosting optimization**: Hosting the shared AI Engine on AWS Lambda container images with direct synchronous invocations optimizes compute footprint across multiple CDO platforms (eliminating idle compute costs) while keeping tenant workloads isolated via the `X-Tenant-Id` header and IAM invocation permissions.
- **Complete compliance**: The dual-layer audit trail (DynamoDB for UI speed and S3 with Object Lock for immutability) guarantees that all automated and proposed actions are preserved for at least 90 days, meeting financial audit regulations. Every audit trail entry is cryptographically chained via `sha256(current_payload + previous_hash)` for tamper-proofing.
- **Risk-free operation**: Strict dry-run defaults in production and staging environments prevent accidental service outages. Automation is safely restricted to non-production/sandbox environments where policies are strictly enforced.
- **Multi-tenant isolation**: Structural S3 prefixes and Glue partitioning separate cost data by account and squad. Cross-account access relies on read-only IAM assume-role policies, preventing unauthorized lateral movements.

---

## 4. Curveball responses

Architectural justifications for common challenging questions:

- **How do you handle AWS CUR data export lag (up to 24 hours)?**
  - *Response*: The CDO platform default ingestion pipeline retrieves finalized CUR parquet exports from S3 using partition pulls (`S3_POINTER` format, asserting `telemetry_delay_event = false` and returning `data_confidence = HIGH`). If platform lag checks detect a billing data delay, the CDO pipeline sets the request parameter `telemetry_delay_event = true`, triggers fallback querying of daily AWS Cost Explorer API metrics, and the AI Engine returns `data_confidence = LOW` to alert stakeholders of the degraded data freshness.
- **How do you handle AI Engine false positives (normal scaling classified as anomaly)?**
  - *Response*: Our safety-first containment posture (ADR-005) ensures that no automated destructive action is ever taken on production resources. Furthermore, engineering squads receive Slack and dashboard alerts detailing the proposed containment plans. An Engineering Operator can manually review and click the "Execute Plan" button, or revert actions if they are determined to be false alarms. Additionally, detection telemetry is hybrid (CUR + Cost Explorer + CloudWatch utilization metrics), which improves classification accuracy. If CloudWatch metrics are unavailable, the platform automatically falls back to CUR-only mode, setting `data_confidence = LOW` and locking containment to dry-run or alert-only, preventing false positive actions. If rollbacks are triggered, the platform tracks the rollback rate and enforces tiered error budget locks: prod locks at >=1%, staging locks at >=10%, and dev/sandbox never locks, displaying the `LOCKED_MODE` banner on the dashboard with lock reason `error_budget_exceeded_threshold`.
- **What happens if a bug triggers automated containment on production assets?**
  - *Response*: Production environment containment is hardcoded at the IAM policy and Lambda runtime levels to dry-run mode (Safety Value: `Never`). Even in the event of database corruption or code malfunction, the IAM roles assigned to the containment Lambda do not possess the permissions necessary to delete, terminate, or shut down production resources.
- **How does the platform handle AWS Cost Explorer API throttling during scaling?**
  - *Response*: The ingestion Lambda features an integrated exponential backoff and retry mechanism. In addition, query results are cached locally in S3 for the duration of the run to prevent duplicate API requests for identical date ranges.
- **What happens if the dashboard becomes out-of-sync with actual AWS resources?**
  - *Response*: The static dashboard assets are updated immediately at the end of each pipeline run. A CloudFront invalidation is triggered programmatically to clear edge caches. A manual "Sync Now" button is also provided on the interface to query DynamoDB records directly.
- **How is rollback security enforced to prevent unauthorized resource changes?**
  - *Response*: Rollback execution is authenticated using Cognito JWT token validation, verified for tenant context, and logged to the WORM audit trail in S3. The CDO backend reads the cached `rollback_payload.boto3_equivalent` configuration from the decide phase and executes standard AWS Boto3 calls directly, ensuring that rollbacks are executed even if the AI Engine itself is offline. The results are then reported back to the rollback audit endpoint. To prevent replay attacks and handle billing delays, we split clock skew checks: API request timestamp skew > 300s is rejected (`ERR_REPLAY_DETECTED`), whereas CUR billing telemetry data delay up to 36 hours is accepted.
- **Who owns the Lambda container deployment and operational lifecycle of the shared AI Engine?**
  - *Response*: CDO owns the hosting infrastructure deployment (VPC, subnets, Lambda functions, concurrency limits, execution roles, queues, and DynamoDB state stores) to guarantee platform availability, security, and IAM execution controls. AIOps owns the AI model logic, RCA/recommendation logic, local fallback rules engine execution, internal API contract enforcement, and container image builds.
- **What happens if the AI Engine fails, times out, or receives duplicate requests?**
  - *Response*: If the AI Engine detects duplicate idempotency keys, it returns a conflict structure (representing HTTP `409` semantics), or a mismatch structure (representing HTTP `400` with `ERR_IDEMPOTENCY_MISMATCH` semantics) if payloads differ. If Bedrock times out (45s Bedrock hard limit, returning `ERR_LLM_TIMEOUT`) or the service is down (`ERR_SERVICE_DOWN`), the CDO pipeline immediately falls back to a static rules engine and triggers SRE alerts, ensuring a fail-safe containment posture. If AI Engine is offline during a rollback action, the CDO backend executes the rollback using the cached `rollback_payload.boto3_equivalent` configuration and reports the execution status, returning `audit_recorded = true`.

---

## 5. Open questions

- [ ] **Slack Webhook Integration Security**: Should we transition from static Slack incoming webhooks to a secure Slack App utilizing AWS Secrets Manager OAuth tokens for increased routing control?
- [ ] **Cognito OIDC Single Sign-On (SSO)**: Should we integrate the Cognito User Pool with the corporate Okta/O365 identity provider for single sign-on (SSO) instead of maintaining a standalone user directory?
- [ ] **Athena Query Limits**: What hard limits should be configured on Athena query data usage per day to prevent runaway billing from ad-hoc analysis?
- [ ] **Bedrock Model Token Budget**: What token limits should be set per tenant in Secrets Manager configurations to prevent Bedrock cost overruns during massive anomaly spikes? (`Evidence needed: Bedrock cost/token model benchmarks`)
