"""
dry_run.py — Simulate containment action, không gọi bất kỳ AWS API nào.

Dry-run vẫn ghi audit record đầy đủ vì Finance cần thấy
"platform would have done X" ngay cả khi không thực sự làm.
Theo ADR-005: "dry-run-first containment guardrail"
"""
from __future__ import annotations

import logging
from typing import Any

from src.model.input import ContainmentInput
from src.model.output import DryRunResult

logger = logging.getLogger(__name__)


def execute_dry_run(inp: ContainmentInput) -> DryRunResult:
    """
    Simulate action — không gọi AWS API, chỉ mô tả sẽ làm gì.

    Args:
        inp: ContainmentInput đầy đủ

    Returns:
        DryRunResult mô tả action sẽ được thực hiện nếu là apply
    """
    applied = inp.applied_payload

    logger.info(
        "dry-run executed",
        extra={
            "anomaly_id": inp.anomaly_id,
            "resource_id": inp.resource_id,
            "would_execute": f"{applied.service}.{applied.method}",
            "environment": inp.environment,
        },
    )

    return DryRunResult(
        would_execute_service=applied.service,
        would_execute_method=applied.method,
        would_execute_parameters=applied.parameters,
        simulation_note=(
            f"dry-run: no AWS API call made. "
            f"Would execute {applied.service}.{applied.method} "
            f"on {inp.resource_id} in {inp.environment}."
        ),
    )
