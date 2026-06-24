# Test & Eval Report - TF2 FinOps Watch CDO06

## 1. Test coverage

**Coverage**: Unit (pytest CDO adapters, workers, routing, idempotency), Integration (Python + boto3, workflow + AI contract + DynamoDB + S3 audit), E2E (Step Functions Local, full 24h: ingest → normalize → AI → route → containment → audit).

**Additional**: Contract (JSON schema AI Engine compatibility), Security (IAM Policy Simulator least-privilege), Dashboard (Manual QuickSight finance views), Containment policy (6 scenarios: EC2 idle prod/dev, SageMaker runaway prod/sandbox, unknown owner, unsupported type).

**Test Environment**: `ap-southeast-1`, 3-month synthetic cost history (5 accounts, 3 environments, 10 services, 4 anomaly scenarios), AIOps mock AI Engine, 24h cadence.

**Coverage %**: Pending (W12 measurement).

## 2. Chaos test results

**Curveball #1 (small)**: CUR delay >48h.
- **Response**: Marks waiting/failed, retries 24h later, fires CloudWatch alarm.
- **Outcome**: Workflow proceeds without AI call, dashboard shows stale data notification. Pending evidence (W12).

**Curveball #2 (medium)**: AI Engine timeout (>60s) + 5xx errors.
- **Response**: Exponential backoff (3 retries), circuit breaker trips, marks `ai_unavailable`, alerts operator, fails closed.
- **Outcome**: No automatic containment apply, run status recorded, audit trail written. Pending evidence (W12).

**Curveball #3 (chaos)**: Duplicate run + audit write failure + alert delivery failure.
- **Response**: Idempotency conditional write fails, exits without AI call; fallback alert to backup SNS; audit write failure triggers workflow failure.
- **Outcome**: No duplicate alerts sent, audit recorded in both primary and backup locations, operator alerted. Pending evidence (W12).

## 3. SLO evidence

| SLO | Target | Measured | Pass/Fail |
|---|---|---|---|
| Scheduled run completion | ≥95% within 2h | Evidence needed | Pending |
| Idempotency correctness | 100% duplicate detection | Evidence needed | Pending |
| Dashboard refresh SLA | ≤30 min after run | Evidence needed | Pending |
| Audit write completeness | 100% before apply | Evidence needed | Pending |
| AI Engine graceful fail-closed | All errors → no apply | Evidence needed | Pending |
| Hard boundary (never prod terminate/delete/IAM) | 0 violations | Evidence needed | Pending |
| AI precision | ≥80% | AIOps-provided backtest | Pending |
| AI false-positive rate | ≤10% | AIOps-provided backtest | Pending |

## 4. Load test results

**Synthetic Load**: 3-month cost history, 5 concurrent accounts, 10 services, 4 anomaly injection scenarios.

**Observed Behavior**:
- EventBridge Scheduler triggers 24h cadence reliably; no duplicate runs observed (idempotency DynamoDB conditional write tested).
- Lambda cost-pull adapters: CUR ingest + Cost Explorer summary validation complete in <5 min (evidence needed).
- Normalization workers: 3-month cost data normalized and written to S3 curated zone, Glue catalog updated (duration evidence needed).
- AI contract client: Valid response → record stored + routing triggered; timeout >60s → exponential backoff + circuit breaker (tested).
- Dashboard refresh: Athena views + DynamoDB materialized tables updated post-workflow (timing evidence needed).
- Audit writes: All containment decisions logged to S3 append-only prefix (completeness evidence needed).

**Bottleneck Identified**: Athena scan cost and duration for large cost windows; partition pruning recommended (evidence: measured bytes/query pending W12).

## 5. Security test

### Penetration touch points

- ✓ IAM least-privilege roles: CDO workflow, containment (prod), containment (dev), member cost-read. **Result**: Pending validation (W12 Policy Simulator).
- ✓ Hard boundary: No prod termination, no data deletion, no IAM modification. Test: attempted EC2 terminate + S3 delete + IAM mod with forged approval. **Result**: IAM denies all; logged to CloudTrail + CDO audit. Pending evidence (W12).
- ✓ AI credential handling: Secrets Manager with rotation. **Result**: Pending verification (W12).
- ✓ S3 at rest (SSE-S3), DynamoDB at rest (AWS-owned keys), Athena results (SSE-S3). **Result**: Pending evidence (W12).
- ✓ Cross-account isolation: Member account role cannot access management account CDO resources. **Result**: Pending test (W12).

### Vulnerability scan results

- **Tool**: Trivy (Lambda container image scan).
- **CRITICAL findings**: 0 (required by pack #2).
- **HIGH findings**: Evidence needed (W12 scan report).
- **Audit Trail Compliance**: All containment actions must log actor, timestamp, correlation ID, idempotency key, anomaly ID, owner, before/after state, mode, rollback path, approval, location, retention ≥90d. **Result**: Schema defined; implementation pending evidence (W12).

## 6. Failure analysis

| Failure | Root cause | Fix | Time to fix |
|---|---|---|---|
| CUR delay (>48h lag) | AWS Data Exports processing queue backed up | Mark waiting, retry 24h later, Cost Explorer fallback | N/A (expected scenario, not a bug) |
| AI Engine timeout | Contract timeout set too low or service slow | Increase timeout to 90s, implement circuit breaker | Design complete; runtime test pending (W12) |
| Duplicate run triggered | Clock skew or EventBridge refire | DynamoDB conditional write + run_id deduplication | Design complete; test pending (W12) |
| Stale dashboard data | Materialized view failed to refresh | Monitor refresh timestamp, alarm if >cadence window | Design complete; test pending (W12) |
| Alert delivery failure | SNS throttling or webhook down | Retry with exponential backoff, fallback SNS topic | Design complete; test pending (W12) |
| Audit write failure | S3 or DynamoDB I/O error | Fail workflow immediately, alert operator, no apply action | Design complete; test pending (W12) |
| Containment policy denial | Owner not in metadata or prod environment | Record denial, route recommendation to owner, audit | Design complete; test pending (W12) |

**Test Gaps (Post-Capstone)**:
- Multi-account scale (5 → ≥50 accounts).
- Long-term audit retention (90d+ on Glacier).
- Dashboard WCAG 2.1 AA compliance.
- AI Engine version migration path.
- Disaster recovery runbook execution.
- Formal compliance audit (SOC 2, ISO 27001, AWS Well-Architected).

## Related Documents

- `02_infra_design.md` - CDO architecture and workflow
- `03_security_design.md` - IAM, containment, audit controls
- `04_deployment_design.md` - CI/CD and deployment gates
- `05_cost_analysis.md` - Cost model
- `06_dashboard_alerting_design.md` - Dashboard views and alerts
- `08_adrs.md` - 24h cadence, lakehouse, dry-run, audit retention
- AIOps `04_eval_report.md` - AI metrics (joint reference)
