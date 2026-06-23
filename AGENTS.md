# AGENTS.md - TF2 FinOps CDO Documentation Builder

## Purpose

This repository contains the client brief and reusable document templates for Task Force 2, "FinOps Watch". Future agents must use this file when creating the CDO documentation pack for the task force.

The goal is to produce a bilingual CDO documentation pack under `docs/tf2-finops/` (English and Vietnamese) that explains how the CDO platform operates the FinOps data/control plane, integrates with the AIOps-owned AI Engine, routes alerts, enforces safe containment, and maintains finance-readable evidence.

## Source Priority

Use sources in this order:

1. `TF2_FINOPS_LEARNER.md` - client brief and hard requirements.
2. Explicit user or client updates in the current conversation.
3. `template-docs/` - reusable structure and baseline section ideas.
4. Agent improvements, only when they do not contradict the sources above.

Do not overwrite files in `template-docs/`. Treat them as templates only.

## Scope

Create CDO documentation only. The docs may reference AI Engine contracts, anomaly metrics, backtest outputs, and alert payloads where needed for platform integration, but they must not invent AI model internals or replace the AIOps team's own documentation.

In scope:

- Requirements analysis for the CDO platform.
- Infrastructure design.
- Security design.
- Deployment and CI/CD design.
- Cost analysis.
- Finance-friendly dashboard and alert routing design.
- CDO test and evaluation report.
- Architecture Decision Records.
- Demo and presentation support document.

Out of scope unless the user explicitly expands scope:

- Full AI engine implementation spec.
- Multi-cloud design.
- Forecasting or budget planning product design.
- RI/SP recommendation engine or auto-trading.
- CloudHealth, Apptio, Vantage, or other third-party FinOps platform integration.
- Real AWS bill access.
- Self-service tenant onboarding UI.

## Default Architecture Choices

Use these defaults unless the user provides different decisions:

- Languages: English (primary) and Vietnamese (translation). Each document has two versions.
- Output folder: `docs/tf2-finops/`.
- Architecture angle: lakehouse-centric FinOps control plane with serverless orchestration and AIOps-owned AI Engine integration.
- AWS Region: `ap-southeast-1` for examples.
- Cadence decision: 24h default, defended as the middle trade-off between data freshness, Cost Explorer/CUR lag, operational cost, and false-positive control.
- Data sources: AWS Data Exports/CUR 2.0 or CUR in S3 plus Cost Explorer API.
- Data lake: S3 raw and curated zones, Glue Data Catalog, Athena views, and governed prefixes for cost, ownership, anomaly, alert, containment, and audit datasets.
- Orchestration: EventBridge Scheduler triggers Step Functions Standard workflows.
- Compute: Lambda for short CDO adapters and policy workers; EKS for hosting the AI Engine runtime and batch workloads.
- AI integration: CDO hosts the AIOps-provided AI Engine on EKS; CDO owns the hosting platform, deployment plumbing, runtime monitoring, autoscaling, node placement, and platform SLOs; AIOps owns AI Engine code, model versions, detection logic, confidence scoring, explanation text, and backtest metrics.
- AI Engine runtime: EKS cluster in `ap-southeast-1`, private subnets, ECR for container images, IRSA for pod-level IAM, internal ALB/NLB or Kubernetes ClusterIP service, CloudWatch Container Insights, Secrets Manager with External Secrets Operator or CSI driver.
- EKS on-demand node group workloads: ai-engine-api, ai-engine-explainer, monitoring, core CDO platform services (stable, always-on).
- EKS spot node group workloads: ai-engine-worker, batch scoring jobs, feature engineering jobs, model retraining jobs (interruptible, cost-optimized with retry/backoff and checkpoint storage).
- EKS scaling: HPA/KEDA for pod autoscaling, Cluster Autoscaler or Karpenter for node scaling, node affinity and tolerations for workload placement across on-demand and spot node groups.
- Analytics storage/query: S3, Glue Data Catalog, Athena, and materialized dashboard tables/views where needed.
- Operational metadata: DynamoDB tables for run state, anomaly records, routing state, idempotency keys, containment audit records, and dashboard materialized views.
- Dashboard: QuickSight or a lightweight internal web dashboard backed by Athena/DynamoDB views.
- Alerting: separate Finance and Engineering channels, such as email/Slack/SNS targets, with routing based on anomaly type and ownership tags.
- Containment posture: dry-run first, safe automation only for non-prod/dev/sandbox resources.

## CDO vs AIOps Responsibility Boundary

Use this boundary in every generated document:

- CDO owns cost data ingestion, normalized cost windows, ownership/tag metadata, scheduling, idempotency, workflow state, dashboard views, alert routing, containment guardrails, audit logs, platform operational SLOs, and the EKS hosting platform for the AI Engine (cluster lifecycle, managed node groups, networking, ingress/service exposure, deployment plumbing, runtime monitoring, autoscaling, node placement, and hosting SLOs).
- AIOps owns anomaly detection logic, model selection, model training/retraining design, model versioning, confidence scoring, anomaly classification, explanation text, AI Engine code and model internals, and AI backtest metrics. AIOps provides versioned container artifacts (images, model weights, configs); CDO deploys and operates them on EKS.
- CDO hosts the AI Engine on EKS and exposes it through an internal service endpoint. CDO consumes the AI Engine through a versioned contract. CDO must document request/response fields, authentication, timeout, retry, circuit-breaker, unavailable-AI fallback, evidence storage, and the EKS deployment/operations runbook.
- CDO must not claim responsibility for AI precision/recall internals. It may report AI metrics only as AIOps-provided integration evidence.
- If AI Engine is unavailable, CDO must fail closed for containment: no automatic apply action, alert operators, preserve the failed run, and write an audit record.

## Client Hard Requirements

Every generated document must respect these requirements from `TF2_FINOPS_LEARNER.md`:

- AWS only.
- Synthetic data only unless the user provides real bill access.
- Backtest target: precision >=80% and false-positive rate <=10% over 3 months.
- Time frame goal must be one of 12h, 24h, or 48h and defended in ADRs.
- NEVER terminate prod, delete data, or modify IAM.
- Auto-action on prod is limited to tag, suggest, or dry-run.
- Implement at least one containment pattern and design at least two more.
- dry-run mode is mandatory for all containment paths.
- Audit trail is mandatory for every containment action.
- Audit retention must be at least 90 days.
- Dashboard must be finance-readable and must not require SQL knowledge.
- Demo path must show synthetic anomaly injection, detection, alerting, and containment action trigger.

For every containment action, document:

- Actor.
- Timestamp.
- Correlation ID.
- Idempotency key.
- Anomaly ID.
- Resource/account/squad owner.
- Before state.
- Proposed or applied after state.
- Execution mode: `dry-run` or `apply`.
- Rollback path.
- Approval status when human approval is required.
- Retention location and retention period.

## Required Output Catalog

Create or update these files under `docs/tf2-finops/`. Every document must be produced in two versions:

- **English version**: uses the base filename (e.g., `02_infra_design.md`).
- **Vietnamese version**: appends `_vi` before the extension (e.g., `02_infra_design_vi.md`).

The Vietnamese version is a full translation of the English version, not a summary or subset. Both versions must contain identical structure, sections, diagrams, tables, and technical detail. See the **Bilingual Translation Rules** section for translation standards.

Each document below lists the **exact heading structure** the agent must produce. Headings use numbered sections matching the template-docs convention. The agent must use these exact section titles (adapted to the FinOps CDO context where the template uses generic placeholders). Content guidance follows each heading.

---

### Document 1 — `01_requirements_analysis.md`

**Title**: `# Requirements Analysis - Task Force 2 · FinOps Watch CDO`

Required sections:

- `## 1. Context` — Summarize the client problem from the CFO perspective. Restate the FinOps Watch brief concisely (1 paragraph).
- `## 2. Infra non-functional requirements` — Table with columns: NFR, Target, Justification. Include rows for scheduled processing cadence, availability, auditability, dashboard readability, cost per run, security baseline (IAM least-priv + audit 90 days).
- `## 3. Differentiation angle (KEY)` — State the lakehouse-centric FinOps control plane angle and why it fits production FinOps cadence. Include: angle chosen, why this angle, trade-off accepted, lock date.
- `## 4. CDO vs AIOps responsibility split` — Table or structured comparison showing CDO-owned vs AIOps-owned responsibilities (replaces the template's "Comparison với 2 nhóm cùng task force" since this project's differentiation is the CDO/AIOps boundary).
- `## 5. Constraints` — AWS only, region, synthetic data only, budget, code freeze, hard boundaries (NEVER terminate prod, delete data, or modify IAM).
- `## 6. Open questions` — Checklist of questions that truly require client or AIOps team clarification.

---

### Document 2 — `02_infra_design.md`

**Title**: `# Infrastructure Design - Task Force 2 · FinOps Watch CDO`

Required sections:

- `## 1. Architecture diagram` — Mermaid diagram showing AWS Data Exports/CUR S3 bucket, Cost Explorer API, S3 raw/curated zones, Glue/Athena, EventBridge Scheduler, Step Functions, Lambda, DynamoDB, EKS cluster with on-demand and spot node groups hosting the AI Engine, ECR, internal service endpoint, dashboard, alerting, and containment workers. Include a caption explaining the flow.
- `## 2. Component table` — Table with columns: Component, AWS Service, Reason, Cost note. One row per service.
- `## 3. Differentiation angle deep-dive`
  - `### 3.1 Why this angle?` — Why lakehouse-centric FinOps control plane with serverless orchestration.
  - `### 3.2 Strengths (with metrics)` — Table comparing CDO angle metrics (cost/run, latency, ops overhead) against alternatives.
  - `### 3.3 Accepted weaknesses` — Honest trade-offs of the chosen angle.
- `## 4. Multi-account approach`
  - `### 4.1 Account model` — How CDO accesses multiple AWS accounts for cost data (read-only cost access).
  - `### 4.2 Isolation pattern` — Data isolation via S3 prefixes, Glue partitions, tag-based ownership.
  - `### 4.3 Onboarding flow` — Steps for onboarding a new account/squad into the CDO pipeline.
  - `### 4.4 Idempotency` — Idempotency for scheduled runs so the same cost period cannot be processed twice.
- `## 5. Alternatives considered`
  - `### 5.1 Orchestration layer` — EventBridge Scheduler + Step Functions vs alternatives.
  - `### 5.2 Data layer` — S3 + Glue/Athena lakehouse vs alternatives.
- `## 6. Scaling strategy` — Vertical and horizontal scaling, triggers.
- `## 7. Failure modes + recovery` — Table with columns: Failure, Detection, Recovery, RTO, RPO. Include rows for CUR delay, Cost Explorer throttling, AI Engine timeout/unavailability, failed run, duplicate run, dashboard stale data, alert delivery failure, and containment denial.
- `## Related documents` — Links to `03_security_design.md`, `04_deployment_design.md`, `05_cost_analysis.md`, `08_adrs.md`.

---

### Document 3 — `03_security_design.md`

**Title**: `# Security Design - Task Force 2 · FinOps Watch CDO`

Required sections:

- `## 1. Network Security`
  - `### 1.1 Network Diagram` — Mermaid diagram showing VPC layout, subnets (including EKS private subnets), security groups, VPC endpoints, and EKS cluster networking.
  - `### 1.2 Security Groups` — Table with columns: SG name, Inbound, Outbound, Attached to.
  - `### 1.3 Network ACL / VPC Endpoint` — List VPC endpoints (S3, Secrets Manager, etc.) for private traffic.
- `## 2. IAM & Access Control`
  - `### 2.1 Service Roles` — Table with columns: Role, Used by, Permissions (least-privilege). Include EKS node roles, IRSA service account roles, and pod execution roles. Explicitly state: NEVER terminate prod, delete data, or modify IAM.
  - `### 2.2 Containment Permissions` — Environment-aware permissions: prod is tag/suggest/dry-run only; dev/sandbox may allow schedule shutdown or quota cap when approved by policy.
  - `### 2.3 Cross-account Access` — Read-only cost access roles, tightly scoped containment roles, AI Engine API authentication.
- `## 3. Secrets Management`
  - `### 3.1 Secrets Inventory` — Table with columns: Secret, Storage, Rotation, Accessed by.
  - `### 3.2 Inject Pattern` — How secrets reach Lambda functions and EKS pods (External Secrets Operator or Secrets Store CSI driver for Kubernetes workloads).
  - `### 3.3 Anti-leak Controls` — Gitleaks, no baked credentials, log redaction.
- `## 4. Encryption`
  - `### 4.1 At Rest` — Table with columns: Data, Storage, KMS key, Notes. Include audit log, cost data, containment records.
  - `### 4.2 In Transit` — TLS requirements, internal service-to-service encryption.
  - `### 4.3 Key Management` — CMK rotation, key policy, KMS audit.
- `## 5. Audit Logging`
  - `### 5.1 What to Log` — Containment actions (all fields from the containment action schema), cost data pulls, AI Engine invocations, infrastructure changes.
  - `### 5.2 Storage + Retention` — Table with columns: Log type, Storage, Retention, Query interface. Audit retention >=90 days, immutable or append-only storage for containment logs.
  - `### 5.3 Synthetic Data Handling` — Controls for synthetic data handling, dashboard access controls.
- `## 6. CI Security Controls` — Image/dependency scanning in CI, fail-on CRITICAL CVE.
- `## 7. Compliance Touchpoints` — Table with columns: Standard, Relevant controls (capstone scope). Brief mapping only.
- `## 8. Open Questions` — Security questions that require further decision.
- `## Related documents` — Links to `02_infra_design.md`, `04_deployment_design.md`, `08_adrs.md`.

---

### Document 4 — `04_deployment_design.md`

**Title**: `# Deployment & CI/CD Design - Task Force 2 · FinOps Watch CDO`

Required sections:

- `## 1. IaC strategy`
  - `### 1.1 Tool choice` — Terraform for AWS infrastructure including EKS; GitOps (ArgoCD/Flux) or Helm-based deployment for Kubernetes workloads; state backend; modular structure.
  - `### 1.2 Module structure` — Directory tree showing IaC modules for the CDO platform.
  - `### 1.3 State management` — Remote state per environment, state lock, plan-on-PR + apply-on-merge gate.
- `## 2. CI/CD pipeline`
  - `### 2.1 Pipeline stages` — Diagram and table with columns: Stage, Tool, What it does, Quality gate. Include plan-on-PR, apply-on-merge/manual approval, smoke tests.
  - `### 2.2 Branch strategy` — Branch model, PR requirements, approval flow.
- `## 3. Deployment gates`
  - `### 3.1 Security scans` — Image/dependency scan, secret scanning, OIDC-based CI access (no static cloud credentials).
  - `### 3.2 Destructive-change review` — How destructive IaC changes are flagged and approved.
  - `### 3.3 AI contract compatibility` — AI Engine dependency handling, contract version check, AIOps container artifact compatibility gate, EKS deployment validation.
- `## 4. Deployment strategy`
  - `### 4.1 Strategy` — Rolling/canary/blue-green approach for EKS workloads and Lambda functions, abort criteria, auto-rollback, spot node draining strategy.
  - `### 4.2 Rollback method` — Primary and secondary rollback, target RTO.
- `## 5. Environment separation` — Table with columns: Env, Purpose, Account, Auto-deploy. Sandbox, staging, prod.
- `## 6. Secrets in pipeline` — OIDC + IAM assume-role, secret scanning on PR, block merge on secret detected.
- `## 7. Scheduled batch deployment` — How EventBridge Scheduler + Step Functions workflows are deployed and updated. Operational runbooks.
- `## 8. Observability stack` — Table with columns: Component, Tool. Metrics, logs, traces, dashboards, alerts.
- `## 9. Open questions` — Deployment questions requiring decision.
- `## Related documents` — Links to `02_infra_design.md`, `03_security_design.md`.

---

### Document 5 — `05_cost_analysis.md`

**Title**: `# Cost Analysis - Task Force 2 · FinOps Watch CDO`

Required sections:

- `## 1. Cost model per cadence run (forecast)` — Table with columns: Component, Unit cost, Usage per run, $/run. Rows for Lambda, Step Functions, S3, Glue/Athena, DynamoDB, EKS control plane, on-demand node group, spot node group, EBS volumes, ECR, load balancer, dashboard, CloudWatch logs and Container Insights, alerting, NAT/VPC endpoints. Separate CDO platform costs from AI Engine hosting costs. Mark unmeasured numbers with `Evidence needed: ...`.
- `## 2. Cost at scale` — Table comparing monthly cost at different tenant/account counts. Show economies of scale.
- `## 3. Cost optimization applied` — Checklist of cost optimizations: S3 lifecycle tiering, DynamoDB on-demand vs provisioned, log retention tiering, VPC endpoints to avoid NAT, Athena query limits.
- `## 4. Cadence cost comparison` — Table comparing 12h, 24h, and 48h cadence costs and operational trade-offs. Defend the chosen 24h cadence.
- `## 5. Measured actual (Pack #2 only)`
  - `### 5.1 Capstone build-period spend` — Table with columns: Service, Forecast, Actual, Delta. Use `Evidence needed: ...` until measured.
  - `### 5.2 Per-run actual` — After running the pipeline, measure real consumption per cadence cycle.
  - `### 5.3 Cost per correct detection (joint with AI eval)` — Table with columns: Metric, Value. Reference AIOps-provided metrics as integration evidence only.
- `## 6. Cost guardrails` — Budgets, alarms, log retention limits, Athena query limits, dashboard refresh controls for the CDO platform itself.
- `## 7. Cost recommendations for production` — Longer-term cost recommendations beyond the capstone.
- `## Related documents` — Links to `02_infra_design.md`, `07_test_eval_report.md`.

---

### Document 6 — `06_dashboard_alerting_design.md`

**Title**: `# Dashboard & Alerting Design - Task Force 2 · FinOps Watch CDO`

> Note: No template exists for this document. Use the section structure below, which is consistent with the numbered-section convention used across all other templates.

Required sections:

- `## 1. Dashboard overview` — Purpose, target audience (Finance stakeholders), design principles (finance-readable, no SQL required).
- `## 2. Dashboard views`
  - `### 2.1 Spend trend` — Spend over time with anomaly overlay.
  - `### 2.2 Anomaly detail` — Confidence visual, severity, evidence window, explanation.
  - `### 2.3 Top impacted accounts/services/squads` — Ranked list with owner routing.
  - `### 2.4 Containment status` — Active containment actions, execution mode (dry-run/apply), audit link.
- `## 3. Alert routing`
  - `### 3.1 Finance alerts` — Route, channel (email/Slack/SNS), payload fields, severity levels.
  - `### 3.2 Engineering alerts` — Route, channel, payload fields, severity levels.
  - `### 3.3 Example alert payload` — Sample JSON/structured payload with field descriptions.
- `## 4. Accessibility and readability` — Clear labels, currency in USD, confidence explained in plain language, no SQL knowledge required.
- `## 5. Open questions` — Dashboard/alerting questions requiring decision.
- `## Related documents` — Links to `02_infra_design.md`, `01_requirements_analysis.md`.

---

### Document 7 — `07_test_eval_report.md`

**Title**: `# Test & Eval Report - Task Force 2 · FinOps Watch CDO`

Required sections:

- `## 1. Test coverage` — Table with columns: Test type, Tool, Coverage / Scope. Rows for unit, integration, E2E, scheduled-run idempotency, chaos/failure.
- `## 2. SLO evidence`
  - Table with columns: SLO, Target, Measured, Window, Pass/Fail. Include scheduled run success rate, data freshness, dashboard refresh, alert delivery.
  - `### 2.1 SLO breach analysis` — Root-cause analysis for any SLO miss.
- `## 3. CDO platform tests`
  - `### 3.1 Data ingestion tests` — CUR/Cost Explorer data pull validation.
  - `### 3.2 Scheduled run idempotency` — Verify same cost period cannot be processed twice.
  - `### 3.3 Dashboard refresh` — Verify dashboard updates after pipeline run.
- `## 4. AI integration tests`
  - `### 4.1 AI contract tests` — AI Engine request/response field validation against versioned contract.
  - `### 4.2 AI Engine timeout handling` — Timeout, retry behavior, circuit-breaker behavior.
  - `### 4.3 Unavailable-AI fallback` — Verify fail-closed containment, operator alert, audit record.
  - `### 4.4 EKS node placement tests` — Verify on-demand/spot workload separation, node affinity, and tolerations.
  - `### 4.5 Spot interruption and retry tests` — Verify batch job retry/backoff on spot interruption, checkpoint recovery.
  - `### 4.6 API availability tests` — Verify AI Engine internal endpoint availability and health checks.
  - `### 4.7 Autoscaling tests` — Verify HPA/KEDA pod scaling and node group scaling behavior.
- `## 5. Alert and containment tests`
  - `### 5.1 Alert routing` — Finance vs Engineering channel routing validation.
  - `### 5.2 Containment dry-run` — Verify dry-run mode for all containment paths.
  - `### 5.3 Audit log write` — Verify all containment action fields are written.
- `## 6. E2E demo scenario` — Synthetic anomaly inject → detect → alert → containment action triggered.
- `## 7. Security test`
  - `### 7.1 Penetration touch points` — Checklist of security test points.
  - `### 7.2 Vulnerability scan` — Tool, findings summary, report location.
- `## 8. Failure analysis`
  - `### 8.1 Failures encountered` — Table with columns: #, Failure, Root cause, Fix, Time to fix.
  - `### 8.2 Test gaps acknowledged` — Honest list of what has not been tested, with `Evidence needed: ...` markers.
- `## Related documents` — Links to `02_infra_design.md`, `03_security_design.md`.

---

### Document 8 — `08_adrs.md`

**Title**: `# Architecture Decision Records - FinOps Watch CDO · Task Force 2`

Preamble: Brief explanation of what ADRs are, when to write them, and the append-only rule. Match the template's blockquote style.

Required ADR entries (minimum, each as `## ADR-NNN - <Short title>`):

- `## ADR-001 - 24h cadence over 12h/48h` — Defend 24h as the middle trade-off.
- `## ADR-002 - Lakehouse-centric FinOps control plane architecture` — Why lakehouse-centric over alternatives.
- `## ADR-003 - CDO/AIOps ownership boundary` — Responsibility split decision.
- `## ADR-004 - CUR S3 plus Cost Explorer API data access` — Data source decision.
- `## ADR-005 - Dry-run-first containment guardrail` — Safety-first containment approach.
- `## ADR-006 - DynamoDB/S3 audit trail with >=90 days retention` — Audit storage decision.
- `## ADR-007 - EKS for AI Engine hosting over serverless containers` — Why CDO hosts AI Engine on EKS with managed node groups instead of Fargate or Lambda.
- `## ADR-008 - On-demand plus spot node group separation` — Cost-performance trade-off for stable vs interruptible workloads.

Each ADR must include these fields (matching template format exactly):

- **Status**: Accepted | Proposed | Superseded by ADR-NNN | Rejected
- **Date**: YYYY-MM-DD
- **Context**: 1-3 sentences on what forced the decision.
- **Decision**: Specific commitment.
- **Consequence**: Bulleted list with Yes pros and Note: trade-offs.
- **Alternatives considered**: Bulleted list with rejection reasons.

Append new ADRs below existing ones. Never delete old ADRs; mark superseded ones with `Status: Superseded by ADR-NNN`.

---

### Document 9 — `09_demo_and_presentation_pack.md`

**Title**: `# Demo & Presentation Pack - Task Force 2 · FinOps Watch CDO`

> Note: No template exists for this document. Use the section structure below, which is consistent with the numbered-section convention used across all other templates.

Required sections:

- `## 1. Demo script` — Step-by-step CDO demo flow: synthetic anomaly injection, scheduled run trigger, dashboard update, Finance alert, Engineering alert, containment dry-run/apply path, audit lookup.
- `## 2. Evidence checklist` — Checklist of evidence items to prepare before demo.
- `## 3. CDO pitch points` — Individual pitch points for CDO responsibilities and platform value.
- `## 4. Curveball responses` — Prepared responses for: data lag, false positives, accidental prod containment, Cost Explorer throttling, dashboard stale data, audit rollback.
- `## 5. Open questions` — Demo-related questions requiring decision.
- `## Related documents` — Links to all other documents in the pack.

---

Vietnamese files (one-to-one translations of the English files above):

1. `01_requirements_analysis_vi.md`
2. `02_infra_design_vi.md`
3. `03_security_design_vi.md`
4. `04_deployment_design_vi.md`
5. `05_cost_analysis_vi.md`
6. `06_dashboard_alerting_design_vi.md`
7. `07_test_eval_report_vi.md`
8. `08_adrs_vi.md`
9. `09_demo_and_presentation_pack_vi.md`

The content requirements for each Vietnamese file are identical to those listed for the corresponding English file above. Each Vietnamese file must use the same numbered section structure and heading hierarchy.

## Document Standards

Use these rules for all generated docs:

- Produce every document in both English and Vietnamese.
- Use Markdown.
- Prefer concrete architecture and data-flow descriptions over generic cloud language.
- Do not claim real measurements unless evidence exists in the repo or conversation.
- Use `Evidence needed: <specific evidence>` for missing measured data.
- Keep business-facing sections readable for Finance stakeholders.
- Keep technical sections specific enough for DevOps/CDO reviewers.
- Use Mermaid diagrams where they clarify architecture, sequence, or controls.
- Preserve client boundaries even if a template suggests a broader platform feature.
- Avoid placeholders such as `TBD`, `TODO`, `<fill>`, `<N>`, or `<M>` in final docs.

## Bilingual Translation Rules

Apply these rules when producing the Vietnamese (`_vi`) version of each document:

- The Vietnamese file must be a complete, faithful translation of the English file, preserving all sections, headings, tables, diagrams, code blocks, and technical detail.
- Keep AWS service names, technical terms, and proper nouns in English (e.g., "Lambda", "Step Functions", "EventBridge Scheduler", "CUR", "Athena", "DynamoDB", "QuickSight", "dry-run", "lakehouse-centric").
- Keep acronyms in English (e.g., CDO, AIOps, IAM, CI/CD, IaC, SLO, ADR, OIDC).
- Keep code snippets, CLI commands, file paths, and Mermaid diagram syntax in English.
- Translate all prose, explanations, section headings, bullet-point descriptions, table headers, and table cell descriptions into natural Vietnamese.
- Use Vietnamese technical vocabulary where widely accepted (e.g., "kiến trúc" for architecture, "triển khai" for deployment, "bảo mật" for security, "chi phí" for cost, "cảnh báo" for alert, "bảng điều khiển" for dashboard).
- Currency references remain in USD; add "(đô la Mỹ)" on first occurrence if helpful.
- Maintain the same heading hierarchy and numbering as the English version.
- The Vietnamese title of each document should include the Vietnamese translation followed by the English title in parentheses for cross-reference. Example: `# Thiết kế Hạ tầng (Infrastructure Design)`.
- Do not add, remove, or reorder content compared to the English version.
- `Evidence needed: ...` markers should be translated as `Cần bằng chứng: ...`.

## Suggested Data Contracts To Reference

The client brief requires three contracts signed with the CDO group. For CDO docs, reference these as integration contracts unless the user asks to write the contracts themselves:

1. Cost data pull contract
   - Owner: CDO.
   - Source: CUR in S3 and Cost Explorer API.
   - Trigger: scheduled CDO pull by cadence.
   - Key fields: account, service, region, tag owner, environment, cost amount, usage date, cost period, currency USD.

2. AI decision output contract
   - Owner: AIOps.
   - Source: AIOps-owned AI Engine after anomaly detection.
   - CDO responsibility: consume this contract, validate required fields, persist evidence, route alerts, and enforce containment policy.
   - Key fields: run ID, model version, anomaly ID, tenant/account, anomaly type, confidence, severity, expected spend, actual spend, delta, evidence window, explanation, recommended route, recommended containment mode, evidence URI.

3. Alert and containment contract
   - Owner: CDO.
   - Source: CDO alert/containment workflow.
   - Key fields: anomaly ID, route target, approval requirement, action type, execution mode, before state, after state, rollback path, audit record ID.

## Review Checklist

Before considering the document pack complete, verify:

- All required English files exist under `docs/tf2-finops/`.
- All required Vietnamese (`_vi`) files exist under `docs/tf2-finops/`.
- Every Vietnamese file is a complete translation of its English counterpart (same sections, same structure).
- `template-docs/` was not overwritten.
- The English docs mention `lakehouse-centric`.
- The English docs mention `AIOps-owned AI Engine`.
- The English docs mention `EKS` and `node group`.
- The English docs mention `on-demand` and `spot` node groups.
- The English docs mention `ai-engine-api` and `ai-engine-worker`.
- The English docs mention `EventBridge Scheduler`.
- The English docs mention `CUR` and `Athena`.
- The English docs mention `dry-run`.
- The English docs mention `90 days` or `>=90 days` audit retention.
- The English docs include the exact hard boundary: `NEVER terminate prod, delete data, or modify IAM`.
- The Vietnamese docs preserve these same terms in English where required by translation rules.
- The docs define 12h, 24h, or 48h cadence and defend the chosen value.
- The docs include finance-readable dashboard requirements.
- The docs include separate Finance and Engineering alert routing.
- The docs include idempotency for scheduled cost-period processing.
- The docs include at least one implemented containment pattern and at least two designed containment patterns.
- The docs do not fabricate measured results.
- Placeholder scan returns no accidental template markers:

```powershell
rg -n "TBD|TODO|<N>|<M>|<fill>|placeholder" docs/tf2-finops
```

Verify both English and Vietnamese files exist:

```powershell
# Check English files
Get-ChildItem docs/tf2-finops/*.md | Where-Object { $_.Name -notmatch '_vi\.md$' } | Select-Object Name

# Check Vietnamese files
Get-ChildItem docs/tf2-finops/*_vi.md | Select-Object Name

# Ensure counts match (9 English + 9 Vietnamese = 18 total)
(Get-ChildItem docs/tf2-finops/*.md).Count
```

Run this targeted constraint check:

```powershell
rg -n "lakehouse-centric|AIOps-owned AI Engine|EKS|node group|on-demand|spot|ai-engine-api|ai-engine-worker|EventBridge Scheduler|CUR|Athena|dry-run|90 days|NEVER terminate prod|delete data|modify IAM" AGENTS.md docs/tf2-finops
```
