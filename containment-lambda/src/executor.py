"""
executor.py — Orchestrator chính của Containment Lambda.

Kết nối tất cả modules lại theo đúng thứ tự:
  1. Validate input
  2. Enforce boundaries (prod guard + confidence guard)
  3. AssumeRole vào member account
  4. Đọc before_state
  5. Cache rollback payload vào DynamoDB (trước khi thực thi)
  6. Ghi pre-action audit vào S3 Object Lock
  7. Thực thi action theo execution_mode
  8. Ghi post-action audit
  9. Cập nhật DynamoDB Dashboard Cache
  10. Return ContainmentOutput

Sequence theo 02_infra_design.md §1.5:
  SF → Cont: Execute proposed containment actions
  Cont → S3: Write execution audit record (Object Lock)
  Cont → SF: Execution outcome
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import boto3

from src.model.input import (
    ContainmentInput,
    MODE_DRY_RUN,
    MODE_TAG,
    MODE_APPLY,
    APPROVAL_DENIED,
)
from src.model.output import (
    ContainmentOutput,
    AuditRecord,
    DeniedActionRecord,
)
from src.policy.boundary import enforce_boundaries
from src.aws.session import load, assume_containment_role
from src.aws.resource_reader import read_before_state, compute_proposed_after_state
from src.actions.dry_run import execute_dry_run
from src.actions.tagger import execute_tag, compute_rollback_path_for_tag
from src.actions.suggester import execute_suggest
from src.actions.stopper import execute_apply
from src.audit.s3_audit import write_pre_action_audit, update_post_action_audit
from src.audit.dynamo_cache import update_dashboard_cache, cache_rollback_payload

logger = logging.getLogger(__name__)


class ContainmentExecutor:
    """
    Orchestrator thực thi toàn bộ containment flow.
    """

    def __init__(self, session: boto3.Session) -> None:
        self._session = session

    def run(self, inp: ContainmentInput) -> ContainmentOutput:
        """
        Thực thi containment theo đúng thứ tự an toàn.

        Args:
            inp: ContainmentInput từ Step Functions

        Returns:
            ContainmentOutput trả về Step Functions
        """
        logger.info(
            "containment executor started",
            extra={
                "run_id": inp.run_id,
                "anomaly_id": inp.anomaly_id,
                "environment": inp.environment,
                "execution_mode": inp.execution_mode,
                "approval_status": inp.approval_status,
                "data_confidence": inp.data_confidence,
            },
        )

        # --- Step 1: Enforce boundaries ---
        # Đây là bước QUAN TRỌNG NHẤT, chạy trước mọi thứ
        enforced_mode = enforce_boundaries(inp)

        # Nếu bị denied → tạo record và return ngay
        if enforced_mode == "denied":
            return self._handle_denied(inp)

        # --- Step 2: AssumeRole vào member account ---
        try:
            member_session = assume_containment_role(
                session=self._session,
                account_id=inp.account_id,
                role_name=inp.containment_role_name,
                anomaly_id=inp.anomaly_id,
                external_id=inp.external_id,
            )
        except RuntimeError as exc:
            logger.error(
                "assume role failed",
                extra={"anomaly_id": inp.anomaly_id, "error": str(exc)},
            )
            return ContainmentOutput(
                run_id=inp.run_id,
                anomaly_id=inp.anomaly_id,
                correlation_id=inp.correlation_id,
                status="failed",
                execution_mode_applied=enforced_mode,
                errors=[str(exc)],
            )

        # --- Step 3: Đọc before_state ---
        before_state = read_before_state(
            session=member_session,
            resource_id=inp.resource_id,
            anomaly_type=inp.anomaly_type,
        )

        # --- Step 4: Tính proposed_after_state và rollback_path ---
        containment_tags = None
        if enforced_mode == MODE_TAG:
            containment_tags = {
                "FinOpsWatch": "ReviewRequired",
                "FinOpsAnomalyId": inp.anomaly_id,
            }

        proposed_after_state = compute_proposed_after_state(
            before_state=before_state,
            execution_mode=enforced_mode,
            containment_tags=containment_tags,
        )

        rollback_path = _compute_rollback_path(enforced_mode, inp, containment_tags)

        # --- Step 5: Cache rollback payload TRƯỚC khi thực thi ---
        # Đảm bảo rollback luôn khả dụng dù action sau này fail
        cache_rollback_payload(
            session=self._session,
            rollback_cache_table=inp.audit_config.rollback_cache_table,
            anomaly_id=inp.anomaly_id,
            correlation_id=inp.correlation_id,
            rollback_payload=inp.rollback_payload.to_dict(),
        )

        # --- Step 6: Build và ghi pre-action audit record ---
        audit_record = AuditRecord(
            actor="cdo-platform-containment-lambda",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            correlation_id=inp.correlation_id,
            anomaly_id=inp.anomaly_id,
            run_id=inp.run_id,
            resource_owner=inp.resource_owner,
            resource_id=inp.resource_id,
            account_id=inp.account_id,
            environment=inp.environment,
            execution_mode=enforced_mode,
            original_execution_mode=inp.execution_mode,
            approval_status=inp.approval_status,
            data_confidence=inp.data_confidence,
            before_state=before_state,
            proposed_after_state=proposed_after_state,
            rollback_path=rollback_path,
        )

        audit_id, audit_s3_uri = write_pre_action_audit(
            session=self._session,
            audit_record=audit_record,
            audit_bucket=inp.audit_config.audit_bucket,
            audit_prefix=inp.audit_config.audit_prefix,
        )

        # --- Step 7: Thực thi action theo enforced_mode ---
        action_result: dict[str, Any] = {}
        status = "completed"
        errors: list[str] = []

        try:
            if enforced_mode == MODE_DRY_RUN:
                result = execute_dry_run(inp)
                action_result = result.to_dict()
                status = "dry-run"

            elif enforced_mode == MODE_TAG:
                result = execute_tag(inp, member_session)
                action_result = result.to_dict()

            elif enforced_mode == "suggest":
                result = execute_suggest(inp)
                action_result = result.to_dict()
                status = "suggested"

            elif enforced_mode == MODE_APPLY:
                result = execute_apply(inp, member_session)
                action_result = result.to_dict()

            else:
                raise ValueError(f"Unknown execution_mode: {enforced_mode}")

        except Exception as exc:
            logger.error(
                "action execution failed",
                extra={
                    "anomaly_id": inp.anomaly_id,
                    "execution_mode": enforced_mode,
                    "error": str(exc),
                },
            )
            status = "failed"
            errors.append(str(exc))
            action_result = {"error": str(exc)}

        # --- Step 8: Ghi post-action audit ---
        update_post_action_audit(
            session=self._session,
            audit_bucket=inp.audit_config.audit_bucket,
            audit_prefix=inp.audit_config.audit_prefix,
            audit_id=audit_id,
            action_result=action_result,
            rollback_status="pending" if status in ("completed", "dry-run") else "not_required",
        )

        # --- Step 9: Cập nhật DynamoDB Dashboard Cache (best-effort) ---
        update_dashboard_cache(
            session=self._session,
            table_name=inp.audit_config.dashboard_table,
            anomaly_id=inp.anomaly_id,
            run_id=inp.run_id,
            correlation_id=inp.correlation_id,
            resource_id=inp.resource_id,
            account_id=inp.account_id,
            environment=inp.environment,
            execution_mode_applied=enforced_mode,
            status=status,
            audit_record_id=audit_id,
            audit_record_s3_uri=audit_s3_uri,
            severity=inp.severity,
            anomaly_type=inp.anomaly_type,
            explanation=inp.explanation,
        )

        logger.info(
            "containment executor completed",
            extra={
                "run_id": inp.run_id,
                "anomaly_id": inp.anomaly_id,
                "status": status,
                "execution_mode_applied": enforced_mode,
                "audit_id": audit_id,
            },
        )

        # --- Step 10: Return output cho Step Functions ---
        output = ContainmentOutput(
            run_id=inp.run_id,
            anomaly_id=inp.anomaly_id,
            correlation_id=inp.correlation_id,
            status=status,
            execution_mode_applied=enforced_mode,
            audit_record_id=audit_id,
            audit_record_s3_uri=audit_s3_uri,
            before_state=before_state,
            proposed_after_state=proposed_after_state,
            rollback_path=rollback_path,
            errors=errors,
        )

        # Gắn action result vào đúng field
        if enforced_mode == MODE_DRY_RUN:
            output.dry_run_result = action_result
        elif enforced_mode == MODE_TAG:
            output.tagging_result = action_result
        elif enforced_mode == "suggest":
            output.suggestion_record = action_result
        elif enforced_mode == MODE_APPLY:
            output.apply_result = action_result

        return output

    def _handle_denied(self, inp: ContainmentInput) -> ContainmentOutput:
        """Xử lý case action bị denied — tạo record và return."""
        denied_record = DeniedActionRecord(
            reason="approval_denied",
            original_execution_mode=inp.execution_mode,
            original_environment=inp.environment,
            denial_note=f"approval_status={inp.approval_status}",
        )

        logger.info(
            "containment denied",
            extra={
                "anomaly_id": inp.anomaly_id,
                "approval_status": inp.approval_status,
            },
        )

        return ContainmentOutput(
            run_id=inp.run_id,
            anomaly_id=inp.anomaly_id,
            correlation_id=inp.correlation_id,
            status="denied",
            execution_mode_applied="denied",
            denied_action_record=denied_record.to_dict(),
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _compute_rollback_path(
    execution_mode: str,
    inp: ContainmentInput,
    containment_tags: dict[str, str] | None,
) -> dict[str, Any]:
    """Tính rollback_path dựa trên execution_mode."""
    if execution_mode == MODE_DRY_RUN:
        return {"action": "none", "note": "dry-run: nothing to rollback"}

    if execution_mode == MODE_TAG and containment_tags:
        from src.actions.tagger import compute_rollback_path_for_tag
        return compute_rollback_path_for_tag(containment_tags)

    if execution_mode == MODE_APPLY:
        # Rollback path = boto3_equivalent từ AI Engine /v1/decide
        return inp.rollback_payload.to_dict()

    return {}
