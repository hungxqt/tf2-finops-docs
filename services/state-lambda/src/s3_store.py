from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from service import (
    DuplicateAttempt,
    RunStateRecord,
    StateServiceError,
    Status,
    _format_timestamp,
)


CONDITIONAL_ERROR_CODES = {
    "PreconditionFailed",
    "ConditionalRequestConflict",
    "412",
}
NOT_FOUND_ERROR_CODES = {"NoSuchKey", "NotFound", "404"}


class S3RunStateStore:
    def __init__(self, client: Any, bucket: str) -> None:
        if client is None:
            raise ValueError("s3 client is required")
        self._bucket = bucket.strip()
        if not self._bucket:
            raise ValueError("s3 bucket name is required")
        self._client = client

    def put_if_absent(
        self, record: RunStateRecord
    ) -> tuple[bool, RunStateRecord | None]:
        try:
            self._put(record, if_none_match="*")
            return True, None
        except ClientError as error:
            if not _is_conditional_error(error):
                raise _store_error("create idempotency object", error) from error
        except BotoCoreError as error:
            raise _store_error("create idempotency object", error) from error

        existing, etag = self._get_with_etag(record.object_key)
        if _parse_timestamp(existing.expires_at) <= datetime.now(timezone.utc):
            try:
                self._put(record, if_match=etag)
                return True, None
            except ClientError as error:
                if not _is_conditional_error(error):
                    raise _store_error(
                        "replace expired idempotency object", error
                    ) from error
            except BotoCoreError as error:
                raise _store_error(
                    "replace expired idempotency object", error
                ) from error
            latest, _ = self._get_with_etag(record.object_key)
            return False, latest
        return False, existing

    def get(self, object_key: str) -> RunStateRecord:
        record, _ = self._get_with_etag(object_key)
        return record

    def update_status(
        self,
        object_key: str,
        run_id: str,
        status: str,
        failure_code: str,
        failure_reason: str,
        updated_at: datetime,
    ) -> RunStateRecord:
        record, etag = self._get_with_etag(object_key)
        if record.run_id != run_id:
            raise StateServiceError(
                "ERR_RUN_ID_MISMATCH",
                f"run state belongs to run_id {record.run_id!r}, not {run_id!r}",
            )
        updated = replace(
            record,
            status=str(status),
            failure_code=failure_code,
            failure_reason=failure_reason,
            updated_at=_format_timestamp(updated_at),
        )
        self._put_with_concurrency(updated, etag, "update idempotency object")
        return updated

    def redrive_failed(
        self,
        object_key: str,
        previous_run_id: str,
        replacement: RunStateRecord,
    ) -> RunStateRecord:
        existing, etag = self._get_with_etag(object_key)
        if existing.run_id != previous_run_id:
            raise StateServiceError(
                "ERR_RUN_ID_MISMATCH",
                f"run state belongs to run_id {existing.run_id!r}, not {previous_run_id!r}",
            )
        if existing.status not in (Status.FAILED, Status.FAILED_CONTRACT_CHECK):
            raise StateServiceError(
                "ERR_INVALID_STATE",
                f"run cannot be redriven from status {existing.status!r}",
            )
        updated = replace(
            replacement,
            previous_run_id=existing.run_id,
            redrive_count=existing.redrive_count + 1,
            duplicate_attempt_count=existing.duplicate_attempt_count,
            last_duplicate_attempt=existing.last_duplicate_attempt,
        )
        self._put_with_concurrency(updated, etag, "redrive idempotency object")
        return updated

    def record_duplicate(
        self, object_key: str, attempted_run_id: str, attempted_at: datetime
    ) -> RunStateRecord:
        record, etag = self._get_with_etag(object_key)
        updated = replace(
            record,
            duplicate_attempt_count=record.duplicate_attempt_count + 1,
            last_duplicate_attempt=DuplicateAttempt(
                attempted_run_id=attempted_run_id,
                attempted_at=_format_timestamp(attempted_at),
            ),
            updated_at=_format_timestamp(attempted_at),
        )
        self._put_with_concurrency(updated, etag, "record duplicate attempt")
        return updated

    def count_ad_hoc(self, tenant_id: str, billing_period_date: str) -> int:
        prefix = f"idempotency/ad-hoc/{tenant_id}/{billing_period_date}/"
        try:
            response = self._client.list_objects_v2(
                Bucket=self._bucket,
                Prefix=prefix,
                MaxKeys=6,
            )
        except (BotoCoreError, ClientError) as error:
            raise _store_error("list ad-hoc idempotency objects", error) from error
        return len(response.get("Contents", []))

    def _get_with_etag(self, object_key: str) -> tuple[RunStateRecord, str]:
        try:
            response = self._client.get_object(
                Bucket=self._bucket, Key=object_key
            )
            body = response["Body"].read()
        except ClientError as error:
            if _error_code(error) in NOT_FOUND_ERROR_CODES:
                raise StateServiceError(
                    "ERR_RUN_NOT_FOUND",
                    f"run-state object {object_key!r} does not exist",
                ) from error
            raise _store_error("get idempotency object", error) from error
        except (BotoCoreError, KeyError, OSError) as error:
            raise _store_error("get idempotency object", error) from error

        try:
            value = json.loads(body)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StateServiceError(
                "ERR_STORE_RECORD_INVALID",
                f"run-state object {object_key!r} is not valid JSON",
            ) from error
        if not isinstance(value, dict):
            raise StateServiceError(
                "ERR_STORE_RECORD_INVALID",
                f"run-state object {object_key!r} must contain a JSON object",
            )
        etag = response.get("ETag")
        if not isinstance(etag, str) or not etag:
            raise StateServiceError(
                "ERR_STORE_RECORD_INVALID",
                f"run-state object {object_key!r} has no ETag",
            )
        return RunStateRecord.from_dict(value), etag

    def _put(
        self,
        record: RunStateRecord,
        *,
        if_none_match: str | None = None,
        if_match: str | None = None,
    ) -> None:
        request: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": record.object_key,
            "Body": json.dumps(
                record.to_dict(), separators=(",", ":"), sort_keys=True
            ).encode("utf-8"),
            "ContentType": "application/json",
        }
        if if_none_match is not None:
            request["IfNoneMatch"] = if_none_match
        if if_match is not None:
            request["IfMatch"] = if_match
        self._client.put_object(**request)

    def _put_with_concurrency(
        self, record: RunStateRecord, etag: str, operation: str
    ) -> None:
        try:
            self._put(record, if_match=etag)
        except ClientError as error:
            if _is_conditional_error(error):
                raise StateServiceError(
                    "ERR_CONCURRENT_UPDATE",
                    "run-state object changed during update; retry from the latest state",
                ) from error
            raise _store_error(operation, error) from error
        except BotoCoreError as error:
            raise _store_error(operation, error) from error


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise StateServiceError(
            "ERR_STORE_RECORD_INVALID", "stored expires_at is invalid"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))


def _is_conditional_error(error: ClientError) -> bool:
    return _error_code(error) in CONDITIONAL_ERROR_CODES


def _store_error(operation: str, error: Exception) -> StateServiceError:
    return StateServiceError("ERR_STORE", f"{operation} failed: {type(error).__name__}")
