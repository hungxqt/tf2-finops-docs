"""
s3writer.py — Ghi và copy objects lên S3 với KMS encryption.
Port từ internal/storage/s3writer.go (Go).
v2.0: Thêm write_signal_json() để lưu CloudTrail signals.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import boto3

from src.model import ObjectRef


class S3Writer:
    """Wrapper xung quanh boto3 S3 client để ghi data vào raw zone."""

    def __init__(self, session: boto3.Session) -> None:
        self._client = session.client("s3")

    def write_ce_json(
        self,
        bucket: str,
        raw_prefix: str,
        run_id: str,
        account_id: str,
        kms_key_arn: str,
        data: bytes,
    ) -> ObjectRef:
        """Ghi Cost Explorer JSON output vào raw zone với KMS encryption.

        Tương đương WriteCEJSON trong Go.
        Key format: {raw_prefix}{run_id}/ce/{account_id}/{timestamp}.json
        """
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        key = f"{raw_prefix}{run_id}/ce/{account_id}/{timestamp}.json"

        resp = self._client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType="application/json",
            SSEKMSKeyId=kms_key_arn,
            ServerSideEncryption="aws:kms",
        )

        return ObjectRef(
            s3_uri=f"s3://{bucket}/{key}",
            etag=resp.get("ETag", ""),
            source="CostExplorer",
            account_id=account_id,
        )

    def copy_cur_object(
        self,
        src_bucket: str,
        src_key: str,
        dest_bucket: str,
        dest_key: str,
        kms_key_arn: str,
        src_etag: str,
    ) -> ObjectRef:
        """Copy một CUR object từ source bucket sang raw zone với KMS encryption.

        Tương đương CopyCURObject trong Go.
        """
        self._client.copy_object(
            CopySource={"Bucket": src_bucket, "Key": src_key},
            Bucket=dest_bucket,
            Key=dest_key,
            SSEKMSKeyId=kms_key_arn,
            ServerSideEncryption="aws:kms",
        )

        return ObjectRef(
            s3_uri=f"s3://{dest_bucket}/{dest_key}",
            etag=src_etag,
            source="CUR",
        )

    def write_signal_json(
        self,
        bucket: str,
        raw_prefix: str,
        run_id: str,
        signal_type: str,
        kms_key_arn: str,
        data: bytes,
    ) -> ObjectRef:
        """
        Ghi signal JSON (CloudTrail) vào raw zone với KMS encryption.
        v2.0 NEW — hỗ trợ Signal 2 và Signal 3.

        Key format: {raw_prefix}{run_id}/{signal_type}/{timestamp}.json
        Ví dụ:
          cost/raw/{run_id}/cloudtrail/20260622T101530Z.json
        """
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # signal_type dùng cho path S3 key
        key = f"{raw_prefix}{run_id}/{signal_type}/{timestamp}.json"

        # Xác định source label từ signal_type
        source = "CloudTrail"

        resp = self._client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType="application/json",
            SSEKMSKeyId=kms_key_arn,
            ServerSideEncryption="aws:kms",
        )

        return ObjectRef(
            s3_uri=f"s3://{bucket}/{key}",
            etag=resp.get("ETag", ""),
            source=source,
        )
