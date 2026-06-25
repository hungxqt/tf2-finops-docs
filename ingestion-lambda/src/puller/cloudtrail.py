"""
cloudtrail.py — Pull CloudTrail events thông qua EventBridge / SQS queue.
Signal 2: aws_cloudtrail_event (v2.0 NEW)

Luồng: CloudTrail → EventBridge Rule → SQS Queue → CDO Ingestion (đây) → AI Engine POST /v2/detect
Mục đích: Rút ngắn MTTD từ 12h (CUR) xuống < 15 phút bằng cách bắt ngay
           các hành động "đốt tiền" (RunInstances P3/P4, CreateDBInstance lớn, v.v.)

SLA: P99 Latency < 40ms khi forward sang AI Engine /v2/detect
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.model import (
    CloudTrailEventPayload,
    CloudTrailRequestParameters,
    IngestionInput,
    ObjectRef,
)
from src.storage.s3writer import S3Writer


# Danh sách event names cần theo dõi — các hành động "đốt tiền"
_WATCHED_EVENTS = frozenset({
    "RunInstances",
    "CreateDBInstance",
    "CreateDBCluster",
    "CreateNotebookInstance",
    "CreateTrainingJob",
    "CreateEndpoint",
    "AllocateHosts",      # EC2 Dedicated Host
    "RequestSpotInstances",
})

# Instance type prefix đáng ngờ (GPU/compute-heavy)
_HIGH_COST_INSTANCE_PREFIXES = ("p3.", "p4.", "p4d.", "p4de.", "g4dn.", "g5.", "trn1.", "inf2.")


def pull_cloudtrail_events(
    session: boto3.Session,
    writer: S3Writer,
    input: IngestionInput,
    logger: logging.Logger,
    sqs_queue_url: str,
    max_messages: int = 100,
) -> list[ObjectRef]:
    """
    Poll SQS queue nhận CloudTrail events từ EventBridge.
    Parse → filter → serialize → lưu S3 raw zone.

    Args:
        session: boto3 Session đã assume role vào account member.
        writer: S3Writer để lưu raw events.
        input: IngestionInput chứa run context.
        logger: Structured logger.
        sqs_queue_url: URL SQS queue nhận events từ EventBridge.
        max_messages: Số message tối đa mỗi lần poll (default 100).

    Returns:
        list[ObjectRef]: Danh sách S3 refs chứa raw CloudTrail events đã filter.

    Raises:
        RuntimeError với prefix CLOUDTRAIL_ERROR nếu SQS poll thất bại.
    """
    sqs = session.client("sqs")
    refs: list[ObjectRef] = []
    events: list[dict] = []

    # SQS receive tối đa 10 messages/call → loop đến max_messages
    received = 0
    receipt_handles: list[str] = []

    try:
        while received < max_messages:
            batch_size = min(10, max_messages - received)
            resp = sqs.receive_message(
                QueueUrl=sqs_queue_url,
                MaxNumberOfMessages=batch_size,
                WaitTimeSeconds=1,          # short poll
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )
            messages = resp.get("Messages", [])
            if not messages:
                break  # Queue trống

            for msg in messages:
                receipt_handles.append(msg["ReceiptHandle"])
                try:
                    body = json.loads(msg["Body"])
                    # EventBridge wrapper → lấy detail
                    ct_event = body.get("detail", body)
                    if _should_capture(ct_event):
                        payload = _parse_event(ct_event)
                        events.append(payload.to_dict())
                        logger.info(
                            "cloudtrail high-cost event captured",
                            extra={
                                "event_name": ct_event.get("eventName"),
                                "region": ct_event.get("awsRegion"),
                                "user": ct_event.get("userIdentity", {}).get("arn", ""),
                            },
                        )
                except Exception as parse_err:
                    logger.warning(
                        "cloudtrail event parse error — skipping",
                        extra={"error": str(parse_err)},
                    )

            received += len(messages)

    except ClientError as exc:
        raise RuntimeError(
            f"CLOUDTRAIL_ERROR: SQS poll failed queue={sqs_queue_url}: {exc}"
        ) from exc

    if not events:
        _delete_messages(sqs, sqs_queue_url, receipt_handles, logger)
        logger.info("no high-cost cloudtrail events in queue", extra={"run_id": input.run_id})
        return refs

    # Serialize và lưu S3
    raw_data = json.dumps(
        {
            "signal_name": "aws_cloudtrail_event",
            "api_version": "v2",
            "run_id": input.run_id,
            "event_count": len(events),
            "events": events,
        },
        indent=2,
        default=str,
    ).encode()

    ref = writer.write_signal_json(
        bucket=input.raw_bucket,
        raw_prefix=input.raw_prefix,
        run_id=input.run_id,
        signal_type="cloudtrail",
        kms_key_arn=input.kms_key_arn,
        data=raw_data,
    )
    refs.append(ref)

    # Xoá messages đã xử lý khỏi SQS
    _delete_messages(sqs, sqs_queue_url, receipt_handles, logger)

    logger.info(
        "cloudtrail events saved",
        extra={
            "run_id": input.run_id,
            "event_count": len(events),
            "s3_uri": ref.s3_uri,
        },
    )
    return refs


def _should_capture(event: dict) -> bool:
    """
    Lọc chỉ giữ lại events đáng ngờ (high-cost actions).
    Giảm noise — không cần gửi mọi CloudTrail event sang AI Engine.
    """
    event_name = event.get("eventName", "")
    if event_name not in _WATCHED_EVENTS:
        return False

    # Với RunInstances: chỉ capture nếu là GPU/compute-heavy instance
    if event_name == "RunInstances":
        params = event.get("requestParameters", {})
        instance_type = params.get("instanceType", "")
        if instance_type and not any(instance_type.startswith(p) for p in _HIGH_COST_INSTANCE_PREFIXES):
            return False  # Instance thông thường — bỏ qua

    return True


def _parse_event(event: dict) -> CloudTrailEventPayload:
    """Chuyển đổi CloudTrail event dict → CloudTrailEventPayload (v2.0 schema)."""
    params = event.get("requestParameters") or {}
    user_identity = event.get("userIdentity", {})

    return CloudTrailEventPayload(
        ts=event.get("eventTime", datetime.now(timezone.utc).isoformat()),
        event_name=event.get("eventName", ""),
        event_source=event.get("eventSource", ""),
        aws_region=event.get("awsRegion", ""),
        user_identity=user_identity.get("arn", user_identity.get("userName", "unknown")),
        request_parameters=CloudTrailRequestParameters(
            instance_type=params.get("instanceType", ""),
            image_id=params.get("imageId", ""),
            min_count=int(params.get("minCount", 0)),
            max_count=int(params.get("maxCount", 0)),
        ),
        resource_tags=_extract_tags(event),
    )


def _extract_tags(event: dict) -> dict[str, str]:
    """Trích xuất resource tags từ CloudTrail event nếu có."""
    tags: dict[str, str] = {}
    # Tags có thể nằm trong requestParameters.tagSpecificationSet
    params = event.get("requestParameters") or {}
    tag_specs = params.get("tagSpecificationSet", {})
    items = tag_specs.get("items", [])
    for spec in items:
        for tag in spec.get("tags", []):
            key = tag.get("key", "")
            val = tag.get("value", "")
            if key:
                tags[key] = val
    return tags


def _delete_messages(
    sqs_client: Any,
    queue_url: str,
    receipt_handles: list[str],
    logger: logging.Logger,
) -> None:
    """Xoá messages đã xử lý khỏi SQS (batch delete, 10 messages/call)."""
    for i in range(0, len(receipt_handles), 10):
        batch = receipt_handles[i:i + 10]
        entries = [
            {"Id": str(j), "ReceiptHandle": rh}
            for j, rh in enumerate(batch)
        ]
        try:
            sqs_client.delete_message_batch(QueueUrl=queue_url, Entries=entries)
        except Exception as exc:
            logger.warning(
                "SQS delete_message_batch failed — messages will redeliver",
                extra={"error": str(exc)},
            )

