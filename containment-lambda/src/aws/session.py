"""
session.py — AWS session management + cross-account AssumeRole.

Containment Lambda chạy trong CDO Management Account nhưng cần
tác động lên resource trong Member Accounts.
Flow: CDO Lambda Role → AssumeRole → FinOpsContainmentWorkerRole (member account)
"""
from __future__ import annotations

import logging

import boto3

logger = logging.getLogger(__name__)

AWS_REGION = "ap-southeast-1"


def load() -> boto3.Session:
    """Trả về boto3 Session mặc định với CDO management account credentials."""
    return boto3.Session(region_name=AWS_REGION)


def assume_containment_role(
    session: boto3.Session,
    account_id: str,
    role_name: str,
    anomaly_id: str,
    external_id: str = "",
) -> boto3.Session:
    """
    Assume FinOpsContainmentWorkerRole trong member account.

    Theo 03_security_design.md §2.3:
    - Mỗi cross-account role phải có external_id
    - Session name phải traceable về anomaly_id
    - IAM role trong member account có explicit deny cho prod resources

    Args:
        session: CDO management account session
        account_id: Member AWS account ID
        role_name: Tên IAM role trong member account (ví dụ FinOpsContainmentWorkerRole)
        anomaly_id: Dùng làm session name để trace trong CloudTrail
        external_id: External ID lấy từ Secrets Manager

    Returns:
        boto3.Session với credentials của member account
    """
    sts = session.client("sts")
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    # Session name traceable — xuất hiện trong CloudTrail của member account
    session_name = f"finops-containment-{anomaly_id[:20]}"

    kwargs: dict = {
        "RoleArn": role_arn,
        "RoleSessionName": session_name,
    }
    if external_id:
        kwargs["ExternalId"] = external_id

    try:
        resp = sts.assume_role(**kwargs)
    except Exception as exc:
        raise RuntimeError(
            f"ASSUME_ROLE_FAILED account={account_id} role={role_name}: {exc}"
        ) from exc

    creds = resp["Credentials"]
    logger.info(
        "assumed containment role",
        extra={
            "account_id": account_id,
            "role_arn": role_arn,
            "session_name": session_name,
            "anomaly_id": anomaly_id,
        },
    )

    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=AWS_REGION,
    )
