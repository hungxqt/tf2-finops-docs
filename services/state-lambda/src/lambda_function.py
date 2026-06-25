from __future__ import annotations

import json
import os
from typing import Any

import boto3

from s3_store import S3RunStateStore
from service import StateService, StateServiceError


_service: StateService | None = None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    fields = _log_fields(event, context)
    try:
        response = _get_service().handle(event)
    except StateServiceError as error:
        _log(
            "ERROR",
            "state lambda operation failed",
            **fields,
            error_code=error.code,
        )
        raise
    except Exception:
        _log(
            "ERROR",
            "state lambda operation failed",
            **fields,
            error_code="ERR_INTERNAL",
        )
        raise

    _log(
        "INFO",
        "state lambda operation completed",
        **fields,
        decision=response["decision"],
        status=response["status"],
    )
    return response


def _get_service() -> StateService:
    global _service
    if _service is None:
        bucket = os.getenv("IDEMPOTENCY_BUCKET_NAME", "").strip()
        if not bucket:
            raise StateServiceError(
                "ERR_CONFIGURATION", "IDEMPOTENCY_BUCKET_NAME is required"
            )
        client = boto3.client("s3")
        _service = StateService(S3RunStateStore(client, bucket))
    return _service


def _log_fields(event: Any, context: Any) -> dict[str, Any]:
    safe_event = event if isinstance(event, dict) else {}
    return {
        "aws_request_id": getattr(context, "aws_request_id", ""),
        "action": safe_event.get("action", ""),
        "tenant_id": safe_event.get("tenant_id", ""),
        "run_id": safe_event.get("run_id", ""),
        "correlation_id": safe_event.get("correlation_id", ""),
    }


def _log(level: str, message: str, **fields: Any) -> None:
    print(
        json.dumps(
            {"level": level, "message": message, **fields},
            separators=(",", ":"),
            default=str,
        ),
        flush=True,
    )
