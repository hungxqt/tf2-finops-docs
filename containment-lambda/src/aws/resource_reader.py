"""
resource_reader.py — Đọc before_state của resource từ member account.

Chạy SAU khi AssumeRole vào member account.
Kết quả dùng để:
  1. Ghi vào audit record (before_state)
  2. Tính proposed_after_state
  3. Tính rollback_path
"""
from __future__ import annotations

import logging
from typing import Any

import boto3

logger = logging.getLogger(__name__)


def read_before_state(
    session: boto3.Session,
    resource_id: str,
    anomaly_type: str,
) -> dict[str, Any]:
    """
    Đọc trạng thái hiện tại của resource trước khi tác động.

    Dispatch sang reader phù hợp dựa trên resource_id prefix.
    Nếu không đọc được (resource không tồn tại hoặc lỗi permission)
    → trả về empty dict, không block containment.

    Args:
        session: Member account session (đã AssumeRole)
        resource_id: ARN hoặc instance ID
        anomaly_type: Dùng để chọn AWS client phù hợp

    Returns:
        dict mô tả trạng thái hiện tại của resource
    """
    try:
        if resource_id.startswith("i-"):
            return _read_ec2_instance(session, resource_id)
        elif "rds" in resource_id.lower() or ":db:" in resource_id:
            return _read_rds_instance(session, resource_id)
        elif "sagemaker" in resource_id.lower() or ":notebook-instance:" in resource_id:
            return _read_sagemaker_notebook(session, resource_id)
        else:
            # Resource type không xác định — trả về minimal state
            logger.warning(
                "unknown resource type, returning minimal before_state",
                extra={"resource_id": resource_id},
            )
            return {"resource_id": resource_id, "state": "unknown"}
    except Exception as exc:
        # Không block containment nếu không đọc được state
        logger.warning(
            "failed to read before_state, continuing with empty state",
            extra={"resource_id": resource_id, "error": str(exc)},
        )
        return {"resource_id": resource_id, "state": "read_failed", "error": str(exc)}


def _read_ec2_instance(session: boto3.Session, instance_id: str) -> dict[str, Any]:
    """Đọc state của EC2 instance."""
    ec2 = session.client("ec2")
    resp = ec2.describe_instances(InstanceIds=[instance_id])

    reservations = resp.get("Reservations", [])
    if not reservations:
        return {"resource_id": instance_id, "state": "not_found"}

    instance = reservations[0]["Instances"][0]

    # Normalize tags thành dict
    tags = {
        tag["Key"]: tag["Value"]
        for tag in instance.get("Tags", [])
    }

    return {
        "resource_id": instance_id,
        "instance_type": instance.get("InstanceType", ""),
        "state": instance.get("State", {}).get("Name", ""),
        "launch_time": str(instance.get("LaunchTime", "")),
        "tags": tags,
    }


def _read_rds_instance(session: boto3.Session, db_identifier: str) -> dict[str, Any]:
    """Đọc state của RDS DB instance."""
    rds = session.client("rds")

    # db_identifier có thể là ARN hoặc identifier name
    # Nếu là ARN thì extract identifier
    identifier = db_identifier.split(":")[-1] if ":" in db_identifier else db_identifier

    resp = rds.describe_db_instances(DBInstanceIdentifier=identifier)
    instances = resp.get("DBInstances", [])
    if not instances:
        return {"resource_id": db_identifier, "state": "not_found"}

    db = instances[0]
    return {
        "resource_id": db_identifier,
        "db_instance_class": db.get("DBInstanceClass", ""),
        "state": db.get("DBInstanceStatus", ""),
        "engine": db.get("Engine", ""),
        "multi_az": db.get("MultiAZ", False),
        "tags": {t["Key"]: t["Value"] for t in db.get("TagList", [])},
    }


def _read_sagemaker_notebook(session: boto3.Session, notebook_name: str) -> dict[str, Any]:
    """Đọc state của SageMaker notebook instance."""
    sm = session.client("sagemaker")

    # Extract tên từ ARN nếu cần
    name = notebook_name.split("/")[-1] if "/" in notebook_name else notebook_name

    resp = sm.describe_notebook_instance(NotebookInstanceName=name)
    return {
        "resource_id": notebook_name,
        "instance_type": resp.get("InstanceType", ""),
        "state": resp.get("NotebookInstanceStatus", ""),
        "tags": {},  # SageMaker tags cần call riêng list_tags
    }


def compute_proposed_after_state(
    before_state: dict[str, Any],
    execution_mode: str,
    containment_tags: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Tính proposed_after_state dựa trên before_state và execution_mode.

    Dùng cho audit record — Finance thấy "sẽ trông như thế nào sau action".
    """
    after = dict(before_state)  # shallow copy

    if execution_mode == "dry-run":
        after["_note"] = "dry-run: state would not change"
        return after

    if execution_mode == "tag" and containment_tags:
        existing_tags = dict(after.get("tags", {}))
        existing_tags.update(containment_tags)
        after["tags"] = existing_tags
        return after

    if execution_mode == "apply":
        after["state"] = "stopped"
        return after

    return after
