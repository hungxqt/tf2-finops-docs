from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Callable, Protocol


DEFAULT_LOCK_TTL_SECONDS = 86_400
DEFAULT_DUPLICATE_RUN_POLICY = "reject_existing_run"
MAX_AD_HOC_RUNS_PER_DAY = 5

ACCOUNT_ID_PATTERN = re.compile(r"^[0-9]{12}$")
BATCH_TYPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
CONTRACT_VERSION_PATTERN = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+$")


class Action(StrEnum):
    ACQUIRE_RUN = "ACQUIRE_RUN"
    GET_RUN = "GET_RUN"
    REDRIVE_RUN = "REDRIVE_RUN"
    COMPLETE_RUN = "COMPLETE_RUN"
    FAIL_RUN = "FAIL_RUN"
    FAIL_CONTRACT_CHECK = "FAIL_CONTRACT_CHECK"


class Status(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    FAILED_CONTRACT_CHECK = "FAILED_CONTRACT_CHECK"
    DUPLICATE_REJECTED = "DUPLICATE_REJECTED"


class Decision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"


class StateServiceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(slots=True)
class StateEvent:
    action: str
    tenant_id: str
    billing_period_date: str
    batch_type: str
    run_id: str
    correlation_id: str
    payload_sha256: str
    account_id: str = ""
    previous_run_id: str = ""
    contract_version: str = ""
    is_ad_hoc: bool = False
    lock_ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS
    duplicate_run_policy: str = DEFAULT_DUPLICATE_RUN_POLICY
    failure_code: str = ""
    failure_reason: str = ""
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DuplicateAttempt:
    attempted_run_id: str
    attempted_at: str


@dataclass(slots=True)
class RunStateRecord:
    idempotency_key: str
    object_key: str
    tenant_id: str
    billing_period_date: str
    batch_type: str
    run_id: str
    correlation_id: str
    payload_sha256: str
    status: str
    is_ad_hoc: bool
    created_at: str
    updated_at: str
    expires_at: str
    account_id: str = ""
    previous_run_id: str = ""
    contract_version: str = ""
    failure_code: str = ""
    failure_reason: str = ""
    redrive_count: int = 0
    duplicate_attempt_count: int = 0
    last_duplicate_attempt: DuplicateAttempt | None = None
    tags: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RunStateRecord:
        data = dict(value)
        attempt = data.get("last_duplicate_attempt")
        if isinstance(attempt, dict):
            data["last_duplicate_attempt"] = DuplicateAttempt(**attempt)
        try:
            return cls(**data)
        except (TypeError, ValueError) as error:
            raise StateServiceError(
                "ERR_STORE_RECORD_INVALID", "stored run-state record is invalid"
            ) from error

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for optional in (
            "account_id",
            "previous_run_id",
            "contract_version",
            "failure_code",
            "failure_reason",
        ):
            if not value[optional]:
                value.pop(optional)
        if value["last_duplicate_attempt"] is None:
            value.pop("last_duplicate_attempt")
        if not value["tags"]:
            value.pop("tags")
        return value


@dataclass(slots=True)
class DuplicateMetadata:
    existing_run_id: str
    existing_status: str
    attempted_run_id: str
    attempted_at: str = ""
    attempt_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        if not value["attempted_at"]:
            value.pop("attempted_at")
        return value


@dataclass(slots=True)
class StateResponse:
    decision: str
    idempotency_key: str
    object_key: str
    run_id: str
    status: str
    duplicate: bool
    run_state_record: RunStateRecord
    duplicate_metadata: DuplicateMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "decision": self.decision,
            "idempotency_key": self.idempotency_key,
            "object_key": self.object_key,
            "run_id": self.run_id,
            "status": self.status,
            "duplicate": self.duplicate,
            "run_state_record": self.run_state_record.to_dict(),
        }
        if self.duplicate_metadata is not None:
            value["duplicate_metadata"] = self.duplicate_metadata.to_dict()
        return value


class RunStateStore(Protocol):
    def put_if_absent(
        self, record: RunStateRecord
    ) -> tuple[bool, RunStateRecord | None]: ...

    def get(self, object_key: str) -> RunStateRecord: ...

    def update_status(
        self,
        object_key: str,
        run_id: str,
        status: str,
        failure_code: str,
        failure_reason: str,
        updated_at: datetime,
    ) -> RunStateRecord: ...

    def redrive_failed(
        self,
        object_key: str,
        previous_run_id: str,
        replacement: RunStateRecord,
    ) -> RunStateRecord: ...

    def record_duplicate(
        self, object_key: str, attempted_run_id: str, attempted_at: datetime
    ) -> RunStateRecord: ...

    def count_ad_hoc(self, tenant_id: str, billing_period_date: str) -> int: ...


class StateService:
    def __init__(
        self,
        store: RunStateStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def handle(self, raw_event: dict[str, Any]) -> dict[str, Any]:
        event = _normalize_event(raw_event)
        _validate_common(event)
        _validate_action(event)

        if event.action == Action.ACQUIRE_RUN:
            response = self._acquire_run(event)
        elif event.action == Action.GET_RUN:
            response = _accepted_response(self._store.get(_object_key(event)))
        elif event.action == Action.REDRIVE_RUN:
            replacement = _new_record(event, self._now())
            response = _accepted_response(
                self._store.redrive_failed(
                    replacement.object_key,
                    event.previous_run_id,
                    replacement,
                )
            )
        elif event.action == Action.COMPLETE_RUN:
            response = self._update_status(event, Status.COMPLETED)
        elif event.action == Action.FAIL_RUN:
            response = self._update_status(event, Status.FAILED)
        elif event.action == Action.FAIL_CONTRACT_CHECK:
            response = self._update_status(event, Status.FAILED_CONTRACT_CHECK)
        else:
            raise StateServiceError(
                "ERR_UNSUPPORTED_ACTION", f"unsupported action {event.action!r}"
            )
        return response.to_dict()

    def _acquire_run(self, event: StateEvent) -> StateResponse:
        now = self._now()
        if event.is_ad_hoc:
            count = self._store.count_ad_hoc(
                event.tenant_id, event.billing_period_date
            )
            if count >= MAX_AD_HOC_RUNS_PER_DAY:
                raise StateServiceError(
                    "ERR_AD_HOC_LIMIT",
                    f"ad-hoc run limit of {MAX_AD_HOC_RUNS_PER_DAY} per tenant/day exceeded",
                )

        record = _new_record(event, now)
        created, existing = self._store.put_if_absent(record)
        if created:
            return _accepted_response(record)
        if existing is None:
            raise StateServiceError(
                "ERR_STORE", "idempotency store returned no existing record"
            )
        if existing.payload_sha256 != record.payload_sha256:
            raise StateServiceError(
                "ERR_IDEMPOTENCY_MISMATCH",
                f"key {record.idempotency_key!r} already exists with a different payload hash",
            )

        existing = self._store.record_duplicate(
            existing.object_key, event.run_id, now
        )
        return _duplicate_response(event.run_id, existing)

    def _update_status(self, event: StateEvent, status: Status) -> StateResponse:
        record = self._store.update_status(
            _object_key(event),
            event.run_id,
            status,
            event.failure_code,
            event.failure_reason,
            self._now(),
        )
        return _accepted_response(record)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def _normalize_event(raw_event: dict[str, Any]) -> StateEvent:
    if not isinstance(raw_event, dict):
        raise StateServiceError("ERR_INVALID_SCHEMA", "event must be an object")

    def text(name: str) -> str:
        value = raw_event.get(name, "")
        if value is None:
            return ""
        if not isinstance(value, str):
            raise StateServiceError(
                "ERR_INVALID_SCHEMA", f"{name} must be a string"
            )
        return value.strip()

    is_ad_hoc = raw_event.get("is_ad_hoc", False)
    if not isinstance(is_ad_hoc, bool):
        raise StateServiceError(
            "ERR_INVALID_SCHEMA", "is_ad_hoc must be a boolean"
        )

    lock_ttl = raw_event.get("lock_ttl_seconds", DEFAULT_LOCK_TTL_SECONDS)
    if lock_ttl in (None, 0):
        lock_ttl = DEFAULT_LOCK_TTL_SECONDS
    if isinstance(lock_ttl, bool) or not isinstance(lock_ttl, int):
        raise StateServiceError(
            "ERR_INVALID_SCHEMA", "lock_ttl_seconds must be an integer"
        )

    tags = raw_event.get("tags") or {}
    if not isinstance(tags, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in tags.items()
    ):
        raise StateServiceError(
            "ERR_INVALID_SCHEMA", "tags must be a string-to-string object"
        )

    return StateEvent(
        action=text("action"),
        tenant_id=text("tenant_id"),
        account_id=text("account_id"),
        billing_period_date=text("billing_period_date"),
        batch_type=text("batch_type").lower(),
        run_id=text("run_id"),
        previous_run_id=text("previous_run_id"),
        correlation_id=text("correlation_id"),
        payload_sha256=text("payload_sha256").lower(),
        contract_version=text("contract_version"),
        is_ad_hoc=is_ad_hoc,
        lock_ttl_seconds=lock_ttl,
        duplicate_run_policy=text("duplicate_run_policy")
        or DEFAULT_DUPLICATE_RUN_POLICY,
        failure_code=text("failure_code"),
        failure_reason=text("failure_reason"),
        tags=dict(tags),
    )


def _validate_common(event: StateEvent) -> None:
    required = {
        "action": event.action,
        "tenant_id": event.tenant_id,
        "billing_period_date": event.billing_period_date,
        "batch_type": event.batch_type,
        "run_id": event.run_id,
        "correlation_id": event.correlation_id,
        "payload_sha256": event.payload_sha256,
    }
    for name, value in required.items():
        if not value:
            raise StateServiceError(
                "ERR_INVALID_SCHEMA", f"{name} is required"
            )

    if not UUID_PATTERN.fullmatch(event.tenant_id):
        raise StateServiceError(
            "ERR_INVALID_SCHEMA", "tenant_id must be a UUID"
        )
    if event.account_id and not ACCOUNT_ID_PATTERN.fullmatch(event.account_id):
        raise StateServiceError(
            "ERR_INVALID_SCHEMA",
            "account_id must be a 12-digit AWS account ID",
        )
    try:
        parsed_date = date.fromisoformat(event.billing_period_date)
    except ValueError as error:
        raise StateServiceError(
            "ERR_INVALID_SCHEMA",
            "billing_period_date must be a valid YYYY-MM-DD date",
        ) from error
    if parsed_date.isoformat() != event.billing_period_date:
        raise StateServiceError(
            "ERR_INVALID_SCHEMA",
            "billing_period_date must be a valid YYYY-MM-DD date",
        )
    if not BATCH_TYPE_PATTERN.fullmatch(event.batch_type):
        raise StateServiceError(
            "ERR_INVALID_SCHEMA",
            "batch_type must contain lowercase letters, digits, or hyphens",
        )
    if not UUID_PATTERN.fullmatch(event.correlation_id):
        raise StateServiceError(
            "ERR_INVALID_SCHEMA", "correlation_id must be a UUID"
        )
    if not SHA256_PATTERN.fullmatch(event.payload_sha256):
        raise StateServiceError(
            "ERR_INVALID_SCHEMA",
            "payload_sha256 must be a 64-character SHA-256 hex digest",
        )
    if event.contract_version and not CONTRACT_VERSION_PATTERN.fullmatch(
        event.contract_version
    ):
        raise StateServiceError(
            "ERR_INVALID_SCHEMA",
            "contract_version must use semantic version format",
        )
    if event.lock_ttl_seconds != DEFAULT_LOCK_TTL_SECONDS:
        raise StateServiceError(
            "ERR_INVALID_SCHEMA", "lock_ttl_seconds must be 86400 (24 hours)"
        )
    if event.duplicate_run_policy != DEFAULT_DUPLICATE_RUN_POLICY:
        raise StateServiceError(
            "ERR_INVALID_SCHEMA",
            f"unsupported duplicate_run_policy {event.duplicate_run_policy!r}",
        )
    if len(event.failure_reason) > 2_048 or len(event.tags) > 50:
        raise StateServiceError(
            "ERR_INVALID_SCHEMA", "failure_reason or tags exceed supported limits"
        )


def _validate_action(event: StateEvent) -> None:
    try:
        action = Action(event.action)
    except ValueError as error:
        raise StateServiceError(
            "ERR_UNSUPPORTED_ACTION", f"unsupported action {event.action!r}"
        ) from error

    if action == Action.REDRIVE_RUN and not event.previous_run_id:
        raise StateServiceError(
            "ERR_INVALID_SCHEMA",
            "previous_run_id is required for REDRIVE_RUN",
        )
    if (
        action in (Action.FAIL_RUN, Action.FAIL_CONTRACT_CHECK)
        and not event.failure_code
    ):
        raise StateServiceError(
            "ERR_INVALID_SCHEMA",
            f"failure_code is required for {event.action}",
        )


def _new_record(event: StateEvent, now: datetime) -> RunStateRecord:
    timestamp = _format_timestamp(now)
    return RunStateRecord(
        idempotency_key=_idempotency_key(event),
        object_key=_object_key(event),
        tenant_id=event.tenant_id,
        account_id=event.account_id,
        billing_period_date=event.billing_period_date,
        batch_type=event.batch_type,
        run_id=event.run_id,
        previous_run_id=event.previous_run_id,
        correlation_id=event.correlation_id,
        payload_sha256=event.payload_sha256,
        contract_version=event.contract_version,
        status=Status.IN_PROGRESS,
        is_ad_hoc=event.is_ad_hoc,
        created_at=timestamp,
        updated_at=timestamp,
        expires_at=_format_timestamp(
            now + timedelta(seconds=event.lock_ttl_seconds)
        ),
        tags=dict(event.tags),
    )


def _idempotency_key(event: StateEvent) -> str:
    return f"{event.tenant_id}:{event.billing_period_date}:{event.batch_type}"


def _object_key(event: StateEvent) -> str:
    if event.is_ad_hoc:
        return (
            f"idempotency/ad-hoc/{event.tenant_id}/"
            f"{event.billing_period_date}/{event.run_id}"
        )
    return f"idempotency/{_idempotency_key(event)}"


def _accepted_response(record: RunStateRecord) -> StateResponse:
    return StateResponse(
        decision=Decision.ACCEPTED,
        idempotency_key=record.idempotency_key,
        object_key=record.object_key,
        run_id=record.run_id,
        status=record.status,
        duplicate=False,
        run_state_record=record,
    )


def _duplicate_response(
    attempted_run_id: str, record: RunStateRecord
) -> StateResponse:
    attempt = record.last_duplicate_attempt
    return StateResponse(
        decision=Decision.REJECTED_DUPLICATE,
        idempotency_key=record.idempotency_key,
        object_key=record.object_key,
        run_id=attempted_run_id,
        status=Status.DUPLICATE_REJECTED,
        duplicate=True,
        duplicate_metadata=DuplicateMetadata(
            existing_run_id=record.run_id,
            existing_status=record.status,
            attempted_run_id=attempted_run_id,
            attempted_at=attempt.attempted_at if attempt else "",
            attempt_count=record.duplicate_attempt_count,
        ),
        run_state_record=record,
    )


def _format_timestamp(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
