"""
test_actions.py — Unit tests cho actions/ với moto mock AWS.

Dùng moto để mock EC2, RDS, SageMaker — không cần AWS account thật.
Chạy: pytest tests/test_actions.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

from src.model.input import (
    ContainmentInput,
    Boto3Payload,
    AuditWriterConfig,
    APPROVAL_APPROVED,
    DATA_CONFIDENCE_HIGH,
    MODE_APPLY,
    MODE_DRY_RUN,
    MODE_TAG,
)
from src.actions.dry_run import execute_dry_run
from src.actions.suggester import execute_suggest, _determine_route, ROUTE_ENGINEERING, ROUTE_FINANCE


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def _make_input(
    environment: str = "sandbox",
    execution_mode: str = MODE_DRY_RUN,
    anomaly_type: str = "runaway_usage",
    resource_id: str = "i-0test12345",
) -> ContainmentInput:
    return ContainmentInput(
        run_id="run-test-001",
        anomaly_id="anom-test-001",
        correlation_id="corr-test-001",
        model_version="v1.0.0",
        anomaly_type=anomaly_type,
        confidence=0.92,
        severity="high",
        explanation="GPU cluster running 24/7 with no traffic",
        data_confidence=DATA_CONFIDENCE_HIGH,
        resource_id=resource_id,
        resource_owner="squad-ml-core",
        account_id="200000000012",
        environment=environment,
        containment_role_name="FinOpsContainmentWorkerRole",
        external_id="test-external-id",
        execution_mode=execution_mode,
        approval_status=APPROVAL_APPROVED,
        recommended_containment_mode="auto-shutdown",
        applied_payload=Boto3Payload(
            service="ec2",
            method="stop_instances",
            parameters={"InstanceIds": [resource_id]},
        ),
        rollback_payload=Boto3Payload(
            service="ec2",
            method="start_instances",
            parameters={"InstanceIds": [resource_id]},
        ),
        audit_config=AuditWriterConfig(
            audit_bucket="company-cdo-200000000012-telemetry",
            audit_prefix="audit/",
            dashboard_table="finops-dashboard-cache-sandbox",
            rollback_cache_table="finops-rollback-cache",
        ),
    )


# ---------------------------------------------------------------------------
# Tests: dry_run
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_returns_correct_service(self):
        inp = _make_input(execution_mode=MODE_DRY_RUN)
        result = execute_dry_run(inp)
        assert result.would_execute_service == "ec2"

    def test_dry_run_returns_correct_method(self):
        inp = _make_input(execution_mode=MODE_DRY_RUN)
        result = execute_dry_run(inp)
        assert result.would_execute_method == "stop_instances"

    def test_dry_run_no_aws_call(self):
        """Dry run không được gọi bất kỳ AWS API nào."""
        inp = _make_input(execution_mode=MODE_DRY_RUN)
        # Nếu có AWS call thì sẽ raise NoCredentialsError — test sẽ fail
        result = execute_dry_run(inp)
        assert "dry-run" in result.simulation_note.lower()

    def test_dry_run_includes_resource_id(self):
        inp = _make_input(resource_id="i-0abc123test")
        result = execute_dry_run(inp)
        assert "i-0abc123test" in result.simulation_note

    def test_dry_run_to_dict(self):
        inp = _make_input()
        result = execute_dry_run(inp)
        d = result.to_dict()
        assert "would_execute_service" in d
        assert "would_execute_method" in d
        assert "simulation_note" in d


# ---------------------------------------------------------------------------
# Tests: tagger (mock boto3)
# ---------------------------------------------------------------------------

class TestTagger:
    def test_tag_calls_create_tags(self):
        """Verify ec2.create_tags được gọi với đúng parameters."""
        from src.actions.tagger import execute_tag

        inp = _make_input(execution_mode=MODE_TAG, resource_id="i-0test999")

        mock_ec2 = MagicMock()
        mock_ec2.create_tags.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req-001"}
        }

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ec2

        result = execute_tag(inp, mock_session)

        # Verify create_tags was called
        mock_ec2.create_tags.assert_called_once()
        call_kwargs = mock_ec2.create_tags.call_args[1]
        assert "i-0test999" in call_kwargs["Resources"]

        # Verify tags contain FinOpsWatch key
        tag_keys = [t["Key"] for t in call_kwargs["Tags"]]
        assert "FinOpsWatch" in tag_keys
        assert "FinOpsAnomalyId" in tag_keys

    def test_tag_result_contains_anomaly_id(self):
        from src.actions.tagger import execute_tag

        inp = _make_input(execution_mode=MODE_TAG)

        mock_ec2 = MagicMock()
        mock_ec2.create_tags.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req-002"}
        }
        mock_session = MagicMock()
        mock_session.client.return_value = mock_ec2

        result = execute_tag(inp, mock_session)
        assert inp.anomaly_id in result.tags_applied.get("FinOpsAnomalyId", "")

    def test_rollback_path_for_tag(self):
        from src.actions.tagger import compute_rollback_path_for_tag
        tags = {"FinOpsWatch": "ReviewRequired", "FinOpsAnomalyId": "anom-001"}
        rollback = compute_rollback_path_for_tag(tags)
        assert rollback["action"] == "remove_tags"
        assert "FinOpsWatch" in rollback["keys"]


# ---------------------------------------------------------------------------
# Tests: suggester
# ---------------------------------------------------------------------------

class TestSuggester:
    def test_runaway_usage_routes_to_engineering(self):
        route = _determine_route("runaway_usage", "sandbox")
        assert route == ROUTE_ENGINEERING

    def test_idle_resource_routes_to_engineering(self):
        route = _determine_route("idle_resource", "sandbox")
        assert route == ROUTE_ENGINEERING

    def test_untagged_spend_routes_to_finance(self):
        route = _determine_route("untagged_spend", "prod")
        assert route == ROUTE_FINANCE

    def test_sudden_spike_routes_to_finance(self):
        route = _determine_route("sudden_spike", "prod")
        assert route == ROUTE_FINANCE

    def test_gradual_drift_routes_to_finance(self):
        route = _determine_route("gradual_drift", "sandbox")
        assert route == ROUTE_FINANCE

    def test_unknown_anomaly_defaults_to_engineering(self):
        route = _determine_route("unknown_type", "sandbox")
        assert route == ROUTE_ENGINEERING

    def test_suggest_returns_record_with_anomaly_id(self):
        inp = _make_input(anomaly_type="runaway_usage")
        result = execute_suggest(inp)
        assert result.anomaly_id == inp.anomaly_id

    def test_suggest_prod_requires_approval(self):
        inp = _make_input(environment="prod", anomaly_type="runaway_usage")
        result = execute_suggest(inp)
        assert result.approval_required is True

    def test_suggest_sandbox_auto_shutdown_requires_approval(self):
        inp = _make_input(environment="sandbox", anomaly_type="runaway_usage")
        inp.recommended_containment_mode = "auto-shutdown"
        result = execute_suggest(inp)
        assert result.approval_required is True

    def test_suggest_sandbox_tag_no_approval_needed(self):
        inp = _make_input(environment="sandbox", anomaly_type="idle_resource")
        inp.recommended_containment_mode = "tag-for-review"
        result = execute_suggest(inp)
        assert result.approval_required is False


# ---------------------------------------------------------------------------
# Tests: stopper (mock boto3)
# ---------------------------------------------------------------------------

class TestStopper:
    def test_stop_ec2_instance(self):
        from src.actions.stopper import execute_apply

        inp = _make_input(
            environment="sandbox",
            execution_mode=MODE_APPLY,
            resource_id="i-0test567",
        )

        mock_ec2 = MagicMock()
        mock_ec2.stop_instances.return_value = {
            "StoppingInstances": [{"CurrentState": {"Name": "stopping"}}],
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req-stop-001"},
        }
        mock_session = MagicMock()
        mock_session.client.return_value = mock_ec2

        result = execute_apply(inp, mock_session)

        mock_ec2.stop_instances.assert_called_once_with(
            InstanceIds=["i-0test567"]
        )
        assert result.boto3_http_status == 200
        assert result.action_executed == "ec2.stop_instances"

    def test_stop_rds_instance(self):
        from src.actions.stopper import execute_apply

        inp = _make_input(environment="sandbox", execution_mode=MODE_APPLY)
        inp.applied_payload = Boto3Payload(
            service="rds",
            method="stop_db_instance",
            parameters={"DBInstanceIdentifier": "my-db-01"},
        )

        mock_rds = MagicMock()
        mock_rds.stop_db_instance.return_value = {
            "DBInstance": {"DBInstanceStatus": "stopping"},
            "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req-rds-001"},
        }
        mock_session = MagicMock()
        mock_session.client.return_value = mock_rds

        result = execute_apply(inp, mock_session)

        mock_rds.stop_db_instance.assert_called_once_with(
            DBInstanceIdentifier="my-db-01"
        )
        assert result.action_executed == "rds.stop_db_instance"
