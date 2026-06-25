"""
puller.py — Orchestrator chính: assume role, pull CUR + CE + CloudTrail.
v2.0: Thêm Signal 2 (CloudTrail) theo Telemetry Contract v2.0.

Dual-run window: Hỗ trợ song song v1 (CUR + CE) và v2 (+ CloudTrail) trong 30 ngày
kể từ 2026-06-25. Kiểm tra input.api_version để quyết định.

Note: EKS metrics (Signal 3) không dùng — runtime là Lambda container image thay vì EKS.
"""
from __future__ import annotations

import logging
import os

import boto3

from src.model import (
    AccountConfig,
    AccountStatus,
    IngestionInput,
    IngestionOutput,
    PullError,
)
from src.storage.s3writer import S3Writer
from src.puller.costexplorer import pull_cost_explorer
from src.puller.cur import pull_cur
from src.puller.cloudtrail import pull_cloudtrail_events


class Puller:
    """Orchestrator thực thi toàn bộ ingestion v2.0:
    - Signal 1 (v1 + v2): CUR micro-batch Parquet + Cost Explorer daily
    - Signal 2 (v2 NEW): CloudTrail real-time events → rút ngắn MTTD < 15 phút

    Dual-run window: nếu input.api_version == "v1", chỉ chạy Signal 1 (backward compat).
    """

    def __init__(self, session: boto3.Session, logger: logging.Logger) -> None:
        self._session = session
        self._writer = S3Writer(session)
        self._logger = logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, input: IngestionInput) -> IngestionOutput:
        """Thực thi toàn bộ ingestion theo api_version."""
        out = IngestionOutput(run_id=input.run_id, api_version=input.api_version)
        total_accounts = len(input.accounts)
        success_count = 0

        for account in input.accounts:
            source_uri_count_before = len(out.source_uris)
            status = AccountStatus(
                account_id=account.account_id,
                cost_period_start=input.cost_period_start,
                cost_period_end=input.cost_period_end,
            )

            self._logger.info(
                "processing account",
                extra={
                    "account_id": account.account_id,
                    "run_id": input.run_id,
                    "api_version": input.api_version,
                },
            )

            # --- Assume role vào account member ---
            try:
                role_session = self._assume_role(account)
            except Exception as exc:
                err_code = _extract_code(exc)
                status.cur_status = "error"
                status.ce_status = "error"
                status.cloudtrail_status = "error"
                out.errors.append(PullError(
                    account_id=account.account_id,
                    source="AssumeRole",
                    code=err_code,
                    message=str(exc),
                ))
                self._logger.error(
                    "assume role failed",
                    extra={"account_id": account.account_id, "error": str(exc)},
                )
                out.account_statuses.append(status)
                continue

            # -------------------------------------------------------
            # Signal 1a: Pull CUR (v1 + v2)
            # -------------------------------------------------------
            cur_ok = True
            for src in input.cur_sources:
                try:
                    refs = pull_cur(role_session, self._writer, src, input)
                    for ref in refs:
                        ref.account_id = account.account_id
                        out.cur_refs.append(ref)
                        out.source_uris.append(ref.s3_uri)
                except Exception as exc:
                    err_code = _extract_code(exc)
                    status.cur_status = _status_from_error("CUR", err_code)
                    out.errors.append(PullError(
                        account_id=account.account_id,
                        source="CUR",
                        code=err_code,
                        message=str(exc),
                    ))
                    self._logger.error(
                        "CUR pull failed",
                        extra={
                            "account_id": account.account_id,
                            "source_bucket": src.bucket,
                            "error": str(exc),
                        },
                    )
                    cur_ok = False

            if cur_ok and not status.cur_status:
                status.cur_status = "ok"

            # -------------------------------------------------------
            # Signal 1b: Pull Cost Explorer (v1 + v2)
            # -------------------------------------------------------
            try:
                ce_data = pull_cost_explorer(role_session, account, input, self._logger)
                ref = self._writer.write_ce_json(
                    bucket=input.raw_bucket,
                    raw_prefix=input.raw_prefix,
                    run_id=input.run_id,
                    account_id=account.account_id,
                    kms_key_arn=input.kms_key_arn,
                    data=ce_data,
                )
                status.ce_status = "ok"
                out.ce_json_refs.append(ref)
                out.source_uris.append(ref.s3_uri)
            except Exception as exc:
                err_code = _extract_code(exc)
                status.ce_status = _status_from_error("CostExplorer", err_code)
                out.errors.append(PullError(
                    account_id=account.account_id,
                    source="CostExplorer",
                    code=err_code,
                    message=str(exc),
                ))
                self._logger.error(
                    "CE pull failed",
                    extra={"account_id": account.account_id, "error": str(exc)},
                )

            # -------------------------------------------------------
            # Signal 2: CloudTrail real-time events (v2.0 NEW)
            # Chỉ chạy khi api_version == "v2" và enable_cloudtrail_streaming = True
            # -------------------------------------------------------
            if input.api_version == "v2" and input.enable_cloudtrail_streaming:
                sqs_queue_url = _get_cloudtrail_sqs_url(account.account_id)
                if sqs_queue_url:
                    try:
                        ct_refs = pull_cloudtrail_events(
                            session=role_session,
                            writer=self._writer,
                            input=input,
                            logger=self._logger,
                            sqs_queue_url=sqs_queue_url,
                        )
                        for ref in ct_refs:
                            ref.account_id = account.account_id
                            out.cloudtrail_refs.append(ref)
                            out.source_uris.append(ref.s3_uri)
                        status.cloudtrail_status = "ok"
                    except Exception as exc:
                        err_code = _extract_code(exc)
                        status.cloudtrail_status = "error"
                        out.errors.append(PullError(
                            account_id=account.account_id,
                            source="CloudTrail",
                            code=err_code,
                            message=str(exc),
                        ))
                        self._logger.error(
                            "CloudTrail pull failed — non-blocking, continuing",
                            extra={"account_id": account.account_id, "error": str(exc)},
                        )
                        # CloudTrail failure không block ingestion — fallback sang CUR-only MTTD
                else:
                    status.cloudtrail_status = "skipped"
                    self._logger.info(
                        "cloudtrail SQS URL not configured — skipping Signal 2",
                        extra={"account_id": account.account_id},
                    )
            else:
                status.cloudtrail_status = "skipped"

            # -------------------------------------------------------
            # Tổng hợp account status
            # -------------------------------------------------------
            if len(out.source_uris) > source_uri_count_before:
                success_count += 1

            out.account_statuses.append(status)

        # --- Xác định overall status ---
        if total_accounts == 0:
            out.status = "failed"
            out.errors.append(PullError(
                account_id="",
                source="Input",
                code="UNKNOWN",
                message="no accounts configured for ingestion",
            ))
            raise RuntimeError("no accounts configured for ingestion", out)
        if success_count == total_accounts and not out.errors:
            out.status = "completed"
        elif success_count == 0:
            out.status = "failed"
            raise RuntimeError(
                f"all {total_accounts} accounts failed ingestion", out
            )
        else:
            out.status = "partial"

        self._logger.info(
            "ingestion run complete",
            extra={
                "run_id": input.run_id,
                "api_version": input.api_version,
                "status": out.status,
                "success": success_count,
                "total": total_accounts,
                "cur_refs": len(out.cur_refs),
                "ce_refs": len(out.ce_json_refs),
                "cloudtrail_refs": len(out.cloudtrail_refs),
                "errors": len(out.errors),
            },
        )

        return out

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _assume_role(self, account: AccountConfig) -> boto3.Session:
        """Assume role vào account member, trả về boto3 Session mới."""
        sts_client = self._session.client("sts")

        kwargs: dict = {
            "RoleArn": account.role_arn,
            "RoleSessionName": "finops-ingestion-puller",
        }
        if account.external_id:
            kwargs["ExternalId"] = account.external_id

        try:
            resp = sts_client.assume_role(**kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"ASSUME_ROLE_FAILED account={account.account_id}: {exc}"
            ) from exc

        creds = resp["Credentials"]
        return boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name="ap-southeast-1",
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _extract_code(exc: Exception) -> str:
    """Lấy error code từ message prefix (CE_THROTTLE, CUR_DELAY, ...)."""
    msg = str(exc)
    for code in (
        "ASSUME_ROLE_FAILED",
        "CUR_DELAY",
        "CE_THROTTLE",
        "CLOUDTRAIL_ERROR",
    ):
        if msg.startswith(code):
            return code
    return "UNKNOWN"


def _status_from_error(source: str, code: str) -> str:
    if source == "CUR" and code == "CUR_DELAY":
        return "delayed"
    if source == "CostExplorer" and code == "CE_THROTTLE":
        return "throttled"
    return "error"


def _get_cloudtrail_sqs_url(account_id: str) -> str:
    """
    Lấy SQS queue URL cho CloudTrail events của account.
    Đọc từ environment variable theo convention:
      CLOUDTRAIL_SQS_URL_{account_id} hoặc CLOUDTRAIL_SQS_URL (shared queue)
    """
    specific = os.environ.get(f"CLOUDTRAIL_SQS_URL_{account_id}", "")
    if specific:
        return specific
    return os.environ.get("CLOUDTRAIL_SQS_URL", "")
