"""
test_audit.py — Unit tests cho audit/ với moto mock S3 + DynamoDB.

Chạy: pytest tests/test_audit.py -v
"""
import json
import time
import pytest

try:
    from moto import mock_aws
    MOTO_AVAILABLE = True
except ImportError:
    MOTO_AVAILABLE = False

import boto3

from src.model.output import AuditRecord


# Skip toàn bộ module nếu moto chưa install
pytestmark = pytest.mark.skipif(
    not MOTO_AVAILABLE,
    reason="moto not installed — run: pip install moto[s3,dynamodb]"
)

AWS_REGION = "ap-southeast-1"
TEST_BUCKET = "company-cdo-200000000012-telemetry"
TEST_TABLE = "finops-dashboard-cache-sandbox"
TEST_ROLLBACK_TABLE = "finops-rollback-cache"


def _make_audit_record() -> AuditRecord:
    return AuditRecord(
        actor="cdo-platform-containment-lambda",
        timestamp="2026-06-26T10:00:00Z",
        correlation_id="corr-test-001",
        anomaly_id="anom-test-001",
        run_id="run-test-001",
        resource_owner="squad-ml-core",
        resource_id="i-0test12345",
        account_id="200000000012",
        environment="sandbox",
        execution_mode="dry-run",
        original_execution_mode="apply",
        approval_status="approved",
        data_confidence="HIGH",
        before_state={"state": "running", "instance_type": "p3.2xlarge"},
        proposed_after_state={"state": "stopped"},
        rollback_path={"action": "start_instances"},
    )


# ---------------------------------------------------------------------------
# Tests: s3_audit
# ---------------------------------------------------------------------------

class TestS3Audit:
    @mock_aws
    def test_pre_action_audit_written_to_s3(self):
        """Verify audit record được ghi vào S3."""
        session = boto3.Session(region_name=AWS_REGION)

        # Setup mock S3 bucket
        s3 = session.client("s3")
        s3.create_bucket(
            Bucket=TEST_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
        )

        from src.audit.s3_audit import write_pre_action_audit
        audit_record = _make_audit_record()

        audit_id, s3_uri = write_pre_action_audit(
            session=session,
            audit_record=audit_record,
            audit_bucket=TEST_BUCKET,
            audit_prefix="audit/",
        )

        # Verify audit_id được tạo
        assert len(audit_id) > 0
        assert TEST_BUCKET in s3_uri

        # Verify object tồn tại trong S3
        prefix = "audit/"
        objects = s3.list_objects_v2(Bucket=TEST_BUCKET, Prefix=prefix)
        assert objects["KeyCount"] >= 1

    @mock_aws
    def test_audit_record_content_correct(self):
        """Verify nội dung audit record được ghi đúng."""
        session = boto3.Session(region_name=AWS_REGION)
        s3 = session.client("s3")
        s3.create_bucket(
            Bucket=TEST_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
        )

        from src.audit.s3_audit import write_pre_action_audit
        audit_record = _make_audit_record()

        audit_id, s3_uri = write_pre_action_audit(
            session=session,
            audit_record=audit_record,
            audit_bucket=TEST_BUCKET,
        )

        # Đọc object và verify nội dung
        key = s3_uri.replace(f"s3://{TEST_BUCKET}/", "")
        obj = s3.get_object(Bucket=TEST_BUCKET, Key=key)
        content = json.loads(obj["Body"].read())

        assert content["anomaly_id"] == "anom-test-001"
        assert content["actor"] == "cdo-platform-containment-lambda"
        assert content["environment"] == "sandbox"
        assert content["execution_mode"] == "dry-run"

    @mock_aws
    def test_audit_chain_hash_computed(self):
        """Verify audit_chain.event_hash được tính."""
        session = boto3.Session(region_name=AWS_REGION)
        s3 = session.client("s3")
        s3.create_bucket(
            Bucket=TEST_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
        )

        from src.audit.s3_audit import write_pre_action_audit
        audit_record = _make_audit_record()

        audit_id, _ = write_pre_action_audit(
            session=session,
            audit_record=audit_record,
            audit_bucket=TEST_BUCKET,
        )

        assert len(audit_record.audit_chain.get("event_hash", "")) == 64  # SHA256 hex


# ---------------------------------------------------------------------------
# Tests: dynamo_cache
# ---------------------------------------------------------------------------

class TestDynamoCache:
    @mock_aws
    def test_dashboard_cache_updated(self):
        """Verify DynamoDB Dashboard Cache được cập nhật."""
        session = boto3.Session(region_name=AWS_REGION)

        # Setup mock DynamoDB table
        dynamodb = session.resource("dynamodb")
        dynamodb.create_table(
            TableName=TEST_TABLE,
            KeySchema=[{"AttributeName": "anomaly_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "anomaly_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        from src.audit.dynamo_cache import update_dashboard_cache
        success = update_dashboard_cache(
            session=session,
            table_name=TEST_TABLE,
            anomaly_id="anom-test-001",
            run_id="run-test-001",
            correlation_id="corr-test-001",
            resource_id="i-0test12345",
            account_id="200000000012",
            environment="sandbox",
            execution_mode_applied="dry-run",
            status="dry-run",
            audit_record_id="audit-id-001",
            audit_record_s3_uri="s3://test-bucket/audit/2026/01/audit-id-001.json",
        )

        assert success is True

        # Verify item tồn tại trong DynamoDB
        table = dynamodb.Table(TEST_TABLE)
        item = table.get_item(Key={"anomaly_id": "anom-test-001"}).get("Item")
        assert item is not None
        assert item["status"] == "dry-run"
        assert item["execution_mode_applied"] == "dry-run"

    @mock_aws
    def test_rollback_cache_stored(self):
        """Verify rollback payload được lưu vào finops-rollback-cache."""
        session = boto3.Session(region_name=AWS_REGION)

        dynamodb = session.resource("dynamodb")
        dynamodb.create_table(
            TableName=TEST_ROLLBACK_TABLE,
            KeySchema=[{"AttributeName": "anomaly_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "anomaly_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        from src.audit.dynamo_cache import cache_rollback_payload
        rollback_payload = {
            "service": "ec2",
            "method": "start_instances",
            "parameters": {"InstanceIds": ["i-0test12345"]},
        }

        success = cache_rollback_payload(
            session=session,
            rollback_cache_table=TEST_ROLLBACK_TABLE,
            anomaly_id="anom-test-001",
            correlation_id="corr-test-001",
            rollback_payload=rollback_payload,
        )

        assert success is True

        # Verify item trong cache
        table = dynamodb.Table(TEST_ROLLBACK_TABLE)
        item = table.get_item(Key={"anomaly_id": "anom-test-001"}).get("Item")
        assert item is not None
        assert item["boto3_equivalent"]["service"] == "ec2"
        assert item["boto3_equivalent"]["method"] == "start_instances"

    @mock_aws
    def test_dashboard_cache_fails_gracefully(self):
        """DynamoDB fail không nên block containment flow."""
        session = boto3.Session(region_name=AWS_REGION)
        # Không tạo table → ClientError khi write
        from src.audit.dynamo_cache import update_dashboard_cache
        # Phải return False thay vì raise exception
        success = update_dashboard_cache(
            session=session,
            table_name="non-existent-table",
            anomaly_id="anom-test-001",
            run_id="run-test-001",
            correlation_id="corr-test-001",
            resource_id="i-0test",
            account_id="200000000012",
            environment="sandbox",
            execution_mode_applied="dry-run",
            status="dry-run",
            audit_record_id="audit-001",
            audit_record_s3_uri="s3://bucket/key",
        )
        assert success is False
