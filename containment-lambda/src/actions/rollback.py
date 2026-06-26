"""
rollback.py — Thực thi rollback từ DynamoDB finops-rollback-cache.

Rollback KHÔNG phụ thuộc AI Engine availability.
CDO tự execute boto3 command từ cached rollback_payload.boto3_equivalent,
sau đó report kết quả lên AI Engine qua POST /v1/audit/{audit_id}/rollback.

Theo deployment-contract.md §CDO Rollback Cache:
  - Read trigger: next_action = ROLLBACK hoặc manual engineer trigger
  - Execution: CDO boto3 client tự gọi, không qua AI Engine
  - Post-execution: publish SQS finops-watch-rollback (audit completion only)
"""
from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.model.input import ContainmentInput, Boto3Payload
from src.model.output import RollbackResult

logger = logging.getLogger(__name__)


def execute_rollback_from_cache(
    anomaly_id: str,
    rollback_cache_table: str,
    management_session: boto3.Session,
    member_session: boto3.Session,
) -> RollbackResult:
    """
    Đọc rollback payload từ DynamoDB cache và thực thi.

    Flow:
    1. Read finops-rollback-cache[anomaly_id]
    2. Execute boto3_equivalent command trong member account
    3. Return result (caller sẽ report lên AI Engine)

    Args:
        anomaly_id: Key để tìm trong DynamoDB rollback cache
        rollback_cache_table: Tên DynamoDB table (finops-rollback-cache)
        management_session: Session CDO management account (để đọc DynamoDB)
        member_session: Session member account (để thực thi rollback)

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

        return RollbackResult(
            anomaly_id=anomaly_id,
            rollback_service=boto3_payload.service,
            rollback_method=boto3_payload.method,
            boto3_http_status=http_status,
            boto3_request_id=request_id,
            rollback_note="rollback executed from DynamoDB cache, independent of AI Engine",
        )

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
