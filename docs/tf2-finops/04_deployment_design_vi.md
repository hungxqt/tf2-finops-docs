# Deployment & CI/CD Design - Task Force 2 · CDO06


## 1. IaC Strategy

### 1.1 Tool choice

- **IaC tool**: **Terraform**
  - Lý do: toàn bộ cohort dùng Terraform; state management rõ ràng với S3 backend + `use_lockfile = true` (S3 native locking); module reuse tốt cho multi-account pattern; không cần runtime container như CDK.
- **State backend**: S3 bucket (`finops-watch-tf-state-<account-id>`) với **S3 native locking** (`use_lockfile = true`) — remote state per environment, lock tránh concurrent apply. **Không dùng DynamoDB lock table** — yêu cầu AWS provider ≥ 5.47.
- **Modular structure**: shared modules tái sử dụng + environment-specific roots override variables.

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
│   └── dashboard/           # QuickSight dataset + analysis (hoặc lightweight internal dashboard)
├── environments/
│   ├── sandbox/             # main.tf + terraform.tfvars (account-sandbox)
│   ├── staging/             # main.tf + terraform.tfvars (account-staging)
│   └── prod/                # main.tf + terraform.tfvars (account-prod) — manual apply only
└── README.md
```

### 1.3 State management

- Remote state per environment: `s3://finops-watch-tf-state-<env>/terraform.tfstate`
- State lock via **S3 native lockfile** (`use_lockfile = true`) — Terraform tự tạo object `.terraform.lock.info` trong cùng S3 bucket; không cần DynamoDB table

**Terraform backend config mẫu:**
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
- **Plan-on-PR**: GitHub Actions chạy `terraform plan` và post output vào PR comment
- **Apply-on-merge**: `terraform apply` chạy tự động cho sandbox khi merge vào `develop` và cho staging khi merge vào `main`; prod yêu cầu manual approval gate
- Không bao giờ run `terraform apply` local trực tiếp lên staging/prod — mọi change qua pipeline

---

## 2. CI/CD Pipeline

### 2.1 Pipeline stages

```
PR opened ──► Lint ──► Test ──► Security Scan ──► TF Plan ──► Review ──► Merge ──► TF Apply ──► Smoke Test
```

| Stage | Tool | Mô tả | Quality gate |
|---|---|---|---|
| Lint | `terraform fmt`, `tflint` | Kiểm tra format + best practices Terraform | No format error, no lint warning |
| Unit test | `go test ./...` (các package Lambda Go) | Test logic Lambda: normalizer, router, containment policy | Coverage ≥ 80% |
| Security scan | **Trivy** (IaC scan) + **Gitleaks** (secret scan) | Phát hiện misconfiguration IaC + secrets bị lộ trong code | No CRITICAL IaC misconfiguration; no secret detected |
| TF Plan | `terraform plan` | Preview infra change, post diff vào PR comment | Plan success; reviewer approve diff |
| TF Apply | `terraform apply -auto-approve` | Deploy infra lên environment tương ứng | Apply exit 0 |
| Smoke test | Script smoke test tùy chỉnh | Gọi health check endpoint, verify Step Functions có thể start, verify S3 bucket accessible | All checks pass |

### 2.2 Branch strategy

```
main          ──── production-ready (auto-deploy staging, manual-approve prod)
  └── develop ──── integration branch (auto-deploy sandbox)
        └── feature/* ──── feature branches (trigger plan-only, no apply)
```

- PR vào `develop`: trigger Lint + Test + Scan + Plan. Apply sandbox tự động sau merge.
- PR vào `main` từ `develop`: trigger Plan staging. Apply staging tự động; apply prod cần manual approval.
- **No direct push** vào `main` hoặc `develop` — protected branches, require PR + review.

---

## 3. GitOps

### 3.1 Approach

Platform này **không dùng ArgoCD/Flux** vì không có Kubernetes cluster — compute là Lambda + Step Functions (serverless). GitOps pattern được áp dụng theo cách:

- **Git là source of truth**: mọi thay đổi infra đều qua commit → PR → merge. Không click console, không manual `apply`.
- **IaC = desired state**: Terraform state drift được phát hiện qua scheduled `terraform plan` hàng ngày.
- **Audit trail**: Git history + Terraform state + CloudTrail = chuỗi bằng chứng đầy đủ cho mọi change.

### 3.2 Drift detection

| Cơ chế | Tần suất | Hành động |
|---|---|---|
| Scheduled `terraform plan` | Hàng ngày 9h sáng | GitHub Actions chạy plan; nếu có diff → mở issue tự động + notify Slack Engineering |
| CloudTrail → CloudWatch alarm | Real-time | Alarm nếu có manual console change trên resource được quản lý bởi Terraform |
| S3 run state check | Sau mỗi workflow run | Verify last successful run < 26h qua S3 object metadata (last-modified); nếu không → CloudWatch alarm |

### 3.3 Change control

- **Non-destructive changes** (thêm resource, update Lambda code): auto-apply sau review.
- **Destructive changes** (xóa S3 bucket, thay đổi core resource): require explicit `lifecycle { prevent_destroy = true }` override + manual approval step trong pipeline.
- **Contract-related changes** (thay đổi Lambda AI client interface): require AIOps team sign-off trước khi merge — đây là frozen contract sau T5 W11.

---

## 4. Deployment Strategy

### 4.1 Lambda deployment strategy

Lambda không có traffic routing như container service, nên dùng **alias + weighted routing**:

```
Lambda function: finops-watch-ai-client
  ├── $LATEST           (development)
  ├── alias: stable     (100% traffic — current version)
  └── alias: canary     (10% → 50% → 100% shift qua CodeDeploy Lambda)
```

- **Canary shift**: 10% → 50% → 100% trong 15 phút (CodeDeploy `LambdaLinear10PercentEvery3Minutes`)
- **Abort criteria**:
  - Lambda error rate > 1% trong bất kỳ canary window nào
  - P99 duration > 800ms (CloudWatch alarm trigger)
  - Step Functions execution fail rate > 5%
- **Auto-rollback**: CodeDeploy tự động rollback alias về version cũ nếu alarm trigger

### 4.2 Step Functions + EventBridge update strategy

- Step Functions state machine definition thay đổi qua Terraform → apply tạo revision mới tự động.
- EventBridge Scheduler không bị interrupt trong quá trình update state machine (execution đang chạy hoàn thành với definition cũ).
- Nếu cần rollback state machine: Terraform `apply` lại commit cũ → tạo revision trước đó.

### 4.3 Rollback method

| Layer | Primary rollback | Secondary rollback | Target RTO |
|---|---|---|---|
| Lambda | CodeDeploy alias rollback về version cũ | `terraform apply` với version cũ trong tfvars | < 60s |
| Step Functions | `terraform apply` commit trước đó | Manual update via AWS Console (emergency only) | < 5 phút |
| S3/Glue/Athena | Không rollback — append-only data; rollback = reprocess | Restore từ S3 Versioning nếu object bị overwrite | < 30 phút |
| S3 State Lock | Xóa thủ công object `.terraform.lock.info` nếu lock bị treo | `terraform force-unlock` | < 5 phút |

---

## 5. Environment Separation

| Env | Mục đích | AWS Account | Auto-deploy | Containment behavior |
|---|---|---|---|---|
| **Sandbox** | Dev experimentation, W11 base IaC build, W12 testing | `account-sandbox` | Tự động khi merge vào `develop` | Tag + schedule shutdown + quota cap (approved) |
| **Staging** | Pre-prod integration, E2E test, chaos test W12 | `account-staging` | Tự động khi merge vào `main` | Tag + dry-run schedule shutdown + dry-run quota cap |
| **Prod** | Demo day T5 02/07, panel presentation | `account-prod` | Manual approval gate trong pipeline | Tag only + suggest only — KHÔNG apply bất kỳ containment nào |

**Hard rule**: `NEVER terminate prod, delete data, or modify IAM` — enforced bằng:
1. `lifecycle { prevent_destroy = true }` trên critical resources trong prod module.
2. SCP (Service Control Policy) trên account-prod block các action nguy hiểm.
3. Lambda containment worker kiểm tra `ENVIRONMENT` env var trước mọi action — nếu `prod` → chỉ dry-run.

---

## 6. Secrets in Pipeline

- **CI/CD authentication**: GitHub Actions dùng **OIDC + IAM assume-role** — không có static AWS keys trong GitHub Secrets.
- **Lambda runtime secrets**: AWS Secrets Manager — Lambda IAM role có `secretsmanager:GetSecretValue` chỉ cho secret ARN cụ thể.
- **Secret scanning**: Gitleaks chạy trên mọi PR — block merge nếu phát hiện secret pattern.
- **AI Engine credentials** (nếu có): lưu trong Secrets Manager, Lambda AI client fetch tại runtime, không hardcode trong environment variables.
- **Rotation**: Secrets Manager auto-rotation mỗi 30 ngày cho database credentials (nếu dùng).

---

## 7. Tenant (Account) Onboarding Deployment

Với TF2, "tenant" = một AWS member account cần được monitor chi phí.

```
1. Operator thêm account ID vào accounts.tfvars trong repo
2. PR review → merge → Terraform plan/apply:
   - Tạo cross-account IAM role trên management account (read-only cost + scoped containment)
   - Thêm account vào S3 owner mapping file (accounts/owner_mapping.json trong lakehouse bucket)
   - Cập nhật EventBridge Scheduler scope (nếu cần per-account schedule)
3. Smoke test: Lambda puller test assume-role vào account mới → verify Cost Explorer accessible
4. Confirm trong S3: account status object = "active" (s3://finops-watch-accounts/<account-id>/status.json)
```

Target time: **< 30 phút** từ khi merge PR đến khi account có data trong lakehouse.

---

## 8. Observability Stack

| Component | Tool | Mục đích |
|---|---|---|
| Metrics | **CloudWatch Metrics** (custom namespace `FinOpsWatch/CDO`) | Lambda duration/errors, Step Functions execution success/fail, S3 request metrics |
| Logs | **CloudWatch Logs** — structured JSON logging | Mọi Lambda emit JSON log với `run_id`, `correlation_id`, `cost_period`, `status` |
| Traces | **AWS X-Ray** + Lambda active tracing | End-to-end trace một workflow run: Scheduler → SFN → Lambda chain → AI call |
| Dashboards | **CloudWatch Dashboard** `FinOpsWatch-CDO-Ops` | Ops dashboard cho team (khác với finance dashboard cho CFO) |
| Alerts | **CloudWatch Alarms** → SNS Engineering route | Lambda error rate, SFN failure, AI client timeout, drift detection, audit write failure |

**Key alarms cần có trước demo:**

| Alarm | Metric | Threshold | Action |
|---|---|---|---|
| `WorkflowFailed` | SFN ExecutionsFailed | > 0 trong 5 phút | SNS Engineering |
| `AIClientTimeout` | Lambda `ai-client` errors | > 2 trong 5 phút | SNS Engineering + set `ai_unavailable` |
| `DriftDetected` | Custom metric từ scheduled plan | plan diff != 0 | SNS Engineering + open GitHub issue |
| `AuditWriteFailed` | Lambda `audit-writer` errors | > 0 | SNS Engineering + fail-closed workflow |
| `StaleWorkflow` | Custom metric: hours since last success | > 26h | SNS Finance + Engineering |

---

## 9. Open Questions

- [ ] **Q1**: AI Engine skeleton deploy trên Lambda hay Fargate? — cần biết để config VPC peering hay public endpoint cho Lambda AI client. *Resolve với AIOps EOD T4 W11.*
- [ ] **Q2**: CodeDeploy Lambda canary có available trên account sandbox không? — nếu không thì fallback về alias swap manual. *Verify T3 W11.*
- [ ] **Q3**: Prod account có cần separate AWS account thật hay dùng chung sandbox với env=prod flag? — ảnh hưởng SCP và IAM isolation. *Resolve T5 onsite với mentor.*

---

## Related Documents

- [`01_requirements_analysis.md`](01_requirements_analysis.md) — NFR targets và differentiation angle serverless-first
- [`02_infra_design.md`](02_infra_design.md) — Architecture lakehouse, Step Functions, Lambda chain, containment patterns
- [`03_security_design.md`](03_security_design.md) — IAM least-privilege, cross-account roles, SCP, audit trail
- [`08_adrs.md`](08_adrs.md) — ADR: chọn Terraform over CDK; ADR: GitOps without ArgoCD (serverless); ADR: canary Lambda alias over blue/green
