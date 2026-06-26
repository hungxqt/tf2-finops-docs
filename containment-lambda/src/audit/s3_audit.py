"""
s3_audit.py — Ghi audit record vào S3 Object Lock (WORM).

Theo 03_security_design.md §5.1:
  - Ghi TRƯỚC khi thực thi action (pre-action audit)
  - Cập nhật SAU khi xong (post-action audit)
  - Object Lock bảo đảm immutability (không xóa được trong 90 ngày)
  - Audit chain: sha256(current_payload + previous_hash)
  - Retention: 90 days minimum

S3 path: s3://company-cdo-{account_id}-telemetry/audit/year={}/month={}/{audit_id}.json
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.model.output import AuditRecord, AuditChain

logger = logging.getLogger(__name__)

ACTOR = "cdo-platform-containment-lambda"
RETENTION_PERIOD_DAYS = 90


def write_pre_action_audit(
    session: boto3.Session,
    audit_record: AuditRecord,
    audit_bucket: str,
    audit_prefix: str = "audit/",
) -> tuple[str, str]:
    """
    Ghi initial audit record TRƯỚC khi thực thi action.

    Args:
        session: CDO management account session
        audit_record: AuditRecord đã build sẵn
        audit_bucket: company-cdo-{account_id}-telemetry
        audit_prefix: Prefix trong bucket, mặc định "audit/"

    Returns:
        (audit_id, s3_uri) tuple
    """
    audit_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    s3_key = _build_s3_key(audit_prefix, now, audit_id)
    s3_uri = f"s3://{audit_bucket}/{s3_key}"

    # Cập nhật fields
    audit_record.retention_location = s3_uri
    audit_record.audit_chain = AuditChain(
        audit_id=audit_id,
        event_hash=audit_record.compute_hash(),
        previous_hash="",
    ).to_dict()

    _put_object_with_lock(
        session=session,
        bucket=audit_bucket,
        key=s3_key,
        body=json.dumps(audit_record.to_dict(), default=str),
        retain_until_date=_compute_retain_until(now, RETENTION_PERIOD_DAYS),
    )

    logger.info(
        "pre-action audit written",
        extra={
            "audit_id": audit_id,
            "s3_uri": s3_uri,
            "anomaly_id": audit_record.anomaly_id,
        },
    )

    return audit_id, s3_uri


def update_post_action_audit(
    session: boto3.Session,
    audit_bucket: str,
    audit_prefix: str,
    audit_id: str,
    action_result: dict[str, Any],
    rollback_status: str = "not_required",
) -> None:
    """
    Ghi post-action audit record (file mới với suffix _post).

    Không overwrite pre-action record (S3 Object Lock không cho phép).
    Thay vào đó ghi file mới với audit_id + "_post" suffix.

    Args:
        session: CDO management account session
        audit_bucket: S3 bucket
        audit_prefix: Prefix trong bucket
        audit_id: ID của pre-action audit đã ghi
        action_result: Kết quả thực tế của action
        rollback_status: pending | success | not_required
    """
    now = datetime.now(tz=timezone.utc)
    post_audit_id = f"{audit_id}_post"
    s3_key = _build_s3_key(audit_prefix, now, post_audit_id)

    post_record = {
        "type": "post-action-audit",
        "pre_action_audit_id": audit_id,
        "post_audit_id": post_audit_id,
        "timestamp": now.isoformat(),
        "action_result": action_result,
        "rollback_status": rollback_status,
        "rollback_executed_at": now.isoformat() if rollback_status == "success" else "",
    }

    _put_object_with_lock(
        session=session,
        bucket=audit_bucket,
        key=s3_key,
        body=json.dumps(post_record, default=str),
        retain_until_date=_compute_retain_until(now, RETENTION_PERIOD_DAYS),
    )

    logger.info(
        "post-action audit written",
        extra={
            "audit_id": audit_id,
            "post_audit_id": post_audit_id,
        },
    )


def _put_object_with_lock(
    session: boto3.Session,
    bucket: str,
    key: str,
    body: str,
    retain_until_date: datetime,
) -> None:
    """Ghi object lên S3 với Object Lock (COMPLIANCE mode)."""
    s3 = session.client("s3")

    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
            ObjectLockMode="COMPLIANCE",
            ObjectLockRetainUntilDate=retain_until_date,
        )
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        # Nếu bucket không bật Object Lock, fallback ghi không có lock
        # (môi trường local test có thể không support Object Lock)
        if error_code in ("InvalidRequest", "NoSuchObjectLockConfiguration"):
            logger.warning(
                "Object Lock not enabled on bucket, writing without lock",
                extra={"bucket": bucket, "key": key, "error_code": error_code},
            )
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="application/json",
            )
        else:
            raise


def _build_s3_key(prefix: str, now: datetime, audit_id: str) -> str:
    """Build S3 key với partition theo year/month."""
    return (
        f"{prefix}"
        f"year={now.year}/month={now.month:02d}/"
        f"{audit_id}.json"
    )


def _compute_retain_until(now: datetime, days: int) -> datetime:
    """Tính retain_until_date = now + retention_days."""
    from datetime import timedelta
    return now + timedelta(days=days)
