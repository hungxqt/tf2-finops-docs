# AI API Contract v1.3 Document Stash Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the `docs/tf2-finops/` document stash with the updated `docs/contracts/ai-api-contract.md` v1.3.0 contract without changing `template-docs/`.

**Architecture:** Treat `docs/contracts/ai-api-contract.md` as the integration contract source for AI API semantics, while preserving the durable CDO platform boundary already established in `AGENTS.md` and the existing ADR chain. Update English documents first, then update each Vietnamese counterpart as a complete one-to-one translation with identical structure, diagrams, tables, and technical detail.

**Tech Stack:** Markdown, Mermaid, PowerShell, ripgrep, Git.

---

## File Structure

Primary contract source:
- Read only: `docs/contracts/ai-api-contract.md`
- Read only unless needed for cross-contract wording: `docs/contracts/deployment-contract.md`
- Read only unless needed for telemetry field names: `docs/contracts/telemetry-contract.md`

English stash files to update:
- Modify: `docs/tf2-finops/01_requirements_analysis.md`
- Modify: `docs/tf2-finops/02_infra_design.md`
- Modify: `docs/tf2-finops/03_security_design.md`
- Modify: `docs/tf2-finops/04_deployment_design.md`
- Modify: `docs/tf2-finops/05_cost_analysis.md`
- Modify: `docs/tf2-finops/06_dashboard_alerting_design.md`
- Modify: `docs/tf2-finops/07_test_eval_report.md`
- Modify: `docs/tf2-finops/08_adrs.md`
- Modify: `docs/tf2-finops/09_demo_and_presentation_pack.md`
- Modify: `docs/tf2-finops/AWS_Component_details.md`
- Modify: `docs/tf2-finops/NOTES.md`

Vietnamese stash files to update after each English change:
- Modify: `docs/tf2-finops/01_requirements_analysis_vi.md`
- Modify: `docs/tf2-finops/02_infra_design_vi.md`
- Modify: `docs/tf2-finops/03_security_design_vi.md`
- Modify: `docs/tf2-finops/04_deployment_design_vi.md`
- Modify: `docs/tf2-finops/05_cost_analysis_vi.md`
- Modify: `docs/tf2-finops/06_dashboard_alerting_design_vi.md`
- Modify: `docs/tf2-finops/07_test_eval_report_vi.md`
- Modify: `docs/tf2-finops/08_adrs_vi.md`
- Modify: `docs/tf2-finops/09_demo_and_presentation_pack_vi.md`
- Modify: `docs/tf2-finops/AWS_Component_details_vi.md`
- Modify: `docs/tf2-finops/NOTES_vi.md`

Do not modify:
- `template-docs/`
- `docs/contracts/ai-api-contract.md` unless the user explicitly asks to revise the contract itself.

## Canonical Contract Deltas To Apply

Use these exact deltas from `docs/contracts/ai-api-contract.md` v1.3.0 as the synchronization checklist:

- Contract version is `v1.3.0`.
- `POST /v1/detect` remains synchronous and returns `DetectResponse` directly; target P99 is `< 300 ms`.
- `GET /v1/status/{id}` remains available for remediation or audit status, not for detection polling.
- `aws_cost_explorer_daily` is conditional, not always required; send it only when `telemetry_delay_event = true`.
- CUR from S3 is the default truth source for the scheduled 24h flow. Cost Explorer is a fallback for CUR delay, not the default AI detect payload when CUR is finalized.
- `data_confidence` is required in detect responses: `HIGH` for finalized CUR and `LOW` for Cost Explorer fallback.
- CDO sends raw `cpu_utilization_hourly`; the AI Engine computes `idle_hours_continuous`.
- `callback_url` is optional and additive. It does not replace the synchronous detect response.
- `s3_bucket_uri` must follow `s3://tf2-cdo{NN}-telemetry-{region}/...json.gz`.
- Default IAM mode is per-CDO AI Engine deployment with access to one telemetry bucket. Shared skeleton mode can use wildcard S3 access or cross-account STS AssumeRole with `ExternalId` based on `X-Tenant-Id`.
- CDO caches `rollback_payload.boto3_equivalent` immediately after `/v1/decide`.
- Rollback execution is CDO-owned and independent: CDO reads the cached boto3 payload, executes rollback, then calls `POST /v1/audit/{audit_id}/rollback` so AI Engine records audit and feedback.
- Rollback notification request fields are `reason`, `rolled_back_by`, `rollback_executed_at`, `rollback_status`, and optional `boto3_result`.
- Rollback notification response uses `audit_recorded`, not `rollback_initiated`.
- Error budget lock is environment-tiered: prod/prod-core/prod-payments lock at 1 percent rollback rate over 30 days, staging locks at 10 percent, and dev/sandbox/ml-research/data-analytics do not auto-lock.
- Lock response reason is `error_budget_exceeded_threshold`.
- Request timestamp skew is 300 seconds; CUR data timestamp delay up to 36 hours is normal and accepted.
- Bedrock LLM calls belong to `/v1/decide`, not `/v1/detect`; Bedrock hard timeout is 45 seconds.

### Task 1: Baseline Contract And Stash Drift

**Files:**
- Read: `docs/contracts/ai-api-contract.md`
- Read: `docs/tf2-finops/*.md`
- Read: `docs/tf2-finops/*_vi.md`

- [ ] **Step 1: Confirm the updated contract diff**

Run:

```powershell
git -c safe.directory=E:/code-folder/xbrain_projects/capstone_phase2_main/tf2-finops-docs diff --unified=1 -- docs/contracts/ai-api-contract.md
```

Expected: diff shows contract version `v1.3.0`, the `tf2-cdo{NN}-telemetry-{region}` bucket convention, optional `callback_url`, conditional `aws_cost_explorer_daily`, `data_confidence`, independent rollback via `rollback_payload.boto3_equivalent`, and environment-tiered `LOCKED_MODE`.

- [ ] **Step 2: Inventory stale terms in the English stash**

Run:

```powershell
rg -n "v1\.1|v1\.2|primary daily querying|aws_cost_explorer_daily.*required|rollback_initiated|error_budget_exceeded_1pct|idle_hours_continuous|confidence \*= 0\.5|202 Accepted|P99 ACK|status polling|polling active detection|Cost Explorer API serves as the primary|daily calls to the AWS Cost Explorer API" docs\tf2-finops -g "*.md"
```

Expected before edits: hits in `01_requirements_analysis.md`, `02_infra_design.md`, `03_security_design.md`, `06_dashboard_alerting_design.md`, `07_test_eval_report.md`, `08_adrs.md`, `09_demo_and_presentation_pack.md`, `AWS_Component_details.md`, and `NOTES.md`.

- [ ] **Step 3: Inventory missing v1.3 terms in the English stash**

Run:

```powershell
rg -n "v1\.3\.0|telemetry_delay_event|data_confidence|callback_url|rollback_payload\.boto3_equivalent|tf2-cdo\{NN\}-telemetry-\{region\}|error_budget_exceeded_threshold|cpu_utilization_hourly|Request Timestamp|Data Timestamp|36 hours|rollback_status|audit_recorded" docs\tf2-finops -g "*.md"
```

Expected before edits: sparse or missing coverage for the new v1.3.0 terms. Record the files with no hits so later tasks can update them.

- [ ] **Step 4: Commit the baseline plan checkpoint if commits are desired**

Run:

```powershell
git add docs/superpowers/plans/2026-06-25-ai-api-contract-v1-3-doc-stash-sync.md
git commit -m "docs: plan ai api contract v1.3 stash sync"
```

Expected: Git creates a commit containing only this plan file. Skip this step if the user has not requested commits.

### Task 2: Update Requirements And Infrastructure Narrative

**Files:**
- Modify: `docs/tf2-finops/01_requirements_analysis.md`
- Modify: `docs/tf2-finops/01_requirements_analysis_vi.md`
- Modify: `docs/tf2-finops/02_infra_design.md`
- Modify: `docs/tf2-finops/02_infra_design_vi.md`
- Modify: `docs/tf2-finops/AWS_Component_details.md`
- Modify: `docs/tf2-finops/AWS_Component_details_vi.md`

- [ ] **Step 1: Update `01_requirements_analysis.md` contract mapping**

Make these exact content changes:
- Change `### 1.1 Programmatic Contract Mapping (v1.1)` to `### 1.1 Programmatic Contract Mapping (v1.3.0)`.
- Revise the context paragraphs so CDO sends CUR-by-default and only sends Cost Explorer data when `telemetry_delay_event = true`.
- Replace any statement that CDO sends `idle_hours_continuous` with a statement that CDO sends `cpu_utilization_hourly` and AIOps computes continuous idle windows.
- Add `data_confidence` as a required detect response field used by dashboard and containment policy.
- Add optional `callback_url` as an additive callback path that does not replace synchronous `POST /v1/detect`.
- Keep the hard boundary that logical `/v1/*` operations are contract semantics, not separate physical REST routes in the baseline batch pipeline.

- [ ] **Step 2: Update `02_infra_design.md` data flow and architecture text**

Make these exact content changes:
- In architecture captions and Mermaid labels, preserve the 24h EventBridge Scheduler baseline and add S3 CUR object-arrival readiness through EventBridge as a data-availability signal. State explicitly that the platform does not poll for CUR files.
- Change Cost Explorer from primary daily detect input to conditional fallback for CUR delay over 36 hours.
- Update `/v1/detect` latency language from `typically 30-45 seconds` to target P99 `< 300 ms` for schema validation, idempotency, and model scoring. Keep Bedrock 45-second timeout only under `/v1/decide`.
- Update the sequence diagram so `/v1/decide` returns `rollback_payload.boto3_equivalent`, CDO caches it immediately, and rollback uses the cached boto3 payload before notifying `/v1/audit/{audit_id}/rollback`.
- Update section `4.5 Cost Data Caching & Cost Explorer Rate Limit Control` to describe Cost Explorer as fallback cache for `telemetry_delay_event = true`, not as the normal input path when CUR is finalized.
- Update section `4.6 Telemetry Ingestion Compliance & Validation` so CloudWatch utilization metrics are part of detection telemetry and `cpu_utilization_hourly` replaces `idle_hours_continuous`.
- Add the bucket naming rule `s3://tf2-cdo{NN}-telemetry-{region}/...json.gz` to the isolation or onboarding sections.

- [ ] **Step 3: Update `AWS_Component_details.md` component responsibilities**

Make these exact content changes:
- Change Cost Explorer component language from always-pulled daily signal to conditional fallback when CUR is delayed.
- Add the `tf2-cdo{NN}-telemetry-{region}` naming convention to the CUR/S3 and IAM role component descriptions.
- Update Ingestion Lambda input/output to include `telemetry_delay_event`, `data_confidence`, and `cpu_utilization_hourly`.
- Update AI Engine Lambda output to include `data_confidence`, `callback_url` behavior, and `rollback_payload.boto3_equivalent`.
- Update Containment Lambda and Audit Writer Lambda sections so rollback is CDO-executed from cached boto3 payload, then reported to AI Engine for audit/feedback.

- [ ] **Step 4: Translate Task 2 changes into Vietnamese**

Apply a faithful translation of the Task 2 English changes to:
- `docs/tf2-finops/01_requirements_analysis_vi.md`
- `docs/tf2-finops/02_infra_design_vi.md`
- `docs/tf2-finops/AWS_Component_details_vi.md`

Use these Vietnamese terms consistently:
- `Cần bằng chứng` for `Evidence needed`.
- `độ tin cậy dữ liệu` for `data confidence` while keeping `data_confidence` unchanged in code-style fields.
- `dự phòng khi CUR bị trễ` for Cost Explorer fallback.
- `CDO thực thi rollback độc lập bằng boto3` for independent CDO rollback.

- [ ] **Step 5: Verify Task 2 edits**

Run:

```powershell
rg -n "Programmatic Contract Mapping \(v1\.1\)|typically 30-45 seconds|Cost Explorer API serves as the primary|idle_hours_continuous|confidence \*= 0\.5|rollback_payload\)" docs\tf2-finops\01_requirements_analysis.md docs\tf2-finops\02_infra_design.md docs\tf2-finops\AWS_Component_details.md
rg -n "v1\.3\.0|telemetry_delay_event|data_confidence|callback_url|rollback_payload\.boto3_equivalent|tf2-cdo\{NN\}-telemetry-\{region\}|cpu_utilization_hourly|36 hours" docs\tf2-finops\01_requirements_analysis.md docs\tf2-finops\02_infra_design.md docs\tf2-finops\AWS_Component_details.md
```

Expected: first command has no stale hits except acceptable historical ADR references outside these files; second command shows the new contract terms in the updated files.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add docs/tf2-finops/01_requirements_analysis.md docs/tf2-finops/01_requirements_analysis_vi.md docs/tf2-finops/02_infra_design.md docs/tf2-finops/02_infra_design_vi.md docs/tf2-finops/AWS_Component_details.md docs/tf2-finops/AWS_Component_details_vi.md
git commit -m "docs: sync requirements and infra to ai contract v1.3"
```

Expected: Git creates a focused docs commit. Skip this step if the user has not requested commits.

### Task 3: Update Security, Deployment, And Cost Controls

**Files:**
- Modify: `docs/tf2-finops/03_security_design.md`
- Modify: `docs/tf2-finops/03_security_design_vi.md`
- Modify: `docs/tf2-finops/04_deployment_design.md`
- Modify: `docs/tf2-finops/04_deployment_design_vi.md`
- Modify: `docs/tf2-finops/05_cost_analysis.md`
- Modify: `docs/tf2-finops/05_cost_analysis_vi.md`
- Modify: `docs/tf2-finops/NOTES.md`
- Modify: `docs/tf2-finops/NOTES_vi.md`

- [ ] **Step 1: Update security lock and IAM semantics**

In `03_security_design.md`, make these exact content changes:
- Replace flat 1 percent `LOCKED_MODE` trigger wording with the v1.3.0 tiered thresholds: prod/prod-core/prod-payments at 1 percent, staging at 10 percent, and dev/sandbox/ml-research/data-analytics disabled.
- Replace `error_budget_exceeded_1pct` with `error_budget_exceeded_threshold`.
- Add the `rollback_status`, `rollback_executed_at`, and optional `boto3_result` fields to audit logging for rollback notification.
- Add the bucket naming convention and IAM modes: per-CDO one-bucket access by default; shared skeleton wildcard or STS AssumeRole with `ExternalId` as optional modes.
- Add the clock-skew split: `X-Request-Timestamp` skew limit is 300 seconds; CUR data timestamp delay up to 36 hours is accepted.

- [ ] **Step 2: Update deployment gates**

In `04_deployment_design.md`, make these exact content changes:
- In AI contract compatibility gates, require a v1.3.0 schema check for `telemetry_delay_event`, `data_confidence`, `callback_url`, `rollback_payload.boto3_equivalent`, and the `s3_bucket_uri` regex.
- Add a smoke test that invokes logical `/v1/detect` synchronously and verifies `data_confidence`.
- Add a smoke test that invokes logical `/v1/decide`, writes `rollback_payload.boto3_equivalent` to the CDO cache, and verifies that rollback does not depend on AI Engine availability.
- Update bucket creation guidance to enforce `tf2-cdo{NN}-telemetry-{region}` and avoid `BucketAlreadyExists` collisions.
- Keep ECR image digest pinning and Lambda reserved concurrency as deployment gates.

- [ ] **Step 3: Update cost analysis**

In `05_cost_analysis.md`, make these exact content changes:
- Change Cost Explorer usage language from normal daily detect payload to conditional fallback for `telemetry_delay_event = true`.
- Add a note that optional callback delivery can add HTTP egress, log, and retry telemetry costs only when `callback_url` is enabled.
- Fix any contradiction that says Lambda reserved concurrency is not applicable; the baseline uses reserved concurrency as a blast-radius and throttling guardrail, while Provisioned Concurrency remains optional.
- In cost risks, add runaway callback retry and rollback-cache growth as bounded costs with log retention and DynamoDB/S3 lifecycle controls.

- [ ] **Step 4: Update notes**

In `NOTES.md`, make these exact content changes:
- Replace the statement that detection uses CUR plus Cost Explorer API by default with CUR-first detection plus Cost Explorer fallback on `telemetry_delay_event`.
- Replace `confidence *= 0.5` with `data_confidence: LOW` and dry-run/alert-only containment when fallback data is used.
- Add `cpu_utilization_hourly` as the raw metric CDO sends to AI Engine.

- [ ] **Step 5: Translate Task 3 changes into Vietnamese**

Apply faithful translations to:
- `docs/tf2-finops/03_security_design_vi.md`
- `docs/tf2-finops/04_deployment_design_vi.md`
- `docs/tf2-finops/05_cost_analysis_vi.md`
- `docs/tf2-finops/NOTES_vi.md`

Keep field names such as `callback_url`, `telemetry_delay_event`, `rollback_payload.boto3_equivalent`, `rollback_status`, and `data_confidence` unchanged.

- [ ] **Step 6: Verify Task 3 edits**

Run:

```powershell
rg -n "error_budget_exceeded_1pct|confidence \*= 0\.5|Lambda reserved concurrency.*Not applicable|Cost Explorer.*normal daily|Cost Explorer.*default|rollback_initiated" docs\tf2-finops\03_security_design.md docs\tf2-finops\04_deployment_design.md docs\tf2-finops\05_cost_analysis.md docs\tf2-finops\NOTES.md
rg -n "error_budget_exceeded_threshold|rollback_executed_at|rollback_status|boto3_result|tf2-cdo\{NN\}-telemetry-\{region\}|telemetry_delay_event|data_confidence|callback_url|cpu_utilization_hourly" docs\tf2-finops\03_security_design.md docs\tf2-finops\04_deployment_design.md docs\tf2-finops\05_cost_analysis.md docs\tf2-finops\NOTES.md
```

Expected: first command returns no stale operational claims. Second command shows the new v1.3.0 contract controls.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add docs/tf2-finops/03_security_design.md docs/tf2-finops/03_security_design_vi.md docs/tf2-finops/04_deployment_design.md docs/tf2-finops/04_deployment_design_vi.md docs/tf2-finops/05_cost_analysis.md docs/tf2-finops/05_cost_analysis_vi.md docs/tf2-finops/NOTES.md docs/tf2-finops/NOTES_vi.md
git commit -m "docs: sync security deployment and cost controls to ai contract v1.3"
```

Expected: Git creates a focused docs commit. Skip this step if the user has not requested commits.

### Task 4: Update Dashboard, Test Report, And Demo Flow

**Files:**
- Modify: `docs/tf2-finops/06_dashboard_alerting_design.md`
- Modify: `docs/tf2-finops/06_dashboard_alerting_design_vi.md`
- Modify: `docs/tf2-finops/07_test_eval_report.md`
- Modify: `docs/tf2-finops/07_test_eval_report_vi.md`
- Modify: `docs/tf2-finops/09_demo_and_presentation_pack.md`
- Modify: `docs/tf2-finops/09_demo_and_presentation_pack_vi.md`

- [ ] **Step 1: Update dashboard data and rollback UX**

In `06_dashboard_alerting_design.md`, make these exact content changes:
- Add `data_confidence` to anomaly detail and alert payload displays, with Finance-readable labels for `HIGH` and `LOW`.
- Update `LOCKED_MODE` dashboard banner to use tiered thresholds and `error_budget_exceeded_threshold`.
- Update rollback request parameters from only `reason` and `rolled_back_by` to `reason`, `rolled_back_by`, `rollback_executed_at`, `rollback_status`, and optional `boto3_result`.
- Update rollback response state from `rollback_initiated` to `audit_recorded`.
- State that the dashboard action reads the CDO cached `rollback_payload.boto3_equivalent` and executes rollback through the CDO backend before notifying the AI audit endpoint.
- Add optional callback observability: if `callback_url` is enabled, callback delivery status is operational telemetry and callback failure does not invalidate the synchronous detect result.

- [ ] **Step 2: Update test report cases**

In `07_test_eval_report.md`, make these exact content changes:
- Add contract tests for `telemetry_delay_event = false` with CUR-only finalized data and `data_confidence = HIGH`.
- Add contract tests for `telemetry_delay_event = true` requiring `aws_cost_explorer_daily` and expecting `data_confidence = LOW`.
- Add validation that `s3_bucket_uri` matches `s3://tf2-cdo{NN}-telemetry-{region}/...json.gz`.
- Add tests that CDO sends `cpu_utilization_hourly` and does not precompute `idle_hours_continuous`.
- Add callback tests: 0s, 30s, 120s retry schedule; callback failure logs `CALLBACK_EXHAUSTED` and does not fail sync detect.
- Replace rollback tests so they assert CDO caches `rollback_payload.boto3_equivalent`, executes rollback via boto3 while AI Engine is unavailable, then calls `/v1/audit/{audit_id}/rollback` with `rollback_status`.
- Add error budget tests for prod 1 percent, staging 10 percent, and no auto-lock in dev/sandbox.
- Add clock skew tests for 300-second request timestamp rejection and 36-hour CUR data timestamp acceptance.

- [ ] **Step 3: Update demo and curveball responses**

In `09_demo_and_presentation_pack.md`, make these exact content changes:
- In Step 1 and Step 3, use CUR `S3_POINTER` as the normal detect payload and present Cost Explorer as fallback only when `telemetry_delay_event = true`.
- Show `data_confidence` in the demo evidence after detect.
- In Step 5, verify `/v1/decide` returns `rollback_payload.boto3_equivalent`, not only CLI rollback commands.
- In Step 10, show CDO reading cached boto3 payload, executing rollback independently, then notifying `/v1/audit/{audit_id}/rollback`.
- Update curveball answers for data lag, false positives, rollback security, and AI Engine failure to use conditional Cost Explorer fallback, `data_confidence`, independent rollback cache, and tiered `LOCKED_MODE`.
- Add a short optional callback demo note: if enabled, callback mirrors `DetectResponse`; callback failure is logged and does not change the synchronous result.

- [ ] **Step 4: Translate Task 4 changes into Vietnamese**

Apply faithful translations to:
- `docs/tf2-finops/06_dashboard_alerting_design_vi.md`
- `docs/tf2-finops/07_test_eval_report_vi.md`
- `docs/tf2-finops/09_demo_and_presentation_pack_vi.md`

Keep the same section hierarchy, sample JSON fields, route names, and table structure as the English files.

- [ ] **Step 5: Verify Task 4 edits**

Run:

```powershell
rg -n "rollback_initiated|error_budget_exceeded_1pct|confidence \*= 0\.5|daily calls to the AWS Cost Explorer API|Cost Explorer API queries\)|idle_hours_continuous" docs\tf2-finops\06_dashboard_alerting_design.md docs\tf2-finops\07_test_eval_report.md docs\tf2-finops\09_demo_and_presentation_pack.md
rg -n "data_confidence|telemetry_delay_event|callback_url|CALLBACK_EXHAUSTED|rollback_payload\.boto3_equivalent|rollback_status|audit_recorded|tf2-cdo\{NN\}-telemetry-\{region\}|cpu_utilization_hourly|error_budget_exceeded_threshold" docs\tf2-finops\06_dashboard_alerting_design.md docs\tf2-finops\07_test_eval_report.md docs\tf2-finops\09_demo_and_presentation_pack.md
```

Expected: first command returns no stale user-facing claims. Second command shows v1.3.0 terms in dashboard, test, and demo docs.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add docs/tf2-finops/06_dashboard_alerting_design.md docs/tf2-finops/06_dashboard_alerting_design_vi.md docs/tf2-finops/07_test_eval_report.md docs/tf2-finops/07_test_eval_report_vi.md docs/tf2-finops/09_demo_and_presentation_pack.md docs/tf2-finops/09_demo_and_presentation_pack_vi.md
git commit -m "docs: update dashboard tests and demo for ai contract v1.3"
```

Expected: Git creates a focused docs commit. Skip this step if the user has not requested commits.

### Task 5: Update ADRs Append-Only

**Files:**
- Modify: `docs/tf2-finops/08_adrs.md`
- Modify: `docs/tf2-finops/08_adrs_vi.md`

- [ ] **Step 1: Mark superseded ADR content without deleting history**

In `08_adrs.md`, make these exact content changes:
- Mark `ADR-004 - CUR S3 plus Cost Explorer API data access` as `Status: Superseded by ADR-019` because the old decision makes Cost Explorer the primary daily querying mechanism.
- Keep the old ADR body in place to preserve history.
- Update non-decision version references in ADR-015 and ADR-018 from v1.1.0 to v1.3.0 where they only describe the current contract basis. Do not change their accepted decision unless the text contradicts v1.3.0.

- [ ] **Step 2: Append ADR-019**

Append this ADR after ADR-018 in `08_adrs.md`:

```markdown
## ADR-019 - CUR-primary detection with conditional Cost Explorer fallback

- **Status**: Accepted
- **Date**: 2026-06-25
- **Context**: The AI API contract v1.3.0 changed `aws_cost_explorer_daily` from an always-required input to a conditional fallback used only when CUR is delayed. The CDO platform also needs globally unique telemetry bucket names so multiple CDO teams can deploy in parallel without S3 name collisions.
- **Decision**: Use CUR data in S3 as the default scheduled detection source. Set `telemetry_delay_event = true` and include Cost Explorer daily data only when CUR is not finalized within the accepted 36-hour data timestamp window. Enforce telemetry object URIs under `s3://tf2-cdo{NN}-telemetry-{region}/...json.gz`.
- **Consequence**:
  - Pro: Reduces Cost Explorer API calls in the normal path and avoids duplicate aggregate data when finalized CUR is available.
  - Pro: Aligns the CDO lakehouse with the authoritative billing export source while preserving an operational fallback during CUR delay.
  - Pro: Prevents S3 `BucketAlreadyExists` collisions across CDO teams.
  - Note: Cost Explorer fallback records have lower certainty and must be surfaced as `data_confidence = LOW`.
  - Note: Cross-team shared skeleton deployments require either constrained wildcard bucket access or STS AssumeRole with an `ExternalId`.
- **Alternatives considered**:
  - Keep Cost Explorer as the primary daily input: Rejected because v1.3.0 makes Cost Explorer conditional and CUR is the authoritative source when finalized.
  - Remove Cost Explorer entirely: Rejected because CUR delivery can lag and the demo needs a controlled fallback path.
  - Use a single shared bucket name: Rejected because S3 bucket names are globally unique and parallel CDO deployments would collide.
```

- [ ] **Step 3: Append ADR-020**

Append this ADR after ADR-019 in `08_adrs.md`:

```markdown
## ADR-020 - CDO-owned rollback cache and environment-tiered error budget lock

- **Status**: Accepted
- **Date**: 2026-06-25
- **Context**: The AI API contract v1.3.0 moved rollback execution responsibility to CDO so rollback remains possible even when AI Engine is unavailable. The contract also changed error budget lock behavior from one flat threshold to environment-specific thresholds.
- **Decision**: Cache `rollback_payload.boto3_equivalent` immediately after `/v1/decide`, execute rollback from the CDO-owned cache, and call `POST /v1/audit/{audit_id}/rollback` only to notify AI Engine of the result. Apply `LOCKED_MODE` at 1 percent rollback rate for prod/prod-core/prod-payments, 10 percent for staging, and no auto-lock for dev/sandbox/ml-research/data-analytics.
- **Consequence**:
  - Pro: Rollback no longer depends on live AI Engine connectivity during an incident.
  - Pro: Keeps containment safety stricter in production while avoiding unnecessary lockouts in dev and sandbox.
  - Pro: Preserves AI feedback and audit updates after CDO completes rollback.
  - Note: CDO must secure the rollback cache because it contains executable boto3 intent.
  - Note: Staging auto-reset behavior must be monitored to avoid hiding recurring quality issues.
- **Alternatives considered**:
  - Let AI Engine execute rollback directly: Rejected because CDO owns member-account credentials and containment permissions.
  - Call AI Engine to regenerate rollback instructions during rollback: Rejected because rollback must still work when AI Engine is unavailable.
  - Keep a flat 1 percent lock threshold for every environment: Rejected because v1.3.0 explicitly disables auto-lock in dev/sandbox and raises staging tolerance to 10 percent.
```

- [ ] **Step 4: Translate ADR changes into Vietnamese**

Apply faithful translation to `docs/tf2-finops/08_adrs_vi.md`:
- Preserve ADR numbers, route names, code fields, and `Status` values.
- Translate prose and table/bullet descriptions into Vietnamese.
- Keep `ADR-019`, `ADR-020`, `telemetry_delay_event`, `data_confidence`, `rollback_payload.boto3_equivalent`, `LOCKED_MODE`, and route names unchanged.

- [ ] **Step 5: Verify ADR edits**

Run:

```powershell
rg -n "ADR-004|Superseded by ADR-019|ADR-019|ADR-020|telemetry_delay_event|data_confidence|rollback_payload\.boto3_equivalent|error_budget_exceeded_threshold|v1\.3\.0" docs\tf2-finops\08_adrs.md docs\tf2-finops\08_adrs_vi.md
```

Expected: both English and Vietnamese ADR files include the supersession marker and new ADRs.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add docs/tf2-finops/08_adrs.md docs/tf2-finops/08_adrs_vi.md
git commit -m "docs: add ADRs for ai contract v1.3 decisions"
```

Expected: Git creates a focused ADR commit. Skip this step if the user has not requested commits.

### Task 6: Bilingual Parity And Stash-Wide Verification

**Files:**
- Verify: `docs/tf2-finops/*.md`
- Verify: `docs/tf2-finops/*_vi.md`

- [ ] **Step 1: Verify required file pairs exist**

Run:

```powershell
$pairs = @(
  '01_requirements_analysis',
  '02_infra_design',
  '03_security_design',
  '04_deployment_design',
  '05_cost_analysis',
  '06_dashboard_alerting_design',
  '07_test_eval_report',
  '08_adrs',
  '09_demo_and_presentation_pack',
  'AWS_Component_details',
  'NOTES'
)
foreach ($base in $pairs) {
  $en = "docs/tf2-finops/$base.md"
  $vi = "docs/tf2-finops/${base}_vi.md"
  if (!(Test-Path $en)) { Write-Output "MISSING $en" }
  if (!(Test-Path $vi)) { Write-Output "MISSING $vi" }
}
```

Expected: no `MISSING` output.

- [ ] **Step 2: Verify heading-count parity for each English/Vietnamese pair**

Run:

```powershell
$pairs = @(
  '01_requirements_analysis',
  '02_infra_design',
  '03_security_design',
  '04_deployment_design',
  '05_cost_analysis',
  '06_dashboard_alerting_design',
  '07_test_eval_report',
  '08_adrs',
  '09_demo_and_presentation_pack',
  'AWS_Component_details',
  'NOTES'
)
foreach ($base in $pairs) {
  $en = Select-String -Path "docs/tf2-finops/$base.md" -Pattern '^\s*#{1,6}\s+' | ForEach-Object { $_.Line.Trim() }
  $vi = Select-String -Path "docs/tf2-finops/${base}_vi.md" -Pattern '^\s*#{1,6}\s+' | ForEach-Object { $_.Line.Trim() }
  if ($en.Count -ne $vi.Count) {
    Write-Output "$base heading count mismatch EN=$($en.Count) VI=$($vi.Count)"
  }
}
```

Expected: no heading count mismatch output. If a mismatch appears, compare the corresponding pair manually and add the missing translated heading.

- [ ] **Step 3: Verify Mermaid block parity**

Run:

```powershell
$pairs = @(
  '01_requirements_analysis',
  '02_infra_design',
  '03_security_design',
  '04_deployment_design',
  '05_cost_analysis',
  '06_dashboard_alerting_design',
  '07_test_eval_report',
  '08_adrs',
  '09_demo_and_presentation_pack',
  'AWS_Component_details',
  'NOTES'
)
foreach ($base in $pairs) {
  $en = (Select-String -Path "docs/tf2-finops/$base.md" -Pattern '^```mermaid').Count
  $vi = (Select-String -Path "docs/tf2-finops/${base}_vi.md" -Pattern '^```mermaid').Count
  if ($en -ne $vi) { Write-Output "$base Mermaid mismatch EN=$en VI=$vi" }
}
```

Expected: no Mermaid mismatch output.

- [ ] **Step 4: Verify stale v1.1/v1.2 operational claims are gone**

Run:

```powershell
rg -n "Programmatic Contract Mapping \(v1\.1\)|ai-api-contract.*v1\.1|ai-api-contract.*v1\.2|primary daily querying|aws_cost_explorer_daily.*always|required.*aws_cost_explorer_daily|rollback_initiated|error_budget_exceeded_1pct|idle_hours_continuous|confidence \*= 0\.5|202 Accepted|P99 ACK|DetectResponse \(status: \"processing\"\)|polling active detection|Cost Explorer API serves as the primary|daily calls to the AWS Cost Explorer API" docs\tf2-finops -g "*.md"
```

Expected: no output, except historical contract history inside ADRs only if the line is explicitly marked superseded and does not describe current behavior.

- [ ] **Step 5: Verify new v1.3.0 terms are present**

Run:

```powershell
rg -n "v1\.3\.0|telemetry_delay_event|data_confidence|callback_url|rollback_payload\.boto3_equivalent|tf2-cdo\{NN\}-telemetry-\{region\}|error_budget_exceeded_threshold|cpu_utilization_hourly|Request Timestamp|Data Timestamp|36 hours|rollback_status|audit_recorded|CALLBACK_EXHAUSTED" docs\tf2-finops -g "*.md"
```

Expected: hits across the relevant English and Vietnamese stash files.

- [ ] **Step 6: Verify required hard boundaries remain**

Run:

```powershell
rg -n "NEVER terminate prod, delete data, or modify IAM|dry-run|90 days|>=90 days|AIOps-owned AI Engine|Lambda container image|ECR image digest pinning|reserved concurrency|EventBridge Scheduler|CUR|Athena|SQS|DLQ|lakehouse-centric" docs\tf2-finops -g "*.md"
```

Expected: each required boundary appears in the stash. If a required term is absent from the English docs, add it to the most relevant section and mirror it in Vietnamese.

- [ ] **Step 7: Verify `template-docs/` remains untouched**

Run:

```powershell
git -c safe.directory=E:/code-folder/xbrain_projects/capstone_phase2_main/tf2-finops-docs status --short template-docs
```

Expected: no output.

- [ ] **Step 8: Review final diff**

Run:

```powershell
git -c safe.directory=E:/code-folder/xbrain_projects/capstone_phase2_main/tf2-finops-docs diff -- docs/tf2-finops docs/superpowers/plans/2026-06-25-ai-api-contract-v1-3-doc-stash-sync.md
```

Expected: diff only updates the plan and the intended stash files. No `template-docs/` files are changed.

- [ ] **Step 9: Commit final verification updates**

Run:

```powershell
git add docs/tf2-finops docs/superpowers/plans/2026-06-25-ai-api-contract-v1-3-doc-stash-sync.md
git commit -m "docs: verify ai contract v1.3 stash sync"
```

Expected: Git creates the final verification commit if there are remaining uncommitted documentation updates. Skip this step if the user has not requested commits.

## Self-Review Checklist

- [ ] Every English file touched has a matching Vietnamese update.
- [ ] `template-docs/` has no changes.
- [ ] Current behavior says CUR is the default source and Cost Explorer is conditional fallback.
- [ ] Current behavior says `/v1/detect` is synchronous with P99 `< 300 ms`.
- [ ] Current behavior says `/v1/status/{id}` is not detection polling.
- [ ] Current behavior includes `data_confidence`, `telemetry_delay_event`, `callback_url`, and `rollback_payload.boto3_equivalent`.
- [ ] Rollback is CDO-executed from cached boto3 payload before AI audit notification.
- [ ] Error budget lock is tiered by environment.
- [ ] S3 telemetry bucket naming uses `tf2-cdo{NN}-telemetry-{region}`.
- [ ] ADR history is preserved and superseded decisions are marked, not deleted.
- [ ] All commands in Task 6 pass or produce only explicitly accepted historical ADR references.
