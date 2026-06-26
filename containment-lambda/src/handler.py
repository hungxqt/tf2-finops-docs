"""
handler.py — AWS Lambda entrypoint.

AWS gọi hàm này khi Step Functions invoke Containment Lambda.
Nhiệm vụ: parse event → chạy executor → return output dict.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src.aws.session import load
from src.executor import ContainmentExecutor
from src.model.input import ContainmentInput
from src.model.output import ContainmentOutput


def _make_logger() -> logging.Logger:
    logger = logging.getLogger("containment-lambda")
    logger.setLevel(logging.INFO)
    return logger


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    AWS Lambda entrypoint — dipanggil oleh Step Functions.

    Args:
        event: JSON payload dari Step Functions (berisi AI decision + context)
        context: Lambda runtime context (timeout, request ID, dll)

    Returns:
        ContainmentOutput sebagai dict untuk Step Functions
    """
    logger = _make_logger()

    # Parse input
    try:
        if isinstance(event, str):
            event = json.loads(event)
        inp = ContainmentInput.from_dict(event)
    except (KeyError, ValueError, TypeError) as exc:
        logger.error("invalid input payload", extra={"error": str(exc)})
        raise

    logger.info(
        "containment lambda started",
        extra={
            "run_id": inp.run_id,
            "anomaly_id": inp.anomaly_id,
            "environment": inp.environment,
            "execution_mode": inp.execution_mode,
            "approval_status": inp.approval_status,
        },
    )

    # Load AWS session (CDO management account)
    session = load()

    # Run executor
    executor = ContainmentExecutor(session)
    output: ContainmentOutput = executor.run(inp)

    logger.info(
        "containment lambda completed",
        extra={
            "run_id": inp.run_id,
            "anomaly_id": inp.anomaly_id,
            "status": output.status,
            "execution_mode_applied": output.execution_mode_applied,
            "audit_record_id": output.audit_record_id,
        },
    )

    return output.to_dict()
