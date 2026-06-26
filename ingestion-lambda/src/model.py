"""
model.py — Domain types cho ingestion-lambda v2.0.
Cập nhật theo Telemetry Contract v2.0 (2026-06-25):
  - Thêm CloudTrailEvent signal type (Signal 2)
  - Nested JSON payload structure (v2.0)
  - Idempotency key format v2: [tenant_id]_[billing_period_YYYYMMDD]_[batch_sequence_id]_[api_version_v2]
  - Dual-run window: hỗ trợ song song v1.0 và v2.0 trong 30 ngày

Note: Signal 3 (EKS metrics) không dùng — runtime là Lambda container image.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Input types
# ---------------------------------------------------------------------------

@dataclass
class RetryConfig:
    """Retry và backoff settings."""
    max_attempts: int = 3     # default 3
    base_delay_ms: int = 500  # default 500 ms
    max_delay_ms: int = 30000 # default 30 s

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RetryConfig":
        return cls(
            max_attempts=d.get("max_attempts", 3),
            base_delay_ms=d.get("base_delay_ms", 500),
            max_delay_ms=d.get("max_delay_ms", 30000),
        )


@dataclass
class AccountConfig:
    account_id: str
    role_arn: str
    external_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AccountConfig":
        return cls(
            account_id=d["account_id"],
            role_arn=d["role_arn"],
            external_id=d.get("external_id", ""),
        )


@dataclass
class CURSource:
    bucket: str
    prefix: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CURSource":
        return cls(bucket=d["bucket"], prefix=d["prefix"])


@dataclass
class IngestionInput:
    """Payload từ Step Functions — v2.0."""
    accounts: list[AccountConfig]
    cur_sources: list[CURSource]
    cost_period_start: str   # "2025-06-01"
    cost_period_end: str     # "2025-06-30"
    raw_bucket: str
    raw_prefix: str          # "cost/raw/"
    kms_key_arn: str
    retry: RetryConfig
    run_id: str
    # --- v2.0 NEW ---
    tenant_id: str = ""                       # UUID ánh xạ từ Linked Account ID
    api_version: str = "v2"                   # "v1" | "v2" — dual-run window support
    enable_cloudtrail_streaming: bool = True  # Signal 2 — bật/tắt real-time CloudTrail

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IngestionInput":
        return cls(
            accounts=[AccountConfig.from_dict(a) for a in d.get("accounts", [])],
            cur_sources=[CURSource.from_dict(s) for s in d.get("cur_sources", [])],
            cost_period_start=d["cost_period_start"],
            cost_period_end=d["cost_period_end"],
            raw_bucket=d["raw_bucket"],
            raw_prefix=d["raw_prefix"],
            kms_key_arn=d["kms_key_arn"],
            retry=RetryConfig.from_dict(d.get("retry", {})),
            run_id=d["run_id"],
            tenant_id=d.get("tenant_id", ""),
            api_version=d.get("api_version", "v2"),
            enable_cloudtrail_streaming=d.get("enable_cloudtrail_streaming", True),
        )


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

@dataclass
class ObjectRef:
    s3_uri: str
    etag: str
    source: str          # "CUR" | "CostExplorer" | "CloudTrail"
    account_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d["account_id"]:
            del d["account_id"]
        return d


@dataclass
class AccountStatus:
    account_id: str
    cur_status: str = ""         # "ok" | "delayed" | "error" | "skipped"
    ce_status: str = ""          # "ok" | "throttled" | "error"
    cloudtrail_status: str = ""  # "ok" | "error" | "skipped"
    cost_period_start: str = ""
    cost_period_end: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PullError:
    account_id: str
    source: str   # "CUR" | "CostExplorer" | "AssumeRole" | "CloudTrail"
    code: str     # "CUR_DELAY" | "CE_THROTTLE" | "ASSUME_ROLE_FAILED" | "CLOUDTRAIL_ERROR"
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IngestionOutput:
    """Trả về Step Functions — v2.0."""
    run_id: str
    status: str = ""
    cur_refs: list[ObjectRef] = field(default_factory=list)
    ce_json_refs: list[ObjectRef] = field(default_factory=list)
    cloudtrail_refs: list[ObjectRef] = field(default_factory=list)
    source_uris: list[str] = field(default_factory=list)
    account_statuses: list[AccountStatus] = field(default_factory=list)
    errors: list[PullError] = field(default_factory=list)
    api_version: str = "v2"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "run_id": self.run_id,
            "status": self.status,
            "api_version": self.api_version,
            "cur_refs": [r.to_dict() for r in self.cur_refs],
            "ce_json_refs": [r.to_dict() for r in self.ce_json_refs],
            "cloudtrail_refs": [r.to_dict() for r in self.cloudtrail_refs],
            "source_uris": self.source_uris,
            "account_statuses": [s.to_dict() for s in self.account_statuses],
        }
        if self.errors:
            d["errors"] = [e.to_dict() for e in self.errors]
        return d


# ---------------------------------------------------------------------------
# v2.0 Signal payload types (nested JSON structure)
# ---------------------------------------------------------------------------

@dataclass
class ResourceLabels:
    """Nhãn tài nguyên — nested trong payload v2.0 (Signal 1)."""
    resource_id: str
    resource_type: str
    region: str
    service: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CostLabels:
    """Nhãn chi phí — nested trong payload v2.0 (Signal 1)."""
    unblended_rate: float
    unblended_cost: float
    currency: str = "USD"
    billing_period_start: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UsageLabels:
    """Nhãn usage — nested trong payload v2.0 (Signal 1)."""
    amount: float
    unit: str
    operation: str
    usage_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TagLabels:
    """Nhãn tag — nested trong payload v2.0 (Signal 1)."""
    team: str = ""
    environment: str = ""
    cost_center: str = ""
    owner: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v}


@dataclass
class CURSpendPayload:
    """
    Signal 1: daily_cur_spend_usd_v2 — Nested payload v2.0.
    Tối ưu 40% dung lượng so với v1 flat structure.
    POST /v2/detect
    """
    ts: str
    value: float
    resource: ResourceLabels
    cost: CostLabels
    usage: UsageLabels
    tags: TagLabels
    signal_name: str = "daily_cur_spend_usd_v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "signal_name": self.signal_name,
            "value": self.value,
            "labels": {
                "resource": self.resource.to_dict(),
                "cost": self.cost.to_dict(),
                "usage": self.usage.to_dict(),
                "tags": self.tags.to_dict(),
            },
        }


@dataclass
class CloudTrailRequestParameters:
    """Tham số request từ CloudTrail event (Signal 2 — v2.0 NEW)."""
    instance_type: str = ""
    image_id: str = ""
    min_count: int = 0
    max_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v}


@dataclass
class CloudTrailEventPayload:
    """
    Signal 2: aws_cloudtrail_event — Real-time provisioning event (v2.0 NEW).
    PUSH ngay khi sự kiện xảy ra. Rút ngắn MTTD xuống < 15 phút.
    Nguồn: CloudTrail → EventBridge Rule → CDO Ingestion → AI Engine POST /v2/detect
    """
    ts: str
    event_name: str
    event_source: str
    aws_region: str
    user_identity: str
    request_parameters: CloudTrailRequestParameters
    resource_tags: dict[str, str] = field(default_factory=dict)
    signal_name: str = "aws_cloudtrail_event"
    value: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "signal_name": self.signal_name,
            "value": self.value,
            "labels": {
                "event_name": self.event_name,
                "event_source": self.event_source,
                "aws_region": self.aws_region,
                "user_identity": self.user_identity,
                "request_parameters": self.request_parameters.to_dict(),
                "resource_tags": self.resource_tags,
            },
        }


# ---------------------------------------------------------------------------
# v2.0 Idempotency Key builder
# ---------------------------------------------------------------------------

def build_idempotency_key_v2(
    tenant_id: str,
    billing_period: str,   # "YYYYMMDD"
    batch_sequence_id: str,
) -> str:
    """
    Tạo idempotency key theo cấu trúc v2.0:
    [tenant_id]_[billing_period_YYYYMMDD]_[batch_sequence_id]_[api_version_v2]
    """
    return f"{tenant_id}_{billing_period}_{batch_sequence_id}_api_version_v2"
