"""
stopper.py — Thực thi stop/shutdown action trên non-prod resources.

CHỈ chạy khi:
  - environment NOT IN {prod, prod-core, prod-payments}
  - approval_status = approved
  - execution_mode = apply

Boundary check đã được enforce trước đó trong policy/boundary.py.
File này KHÔNG tự kiểm tra boundary — đó là responsibility của executor.py.

Theo deployment-contract.md §CDO Containment:
  auto-shutdown: ec2:StopInstances, rds:StopDBInstance, sagemaker:StopNotebookInstance
  Environments: dev, sandbox, ml-research, staging
"""
from __future__ import annotations

import logging
from typing import Any

import boto3

from src.model.input import ContainmentInput, Boto3Payload
from src.model.output import ApplyResult

logger = logging.getLogger(__name__)


def execute_apply(
    inp: ContainmentInput,
    member_session: boto3.Session,
) -> ApplyResult:
    """
    Thực thi boto3 command từ applied_payload.

    Dùng applied_payload.boto3_equivalent từ /v1/decide response —
    không tự build command, chỉ execute những gì AI Engine đã recommend.

    Args:
        inp: ContainmentInput
        member_session: Session đã AssumeRole vào member account

    Returns:
        ApplyResult với boto3 execution outcome
    """
    payload = inp.applied_payload
    resource_id = inp.resource_id

    logger.info(
        "executing apply action",
        extra={
            "anomaly_id": inp.anomaly_id,
            "resource_id": resource_id,
            "service": payload.service,
            "method": payload.method,
            "environment": inp.environment,
        },
    )

    try:
        result = _dispatch_boto3(member_session, payload)

        logger.info(
            "apply action succeeded",
            extra={
                "anomaly_id": inp.anomaly_id,
                "resource_id": resource_id,
                "http_status": result.boto3_http_status,
            },
        )
        return result

    except Exception as exc:
        logger.error(
            "apply action failed",
            extra={
                "anomaly_id": inp.anomaly_id,
                "resource_id": resource_id,
                "service": payload.service,
                "method": payload.method,
                "error": str(exc),
            },
        )
        raise RuntimeError(
            f"APPLY_FAILED resource={resource_id} "
            f"action={payload.service}.{payload.method}: {exc}"
        ) from exc


def _dispatch_boto3(
    session: boto3.Session,
    payload: Boto3Payload,
) -> ApplyResult:
    """
    Dispatch boto3 call dựa trên service + method từ payload.

    Hỗ trợ các actions theo deployment-contract.md:
    - ec2: stop_instances
    - rds: stop_db_instance
    - sagemaker: stop_notebook_instance
    """
    service = payload.service.lower()
    method = payload.method.lower()
    params = payload.parameters

    client = session.client(service)

    # Gọi method tương ứng
    if service == "ec2" and method == "stop_instances":
        resp = client.stop_instances(**params)
        instances = resp.get("StoppingInstances", [{}])
        resource_id = params.get("InstanceIds", ["unknown"])[0]
        return ApplyResult(
            resource_id=resource_id,
            action_executed="ec2.stop_instances",
            boto3_http_status=resp["ResponseMetadata"]["HTTPStatusCode"],
            boto3_request_id=resp["ResponseMetadata"]["RequestId"],
            execution_note=f"state: {instances[0].get('CurrentState', {}).get('Name', '')}",
        )

    elif service == "rds" and method == "stop_db_instance":
        resp = client.stop_db_instance(**params)
        db = resp.get("DBInstance", {})
        resource_id = params.get("DBInstanceIdentifier", "unknown")
        return ApplyResult(
            resource_id=resource_id,
            action_executed="rds.stop_db_instance",
            boto3_http_status=resp["ResponseMetadata"]["HTTPStatusCode"],
            boto3_request_id=resp["ResponseMetadata"]["RequestId"],
            execution_note=f"status: {db.get('DBInstanceStatus', '')}",
        )

    elif service == "sagemaker" and method == "stop_notebook_instance":
        resp = client.stop_notebook_instance(**params)
        resource_id = params.get("NotebookInstanceName", "unknown")
        return ApplyResult(
            resource_id=resource_id,
            action_executed="sagemaker.stop_notebook_instance",
            boto3_http_status=resp["ResponseMetadata"]["HTTPStatusCode"],
            boto3_request_id=resp["ResponseMetadata"]["RequestId"],
        )

    elif service == "servicequotas" and method in ("get_service_quota", "request_service_quota_increase"):
        # quota-cap action: dev, sandbox, data-analytics only
        # Theo deployment-contract.md §CDO Containment
        boto3_method_fn = getattr(client, method)
        resp = boto3_method_fn(**params)
        resource_id = params.get("ServiceCode", "unknown")
        return ApplyResult(
            resource_id=resource_id,
            action_executed=f"servicequotas.{method}",
            boto3_http_status=resp["ResponseMetadata"]["HTTPStatusCode"],
            boto3_request_id=resp["ResponseMetadata"]["RequestId"],
            execution_note="quota-cap action applied",
        )

    else:
        # Generic fallback — gọi method bất kỳ nếu tên khớp
        # Dùng cho future actions mà chưa có handler riêng
        boto3_method = getattr(client, method, None)
        if boto3_method is None:
            raise ValueError(
                f"Unsupported boto3 method: {service}.{method}"
            )
        resp = boto3_method(**params)
        resource_id = str(list(params.values())[0]) if params else "unknown"
        return ApplyResult(
            resource_id=resource_id,
            action_executed=f"{service}.{method}",
            boto3_http_status=resp.get("ResponseMetadata", {}).get("HTTPStatusCode", 0),
            boto3_request_id=resp.get("ResponseMetadata", {}).get("RequestId", ""),
        )
