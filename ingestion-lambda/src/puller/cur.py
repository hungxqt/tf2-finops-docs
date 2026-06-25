"""
cur.py — List và copy CUR objects từ source bucket sang raw zone.
Port từ internal/puller/cur.go (Go).
"""
from __future__ import annotations

import boto3

from src.model import CURSource, IngestionInput, ObjectRef
from src.storage.s3writer import S3Writer


_CUR_EXTENSIONS = (".parquet", ".csv.gz", ".json")


def pull_cur(
    session: boto3.Session,
    writer: S3Writer,
    source: CURSource,
    input: IngestionInput,
) -> list[ObjectRef]:
    """List CUR objects trong source bucket và copy sang raw zone.

    Tương đương pullCUR trong Go.
    Raises RuntimeError với prefix CUR_DELAY nếu không tìm thấy file.
    """
    s3_client = session.client("s3")

    # Tìm CUR files theo tháng của cost period (YYYY-MM)
    month_prefix = f"{source.prefix}{input.cost_period_start[:7]}/"

    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=source.bucket, Prefix=month_prefix)

    refs: list[ObjectRef] = []

    try:
        for page in pages:
            for obj in page.get("Contents", []):
                src_key: str = obj["Key"]
                if not _is_cur_file(src_key):
                    continue

                # Normalise bucket name cho dest key (thay '.' bằng '-')
                safe_bucket = source.bucket.replace(".", "-")
                dest_key = (
                    f"{input.raw_prefix}{input.run_id}/cur/{safe_bucket}/{src_key}"
                )

                ref = writer.copy_cur_object(
                    src_bucket=source.bucket,
                    src_key=src_key,
                    dest_bucket=input.raw_bucket,
                    dest_key=dest_key,
                    kms_key_arn=input.kms_key_arn,
                    src_etag=obj.get("ETag", ""),
                )
                ref.account_id = ""  # sẽ được gán bên ngoài
                refs.append(ref)

    except Exception as exc:
        raise RuntimeError(
            f"CUR_DELAY: list objects failed s3://{source.bucket}/{month_prefix}: {exc}"
        ) from exc

    if not refs:
        raise RuntimeError(
            f"CUR_DELAY: no CUR files found for period "
            f"{input.cost_period_start[:7]} under s3://{source.bucket}/{month_prefix}"
        )

    return refs


def _is_cur_file(key: str) -> bool:
    """Kiểm tra file có phải CUR file không.

    Tương đương isCURFile trong Go.
    """
    return any(key.endswith(ext) for ext in _CUR_EXTENSIONS)
