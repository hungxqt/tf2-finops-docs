# AGENTS.md - TF2 FinOps CDO Documentation Builder

## Purpose

This repository contains the client brief and reusable document templates for Task Force 2, "FinOps Watch". Future agents must use this file when creating the CDO documentation pack for the task force.

The goal is to produce an English-only CDO documentation pack under `docs/tf2-finops/` that explains how the CDO platform hosts, schedules, secures, deploys, monitors, and evaluates the FinOps Watch system.

## Source Priority

Use sources in this order:

1. `TF2_FINOPS_LEARNER.md` - client brief and hard requirements.
2. Explicit user or client updates in the current conversation.
3. `template-docs/` - reusable structure and baseline section ideas.
4. Agent improvements, only when they do not contradict the sources above.

Do not overwrite files in `template-docs/`. Treat them as templates only.

## Scope

Create CDO documentation only. The docs may reference AI engine contracts, anomaly metrics, backtest outputs, and alert payloads where needed for platform integration, but they must not invent AI model internals or replace the AI team's own documentation.

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

- Language: English only.
- Output folder: `docs/tf2-finops/`.
- Architecture angle: serverless batch-first.
- AWS Region: `ap-southeast-1` for examples.
- Cadence decision: 24h default, defended as the middle trade-off between data freshness, Cost Explorer/CUR lag, operational cost, and false-positive control.
- Data sources: CUR in S3 plus Cost Explorer API.
- Orchestration: EventBridge scheduled rule triggers Step Functions.
- Compute: Lambda for short CDO tasks; Fargate only if a long-running adapter is required.
- Analytics storage/query: S3, Glue Data Catalog, and Athena.
- Operational metadata: DynamoDB tables for run state, anomaly records, routing state, idempotency keys, containment audit records, and dashboard materialized views.
- Dashboard: QuickSight or a lightweight internal web dashboard backed by Athena/DynamoDB views.
- Alerting: separate Finance and Engineering channels, such as email/Slack/SNS targets, with routing based on anomaly type and ownership tags.
- Containment posture: dry-run first, safe automation only for non-prod/dev/sandbox resources.

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

Create or update these files under `docs/tf2-finops/`:

1. `01_requirements_analysis.md`
   - Summarize the client problem from the CFO perspective.
   - Translate client hard requirements into CDO platform requirements.
   - Define CDO non-functional requirements for scheduled processing, availability, auditability, dashboard readability, and cost.
   - State the serverless batch-first angle and why it fits FinOps cadence.
   - List open questions that truly require client or AI team clarification.

2. `02_infra_design.md`
   - Use a Mermaid diagram showing EventBridge, Step Functions, Lambda, CUR S3 bucket, Cost Explorer API, Glue/Athena, DynamoDB, dashboard, alerting, and containment workers.
   - Include a component table with AWS service, responsibility, reason, and cost note.
   - Explain multi-account access using read-only cost access and tightly scoped containment roles.
   - Include idempotency for scheduled runs so the same cost period cannot be processed twice.
   - Include failure modes for CUR delay, Cost Explorer throttling, failed run, duplicate run, dashboard stale data, alert delivery failure, and containment denial.

3. `03_security_design.md`
   - Focus on DevOps/CDO controls: IAM least privilege, network boundaries, secrets, encryption, audit logging, CI scans, and compliance touchpoints.
   - Explicitly state the hard boundary: NEVER terminate prod, delete data, or modify IAM.
   - Define environment-aware containment permissions: prod is tag/suggest/dry-run only; dev/sandbox may allow schedule shutdown or quota cap when approved by policy.
   - Include audit retention >=90 days and immutable or append-only storage for containment logs.
   - Include controls for synthetic data handling and dashboard access.

4. `04_deployment_design.md`
   - Define IaC structure, CI/CD pipeline, environment separation, and release strategy.
   - Use OIDC-based CI access, no static cloud credentials.
   - Include plan-on-PR, apply-on-merge/manual approval, smoke tests, and rollback.
   - Describe scheduled batch deployment and operational runbooks.
   - Include deployment gates for security scans and destructive-change review.

5. `05_cost_analysis.md`
   - Estimate cost of the FinOps Watch CDO platform itself.
   - Include cost model rows for Lambda, Step Functions, S3, Glue/Athena, DynamoDB, dashboard, CloudWatch logs, alerting, and NAT/VPC endpoints if used.
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
   - Reference AI backtest metrics only as integration evidence from the AI group.
   - Include E2E demo scenario: synthetic anomaly inject -> detect -> alert -> containment action triggered.
   - Use `Evidence needed: ...` for any result that has not been run.

8. `08_adrs.md`
   - Keep append-only ADR format.
   - Include at least these ADRs:
     - Cadence choice: 24h over 12h/48h.
     - Serverless batch-first architecture.
     - CUR S3 plus Cost Explorer API data access.
     - Dry-run-first containment guardrail.
     - DynamoDB/S3 audit trail with >=90 days retention.
   - Each ADR must include status, date, context, decision, consequences, and alternatives considered.

9. `09_demo_and_presentation_pack.md`
   - Provide the CDO demo script and evidence checklist.
   - Cover synthetic anomaly injection, scheduled run, dashboard update, Finance alert, Engineering alert, containment dry-run/apply path, and audit lookup.
   - Include individual pitch points for CDO responsibilities.
   - Include curveball responses for data lag, false positives, accidental prod containment, Cost Explorer throttling, dashboard stale data, and audit rollback.

## Document Standards

Use these rules for all generated docs:

- English only.
- Use Markdown.
- Prefer concrete architecture and data-flow descriptions over generic cloud language.
- Do not claim real measurements unless evidence exists in the repo or conversation.
- Use `Evidence needed: <specific evidence>` for missing measured data.
- Keep business-facing sections readable for Finance stakeholders.
- Keep technical sections specific enough for DevOps/CDO reviewers.
- Use Mermaid diagrams where they clarify architecture, sequence, or controls.
- Preserve client boundaries even if a template suggests a broader platform feature.
- Avoid placeholders such as `TBD`, `TODO`, `<fill>`, `<N>`, or `<M>` in final docs.

## Suggested Data Contracts To Reference

The client brief requires three contracts signed with the CDO group. For CDO docs, reference these as integration contracts unless the user asks to write the contracts themselves:

1. Cost data pull contract
   - Source: CUR in S3 and Cost Explorer API.
   - Trigger: scheduled CDO pull by cadence.
   - Key fields: account, service, region, tag owner, environment, cost amount, usage date, cost period, currency USD.

2. AI decision output contract
   - Source: AI engine after anomaly detection.
   - Key fields: anomaly ID, run ID, tenant/account, anomaly type, confidence, severity, expected spend, actual spend, delta, evidence window, recommended route, recommended containment mode.

3. Alert and containment contract
   - Source: CDO alert/containment workflow.
   - Key fields: anomaly ID, route target, approval requirement, action type, execution mode, before state, after state, rollback path, audit record ID.

## Review Checklist

Before considering the document pack complete, verify:

- All required files exist under `docs/tf2-finops/`.
- `template-docs/` was not overwritten.
- The docs mention `serverless batch-first`.
- The docs mention `dry-run`.
- The docs mention `90 days` or `>=90 days` audit retention.
- The docs include the exact hard boundary: `NEVER terminate prod, delete data, or modify IAM`.
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

Run this targeted constraint check:

```powershell
rg -n "serverless batch-first|dry-run|90 days|NEVER terminate prod|delete data|modify IAM" AGENTS.md docs/tf2-finops
```

