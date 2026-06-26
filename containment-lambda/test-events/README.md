# Test Events — Containment Lambda

Các file JSON này dùng để test thủ công Lambda sau khi deploy lên AWS sandbox.

## Cách invoke Lambda

```bash
aws lambda invoke \
  --function-name containment-lambda \
  --payload file://01_dry_run_sandbox.json \
  --cli-binary-format raw-in-base64-out \
  output.json

# Xem kết quả
cat output.json
```

## Danh sách scenarios

| File | Scenario | execution_mode input | Kết quả kỳ vọng |
|---|---|---|---|
| `01_dry_run_sandbox.json` | Dry-run sandbox | `dry-run` | `status=dry-run`, không gọi AWS |
| `02_apply_stop_ec2_sandbox.json` | Stop EC2 thật | `apply` | `status=completed`, instance stopped ⚠️ |
| `03_tag_prod.json` | Tag prod (được phép) | `tag` | `status=completed`, tags gắn vào instance |
| `04_apply_blocked_prod_boundary.json` | Apply prod bị chặn | `apply` → **force `dry-run`** | `execution_mode_applied=dry-run` |
| `05_low_confidence_forced_dry_run.json` | Low confidence bị chặn | `apply` → **force `dry-run`** | `execution_mode_applied=dry-run` |
| `06_denied_approval.json` | Approval denied | `denied` | `status=denied`, không làm gì |
| `07_suggest_finance_route.json` | Suggest → Finance | `suggest` | `suggestion_record.route_target=finance` |

## Verify output

### Scenario 1 — Dry-run
```json
{
  "status": "dry-run",
  "execution_mode_applied": "dry-run",
  "audit_record_id": "...",
  "dry_run_result": {
    "would_execute_service": "ec2",
    "would_execute_method": "stop_instances",
    "simulation_note": "dry-run: no AWS API call made..."
  }
}
```

### Scenario 4 — Prod boundary blocked
```json
{
  "status": "dry-run",
  "execution_mode_applied": "dry-run"
}
```
Quan trọng: `execution_mode_applied` phải là `dry-run` dù input gửi `apply`.

### Scenario 6 — Denied
```json
{
  "status": "denied",
  "execution_mode_applied": "denied",
  "denied_action_record": {
    "reason": "approval_denied",
    "original_execution_mode": "apply"
  }
}
```

## Sau khi test — verify thêm trên AWS Console

**S3 Audit** (scenarios 1, 2, 3, 5, 7):
```
s3://company-cdo-{account_id}-telemetry/audit/year=2026/month=06/
```
Phải có 2 files: `{audit_id}.json` (pre-action) và `{audit_id}_post.json` (post-action).

**DynamoDB Dashboard Cache**:
```
Table: finops-dashboard-cache-{env}
Key: anomaly_id = "{anomaly_id từ event}"
```
Phải có item với `status` và `audit_record_s3_uri`.

**DynamoDB Rollback Cache** (scenarios 1, 2, 3, 5, 7):
```
Table: finops-rollback-cache
Key: anomaly_id = "{anomaly_id từ event}"
```
Phải có item với `boto3_equivalent` để rollback độc lập.

**Scenario 6 (denied)**: KHÔNG có gì trong S3, DynamoDB — vì Lambda return ngay khi denied.
