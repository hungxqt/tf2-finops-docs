"""
suggester.py — Tạo suggestion record gửi Engineering/Finance review.

Suggest action không tác động AWS resource — chỉ tạo record.
Record này được Alert Lambda dùng để gửi Slack/Email tới đúng channel.
Theo 02_infra_design.md §1.4: tách routing Finance vs Engineering.
"""
from __future__ import annotations

import logging

from src.model.input import ContainmentInput
from src.model.output import SuggestionRecord

logger = logging.getLogger(__name__)

# Route targets
ROUTE_FINANCE = "finance"
ROUTE_ENGINEERING = "engineering"

# Anomaly types routing sang Engineering (cần technical action)
ENGINEERING_ANOMALY_TYPES = {
    "runaway_usage",
    "idle_resource",
}

# Anomaly types routing sang Finance (cost visibility)
FINANCE_ANOMALY_TYPES = {
    "untagged_spend",
    "sudden_spike",
    "gradual_drift",
}


def execute_suggest(inp: ContainmentInput) -> SuggestionRecord:
    """
    Tạo suggestion record với route target đúng.

    Route logic:
    - runaway_usage, idle_resource → Engineering (cần tắt/scale down)
    - untagged_spend, sudden_spike, gradual_drift → Finance (cần review cost)
    - Unknown → Engineering (safer default)

    Args:
        inp: ContainmentInput

    Returns:
        SuggestionRecord — sẽ được Alert Lambda pick up để notify
    """
    route_target = _determine_route(inp.anomaly_type, inp.environment)

    record = SuggestionRecord(
        anomaly_id=inp.anomaly_id,
        resource_id=inp.resource_id,
        recommended_action=inp.recommended_containment_mode,
        explanation=inp.explanation,
        route_target=route_target,
        approval_required=_requires_approval(inp.environment, inp.recommended_containment_mode),
    )

    logger.info(
        "suggestion record created",
        extra={
            "anomaly_id": inp.anomaly_id,
            "resource_id": inp.resource_id,
            "route_target": route_target,
            "anomaly_type": inp.anomaly_type,
            "environment": inp.environment,
        },
    )

    return record


def _determine_route(anomaly_type: str, environment: str) -> str:
    """
    Quyết định route target dựa trên anomaly type và environment.

    Engineering nhận alert khi cần technical remediation.
    Finance nhận alert khi cần cost visibility / budget review.
    """
    if anomaly_type in ENGINEERING_ANOMALY_TYPES:
        return ROUTE_ENGINEERING
    if anomaly_type in FINANCE_ANOMALY_TYPES:
        return ROUTE_FINANCE
    # Default: Engineering vì họ có thể escalate sang Finance nếu cần
    return ROUTE_ENGINEERING


def _requires_approval(environment: str, containment_mode: str) -> bool:
    """
    Approval có bắt buộc không?

    - Prod luôn cần approval cho bất kỳ action nào
    - Non-prod chỉ cần approval cho auto-shutdown
    """
    from src.model.input import PROD_ENVS
    if environment in PROD_ENVS:
        return True
    if containment_mode == "auto-shutdown":
        return True
    return False
