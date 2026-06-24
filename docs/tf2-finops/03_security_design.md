# Security Design - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) -> Updated (W12 T4 Pack #2)
-->

## 1. Network Security

### 1.1 Network Diagram

The CDO platform enforces isolation within a dedicated VPC. All compute resources run in isolated private subnets with no internet gateway route. All AWS API communications and external model endpoint calls occur privately using AWS VPC Endpoints.

The security design assumes two primary trust boundaries: the CDO management account boundary and the member account boundary. Cost data, AI decision payloads, alert payloads, and containment audit records stay inside the CDO-controlled AWS network path. The AIOps-owned AI Engine is reachable only through an internal ECS service endpoint; it does not receive direct credentials for member account containment actions.

```mermaid
graph TD
    subgraph "CDO Management Account VPC (ap-southeast-1)"
        subgraph "Private Subnets (ECS & Core Logic)"
            subgraph "ECS Cluster"
                API_P[AI Engine API Tasks]
                WRK_P[AI Engine Worker Tasks]
            end
            L_Pull[Ingestion Lambda]
            L_Cont[Containment Lambda]
            ALB[Internal Application Load Balancer]
        end

        subgraph "VPC Endpoint Subnet"
            VPCE[VPC Endpoints: S3, DDB, Secrets Mgr, ECR]
        end
    end

    subgraph "External Cloud Environment"
        S3Raw[(S3 Raw Zone)]
        S3Cur[(S3 Curated Zone)]
        DDB[(DynamoDB Run State)]
        SM[Secrets Manager]
    end

    %% Network flows
    L_Pull -->|VPC Endpoint HTTPS| VPCE
    VPCE -->|Private link| S3Raw
    L_Cont -->|VPC Endpoint HTTPS| VPCE
    VPCE -->|Private link| DDB
    
    %% ECS traffic
    ALB -->|HTTPS Port 443| API_P
    API_P -->|gRPC/REST| WRK_P
    API_P -->|Fetch secrets via VPCE| VPCE
    VPCE -->|Fetch API Key| SM
```

*Caption: The ECS cluster, load balancer, and orchestration Lambda functions are deployed within private-only subnets. They utilize dedicated AWS VPC Interface Endpoints (Privatelink) to connect to AWS services, preventing data transmission over the public internet.*

### 1.2 Security Groups

Traffic between compute components is regulated using stateful security groups enforcing the principle of least privilege:

| SG name | Inbound | Outbound | Attached to |
|---|---|---|---|
| `alb-sg` | TCP 443 (from Step Functions / Lambda Client) | TCP 80/443 (to `ecs-tasks-sg`) | internal ALB |
| `ecs-tasks-sg` | TCP 80/443 (from `alb-sg`), TCP/UDP 53 (DNS) | TCP 443 (to `vpce-sg`), TCP/UDP 53 | ECS Fargate tasks (always-on & Spot) |
| `lambda-sg` | None | TCP 443 (to `vpce-sg`), TCP 443 (to `alb-sg`) | Lambda functions |
| `vpce-sg` | TCP 443 (from `ecs-tasks-sg` and `lambda-sg`) | None | VPC endpoints (S3, DynamoDB, ECR, Secrets Mgr) |

### 1.3 Network ACL / VPC Endpoint

VPC interface endpoints are configured with private DNS enabled, routing all traffic to:
- `com.amazonaws.ap-southeast-1.s3` (Gateway Endpoint)
- `com.amazonaws.ap-southeast-1.dynamodb` (Gateway Endpoint)
- `com.amazonaws.ap-southeast-1.secretsmanager` (Interface Endpoint)
- `com.amazonaws.ap-southeast-1.ecr.api` (Interface Endpoint)
- `com.amazonaws.ap-southeast-1.ecr.dkr` (Interface Endpoint)
- `com.amazonaws.ap-southeast-1.logs` (Interface Endpoint - CloudWatch logs)

Security groups are deployed in the ECS cluster to restrict task-to-task communications (e.g., blocking AI Engine Worker Tasks on Fargate Spot from initiating connections to anything other than the internal ALB or direct service endpoints).

Endpoint policies are scoped to the smallest practical action set. The S3 gateway endpoint allows reads from approved CUR export prefixes and writes only to the CDO raw/curated buckets. The DynamoDB endpoint allows access only to run-state, idempotency, audit, and dashboard-materialization tables. Interface endpoints for Secrets Manager, ECR, and CloudWatch Logs are restricted to the CDO VPC security groups and execution roles. Network ACLs remain simple and stateless, with public ingress denied and ephemeral return traffic allowed only inside private subnet ranges.

## 2. IAM & Access Control

### 2.1 Service Roles

AWS IAM service roles enforce strict separation. Crucially, no service role has administrative permissions or access to destructive functions on production environments:

| Role | Used by | Permissions |
|---|---|---|
| `FinOpsStepFunctionsRole` | Step Functions | `states:StartExecution`, `states:DescribeExecution`, `lambda:InvokeFunction` |
| `FinOpsCURPullerRole` | `LambdaCURPuller` | `s3:GetObject` (on target account CUR S3 bucket), `s3:PutObject` (on raw S3 bucket), `ce:GetCostAndUsage` |
| `FinOpsTaskExecutionRole` | ECS Agent | `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage`, `secretsmanager:GetSecretValue` (for container secret mapping) |
| `FinOpsAiApiIamRole` | AI Engine API task role | Read model config, read curated feature inputs, write invocation health metrics; no member account access. |
| `FinOpsAiWorkerIamRole` | AI Engine Worker task role | Read curated feature inputs and write batch output/checkpoints; no IAM mutation and no direct containment permissions. |
| `FinOpsContainmentRole` | `LambdaContainment` | `ec2:CreateTags` (non-prod), `asg:UpdateAutoScalingGroup` (non-prod). Explicit deny for `iam:*`, `s3:Delete*`, and prod resource termination. |

> [!IMPORTANT]
> **Hard Security Boundary**: Every CDO execution role has an attached Service Control Policy (SCP) ensuring it can **NEVER terminate prod, delete data, or modify IAM**. Production containment tasks are strictly restricted to tag, suggest, or dry-run audits.

### 2.2 ECS Task Role & ECS Task Execution Role

ECS Fargate tasks utilize two distinct types of IAM roles to enforce the principle of least privilege:
1. **ECS Task Execution Role** (`FinOpsTaskExecutionRole`): Used by the ECS container agent to authenticate with ECR to pull Docker images and to query Secrets Manager to resolve secret mappings in the task definition.
2. **ECS Task Role** (`FinOpsAiApiIamRole`, `FinOpsAiWorkerIamRole`): Used by the application code running inside the container to make AWS API calls, such as reading from S3 or writing metrics to CloudWatch, isolating container privileges.

Workloads do not inherit IAM permissions from EC2 hosts. Each service task is explicitly associated with its respective task role in the ECS task definition.

- **ECS Task Mappings**:

| Service/Task Name | Task Execution Role | Task Role | Managed Policies / Custom Scoped Policies |
|---|---|---|---|
| AI Engine API Tasks | `FinOpsTaskExecutionRole` | `FinOpsAiApiIamRole` | Read-only S3 access (model artifacts), CloudWatch write metrics. |
| `ai-engine-explainer` | `FinOpsTaskExecutionRole` | `FinOpsAiApiIamRole` | Read-only S3 access, CloudWatch write metrics. |
| AI Engine Worker Tasks | `FinOpsTaskExecutionRole` | `FinOpsAiWorkerIamRole` | Read-write S3 access (checkpoint & features), SQS read/write. |

### 2.3 Cross-account Access

Cross-account access to member account CUR buckets is governed by target account S3 bucket policies allowing read access to the centralized `FinOpsCURPullerRole` using External IDs.
Containment actions in member accounts are triggered via cross-account IAM Role Assumption (`AssumeRole`). The management account `LambdaContainment` role assumes `FinOpsContainmentWorkerRole` in the target account, executing tag additions or scaling down sandbox ASGs.

Every cross-account role trust policy includes an external ID, source account condition, and session tagging requirement so audit logs can map each action back to a CDO run. Production roles include explicit deny statements for termination, destructive storage operations, and IAM mutation. Non-production roles may allow limited containment actions only when the incoming request includes an approved `execution_mode`, environment tag, anomaly ID, and policy decision ID. If any of those fields are missing, the containment worker records a denied audit event and exits without retrying.

## 3. Secrets Management

### 3.1 Secrets Inventory

The following secrets are stored in AWS Secrets Manager:

| Secret | Storage | Rotation | Accessed by |
|---|---|---|---|
| `finops/ai-engine/api-key` | AWS Secrets Manager (KMS CMK encrypted) | 30 days automatic | ECS Task Agent (via native task definition Secrets mapping) |
| `finops/dashboard/db-creds` | AWS Secrets Manager | 60 days automatic | Athena crawler / Future QuickSight dataset engine |
| `finops/alerting/slack-webhook` | AWS Secrets Manager | 90 days manual | `LambdaAlertRouting` |
| `finops/ai-engine/contract-signing-key` | AWS Secrets Manager | 90 days automatic | Step Functions validation Lambda and AI Engine API Tasks |
| `finops/containment/external-id-seed` | AWS Secrets Manager | Manual rotation on incident | Containment role provisioning workflow |

### 3.2 Inject Pattern

We use native ECS Task Definition Secrets Manager mapping to inject secrets from AWS Secrets Manager into the container environment variables at runtime. The secrets are fetched by the ECS agent using the Task Execution Role during task startup, avoiding plaintext exposures in state files or code.

```json
{
  "containerDefinitions": [
    {
      "name": "fargate-api-tasks",
      "image": "123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/fargate-api-tasks:latest",
      "secrets": [
        {
          "name": "AI_ENGINE_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:finops/ai-engine/api-key:apiKey::"
        }
      ]
    }
  ]
}
```

For Lambda functions, secrets are resolved during function cold-starts, cached in the `/tmp` memory directory, and validated with cache TTL policies to avoid direct API invocation overhead.

The injection path intentionally differs by runtime. Lambda functions read secrets directly through the Secrets Manager SDK because they are short-lived adapters. ECS workloads receive secrets through native ECS task definition mappings so deployment files never contain plaintext values. Terraform creates secret containers and IAM permissions, but it does not store secret values in `.tfvars`, Terraform state, or build configurations.

### 3.3 Anti-leak Controls

- **CI/CD Scanning**: Gitleaks is integrated into GitHub Actions pipelines, blocking PR merges if plain-text credentials or key headers are detected.
- **VPC Endpoint Restriction**: Secrets Manager VPC Endpoints enforce policies restricting access to only the CDO management VPC CIDR.
- **Log Redaction**: Outbound application logs are passed through a regex-based masking filter, replacing API keys, tokens, and authorization headers with `[REDACTED]`.
- **Terraform State Control**: Terraform state is encrypted, access-controlled, and reviewed so sensitive values are modeled as secret references rather than plaintext outputs.
- **Container Boundary**: ECS workloads run as non-root, mount temporary storage read-only, and avoid writing secret material to persistent volumes or checkpoints.
- **Incident Response**: Suspected secret exposure triggers secret rotation, Git history review, CloudTrail lookup for `GetSecretValue`, and temporary suspension of affected deployment credentials.

## 4. Encryption

### 4.1 At Rest

All platform data is encrypted at rest using Customer Managed Keys (CMKs) in AWS KMS:

| Data | Storage | KMS key | Notes |
|---|---|---|---|
| Raw/Curated Cost Data | S3 | `aws/s3` or custom CMK | S3 Bucket Key enabled to reduce KMS API costs. |
| Run State & Metadata | DynamoDB | `aws/dynamodb` or custom CMK | Encrypted using KMS. |
| Secrets Store | Secrets Manager | `finops-secrets-key` | Decryption requires role trust. |
| Task Storage | Fargate Ephemeral Storage | `aws/ecs` or custom CMK | All task ephemeral storage is encrypted by default. |
| Audit Trail Logs | S3 Object Lock | `finops-audit-key` | Retained for 90 days with compliance lock. |

### 4.2 In Transit

- **TLS Requirements**: All ingress and egress traffic requires TLS 1.3 (with TLS 1.2 as a minimum fallback). Weak ciphers are disabled on the internal ALB.
- **Internal Service Traffic**: ECS task-to-task communications for API-to-worker traffic use private App Mesh integration or direct internal DNS routing with TLS encryption.
- **AI Engine Calls**: Step Functions and Lambda invoke the internal AI Engine endpoint through private networking only. The request includes a contract version and correlation ID, and the response is rejected if the signature, schema, or required fields are invalid.
- **Alert Webhooks**: Slack or email integrations are called from the alerting Lambda after payload minimization. Sensitive cost evidence is linked through internal dashboard/audit references instead of embedded directly in external messages.

### 4.3 Key Management

- **Rotation**: CMK keys rotate automatically every 365 days.
- **Access Policies**: Key policies enforce separation of duties, ensuring only the deployment pipelines can modify key settings, and only execution roles (Lambda/ECS) can call decrypt operations.
- **Audit**: All key usage is monitored and logged in AWS CloudTrail.
- **Blast-radius control**: Separate CMKs are preferred for cost data, audit records, secrets, and ECS task storage unless Finance and Security approve consolidation for cost reasons.
- **Break-glass access**: Manual decrypt access is not granted to day-to-day developers. Temporary access requires incident approval, ticket reference, expiry time, and post-use review.

## 5. Audit Logging

### 5.1 What to Log

Every action taken by the CDO platform is documented. For containment actions, the following schema is logged to the centralized database and S3:
```json
{
  "actor": "cdo-platform-orchestrator",
  "timestamp": "2026-06-23T07:20:00Z",
  "correlation_id": "corr-uuid-4444-5555-6666",
  "idempotency_key": "123456789012:2026-06-22T00:00:00Z",
  "anomaly_id": "anom-9988-7766",
  "resource_owner": "squad-prediction-models",
  "resource_id": "arn:aws:ec2:ap-southeast-1:123456789012:instance/i-0abcdef123456",
  "before_state": {
    "instance_type": "g5.4xlarge",
    "status": "running",
    "tags": {
      "Environment": "sandbox"
    }
  },
  "proposed_after_state": {
    "tags": {
      "Environment": "sandbox",
      "FinOpsWatch": "ReviewRequired",
      "AnomalyDetected": "true"
    }
  },
  "execution_mode": "dry-run",
  "rollback_path": {
    "action": "remove_tags",
    "keys": ["FinOpsWatch", "AnomalyDetected"]
  },
  "approval_status": "pending_squad_response",
  "retention_location": "s3://cdo-audit-trail-bucket/audit/year=2026/month=06/",
  "retention_period_days": 90
}
```

The audit record is written before any apply-mode operation is attempted, and it is updated after the operation with the final status. Dry-run operations still produce audit records because Finance needs to see what the platform would have done and why the action remained safe. AI model training datasets are not logged by CDO; CDO logs only invocation metadata, returned decision fields, and operational evidence references needed for alerting and containment.

### 5.2 Storage + Retention

Audit logs are stored securely with immutable controls:

| Log type | Storage | Retention | Query interface |
|---|---|---|---|
| Containment Audits | S3 + Object Lock | 90 days minimum | Athena / DynamoDB |
| AWS API Calls | CloudTrail (S3 Raw) | 1 year | Athena |
| ECS Container Logs | CloudWatch Logs | 30 days | CloudWatch Logs Insights |
| App/Lambda Logs | CloudWatch Logs | 14 days | CloudWatch Logs Insights |

Containment audit storage is append-only by design. DynamoDB supports low-latency dashboard lookup, while S3 with Object Lock is the durable evidence store. The dashboard should link to the audit record ID rather than duplicating sensitive before/after state in alert messages. Retention shorter than 90 days is not allowed for containment records, even in sandbox, because the capstone requirement measures traceability of automated decisions.

### 5.3 Synthetic Data Handling

To prevent mixing synthetic anomaly logs with real account settings during testing:
- CDO-owned demo injections are marked with `source = "synthetic-demo"`.
- Dashboard filters (S3 + CloudFront UI) allow toggling between real and synthetic data displays.
- Synthetic containment actions are routed to a mock target endpoint, leaving real AWS resources untouched.
- AIOps-owned model training, enhancement, and backtest datasets remain outside CDO ownership. CDO may store AIOps-provided model metrics as integration evidence, but it does not copy or reclassify the AI team's training dataset as CDO operational data.

## 6. CI Security Controls

- **Image & Dependency Scanning**: Trivy is integrated into the CI/CD pipeline. Build actions fail automatically if container images contain `CRITICAL` or `HIGH` severity CVEs.
- **Non-Root Execution**: Container configurations enforce running workloads as a non-root user (e.g., `"user": "1000"` in ECS Task Definition).
- **Task Security Standards**: ECS Task Definitions enforce host network isolation (`awsvpc` network mode) and restrict execution privileges (`readonlyRootFilesystem: true`, `privileged: false`).
- **Spot Workload Isolation**: Worker tasks running batch workloads are configured with ECS Fargate Spot capacity providers, ensuring they run exclusively on Spot instances, avoiding resource starvation on stable always-on service tasks.

## 7. Compliance Touchpoints

| Standard | Relevant controls (capstone scope) |
|---|---|
| **SOC 2 Type II** | Least privilege IAM roles, VPC private network boundaries, Secrets Manager rotation, encrypted S3 buckets. |
| **ISO 27001** | Weekly access audit reports, immutable containment logs, automatic key rotation. |
| **HIPAA** | Out of scope (Cost billing data contains no Protected Health Information). |

The compliance mapping is intentionally limited to capstone-relevant controls. The platform handles billing and operational metadata, not customer application payloads, but the data still reveals account structure, resource usage, and owner tags. That makes least privilege, audit retention, encryption, and alert minimization mandatory even when no regulated customer data is present.

## 8. Open Questions

- [ ] **Cross-Account KMS Strategy**: Should we use a centralized KMS key with cross-account access, or local target account keys for CUR S3 bucket encryption?
- [ ] **Operator Notification Channels**: When a containment action is denied, should the platform escalate alerts via PagerDuty or direct Slack webhook notifications?
- [ ] **External Alert Redaction**: Which cost fields are allowed in Slack/email, and which must remain dashboard-only?
- [ ] **Break-glass Approver**: Who approves temporary decrypt or production investigation access during an incident?

## Related documents

- [`02_infra_design.md`](02_infra_design.md) - Architecture design, VPC layout, and ECS Capacity Providers.
- [`04_deployment_design.md`](04_deployment_design.md) - CI/CD pipeline, GitHub Actions deployment pipelines, and secret rotation gates.
