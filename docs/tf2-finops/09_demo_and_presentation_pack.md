# Demo & Presentation Pack - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Refined (W12 T4 Pack #2)
-->

## 1. Demo script

This script guides presenters through demonstrating the end-to-end FinOps Watch CDO platform capabilities, simulating a real-world synthetic cost anomaly detection and mitigation workflow.

### Step 1 - Inject synthetic cost anomaly
- **Action**: Run the synthetic injection script to insert cost records into the raw S3 billing bucket.
- **Payload**: A batch of mock EC2 usage records showing a sudden 10x cost increase on an unmanaged GPU instance cluster (e.g., $500 spend on EC2 g5.4xlarge).
- **Verification**: Check S3 raw zone file path: `s3://cdo-raw-cost-bucket/exports/year=2026/month=06/`.

### Step 2 - Trigger pipeline scheduler
- **Action**: Manually invoke the EventBridge Scheduler rule or run the trigger command via the AWS CLI.
- **CLI Command**: `aws stepfunctions start-execution --state-machine-arn <State_Machine_ARN> --input "{\"Date\": \"2026-06-24\"}"` (using the rtk wrapper).
- **Verification**: Step Functions console shows a green "Running" status.

### Step 3 - Invoke AI Engine ALB endpoint
- **Action**: Monitor the ingestion Step Functions workflow as it reaches the AI scoring state.
- **Internal Action**: The worker Lambda queries the raw partitioned cost data and performs an HTTP POST request to the internal ALB endpoint of the AI Engine API.
- **Verification**: Check Lambda execution logs for HTTP 200 response and correct correlation ID propagation.

### Step 4 - Execute AI Engine container task
- **Action**: Observe the AI Engine container task running on ECS Fargate.
- **Internal Action**: The container processes the cost features, evaluates the anomaly confidence score (e.g., 0.89), generates the explanation text, and writes the results to the DynamoDB anomaly records table.
- **Verification**: Check DynamoDB anomaly table for the newly inserted record with status `PendingReview`.

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

### Step 7 - Execute dry-run containment
- **Action**: Inspect the containment audit trail.
- **Internal Action**: The containment engine executes policy checks on the target resource. Since the resource is marked under production rules, the engine executes in `dry-run` mode.
- **Verification**: Verify that the targeted AWS EC2 instance remains running, but the DynamoDB audit log table has a new record showing a proposed action `stop_instance` with `execution_mode: dry-run`.

### Step 8 - Execute rollback simulation
- **Action**: Revert the simulated containment state from the dashboard interface.
- **Internal Action**: The administrator clicks the "Revert" button on the CDO dashboard, executing the rollback steps defined in the audit record (e.g., restoring original tag state).
- **Verification**: Check CLI logs and DynamoDB records to confirm the audit state changes to `RollbackCompleted`.

---

## 2. Evidence checklist

This checklist outlines the specific log files, database tables, and communication logs required to verify the successful execution of the CDO platform pipeline during audits.

- **CUR logs in S3**: Ingestion files stored under `s3://cdo-raw-cost-bucket/exports/` confirming raw data format compatibility.
- **DynamoDB records**:
  - Anomalies table: Record containing `anomaly_id`, `confidence_score`, and `explanation` from the AI Engine.
  - Audit trail table: Record containing all 14 containment action fields, verifying `correlation_id` matches the Step Functions execution.
- **Slack webhooks**: Webhook logs from the target Slack application channel, confirming correct JSON payload delivery without exposing raw cost structures.
- **QuickSight / Dashboard screenshots**: High-resolution image references showing:
  - Daily spend trend with anomaly point overlays.
  - Active containment list detailing the `dry-run` mode marker.
- **CLI tag logs**: CloudTrail API logs confirming `ec2:CreateTags` dry-run API calls matching the targeted instance ARN.

---

## 3. CDO pitch points

Key selling points of the serverless lakehouse-centric FinOps control plane architecture:

- **Serverless cost savings**: By selecting S3, Glue, and Athena for the data lakehouse, the platform runs at a fraction of the cost of traditional always-on databases (RDS/Redshift). Compute costs are only incurred during the query execution window, resulting in up to 90% savings for daily batch operations.
- **Complete compliance**: The dual-layer audit trail (DynamoDB for UI speed and S3 with Object Lock for immutability) guarantees that all automated and proposed actions are preserved for at least 90 days, meeting financial audit regulations.
- **Risk-free operation**: Strict dry-run defaults in production and staging environments prevent accidental service outages. Automation is safely restricted to non-production/sandbox environments where policies are strictly enforced.
- **Multi-tenant isolation**: Structural S3 prefixes and Glue partitioning separate cost data by account and squad. Cross-account access relies on read-only IAM assume-role policies, preventing unauthorized lateral movements.

---

## 4. Curveball responses

Architectural justifications for common challenging questions:

- **How do you handle AWS CUR data export lag (up to 24 hours)?**
  - *Response*: While CUR exports have an inherent lag, our 24-hour scheduled cadence (ADR-001) is designed to align with this cycle. To bridge the gap for critical real-time alerts, our data plane combines CUR exports with daily calls to the AWS Cost Explorer API, which provides lower-latency cost aggregates.
- **How do you handle AI Engine false positives (normal scaling classified as anomaly)?**
  - *Response*: Our safety-first containment posture (ADR-005) ensures that no automated destructive action is ever taken on production resources. Furthermore, engineering squads receive Slack alerts with a "Snooze" button, allowing them to mark the classification as normal scaling and suppress subsequent containment triggers for that resource.
- **What happens if a bug triggers automated containment on production assets?**
  - *Response*: Production environment containment is hardcoded at the IAM policy and Lambda runtime levels to dry-run mode. Even in the event of database corruption or code malfunction, the IAM roles assigned to the containment Lambda do not possess the permissions necessary to delete, terminate, or shut down production resources.
- **How does the platform handle AWS Cost Explorer API throttling during scaling?**
  - *Response*: The ingestion Lambda features an integrated exponential backoff and retry mechanism. In addition, query results are cached locally in S3 for the duration of the run to prevent duplicate API requests for identical date ranges.
- **What happens if the dashboard becomes out-of-sync with actual AWS resources?**
  - *Response*: The static dashboard assets are updated immediately at the end of each pipeline run. A CloudFront invalidation is triggered programmatically to clear edge caches. A manual "Sync Now" button is also provided on the interface to query DynamoDB records directly.
- **How is rollback security enforced to prevent unauthorized resource changes?**
  - *Response*: Rollback execution requires identical IAM permissions and MFA verification. Every rollback request must be tied to a valid incident ID or change ticket, and the action is fully logged to the WORM audit trail in S3.

---

## 5. Open questions

- [ ] **Slack Webhook Integration Security**: Should we transition from static Slack incoming webhooks to a secure Slack App utilizing AWS Secrets Manager OAuth tokens for increased routing control?
- [ ] **Cognito OIDC Custom Domain**: Will the Finance team require AWS Cognito OIDC user authentication with single sign-on (SSO) integration for dashboard access?
- [ ] **Production Rollback Automation**: Should the platform support automated one-click rollback for production tag suggestions, or should rollbacks in production remain strictly manual CLI actions?
- [ ] **Athena Query Limits**: What hard limits should be configured on Athena query data usage per day to prevent runaway billing from ad-hoc analysis?
