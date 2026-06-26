"""
test_boundary.py — Unit tests cho policy/boundary.py và confidence_guard.py

Chạy: pytest tests/test_boundary.py -v
Không cần AWS account — pure Python logic.
"""
import pytest

from src.model.input import (
    ContainmentInput,
    Boto3Payload,
    AuditWriterConfig,
    APPROVAL_APPROVED,
    APPROVAL_DENIED,
    APPROVAL_PENDING,
    DATA_CONFIDENCE_HIGH,
    DATA_CONFIDENCE_LOW,
    MODE_APPLY,
    MODE_DRY_RUN,
    MODE_TAG,
)
from src.policy.boundary import enforce_boundaries, is_prod_environment
from src.policy.confidence_guard import is_confidence_sufficient, get_confidence_override_reason


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_input(
    environment: str = "sandbox",
    execution_mode: str = MODE_APPLY,
    approval_status: str = APPROVAL_APPROVED,
    data_confidence: str = DATA_CONFIDENCE_HIGH,
) -> ContainmentInput:
    """Helper tạo ContainmentInput với defaults hợp lý."""
    return ContainmentInput(
        run_id="run-test-001",
        anomaly_id="anom-test-001",
        correlation_id="corr-test-001",
        model_version="v1.0.0",
        anomaly_type="runaway_usage",
        confidence=0.92,
        severity="high",
        explanation="Test anomaly",
        data_confidence=data_confidence,
        resource_id="i-0test12345",
        resource_owner="squad-ml-core",
        account_id="200000000012",
        environment=environment,
        containment_role_name="FinOpsContainmentWorkerRole",
        external_id="test-external-id",
        execution_mode=execution_mode,
        approval_status=approval_status,
        recommended_containment_mode="auto-shutdown",
        applied_payload=Boto3Payload(
            service="ec2",
            method="stop_instances",
            parameters={"InstanceIds": ["i-0test12345"]},
        ),
        rollback_payload=Boto3Payload(
            service="ec2",
            method="start_instances",
            parameters={"InstanceIds": ["i-0test12345"]},
        ),
        audit_config=AuditWriterConfig(
            audit_bucket="company-cdo-200000000012-telemetry",
            audit_prefix="audit/",
            dashboard_table="finops-dashboard-cache-sandbox",
            rollback_cache_table="finops-rollback-cache",
        ),
    )


# ---------------------------------------------------------------------------
# Tests: is_prod_environment
# ---------------------------------------------------------------------------

class TestIsProdEnvironment:
    def test_prod_is_prod(self):
        assert is_prod_environment("prod") is True

    def test_prod_core_is_prod(self):
        assert is_prod_environment("prod-core") is True

    def test_prod_payments_is_prod(self):
        assert is_prod_environment("prod-payments") is True

    def test_sandbox_is_not_prod(self):
        assert is_prod_environment("sandbox") is False

    def test_dev_is_not_prod(self):
        assert is_prod_environment("dev") is False

    def test_ml_research_is_not_prod(self):
        assert is_prod_environment("ml-research") is False

    def test_staging_is_not_prod(self):
        assert is_prod_environment("staging") is False


# ---------------------------------------------------------------------------
# Tests: enforce_boundaries — prod environment
# ---------------------------------------------------------------------------

class TestProdBoundary:
    def test_prod_apply_forced_to_dry_run(self):
        inp = _make_input(environment="prod", execution_mode=MODE_APPLY)
        result = enforce_boundaries(inp)
        assert result == MODE_DRY_RUN

    def test_prod_core_apply_forced_to_dry_run(self):
        inp = _make_input(environment="prod-core", execution_mode=MODE_APPLY)
        result = enforce_boundaries(inp)
        assert result == MODE_DRY_RUN

    def test_prod_payments_apply_forced_to_dry_run(self):
        inp = _make_input(environment="prod-payments", execution_mode=MODE_APPLY)
        result = enforce_boundaries(inp)
        assert result == MODE_DRY_RUN

    def test_prod_dry_run_stays_dry_run(self):
        inp = _make_input(environment="prod", execution_mode=MODE_DRY_RUN)
        result = enforce_boundaries(inp)
        assert result == MODE_DRY_RUN

    def test_prod_tag_allowed(self):
        inp = _make_input(environment="prod", execution_mode=MODE_TAG)
        result = enforce_boundaries(inp)
        assert result == MODE_TAG

    def test_prod_suggest_allowed(self):
        inp = _make_input(environment="prod", execution_mode="suggest")
        result = enforce_boundaries(inp)
        assert result == "suggest"


# ---------------------------------------------------------------------------
# Tests: enforce_boundaries — non-prod environment
# ---------------------------------------------------------------------------

class TestNonProdBoundary:
    def test_sandbox_apply_allowed(self):
        inp = _make_input(environment="sandbox", execution_mode=MODE_APPLY)
        result = enforce_boundaries(inp)
        assert result == MODE_APPLY

    def test_dev_apply_allowed(self):
        inp = _make_input(environment="dev", execution_mode=MODE_APPLY)
        result = enforce_boundaries(inp)
        assert result == MODE_APPLY

    def test_ml_research_apply_allowed(self):
        inp = _make_input(environment="ml-research", execution_mode=MODE_APPLY)
        result = enforce_boundaries(inp)
        assert result == MODE_APPLY

    def test_staging_apply_allowed(self):
        inp = _make_input(environment="staging", execution_mode=MODE_APPLY)
        result = enforce_boundaries(inp)
        assert result == MODE_APPLY


# ---------------------------------------------------------------------------
# Tests: enforce_boundaries — approval denied
# ---------------------------------------------------------------------------

class TestApprovalBoundary:
    def test_denied_approval_returns_denied(self):
        inp = _make_input(approval_status=APPROVAL_DENIED)
        result = enforce_boundaries(inp)
        assert result == "denied"

    def test_approved_passes_through(self):
        inp = _make_input(
            environment="sandbox",
            execution_mode=MODE_APPLY,
            approval_status=APPROVAL_APPROVED,
        )
        result = enforce_boundaries(inp)
        assert result == MODE_APPLY

    def test_pending_passes_through(self):
        # pending không bị denied — executor tự handle
        inp = _make_input(
            environment="sandbox",
            execution_mode=MODE_TAG,
            approval_status=APPROVAL_PENDING,
        )
        result = enforce_boundaries(inp)
        assert result == MODE_TAG


# ---------------------------------------------------------------------------
# Tests: enforce_boundaries — data_confidence LOW
# ---------------------------------------------------------------------------

class TestConfidenceBoundary:
    def test_low_confidence_apply_forced_to_dry_run(self):
        inp = _make_input(
            environment="sandbox",
            execution_mode=MODE_APPLY,
            data_confidence=DATA_CONFIDENCE_LOW,
        )
        result = enforce_boundaries(inp)
        assert result == MODE_DRY_RUN

    def test_low_confidence_tag_forced_to_dry_run(self):
        inp = _make_input(
            environment="sandbox",
            execution_mode=MODE_TAG,
            data_confidence=DATA_CONFIDENCE_LOW,
        )
        result = enforce_boundaries(inp)
        assert result == MODE_DRY_RUN

    def test_high_confidence_apply_allowed(self):
        inp = _make_input(
            environment="sandbox",
            execution_mode=MODE_APPLY,
            data_confidence=DATA_CONFIDENCE_HIGH,
        )
        result = enforce_boundaries(inp)
        assert result == MODE_APPLY

    def test_low_confidence_dry_run_stays_dry_run(self):
        inp = _make_input(
            environment="sandbox",
            execution_mode=MODE_DRY_RUN,
            data_confidence=DATA_CONFIDENCE_LOW,
        )
        result = enforce_boundaries(inp)
        assert result == MODE_DRY_RUN


# ---------------------------------------------------------------------------
# Tests: confidence_guard helpers
# ---------------------------------------------------------------------------

class TestConfidenceGuard:
    def test_high_confidence_sufficient(self):
        assert is_confidence_sufficient(DATA_CONFIDENCE_HIGH) is True

    def test_low_confidence_not_sufficient(self):
        assert is_confidence_sufficient(DATA_CONFIDENCE_LOW) is False

    def test_low_confidence_reason_not_empty(self):
        reason = get_confidence_override_reason(DATA_CONFIDENCE_LOW)
        assert len(reason) > 0
        assert "LOW" in reason

    def test_high_confidence_reason_empty(self):
        reason = get_confidence_override_reason(DATA_CONFIDENCE_HIGH)
        assert reason == ""


# ---------------------------------------------------------------------------
# Tests: combined boundaries (prod + low confidence)
# ---------------------------------------------------------------------------

class TestCombinedBoundaries:
    def test_prod_and_low_confidence_both_force_dry_run(self):
        inp = _make_input(
            environment="prod",
            execution_mode=MODE_APPLY,
            data_confidence=DATA_CONFIDENCE_LOW,
        )
        result = enforce_boundaries(inp)
        assert result == MODE_DRY_RUN

    def test_denied_trumps_everything(self):
        # Dù environment là sandbox và confidence HIGH,
        # approval_denied vẫn phải return "denied"
        inp = _make_input(
            environment="sandbox",
            execution_mode=MODE_APPLY,
            approval_status=APPROVAL_DENIED,
            data_confidence=DATA_CONFIDENCE_HIGH,
        )
        result = enforce_boundaries(inp)
        assert result == "denied"
