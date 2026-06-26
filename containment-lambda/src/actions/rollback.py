"""
rollback.py — Thực thi rollback từ DynamoDB finops-rollback-cache.

Rollback KHÔNG phụ thuộc AI Engine availability.
CDO tự execute boto3 command từ cached rollback_payload.boto3_equivalent,
sau đó report kết quả lên AI Engine qua POST /v1/audit/{audit_id}/rollback.

Theo deployment-contract.md §CDO Rollback Cache:
  - Read trigger: next_action = ROLLBACK hoặc manual engineer trigger
  - Execution: CDO boto3 client tự gọi, không qua AI Engine
  - Post-execution: publish SQS finops-watch-rollback (audit completion only — KHÔNG dùng để dispatch rollback)
"""
from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.model.input import Boto3Payload
from src.model.output import RollbackResult

logger = logging.getLogger(__name__)


def execute_rollback_from_cache(
    anomaly_id: str,
    rollback_cache_table: str,
    management_session: boto3.Session,
    member_session: boto3.Session,
    sqs_rollback_queue_url: str = "",
    audit_id: str = "",
) -> RollbackResult:
    """
    Đọc rollback payload từ DynamoDB cache và thực thi.

    Flow:
    1. Read finops-rollback-cache[anomaly_id]
    2. Execute boto3_equivalent command trong member account
    3. Publish audit completion notification lên SQS finops-watch-rollback
    4. Return result (caller sẽ report lên AI Engine)

    Args:
        anomaly_id: Key để tìm trong DynamoDB rollback cache
        rollback_cache_table: Tên DynamoDB table (finops-rollback-cache)
        management_session: Session CDO management account (để đọc DynamoDB + publish SQS)
        member_session: Session member account (để thực thi rollback)
        sqs_rollback_queue_url: URL SQS finops-watch-rollback (audit completion only)
        audit_id: Audit ID để ghi vào SQS notification

    Returns:
        RollbackResult
    """
    # Step 1: Đọc rollback payload từ cache
    cached_payload = _read_rollback_cache(
        management_session, rollback_cache_table, anomaly_id
    )

    if not cached_payload:
        raise RuntimeError(
            f"ROLLBACK_CACHE_MISS anomaly_id={anomaly_id}: "
            f"no cached rollback payload found in {rollback_cache_table}"
        )

    boto3_payload = Boto3Payload.from_dict(cached_payload["boto3_equivalent"])

    logger.info(
        "executing rollback from cache",
        extra={
            "anomaly_id": anomaly_id,
            "service": boto3_payload.service,
            "method": boto3_payload.method,
        },
    )

    # Step 2: Execute boto3 command trong member account
    try:
        client = member_session.client(boto3_payload.service)
        boto3_method = getattr(client, boto3_payload.method)
        resp = boto3_method(**boto3_payload.parameters)

        http_status = resp.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        request_id = resp.get("ResponseMetadata", {}).get("RequestId", "")

        logger.info(
            "rollback executed successfully",
            extra={
                "anomaly_id": anomaly_id,
                "http_status": http_status,
            },
        )

        result = RollbackResult(
            anomaly_id=anomaly_id,
            rollback_service=boto3_payload.service,
            rollback_method=boto3_payload.method,
            boto3_http_status=http_status,
            boto3_request_id=request_id,
            rollback_note="rollback executed from DynamoDB cache, independent of AI Engine",
        )

        # Step 3: Publish audit completion notification lên SQS (best-effort)
        # Theo deployment-contract.md §Message Queues:
        # finops-watch-rollback = AUDIT COMPLETION NOTIFICATION ONLY
        # Payload khớp POST /v1/audit/{audit_id}/rollback request body
        if sqs_rollback_queue_url:
            _publish_rollback_completion(
                session=management_session,
                queue_url=sqs_rollback_queue_url,
                anomaly_id=anomaly_id,
                audit_id=audit_id,
                rollback_status="success",
                http_status=http_status,
            )

        return result

    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        raise RuntimeError(
            f"ROLLBACK_BOTO3_FAILED anomaly_id={anomaly_id} "
            f"error_code={error_code}: {exc}"
        ) from exc


def _read_rollback_cache(
    session: boto3.Session,
    table_name: str,
    anomaly_id: str,
) -> dict[str, Any] | None:
    """
    Đọc cached rollback payload từ DynamoDB finops-rollback-cache.

    Returns:
        dict với boto3_equivalent nếu tìm thấy, None nếu không có
    """
    dynamodb = session.resource("dynamodb")
    table = dynamodb.Table(table_name)

    try:
        resp = table.get_item(Key={"anomaly_id": anomaly_id})
        item = resp.get("Item")
        if not item:
            logger.warning(
                "rollback cache miss",
                extra={"anomaly_id": anomaly_id, "table": table_name},
            )
            return None
        return item
    except ClientError as exc:
        raise RuntimeError(
            f"ROLLBACK_CACHE_READ_FAILED anomaly_id={anomaly_id}: {exc}"
        ) from exc


def _publish_rollback_completion(
    session: boto3.Session,
    queue_url: str,
    anomaly_id: str,
    audit_id: str,
    rollback_status: str,
    http_status: int,
) -> None:
    """
    Publish rollback completion notification lên SQS finops-watch-rollback.

    Đây là AUDIT COMPLETION ONLY — không dùng để dispatch rollback command.
    Theo deployment-contract.md §Message Queues §CDO Rollback Cache.
    """
    from datetime import datetime, timezone
    sqs = session.client("sqs")
    payload = {
        "audit_id": audit_id,
        "anomaly_id": anomaly_id,
        "rollback_status": rollback_status,
        "rollback_executed_at": datetime.now(tz=timezone.utc).isoformat(),
        "http_status": http_status,
    }
    try:
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(payload),
        )
        logger.info(
            "rollback completion published to SQS",
            extra={"anomaly_id": anomaly_id, "audit_id": audit_id},
        )
    except ClientError as exc:
        # Best-effort — không block rollback result
        logger.warning(
            "failed to publish rollback completion to SQS (non-blocking)",
            extra={"anomaly_id": anomaly_id, "error": str(exc)},
        )
