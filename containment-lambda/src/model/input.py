"""
input.py — ContainmentInput và các types liên quan.

Input nhận từ Step Functions sau khi /v1/decide trả về action plan.
Lambda này KHÔNG gọi AI Engine — chỉ nhận kết quả đã có và thực thi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Enums (dùng string constant thay vì Enum class cho đơn giản)
# ---------------------------------------------------------------------------

# Execution modes
MODE_DRY_RUN = "dry-run"
MODE_TAG = "tag"
MODE_SUGGEST = "suggest"
MODE_APPLY = "apply"

VALID_EXECUTION_MODES = {MODE_DRY_RUN, MODE_TAG, MODE_SUGGEST, MODE_APPLY}

# Environments — quyết định containment strategy
PROD_ENVS = {"prod", "prod-core", "prod-payments"}
NON_PROD_ENVS = {"staging", "dev", "sandbox", "ml-research", "data-analytics"}

# Approval statuses
APPROVAL_APPROVED = "approved"
APPROVAL_PENDING = "pending"
APPROVAL_DENIED = "denied"

# Data confidence
DATA_CONFIDENCE_HIGH = "HIGH"
DATA_CONFIDENCE_LOW = "LOW"


# ---------------------------------------------------------------------------
# Boto3 equivalent payload — từ /v1/decide rollback_payload.boto3_equivalent
# ---------------------------------------------------------------------------

@dataclass
class Boto3Payload:
    """
    Payload boto3 để thực thi hoặc rollback action.
    Từ DecideResponse.applied_payload hoặc rollback_payload.boto3_equivalent.
    """
    service: str        # "ec2", "rds", "sagemaker", "servicequotas"
    method: str         # "stop_instances", "create_tags", "stop_db_instance"
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Boto3Payload":
        return cls(
            service=d["service"],
            method=d["method"],
            parameters=d.get("parameters", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "method": self.method,
            "parameters": self.parameters,
        }


# ---------------------------------------------------------------------------
# Audit writer config — cấu hình S3 + DynamoDB để ghi audit
# ---------------------------------------------------------------------------

@dataclass
class AuditWriterConfig:
    """Cấu hình storage targets cho audit records."""
    audit_bucket: str           # company-cdo-{account_id}-telemetry
    audit_prefix: str           # "audit/"
    dashboard_table: str        # DynamoDB Dashboard Cache table name
    rollback_cache_table: str   # finops-rollback-cache table name

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AuditWriterConfig":
        return cls(
            audit_bucket=d["audit_bucket"],
            audit_prefix=d.get("audit_prefix", "audit/"),
            dashboard_table=d["dashboard_table"],
            rollback_cache_table=d["rollback_cache_table"],
        )


# ---------------------------------------------------------------------------
# Main input type
# ---------------------------------------------------------------------------

@dataclass
class ContainmentInput:
    """
    Payload từ Step Functions — kết quả sau /v1/decide.

    Step Functions truyền toàn bộ AI decision + context vào đây.
    Lambda chỉ cần đọc và thực thi theo đúng policy.
    """
    # --- AI decision fields (từ /v1/decide response) ---
    run_id: str                     # ID của ingestion run hiện tại
    anomaly_id: str                 # ID anomaly từ AI Engine
    correlation_id: str             # Trace ID xuyên suốt E2E
    model_version: str              # Version AI model đã dùng để detect
    anomaly_type: str               # runaway_usage | idle_resource | untagged_spend | ...
    confidence: float               # 0.0 - 1.0
    severity: str                   # low | medium | high | critical
    explanation: str                # Giải thích từ AI
    data_confidence: str            # HIGH | LOW — nếu LOW thì force dry-run

    # --- Resource context ---
    resource_id: str                # ARN hoặc instance ID
    resource_owner: str             # squad owner
    account_id: str                 # AWS member account ID
    environment: str                # prod | sandbox | dev | ...
    containment_role_name: str      # Tên IAM role để AssumeRole vào member account
    external_id: str                # External ID cho AssumeRole (từ Secrets Manager)

    # --- Policy inputs ---
    execution_mode: str             # dry-run | tag | suggest | apply
    approval_status: str            # approved | pending | denied
    recommended_containment_mode: str  # tag-for-review | auto-shutdown | quota-cap | ...

    # --- Boto3 payloads từ /v1/decide ---
    applied_payload: Boto3Payload           # Command để thực thi action
    rollback_payload: Boto3Payload          # Command để rollback nếu cần

    # --- Audit config ---
    audit_config: AuditWriterConfig

    # --- Optional fields ---
    tenant_id: str = ""
    evidence_uri: str = ""          # S3 URI của evidence từ AI Engine
    cost_window_start: str = ""
    cost_window_end: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContainmentInput":
        return cls(
            run_id=d["run_id"],
            anomaly_id=d["anomaly_id"],
            correlation_id=d["correlation_id"],
            model_version=d.get("model_version", "unknown"),
            anomaly_type=d.get("anomaly_type", "unknown"),
            confidence=float(d.get("confidence", 0.0)),
            severity=d.get("severity", "medium"),
            explanation=d.get("explanation", ""),
            data_confidence=d.get("data_confidence", DATA_CONFIDENCE_HIGH),
            resource_id=d["resource_id"],
            resource_owner=d.get("resource_owner", ""),
            account_id=d["account_id"],
            environment=d["environment"],
            containment_role_name=d["containment_role_name"],
            external_id=d.get("external_id", ""),
            execution_mode=d["execution_mode"],
            approval_status=d.get("approval_status", APPROVAL_PENDING),
            recommended_containment_mode=d.get("recommended_containment_mode", "tag-for-review"),
            applied_payload=Boto3Payload.from_dict(d["applied_payload"]),
            rollback_payload=Boto3Payload.from_dict(d["rollback_payload"]),
            audit_config=AuditWriterConfig.from_dict(d["audit_config"]),
            tenant_id=d.get("tenant_id", ""),
            evidence_uri=d.get("evidence_uri", ""),
            cost_window_start=d.get("cost_window_start", ""),
            cost_window_end=d.get("cost_window_end", ""),
        )
