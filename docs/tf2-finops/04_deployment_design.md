# Deployment & CI/CD Design - Task Force 2 · CDO06


## 1. IaC Strategy

### 1.1 Tool choice

- **IaC tool**: **Terraform**
  - Rationale: the entire cohort uses Terraform; clear state management with S3 backend + `use_lockfile = true` (S3 native locking); good module reuse for multi-account patterns; no runtime container required unlike CDK.
- **State backend**: S3 bucket (`finops-watch-tf-state-<account-id>`) with **S3 native locking** (`use_lockfile = true`) — remote state per environment, lock prevents concurrent applies. **DynamoDB lock table is NOT used** — requires AWS provider ≥ 5.47.
- **Modular structure**: shared reusable modules + environment-specific roots that override variables.

### 1.2 Module structure

```
infra/
├── modules/
│   ├── networking/          # VPC, subnets, SG, VPC endpoints (S3, Step Functions)
│   ├── lakehouse/           # S3 buckets (raw/curated/audit), Glue catalog, Athena workgroup
│   ├── orchestration/       # EventBridge Scheduler, Step Functions Standard, DynamoDB tables
│   ├── compute-lambda/      # Lambda functions (puller, normalizer, ai-client, router, containment)
│   ├── alerting/            # SNS topics, subscriptions (Finance route + Engineering route)
│   ├── observability/       # CloudWatch log groups, metric filters, alarms, dashboard
│   ├── iam/                 # IAM roles: execution roles, cross-account read, containment scoped roles
│   └── dashboard/           # QuickSight dataset + analysis (or lightweight internal dashboard)
├── environments/
│   ├── sandbox/             # main.tf + terraform.tfvars (account-sandbox)
│   ├── staging/             # main.tf + terraform.tfvars (account-staging)
│   └── prod/                # main.tf + terraform.tfvars (account-prod) — manual apply only
└── README.md
```

### 1.3 State management

- Remote state per environment: `s3://finops-watch-tf-state-<env>/terraform.tfstate`
- State lock via **S3 native lockfile** (`use_lockfile = true`) — Terraform automatically creates the `.terraform.lock.info` object in the same S3 bucket; no DynamoDB table required

**Sample Terraform backend config:**
```hcl
terraform {
  backend "s3" {
    bucket       = "finops-watch-tf-state-<env>"
    key          = "terraform.tfstate"
    region       = "ap-southeast-1"
    use_lockfile = true   # S3 native locking — requires AWS provider >= 5.47
    encrypt      = true
  }
}
```
- **Plan-on-PR**: GitHub Actions runs `terraform plan` and posts the output as a PR comment
- **Apply-on-merge**: `terraform apply` runs automatically for sandbox when merging into `develop` and for staging when merging into `main`; prod requires a manual approval gate
- Never run `terraform apply` locally directly against staging/prod — all changes go through the pipeline

---

## 2. CI/CD Pipeline

### 2.1 Pipeline stages

```
PR opened ──► Lint ──► Test ──► Security Scan ──► TF Plan ──► Review ──► Merge ──► TF Apply ──► Smoke Test
```

| Stage | Tool | Description | Quality gate |
|---|---|---|---|
| Lint | `terraform fmt`, `tflint` | Check Terraform format + best practices | No format error, no lint warning |
| Unit test | `pytest` (Lambda functions) | Test Lambda logic: normalizer, router, containment policy | Coverage ≥ 80% |
| Security scan | **Trivy** (IaC scan) + **Gitleaks** (secret scan) | Detect IaC misconfigurations + secrets exposed in code | No CRITICAL IaC misconfiguration; no secret detected |
| TF Plan | `terraform plan` | Preview infra changes, post diff to PR comment | Plan success; reviewer approves diff |
| TF Apply | `terraform apply -auto-approve` | Deploy infra to the corresponding environment | Apply exit 0 |
| Smoke test | Custom Python script | Call health check endpoint, verify Step Functions can start, verify S3 bucket accessible | All checks pass |

### 2.2 Branch strategy

```
main          ──── production-ready (auto-deploy staging, manual-approve prod)
  └── develop ──── integration branch (auto-deploy sandbox)
        └── feature/* ──── feature branches (trigger plan-only, no apply)
```

- PR into `develop`: triggers Lint + Test + Scan + Plan. Sandbox auto-deploys after merge.
- PR into `main` from `develop`: triggers staging Plan. Staging auto-deploys; prod apply requires manual approval.
- **No direct push** into `main` or `develop` — protected branches, require PR + review.

---

## 3. GitOps

### 3.1 Approach

This platform **does not use ArgoCD/Flux** because there is no Kubernetes cluster — compute is Lambda + Step Functions (serverless). The GitOps pattern is applied as follows:

- **Git is the source of truth**: all infra changes go through commit → PR → merge. No console clicks, no manual `apply`.
- **IaC = desired state**: Terraform state drift is detected via a scheduled daily `terraform plan`.
- **Audit trail**: Git history + Terraform state + CloudTrail = a complete chain of evidence for every change.

### 3.2 Drift detection

| Mechanism | Frequency | Action |
|---|---|---|
| Scheduled `terraform plan` | Daily at 9:00 AM | GitHub Actions runs plan; if diff exists → automatically opens an issue + notifies Slack Engineering |
| CloudTrail → CloudWatch alarm | Real-time | Alarm if any manual console change occurs on a Terraform-managed resource |
| S3 run state check | After every workflow run | Verify last successful run < 26h via S3 object metadata (last-modified); if not → CloudWatch alarm |

### 3.3 Change control

- **Non-destructive changes** (adding resources, updating Lambda code): auto-apply after review.
- **Destructive changes** (deleting S3 buckets, modifying core resources): require explicit `lifecycle { prevent_destroy = true }` override + manual approval step in the pipeline.
- **Contract-related changes** (modifying the Lambda AI client interface): require AIOps team sign-off before merging — this is a frozen contract after T5 W11.

---

## 4. Deployment Strategy

### 4.1 Lambda deployment strategy

Lambda has no traffic routing like a container service, so **alias + weighted routing** is used:

```
Lambda function: finops-watch-ai-client
  ├── $LATEST           (development)
  ├── alias: stable     (100% traffic — current version)
  └── alias: canary     (10% → 50% → 100% shift via CodeDeploy Lambda)
```

- **Canary shift**: 10% → 50% → 100% over 15 minutes (CodeDeploy `LambdaLinear10PercentEvery3Minutes`)
- **Abort criteria**:
  - Lambda error rate > 1% in any canary window
  - P99 duration > 800ms (CloudWatch alarm trigger)
  - Step Functions execution fail rate > 5%
- **Auto-rollback**: CodeDeploy automatically rolls back the alias to the previous version if an alarm triggers

### 4.2 Step Functions + EventBridge update strategy

- Step Functions state machine definition changes via Terraform → apply automatically creates a new revision.
- EventBridge Scheduler is not interrupted during state machine updates (in-flight executions complete with the old definition).
- If a state machine rollback is needed: `terraform apply` the previous commit → creates the earlier revision.

### 4.3 Rollback method

| Layer | Primary rollback | Secondary rollback | Target RTO |
|---|---|---|---|
| Lambda | CodeDeploy alias rollback to previous version | `terraform apply` with previous version in tfvars | < 60s |
| Step Functions | `terraform apply` previous commit | Manual update via AWS Console (emergency only) | < 5 minutes |
| S3/Glue/Athena | No rollback — append-only data; rollback = reprocess | Restore from S3 Versioning if object overwritten | < 30 minutes |
| S3 State Lock | Manually delete `.terraform.lock.info` object if lock is stuck | `terraform force-unlock` | < 5 minutes |

---

## 5. Environment Separation

| Env | Purpose | AWS Account | Auto-deploy | Containment behavior |
|---|---|---|---|---|
| **Sandbox** | Dev experimentation, W11 base IaC build, W12 testing | `account-sandbox` | Automatic on merge into `develop` | Tag + schedule shutdown + quota cap (approved) |
| **Staging** | Pre-prod integration, E2E test, chaos test W12 | `account-staging` | Automatic on merge into `main` | Tag + dry-run schedule shutdown + dry-run quota cap |
| **Prod** | Demo day T5 02/07, panel presentation | `account-prod` | Manual approval gate in pipeline | Tag only + suggest only — DO NOT apply any containment |

**Hard rule**: `NEVER terminate prod, delete data, or modify IAM` — enforced by:
1. `lifecycle { prevent_destroy = true }` on critical resources in the prod module.
2. SCP (Service Control Policy) on account-prod blocking dangerous actions.
3. Lambda containment worker checks the `ENVIRONMENT` env var before every action — if `prod` → dry-run only.

---

## 6. Secrets in Pipeline

- **CI/CD authentication**: GitHub Actions uses **OIDC + IAM assume-role** — no static AWS keys in GitHub Secrets.
- **Lambda runtime secrets**: AWS Secrets Manager — Lambda IAM role has `secretsmanager:GetSecretValue` scoped only to specific secret ARNs.
- **Secret scanning**: Gitleaks runs on every PR — blocks merge if a secret pattern is detected.
- **AI Engine credentials** (if any): stored in Secrets Manager, Lambda AI client fetches at runtime, not hardcoded in environment variables.
- **Rotation**: Secrets Manager auto-rotation every 30 days for database credentials (if used).

---

## 7. Tenant (Account) Onboarding Deployment

For TF2, a "tenant" = an AWS member account that needs cost monitoring.

```
1. Operator adds account ID to accounts.tfvars in the repo
2. PR review → merge → Terraform plan/apply:
   - Creates cross-account IAM role on management account (read-only cost + scoped containment)
   - Adds account to S3 owner mapping file (accounts/owner_mapping.json in lakehouse bucket)
   - Updates EventBridge Scheduler scope (if per-account schedule is needed)
3. Smoke test: Lambda puller test assumes-role into new account → verify Cost Explorer accessible
4. Confirm in S3: account status object = "active" (s3://finops-watch-accounts/<account-id>/status.json)
```

Target time: **< 30 minutes** from PR merge to account having data in the lakehouse.

---

## 8. Observability Stack

| Component | Tool | Purpose |
|---|---|---|
| Metrics | **CloudWatch Metrics** (custom namespace `FinOpsWatch/CDO`) | Lambda duration/errors, Step Functions execution success/fail, S3 request metrics |
| Logs | **CloudWatch Logs** — structured JSON logging | Every Lambda emits JSON logs with `run_id`, `correlation_id`, `cost_period`, `status` |
| Traces | **AWS X-Ray** + Lambda active tracing | End-to-end trace of a workflow run: Scheduler → SFN → Lambda chain → AI call |
| Dashboards | **CloudWatch Dashboard** `FinOpsWatch-CDO-Ops` | Ops dashboard for the team (separate from the finance dashboard for CFO) |
| Alerts | **CloudWatch Alarms** → SNS Engineering route | Lambda error rate, SFN failure, AI client timeout, drift detection, audit write failure |

**Key alarms required before demo:**

| Alarm | Metric | Threshold | Action |
|---|---|---|---|
| `WorkflowFailed` | SFN ExecutionsFailed | > 0 in 5 minutes | SNS Engineering |
| `AIClientTimeout` | Lambda `ai-client` errors | > 2 in 5 minutes | SNS Engineering + set `ai_unavailable` |
| `DriftDetected` | Custom metric from scheduled plan | plan diff != 0 | SNS Engineering + open GitHub issue |
| `AuditWriteFailed` | Lambda `audit-writer` errors | > 0 | SNS Engineering + fail-closed workflow |
| `StaleWorkflow` | Custom metric: hours since last success | > 26h | SNS Finance + Engineering |

---

## 9. Open Questions

- [ ] **Q1**: Is the AI Engine skeleton deployed on Lambda or Fargate? — needed to configure VPC peering or public endpoint for the Lambda AI client. *Resolve with AIOps EOD T4 W11.*
- [ ] **Q2**: Is CodeDeploy Lambda canary available on the sandbox account? — if not, fall back to manual alias swap. *Verify T3 W11.*
- [ ] **Q3**: Does the prod account need a separate real AWS account or can it share the sandbox with an `env=prod` flag? — affects SCP and IAM isolation. *Resolve T5 onsite with mentor.*

---

## Related Documents

- [`01_requirements_analysis.md`](01_requirements_analysis.md) — NFR targets and serverless-first differentiation angle
- [`02_infra_design.md`](02_infra_design.md) — Lakehouse architecture, Step Functions, Lambda chain, containment patterns
- [`03_security_design.md`](03_security_design.md) — IAM least-privilege, cross-account roles, SCP, audit trail
- [`08_adrs.md`](08_adrs.md) — ADR: Terraform over CDK; ADR: GitOps without ArgoCD (serverless); ADR: canary Lambda alias over blue/green
