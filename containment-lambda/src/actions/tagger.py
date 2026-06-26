"""
tagger.py — Gắn tag lên resource trong member account.

Tag action được phép trên MỌI environment kể cả prod.
Theo deployment-contract.md §CDO Containment:
  tag-for-review: ec2:CreateTags, rds:AddTagsToResource — tất cả environments
"""
from __future__ import annotations

import logging
from typing import Any

import boto3

from src.model.input import ContainmentInput
from src.model.output import TaggingResult

logger = logging.getLogger(__name__)

# Tags chuẩn CDO gắn khi phát hiện anomaly
FINOPS_WATCH_TAG_KEY = "FinOpsWatch"
ANOMALY_ID_TAG_KEY = "FinOpsAnomalyId"
REVIEW_REQUIRED_VALUE = "ReviewRequired"


def execute_tag(
    inp: ContainmentInput,
    member_session: boto3.Session,
) -> TaggingResult:
    """
    Gắn FinOps review tags lên resource.

    Tags được gắn:
      - FinOpsWatch = ReviewRequired
      - FinOpsAnomalyId = {anomaly_id}

    Dispatch sang đúng AWS service dựa trên resource_id.

    Args:
        inp: ContainmentInput
        member_session: Session đã AssumeRole vào member account

    Returns:
        TaggingResult với kết quả boto3 call
    """
    tags_to_apply = {
        FINOPS_WATCH_TAG_KEY: REVIEW_REQUIRED_VALUE,
        ANOMALY_ID_TAG_KEY: inp.anomaly_id,
    }

    resource_id = inp.resource_id

    try:
        if resource_id.startswith("i-"):
            result = _tag_ec2(member_session, resource_id, tags_to_apply)
        elif "rds" in resource_id.lower() or ":db:" in resource_id:
            result = _tag_rds(member_session, resource_id, tags_to_apply)
        elif "sagemaker" in resource_id.lower():
            result = _tag_sagemaker(member_session, resource_id, tags_to_apply)
        else:
            # Fallback: thử EC2 tagging (works for most resource types)
            result = _tag_ec2(member_session, resource_id, tags_to_apply)

        logger.info(
            "tags applied successfully",
            extra={
                "anomaly_id": inp.anomaly_id,
                "resource_id": resource_id,
                "tags": tags_to_apply,
                "http_status": result.boto3_http_status,
            },
        )
        return result

    except Exception as exc:
        logger.error(
            "tagging failed",
            extra={
                "anomaly_id": inp.anomaly_id,
                "resource_id": resource_id,
                "error": str(exc),
            },
        )
        raise RuntimeError(f"TAGGING_FAILED resource={resource_id}: {exc}") from exc


def _tag_ec2(
    session: boto3.Session,
    resource_id: str,
    tags: dict[str, str],
) -> TaggingResult:
    """Gắn tag lên EC2 resource (instance, volume, snapshot, v.v.)."""
    ec2 = session.client("ec2")
    boto3_tags = [{"Key": k, "Value": v} for k, v in tags.items()]

    resp = ec2.create_tags(Resources=[resource_id], Tags=boto3_tags)

    return TaggingResult(
        resource_id=resource_id,
        tags_applied=tags,
        boto3_http_status=resp["ResponseMetadata"]["HTTPStatusCode"],
        boto3_request_id=resp["ResponseMetadata"]["RequestId"],
    )


def _tag_rds(
    session: boto3.Session,
    resource_id: str,
    tags: dict[str, str],
) -> TaggingResult:
    """Gắn tag lên RDS resource."""
    rds = session.client("rds")
    boto3_tags = [{"Key": k, "Value": v} for k, v in tags.items()]

    # RDS tagging cần ARN đầy đủ
    resp = rds.add_tags_to_resource(ResourceName=resource_id, Tags=boto3_tags)

    return TaggingResult(
        resource_id=resource_id,
        tags_applied=tags,
        boto3_http_status=resp["ResponseMetadata"]["HTTPStatusCode"],
        boto3_request_id=resp["ResponseMetadata"]["RequestId"],
    )


def _tag_sagemaker(
    session: boto3.Session,
    resource_id: str,
    tags: dict[str, str],
) -> TaggingResult:
    """Gắn tag lên SageMaker resource."""
    sm = session.client("sagemaker")
    boto3_tags = [{"Key": k, "Value": v} for k, v in tags.items()]

    resp = sm.add_tags(ResourceArn=resource_id, Tags=boto3_tags)

    return TaggingResult(
        resource_id=resource_id,
        tags_applied=tags,
        boto3_http_status=resp["ResponseMetadata"]["HTTPStatusCode"],
        boto3_request_id=resp["ResponseMetadata"]["RequestId"],
    )


def compute_rollback_path_for_tag(tags_applied: dict[str, str]) -> dict[str, Any]:
    """
    Tính rollback_path cho tag action.
    Rollback = xóa các tags đã gắn.
    """
    return {
        "action": "remove_tags",
        "keys": list(tags_applied.keys()),
    }
