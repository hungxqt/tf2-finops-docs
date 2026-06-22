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
- Compute: Lambda for short CDO adapters and policy workers; Fargate only if a long-running adapter or AI Engine connector is required.
- AI integration: call an AIOps-owned AI Engine endpoint, queue, or contract boundary; CDO owns invocation, timeout, retry, and fallback behavior, not the model internals.
- Analytics storage/query: S3, Glue Data Catalog, Athena, and materialized dashboard tables/views where needed.
- Operational metadata: DynamoDB tables for run state, anomaly records, routing state, idempotency keys, containment audit records, and dashboard materialized views.
- Dashboard: QuickSight or a lightweight internal web dashboard backed by Athena/DynamoDB views.
- Alerting: separate Finance and Engineering channels, such as email/Slack/SNS targets, with routing based on anomaly type and ownership tags.
- Containment posture: dry-run first, safe automation only for non-prod/dev/sandbox resources.

## CDO vs AIOps Responsibility Boundary

Use this boundary in every generated document:

- CDO owns cost data ingestion, normalized cost windows, ownership/tag metadata, scheduling, idempotency, workflow state, dashboard views, alert routing, containment guardrails, audit logs, and platform operational SLOs.
- AIOps owns anomaly detection logic, model selection, model training/retraining design, model versioning, confidence scoring, anomaly classification, explanation text, AI Engine runtime, and AI backtest metrics.
- CDO consumes the AI Engine through a versioned contract. CDO must document request/response fields, authentication, timeout, retry, circuit-breaker, unavailable-AI fallback, and evidence storage.
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

English files:

1. `01_requirements_analysis.md`
   - Summarize the client problem from the CFO perspective.
   - Translate client hard requirements into CDO platform requirements.
   - Define CDO non-functional requirements for scheduled processing, availability, auditability, dashboard readability, and cost.
   - State the lakehouse-centric FinOps control plane angle and why it fits production FinOps cadence.
   - Include the CDO vs AIOps responsibility split.
   - List open questions that truly require client or AIOps team clarification.

2. `02_infra_design.md`
   - Use a Mermaid diagram showing AWS Data Exports/CUR S3 bucket, Cost Explorer API, S3 raw/curated zones, Glue/Athena, EventBridge Scheduler, Step Functions, Lambda, DynamoDB, the AIOps-owned AI Engine boundary, dashboard, alerting, and containment workers.
   - Include a component table with AWS service, responsibility, reason, and cost note.
   - Explain multi-account access using read-only cost access and tightly scoped containment roles.
   - Include idempotency for scheduled runs so the same cost period cannot be processed twice.
   - Include failure modes for CUR delay, Cost Explorer throttling, AI Engine timeout/unavailability, failed run, duplicate run, dashboard stale data, alert delivery failure, and containment denial.

3. `03_security_design.md`
   - Focus on DevOps/CDO controls: IAM least privilege, network boundaries, secrets, encryption, audit logging, CI scans, and compliance touchpoints.
   - Explicitly state the hard boundary: NEVER terminate prod, delete data, or modify IAM.
   - Define environment-aware containment permissions: prod is tag/suggest/dry-run only; dev/sandbox may allow schedule shutdown or quota cap when approved by policy.
   - Include audit retention >=90 days and immutable or append-only storage for containment logs.
   - Include controls for synthetic data handling, dashboard access, AI Engine API authentication, and least-privilege cross-team access.

4. `04_deployment_design.md`
   - Define IaC structure, CI/CD pipeline, environment separation, and release strategy.
   - Use OIDC-based CI access, no static cloud credentials.
   - Include plan-on-PR, apply-on-merge/manual approval, smoke tests, and rollback.
   - Describe scheduled batch deployment and operational runbooks.
   - Include deployment gates for security scans, destructive-change review, AI contract compatibility, and AI Engine dependency handling.

5. `05_cost_analysis.md`
   - Estimate cost of the FinOps Watch CDO platform itself.
   - Include cost model rows for Lambda, Step Functions, S3, Glue/Athena, DynamoDB, dashboard, CloudWatch logs, alerting, and NAT/VPC endpoints if used.
   - Separate CDO platform costs from AIOps AI Engine runtime and model-operation costs.
   - Compare 12h, 24h, and 48h cadence costs and operational trade-offs.
   - Include cost guardrails for the platform itself: budgets, alarms, log retention, Athena query limits, and dashboard refresh controls.
   - Mark unmeasured numbers with `Evidence needed: ...` rather than fabricating exact results.

6. `06_dashboard_alerting_design.md`
   - Define the finance-friendly dashboard views: spend trend, anomaly overlay, confidence visual, top impacted account/service/squad, owner routing, containment status, and audit link.
   - Define alert routes for Finance and Engineering separately.
   - Include example alert payload fields and severity levels.
   - Keep UI language business-readable; do not require SQL knowledge.
   - Include accessibility/readability notes such as clear labels, currency in USD, and confidence explained in plain language.

7. `07_test_eval_report.md`
   - Cover CDO tests: scheduled run idempotency, data ingestion, dashboard refresh, alert routing, containment dry-run, audit log write, failure handling, and security boundaries.
   - Reference AI backtest metrics only as integration evidence from the AIOps team.
   - Include AI contract tests, AI Engine timeout handling, retry behavior, circuit-breaker behavior, and unavailable-AI fallback.
   - Include E2E demo scenario: synthetic anomaly inject -> detect -> alert -> containment action triggered.
   - Use `Evidence needed: ...` for any result that has not been run.

8. `08_adrs.md`
   - Keep append-only ADR format.
   - Include at least these ADRs:
     - Cadence choice: 24h over 12h/48h.
     - Lakehouse-centric FinOps control plane architecture.
     - CDO/AIOps ownership boundary.
     - CUR S3 plus Cost Explorer API data access.
     - Dry-run-first containment guardrail.
     - DynamoDB/S3 audit trail with >=90 days retention.
   - Each ADR must include status, date, context, decision, consequences, and alternatives considered.

9. `09_demo_and_presentation_pack.md`
   - Provide the CDO demo script and evidence checklist.
   - Cover synthetic anomaly injection, scheduled run, dashboard update, Finance alert, Engineering alert, containment dry-run/apply path, and audit lookup.
   - Include individual pitch points for CDO responsibilities.
   - Include curveball responses for data lag, false positives, accidental prod containment, Cost Explorer throttling, dashboard stale data, and audit rollback.

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

The content requirements for each Vietnamese file are identical to those listed for the corresponding English file above.

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
rg -n "lakehouse-centric|AIOps-owned AI Engine|EventBridge Scheduler|CUR|Athena|dry-run|90 days|NEVER terminate prod|delete data|modify IAM" AGENTS.md docs/tf2-finops
```
