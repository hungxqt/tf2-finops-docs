# Deployment & CI/CD Design - Task Force 2 · FinOps Watch CDO

<!-- Doc owner: CDO Team
     Status: Final (W11 T6 Pack #1) → Updated (W12 T4 Pack #2)
-->

## 1. IaC strategy

### 1.1 Tool choice

The CDO platform uses a dual-layer deployment strategy to separate infrastructure provisioning from application workload deployments.
1. **Infrastructure Layer (AWS Resources)**: Provisioned using **Terraform (v1.5+)** to ensure immutable resources (VPC, EKS cluster, node groups, DynamoDB, S3, IAM roles).
2. **Workload Layer (Kubernetes & Applications)**: Deployed using **Helm (v3)** and **GitOps (ArgoCD)** for application states within EKS, and native zip deployment zip files for Lambda functions.

Terraform owns the AWS platform foundation: networking, lakehouse buckets, Glue/Athena metadata, Step Functions, Lambda wrappers, DynamoDB tables, IAM roles, EKS control plane, managed node groups, ECR repositories, IRSA/OIDC foundations, internal load-balancer prerequisites, and secrets plumbing. Runtime Kubernetes desired state is managed through the GitOps layer, so application manifests and Helm values can move independently from infrastructure modules while still depending on Terraform outputs.

### 1.2 Module structure

The repository is organized to separate infrastructure modules from environmental variables:
```

The module boundary is intentionally service-oriented rather than team-oriented. Shared platform concerns such as KMS keys, VPC endpoints, IAM policies, and observability are reusable modules, while environment roots provide only sizing, account IDs, feature flags, and approval-sensitive variables. This prevents sandbox shortcuts from leaking into staging or prod.
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

- **Remote State**: Terraform state is stored in a secure, centralized S3 bucket with server-side encryption, versioning, and environment-specific state keys.
- **State Locking**: Long-lived environment roots use the S3 backend lockfile capability (`use_lockfile = true`) to avoid a separate DynamoDB lock table.
- **GitOps Ingestion**: Plan outputs are generated on PR (`plan-on-PR`) and apply jobs consume reviewed plan artifacts instead of recomputing unreviewed changes.
- **State Access**: CI roles can read/write only the state key for the target environment. Developers can run local validation, but staging and prod applies must be executed by CI with OIDC and environment controls.

### 2.1 CI/CD Pipeline

The CI/CD pipeline is implemented with **GitHub Actions** as the delivery control plane for the CDO infrastructure. It is not part of the runtime FinOps data path, but it controls how the infrastructure components in this design are validated, provisioned, updated, and verified.

The pipeline manages infrastructure and platform changes for:

* EventBridge Scheduler and Step Functions workflow.
* Lambda functions for ingestion, state handling, alert routing, and containment.
* S3 raw/curated zones, Glue Data Catalog, Athena query resources.
* DynamoDB run state and audit tables.
* EKS cluster, managed node groups, Internal ALB, ECR, and Kubernetes workloads.
* IAM roles and environment-specific configuration required by the CDO platform.

```mermaid
graph LR
    Dev[Developer PR / Push] --> GHA[GitHub Actions]
    GHA --> CI[Validate, Lint, Scan]
    CI --> Plan[Terraform Plan]
    Plan --> Review[PR Review]
    Review --> Apply[Terraform Apply]
    Apply --> AWS[AWS Infrastructure]
    Apply --> ECR[Build and Push Image to ECR]
    ECR --> EKS[EKS AI Engine Workloads]
    AWS --> Smoke[Smoke Test]
    EKS --> Smoke
```

*Caption: GitHub Actions validates every infrastructure change, generates a Terraform plan, applies approved changes to AWS, publishes container images to ECR, updates EKS workloads, and runs a smoke test to verify that the CDO platform can execute the FinOps workflow.*

The pipeline follows a simple environment flow:

| Environment | Trigger                        | Purpose                                                                            |
| ----------- | ------------------------------ | ---------------------------------------------------------------------------------- |
| `sandbox`   | Merge to `develop`             | Validate infrastructure and run safe integration tests with synthetic FinOps data. |
| `staging`   | Merge to `main`                | Verify the production-like workflow before final release.                          |
| `prod`      | Manual approval or release tag | Apply reviewed infrastructure changes only after approval.                         |

For Pull Requests, the pipeline runs only validation steps:

* `terraform fmt -check`
* `terraform validate`
* `tflint`
* Secret scanning
* IaC security scanning
* Kubernetes/Helm manifest validation
* Terraform plan generation

Pull Requests do **not** apply changes directly to AWS. The generated Terraform plan is reviewed before merge so the team can see which resources will be created, updated, replaced, or destroyed.

After merge, the deployment stage provisions or updates the infrastructure using Terraform. GitHub Actions assumes an AWS IAM role through **GitHub OIDC**, so no long-lived AWS access keys are stored in GitHub Secrets. Each environment uses a separate IAM role to limit blast radius.

| Pipeline stage  | Main target                           | Purpose                                                        |
| --------------- | ------------------------------------- | -------------------------------------------------------------- |
| Validate        | Terraform, Helm, scripts              | Catch invalid infrastructure code before deployment.           |
| Plan            | Terraform modules                     | Preview AWS infrastructure changes before apply.               |
| Apply           | AWS infrastructure                    | Provision or update CDO platform components.                   |
| Build image     | ECR                                   | Store versioned container images for EKS workloads.            |
| Deploy workload | EKS                                   | Update AI Engine API/worker workloads behind the Internal ALB. |
| Smoke test      | Step Functions, Lambda, EKS, DynamoDB | Verify the FinOps workflow after deployment.                   |

The post-deployment smoke test uses synthetic data and runs in dry-run mode:

```text
1. Trigger the Step Functions workflow manually.
2. Run the ingestion Lambda against synthetic CUR/Cost Explorer data.
3. Confirm raw and curated data are written to S3.
4. Confirm Glue/Athena can query the curated cost dataset.
5. Call the EKS-hosted AI Engine through the Internal ALB.
6. Confirm alert routing produces Finance/Engineering payloads.
7. Confirm containment stays in dry-run mode unless the target is dev/sandbox.
8. Confirm run state and audit records are written to DynamoDB.
```

A deployment is accepted only when the workflow passes validation, Terraform apply completes successfully, EKS workloads become healthy, and the smoke test confirms that ingestion, AI invocation, alert routing, containment dry-run, and audit logging work together.


## 3. Deployment gates

### 3.1 Security scans

In addition to static code analysis, ECR repositories are configured with **Scan on Push** enabled. Any image uploaded by AIOps is automatically scanned. Container deployment is blocked if the image contains severe CVEs. CI pipelines authenticate to AWS using **OpenID Connect (OIDC)**, eliminating the need to store static AWS Access Keys in GitHub.

The security gate also checks Terraform plans, Helm charts, Kubernetes manifests, Lambda dependencies, and container images. Required checks include `terraform fmt`, `terraform validate`, TFLint, Checkov or equivalent IaC scanning, Trivy image scan, Gitleaks secret scan, and policy checks that prevent public AI Engine exposure. Any CRITICAL finding blocks deployment unless a documented capstone exception is approved.

### 3.2 Destructive-change review

Any Terraform plan that modifies resource indexes or indicates resource deletion (e.g., S3 bucket recreation or IAM role changes) is flagged in the PR summary. These changes require explicit manual verification and dual approvals from both the CDO and Security Leads.

The destructive-change gate is stricter for stateful resources. S3 buckets, DynamoDB tables, KMS keys, EKS clusters, node groups, IAM roles, and audit storage require reviewer acknowledgement when replacement or deletion appears in the plan. Production plans must fail if they attempt to terminate prod resources, delete data, or modify IAM outside the approved module set.

### 3.3 AI contract compatibility

Before EKS updates are allowed, a pre-deployment script runs validation checks:
1. Compares the AIOps model version registry against the current EKS target configuration.
2. Performs JSON schema validation on the AI Engine `/detect` request/response API contracts.
3. If schemas mismatch, the build fails before applying Kubernetes changes, ensuring deployment compatibility.

The compatibility check does not evaluate model quality or inspect AIOps training data. It verifies only the operational contract CDO depends on: endpoint health, request schema, response schema, required fields, model version field, timeout behavior, and failure modes. If the AI Engine is unavailable or incompatible, CDO deployment can proceed only for infrastructure changes that do not enable containment apply paths.

## 4. Deployment strategy

### 4.1 Strategy

- **EKS API Workloads**: Deployed using **Rolling Updates** with a max surge of `25%` and max unavailable of `0%`. This ensures stable pods (`ai-engine-api`) have new replicas ready before old ones are terminated.
- **EKS Batch Workers**: Kubernetes Jobs execute dynamically. Updates to worker configurations affect new job invocations without interrupting active runs.
- **Lambda Functions**: Deployed using **Weighted Aliases**. Traffic shifts gradually: `10%` canary for 5 minutes, transitioning to `100%` if no errors occur.
- **Spot Node Draining**: Karpenter handles spot node interruptions. Node termination signals trigger Kubernetes pod eviction, gracefully draining active worker pods. If a batch scoring job is evicted, the orchestrator automatically schedules a retry on a healthy node.

### 4.2 Rollback method

- **Primary Rollback**: Driven by ArgoCD. Reverting a Git commit to the previous stable release SHA triggers an automatic sync rollback in the EKS cluster within 60 seconds.
- **Secondary Rollback**: For Lambda functions, the Step Functions workflow catches invocation errors and immediately shifts the Lambda alias weight back to the previous stable version (RTO < 10 seconds).
- **Infrastructure Rollback**: Terraform rollback is plan-reviewed rather than automatic. State-bearing resources are preserved, `prevent_destroy` remains enabled where supported, and any EKS infrastructure rollback must account for node group, IRSA, and internal endpoint dependencies.
- **Runbook Trigger**: Rollback is triggered by failed smoke tests, AI contract validation failure, elevated Step Functions error rate, unhealthy EKS node groups, or stale dashboard data after deployment.

## 5. Environment separation

We enforce isolation across three AWS accounts:

| Env | Purpose | Account | Auto-deploy |
|---|---|---|---|
| **Sandbox** | Fast iteration, integration smoke tests, and non-prod containment examples. | `1111-2222-3333` | True, from `develop` after checks pass |
| **Staging** | Validation of AIOps container artifacts, EKS hosting, and full Step Functions E2E pipeline execution. | `4444-5555-6666` | True, from `main` after reviewed merge |
| **Prod** | Production control plane. Monitors approved company accounts. Auto-containment is strictly tag/suggest/dry-run. | `7777-8888-9999` | False, requires GitHub environment approval |

Environment-specific values live only in `environments/*`. Sandbox may enable limited non-prod apply-mode examples; staging validates dry-run and integration behavior; prod must keep containment apply disabled by default.

## 6. Secrets in pipeline

Secrets are never embedded in the code or pipeline variables.
1. The CI/CD runner assumes an IAM role via OIDC to retrieve short-lived tokens.
2. Secrets (such as Slack webhooks or database passwords) are stored directly in AWS Secrets Manager.
3. ArgoCD mounts these secrets into EKS pods using the External Secrets Operator during runtime initialization.

GitHub secrets are limited to non-cloud metadata needed to bootstrap OIDC, not long-lived AWS keys. Terraform receives secret names and ARNs, not secret values. The deployment pipeline verifies that Helm values and Terraform outputs do not expose API keys, webhook URLs, or AI Engine credentials.

## 7. Scheduled batch deployment

The Step Functions state machine and EventBridge Scheduler are deployed using Terraform modules. The deployment process incorporates operational check runbooks:

```
1. Deploy updated Step Functions JSON definition via Terraform.
2. Temporarily disable the EventBridge Scheduler rule to prevent triggering midway.
3. Execute smoke-test run to verify API endpoint connectivity and Glue tables.
4. Enable the EventBridge Scheduler rule targeting the new state machine version.
5. Record pipeline transition and execution time in the DynamoDB deployment log.
```

The scheduler deployment sequence prevents half-updated workflow definitions from processing a daily run. If the state machine changes the AI invocation payload, the deployment also runs the AI contract compatibility check before re-enabling the schedule. Failed smoke tests leave the schedule disabled and create an operator alert with the previous known-good state machine ARN.

## 8. Observability stack

The platform's operational health is monitored using a centralized observability suite:

| Component | Tool | Purpose |
|---|---|---|
| **Log Aggregator** | CloudWatch Logs / Container Insights | Centralizes application, Lambda, and EKS container stdout logs. |
| **Trace Analyzer** | AWS X-Ray | Traces requests from Step Functions, through Lambda, to the EKS internal ALB. |
| **Metrics Collector** | Prometheus / Managed Grafana | Tracks EKS pod CPU/Memory usage, node group counts, and Karpenter actions. |
| **Alarms Engine** | CloudWatch Alarms | Sends alerts via SNS if Step Functions fail, or if the dashboard data is stale (>26 hours). |

Core deployment alarms cover Step Functions failure, Lambda error rate, AI Engine internal endpoint unavailability, EKS node group unhealthy state, excessive pending pods, spot interruption spikes, audit write failure, and dashboard data freshness. Deployment is not considered complete until these alarms are present and the smoke test writes an audit record.

## 9. Open questions

- [ ] **ArgoCD Topology**: Should we run ArgoCD in a hub-and-spoke model from the Management account, or deploy localized ArgoCD instances inside each environment's EKS cluster?
- [ ] **Grafana Integration**: Should the engineering metrics dashboard be shared with the AIOps team, or kept restricted to the CDO infrastructure team?
- [ ] **Plan Artifact Retention**: How long should reviewed Terraform plan artifacts be retained for staging and prod audit evidence?
- [ ] **Prod Release Branching**: Should production releases use a protected `prod` branch or GitHub release tags backed by environment approval?

## Related documents

- [`02_infra_design.md`](02_infra_design.md) - EKS cluster layout, network subnets, and node group routing.
- [`03_security_design.md`](03_security_design.md) - IRSA configurations, secrets inventory, and network policies.
