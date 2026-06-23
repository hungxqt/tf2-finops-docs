# Deployment & CI/CD Design - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) → Updated (W12 T4 Pack #2)
-->

## 1. IaC strategy

### 1.1 Tool choice

The CDO platform uses a dual-layer deployment strategy to separate infrastructure provisioning from application workload deployments.
1. **Infrastructure Layer (AWS Resources)**: Provisioned using **Terraform (v1.5+)** to ensure immutable resources (VPC, EKS cluster, node groups, DynamoDB, S3, IAM roles).
2. **Workload Layer (Kubernetes & Applications)**: Deployed using **Helm (v3)** and **GitOps (ArgoCD)** for application states within EKS, and native zip deployment zip files for Lambda functions.

### 1.2 Module structure

The repository is organized to separate infrastructure modules from environmental variables:
```
├── iac/
│   ├── modules/
│   │   ├── vpc/                  # Private VPC, subnets, NAT gateways, VPC endpoints
│   │   ├── eks/                  # EKS cluster control plane, on-demand/spot node groups
│   │   ├── s3-lakehouse/         # Raw and curated S3 buckets, lifecycle policies
│   │   ├── glue-catalog/         # Glue databases and tables
│   │   ├── step-functions/       # Step Functions workflow definitions
│   │   ├── lambdas/              # Lambda functions (CUR puller, routing, containment)
│   │   └── dynamodb/             # Run state, idempotency, and audit tables
│   └── environments/
│       ├── sandbox/              # Sandbox environment variables (.tfvars)
│       ├── staging/              # Staging environment variables
│       └── prod/                 # Production environment variables
```

### 1.3 State management

- **Remote State**: Terraform state is stored in a secure, centralized S3 bucket with server-side encryption (`AES256`) and versioning enabled.
- **State Locking**: Lock states are managed using a DynamoDB table (`cdo-tflock-table`) to prevent concurrent execution runs.
- **GitOps Ingestion**: Plan outputs are generated on PR (`plan-on-PR`) and applied automatically upon merging (`apply-on-merge`) following senior review approval.

## 2. CI/CD pipeline

### 2.1 Pipeline stages

Deployment pipelines are driven by GitHub Actions. The flow consists of compilation, validation, testing, staging deploy, and production manual approvals:

```
[PR Trigger] ──> Lint & Verify ──> Security Scan (Trivy/Gitleaks) ──> TF Plan ──> [Merge Approval]
                                                                                      │
[Smoke Test Prod] <── TF Apply Prod <── [Manual Approval Gate] <── Deploy Staging <───┘
```

The pipeline details are defined below:

| Stage | Tool | What it does | Quality gate |
|---|---|---|---|
| Ingest & Validate | `tflint`, `helm lint` | Validates Terraform syntax and Helm charts. | Zero syntax errors. |
| Security Scan | Trivy / Gitleaks | Scans Docker images and Helm charts for CVEs; detects embedded secrets. | Fail on `CRITICAL` or `HIGH` CVEs; zero secrets. |
| TF Plan | Terraform | Generates speculative plan for AWS infrastructure. | Successful plan execution. |
| Apply Staging | Terraform / ArgoCD | Deploys modules to staging account; synchronization of EKS Helm charts. | Pod status `Running` in EKS; 100% resource match. |
| Smoke Test Staging | Custom Python runner | Injects a test cost record and validates end-to-end alert routing. | Alert successfully delivered to test Slack. |
| Manual Approval Gate | GitHub Environment Gate | Pauses production pipeline, requiring manual approval from CDO Lead. | Manual reviewer signature. |
| Apply Prod | Terraform / ArgoCD | Provisions infrastructure and EKS workloads in production. | Zero errors in execution. |
| Smoke Test Prod | Custom Python runner | Executes a dry-run test sequence. | Dry-run audit record successfully written. |

### 2.2 Branch strategy

- `feature/*`: Dedicated branches for features. PR target: `develop`.
- `develop`: Staging environment branch. Auto-triggers deployment to the Staging account on push.
- `main`: Production branch. Merges from `develop` trigger staging validation before pausing at the production approval gate.

## 3. Deployment gates

### 3.1 Security scans

In addition to static code analysis, ECR repositories are configured with **Scan on Push** enabled. Any image uploaded by AIOps is automatically scanned. Container deployment is blocked if the image contains severe CVEs. CI pipelines authenticate to AWS using **OpenID Connect (OIDC)**, eliminating the need to store static AWS Access Keys in GitHub.

### 3.2 Destructive-change review

Any Terraform plan that modifies resource indexes or indicates resource deletion (e.g., S3 bucket recreation or IAM role changes) is flagged in the PR summary. These changes require explicit manual verification and dual approvals from both the CDO and Security Leads.

### 3.3 AI contract compatibility

Before EKS updates are allowed, a pre-deployment script runs validation checks:
1. Compares the AIOps model version registry against the current EKS target configuration.
2. Performs JSON schema validation on the AI Engine `/detect` request/response API contracts.
3. If schemas mismatch, the build fails before applying Kubernetes changes, ensuring deployment compatibility.

## 4. Deployment strategy

### 4.1 Strategy

- **EKS API Workloads**: Deployed using **Rolling Updates** with a max surge of `25%` and max unavailable of `0%`. This ensures stable pods (`ai-engine-api`) have new replicas ready before old ones are terminated.
- **EKS Batch Workers**: Kubernetes Jobs execute dynamically. Updates to worker configurations affect new job invocations without interrupting active runs.
- **Lambda Functions**: Deployed using **Weighted Aliases**. Traffic shifts gradually: `10%` canary for 5 minutes, transitioning to `100%` if no errors occur.
- **Spot Node Draining**: Karpenter handles spot node interruptions. Node termination signals trigger Kubernetes pod eviction, gracefully draining active worker pods. If a batch scoring job is evicted, the orchestrator automatically schedules a retry on a healthy node.

### 4.2 Rollback method

- **Primary Rollback**: Driven by ArgoCD. Reverting a Git commit to the previous stable release SHA triggers an automatic sync rollback in the EKS cluster within 60 seconds.
- **Secondary Rollback**: For Lambda functions, the Step Functions workflow catches invocation errors and immediately shifts the Lambda alias weight back to the previous stable version (RTO < 10 seconds).

## 5. Environment separation

We enforce isolation across three AWS accounts:

| Env | Purpose | Account | Auto-deploy |
|---|---|---|---|
| **Sandbox** | Local developer testing and testing of synthetic data formats. | `1111-2222-3333` | True (on PR push) |
| **Staging** | Validation of AIOps container artifacts and full Step Functions E2E pipeline execution. | `4444-5555-6666` | True (on merge to `develop`) |
| **Prod** | Production control plane. Monitors cost across all company accounts. Auto-containment is strictly dry-run. | `7777-8888-9999` | False (requires manual approval signature) |

## 6. Secrets in pipeline

Secrets are never embedded in the code or pipeline variables.
1. The CI/CD runner assumes an IAM role via OIDC to retrieve short-lived tokens.
2. Secrets (such as Slack webhooks or database passwords) are stored directly in AWS Secrets Manager.
3. ArgoCD mounts these secrets into EKS pods using the External Secrets Operator during runtime initialization.

## 7. Scheduled batch deployment

The Step Functions state machine and EventBridge Scheduler are deployed using Terraform modules. The deployment process incorporates operational check runbooks:

```
1. Deploy updated Step Functions JSON definition via Terraform.
2. Temporarily disable the EventBridge Scheduler rule to prevent triggering midway.
3. Execute smoke-test run to verify API endpoint connectivity and Glue tables.
4. Enable the EventBridge Scheduler rule targeting the new state machine version.
5. Record pipeline transition and execution time in the DynamoDB deployment log.
```

## 8. Observability stack

The platform's operational health is monitored using a centralized observability suite:

| Component | Tool | Purpose |
|---|---|---|
| **Log Aggregator** | CloudWatch Logs / Container Insights | Centralizes application, Lambda, and EKS container stdout logs. |
| **Trace Analyzer** | AWS X-Ray | Traces requests from Step Functions, through Lambda, to the EKS internal ALB. |
| **Metrics Collector** | Prometheus / Managed Grafana | Tracks EKS pod CPU/Memory usage, node group counts, and Karpenter actions. |
| **Alarms Engine** | CloudWatch Alarms | Sends alerts via SNS if Step Functions fail, or if the dashboard data is stale (>26 hours). |

## 9. Open questions

- [ ] **ArgoCD Topology**: Should we run ArgoCD in a hub-and-spoke model from the Management account, or deploy localized ArgoCD instances inside each environment's EKS cluster?
- [ ] **Grafana Integration**: Should the engineering metrics dashboard be shared with the AIOps team, or kept restricted to the CDO infrastructure team?

## Related documents

- [`02_infra_design.md`](02_infra_design.md) - EKS cluster layout, network subnets, and node group routing.
- [`03_security_design.md`](03_security_design.md) - IRSA configurations, secrets inventory, and network policies.
