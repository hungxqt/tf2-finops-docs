"""
dynamo_cache.py — Cập nhật DynamoDB Dashboard Cache.

DynamoDB là read-cache cho Finance Dashboard — best-effort, không phải authoritative.
S3 Object Lock mới là authoritative audit store.

Nếu DynamoDB write fail → log warning, KHÔNG block containment flow.
Theo 02_infra_design.md §1.4: ContLambda → Update view cache → DynamoDB Dashboard Cache
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def update_dashboard_cache(
    session: boto3.Session,
    table_name: str,
    anomaly_id: str,
    run_id: str,
    correlation_id: str,
    resource_id: str,
    account_id: str,
    environment: str,
    execution_mode_applied: str,
    status: str,
    audit_record_id: str,
    audit_record_s3_uri: str,
    severity: str = "medium",
    anomaly_type: str = "",
    explanation: str = "",
) -> bool:
    """
    Upsert containment summary vào DynamoDB Dashboard Cache.

    Finance Dashboard đọc từ table này để hiển thị:
    - Anomaly nào đã được xử lý
    - Execution mode nào đã chạy
    - Link đến audit record S3

    Args:
        session: CDO management account session
        table_name: DynamoDB Dashboard Cache table name
        ... các fields hiển thị trên dashboard

    Returns:
        True nếu thành công, False nếu thất bại (non-blocking)
    """
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table(table_name)

    item = {
        "anomaly_id": anomaly_id,
        "run_id": run_id,
        "correlation_id": correlation_id,
        "resource_id": resource_id,
        "account_id": account_id,
        "environment": environment,
        "execution_mode_applied": execution_mode_applied,
        "status": status,
        "audit_record_id": audit_record_id,
        "audit_record_s3_uri": audit_record_s3_uri,
        "severity": severity,
        "anomaly_type": anomaly_type,
        "explanation": explanation,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    try:
        table.put_item(Item=item)
        logger.info(
            "dashboard cache updated",
            extra={
                "anomaly_id": anomaly_id,
                "table": table_name,
                "status": status,
            },
        )
        return True

    except ClientError as exc:
        # Best-effort — không block containment
        logger.warning(
            "dashboard cache update failed (non-blocking)",
            extra={
                "anomaly_id": anomaly_id,
                "table": table_name,
                "error": str(exc),
            },
        )
        return False


def cache_rollback_payload(
    session: boto3.Session,
    rollback_cache_table: str,
    anomaly_id: str,
    correlation_id: str,
    rollback_payload: dict[str, Any],
    ttl_days: int = 90,
) -> bool:
    """
    Cache rollback_payload.boto3_equivalent vào finops-rollback-cache.

    Gọi NGAY SAU khi nhận DecideResponse — trước khi thực thi action.
    Đảm bảo rollback độc lập với AI Engine availability.

    Theo deployment-contract.md §CDO Rollback Cache:
    TTL = 90 ngày (khớp audit retention)

    Args:
        session: CDO management account session
        rollback_cache_table: finops-rollback-cache table name
        anomaly_id: Partition key
        correlation_id: Trace ID
        rollback_payload: boto3_equivalent dict từ /v1/decide response
        ttl_days: TTL tính bằng ngày

    Returns:
        True nếu thành công, False nếu thất bại
    """
    import time
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table(rollback_cache_table)

    ttl_epoch = int(time.time()) + (ttl_days * 86400)

    item = {
        "anomaly_id": anomaly_id,
        "correlation_id": correlation_id,
        "boto3_equivalent": rollback_payload,
        "cached_at": datetime.now(tz=timezone.utc).isoformat(),
        "ttl_epoch": ttl_epoch,
    }

    try:
        table.put_item(Item=item)
        logger.info(
            "rollback payload cached",
            extra={
                "anomaly_id": anomaly_id,
                "table": rollback_cache_table,
                "ttl_days": ttl_days,
            },
        )
        return True

    except ClientError as exc:
        logger.warning(
            "rollback cache write failed (non-blocking)",
            extra={
                "anomaly_id": anomaly_id,
                "table": rollback_cache_table,
                "error": str(exc),
            },
        )
        return False
