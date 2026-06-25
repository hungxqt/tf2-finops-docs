# Documentation Notes - Task Force 2 · FinOps Watch CDO

This document serves as an operational guide for the engineering and CDO teams when transitioning the documentation pack from the design phase to the active deployment phase.

## 1. Placeholder Strategy: "Evidence needed" / "Cần bằng chứng"

Throughout the CDO documentation pack, you will find specific placeholders marked as:
- **English**: `Evidence needed: <metric/description>`
- **Vietnamese**: `Cần bằng chứng: <mô tả/chỉ số>`

### Purpose

These placeholders indicate actual operational metrics, telemetry data, AWS cost figures, and validation results that **cannot be simulated or determined during the architecture and design phase**. They represent the required empirical evidence to satisfy the platform's non-functional requirements (NFRs), Service Level Objectives (SLOs), and cost models.

Using placeholders prevents the documentation from presenting speculative or unverified "mock" metrics as actual production telemetry, maintaining compliance and transparency for financial and technical audit logs.

### Scope of Telemetry

In alignment with the signed telemetry and API contracts:
1. **CDO Platform Observability**: Actual measurements must capture the CDO-owned adapters (Lambda execution times, SQS/DLQ queuing latency, direct Lambda invocation volumes, and Athena query sizes) and the operational hosting platform parameters.
2. **AI Workload Execution**: CDO acts as the hosting environment for the AIOps-provided AI Engine container. The hosted engine execution duration, memory consumption, and concurrency patterns must be tracked and separated from CDO platform costs.
3. **Hybrid Telemetry Scope**: In addition to cost data (CUR and Cost Explorer API), the detection loop leverages CloudWatch infrastructure metrics (`resource_utilization_metrics` such as CPU, memory, and database utilization). If CloudWatch utilization metrics are missing, the platform automatically falls back to CUR-only mode, halving detection confidence (`confidence *= 0.5`) and locking containment actions to dry-run/alert-only.

### Instructions for Post-Deployment Updates

Once the infrastructure is successfully deployed in the staging/production AWS accounts and the daily batch schedule is executed, the engineering team must:

1. **Collect Telemetry**: Use AWS Cost Explorer (filtered by the `Project=TF2-FinOps-CDO06` tag), CloudWatch Metrics, AWS X-Ray traces, and the DynamoDB run logs to collect the actual values.
2. **Replace Placeholders**: Locating each placeholder in the documents and replacing the text with the collected figures, links to S3 audit paths, or CloudWatch dashboard snapshots.
3. **Primary Affected Files**:
   - [05_cost_analysis.md](05_cost_analysis.md) / [05_cost_analysis_vi.md](05_cost_analysis_vi.md): Update forecasting and actual cost tables in Section 1, Section 2, Section 5, and Section 5.3 (Cost-per-Correct-Decision).
   - [07_test_eval_report.md](07_test_eval_report.md) / [07_test_eval_report_vi.md](07_test_eval_report_vi.md): Update Section 2 (SLO evidence tables with measured success/freshness rates) and Section 8.2 (acknowledged test gaps).

## 2. Parity Verification Rules

When updating these placeholders:
- Maintain 100% parity between the English primary files and the Vietnamese (`_vi.md`) translation counterparts.
- Run the local verification script (`verify_docs.py`) to confirm that heading counts, code block structures, and link locations remain identical.
