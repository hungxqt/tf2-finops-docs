"""
boundary.py — Hard boundary enforcement.

Hai lớp bảo vệ theo 03_security_design.md §2.1 và deployment-contract.md §CDO Containment:
  1. prod/prod-core/prod-payments → NEVER apply, NEVER stop → force dry-run
  2. data_confidence = LOW (CUR delay) → force dry-run

Đây là lớp QUAN TRỌNG NHẤT. Phải chạy TRƯỚC mọi logic khác.
IAM policy là lớp thứ 2 ở infra level — code này là lớp thứ 1 ở application level.
"""
from __future__ import annotations

import logging

from src.model.input import (
    ContainmentInput,
    PROD_ENVS,
    MODE_DRY_RUN,
    MODE_TAG,
    DATA_CONFIDENCE_LOW,
    APPROVAL_DENIED,
)

logger = logging.getLogger(__name__)


class BoundaryViolation(Exception):
    """Raised khi input vi phạm hard boundary."""
    pass


def enforce_boundaries(inp: ContainmentInput) -> str:
    """
    Kiểm tra tất cả hard boundaries và trả về execution_mode đã được enforce.

    Không raise exception — luôn trả về mode an toàn nhất có thể.
    Nếu bị override, log warning rõ ràng để audit.

    Returns:
        execution_mode đã được enforce (có thể khác inp.execution_mode)
    """
    original_mode = inp.execution_mode
    enforced_mode = original_mode

    # --- Boundary 1: Approval denied → không làm gì ---
    if inp.approval_status == APPROVAL_DENIED:
        logger.warning(
            "containment denied by approval_status",
            extra={
                "anomaly_id": inp.anomaly_id,
                "account_id": inp.account_id,
                "approval_status": inp.approval_status,
            },
        )
        # Return special sentinel — executor sẽ tạo denied_action_record
        return "denied"

    # --- Boundary 2: Production environment → force dry-run ---
    if inp.environment in PROD_ENVS:
        if original_mode not in {MODE_DRY_RUN, MODE_TAG, "suggest"}:
            enforced_mode = MODE_DRY_RUN
            logger.warning(
                "prod boundary: execution_mode overridden to dry-run",
                extra={
                    "anomaly_id": inp.anomaly_id,
                    "account_id": inp.account_id,
                    "environment": inp.environment,
                    "original_mode": original_mode,
                    "enforced_mode": enforced_mode,
                },
            )
        # Prod cho phép tag và suggest, nhưng KHÔNG cho apply
        if original_mode == "apply":
            enforced_mode = MODE_DRY_RUN

    # --- Boundary 3: data_confidence = LOW → force dry-run ---
    # Khi CUR delay > 36h, AI Engine trả LOW confidence
    # CDO phải override sang dry-run để không act trên data không đủ tin cậy
    if inp.data_confidence == DATA_CONFIDENCE_LOW:
        if enforced_mode not in {MODE_DRY_RUN}:
            enforced_mode = MODE_DRY_RUN
            logger.warning(
                "low data_confidence: execution_mode overridden to dry-run",
                extra={
                    "anomaly_id": inp.anomaly_id,
                    "account_id": inp.account_id,
                    "data_confidence": inp.data_confidence,
                    "original_mode": original_mode,
                    "enforced_mode": enforced_mode,
                },
            )

    if enforced_mode != original_mode:
        logger.info(
            "boundary enforcement summary",
            extra={
                "anomaly_id": inp.anomaly_id,
                "original_mode": original_mode,
                "enforced_mode": enforced_mode,
                "environment": inp.environment,
                "data_confidence": inp.data_confidence,
            },
        )

    return enforced_mode


def is_prod_environment(environment: str) -> bool:
    """Helper để check nhanh prod environment."""
    return environment in PROD_ENVS
