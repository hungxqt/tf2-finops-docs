"""
costexplorer.py — Query AWS Cost Explorer với exponential backoff khi throttle.
Port từ internal/puller/costexplorer.go (Go).
"""
from __future__ import annotations

import json
import time
import math
import logging

import boto3
from botocore.exceptions import ClientError

from src.model import AccountConfig, IngestionInput, RetryConfig


def pull_cost_explorer(
    session: boto3.Session,
    account: AccountConfig,
    input: IngestionInput,
    logger: logging.Logger,
) -> bytes:
    """Query CE API với exponential backoff khi bị throttle.

    Tương đương pullCostExplorer trong Go.
    Trả về JSON bytes của GetCostAndUsage response.
    """
    client = session.client("ce", region_name="us-east-1")  # CE chỉ hoạt động ở us-east-1

    req = {
        "TimePeriod": {
            "Start": input.cost_period_start,
            "End": input.cost_period_end,
        },
        "Granularity": "DAILY",
        "Metrics": ["BlendedCost", "UnblendedCost", "UsageQuantity"],
        "GroupBy": [
            {"Type": "DIMENSION", "Key": "SERVICE"},
            {"Type": "DIMENSION", "Key": "LINKED_ACCOUNT"},
        ],
    }

    max_attempts = input.retry.max_attempts or 3
    result = None
    last_err: Exception | None = None

    for attempt in range(max_attempts):
        try:
            result = client.get_cost_and_usage(**req)
            break
        except ClientError as err:
            last_err = err
            if _is_throttle_error(err) and attempt < max_attempts - 1:
                delay_s = _backoff_delay(attempt, input.retry)
                logger.warning(
                    "CE throttled, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "delay_ms": int(delay_s * 1000),
                        "account_id": account.account_id,
                    },
                )
                time.sleep(delay_s)
                continue
            # Throttle habis attempt hoặc non-throttle error
            raise RuntimeError(
                f"CE_THROTTLE account={account.account_id} attempts={attempt + 1}: {err}"
            ) from err

    if result is None:
        raise RuntimeError(
            f"CE_THROTTLE account={account.account_id} attempts={max_attempts}: {last_err}"
        )

    # Loại bỏ ResponseMetadata để output gọn hơn
    result.pop("ResponseMetadata", None)
    return json.dumps(result, indent=2, default=str).encode()


def _is_throttle_error(err: ClientError) -> bool:
    """Kiểm tra lỗi throttling từ AWS SDK.

    Tương đương isThrottleError trong Go.
    """
    error_code = err.response.get("Error", {}).get("Code", "")
    error_msg = str(err).lower()

    return (
        error_code in ("ThrottlingException", "RequestLimitExceeded", "Throttling")
        or "throttl" in error_msg
        or "rate exceeded" in error_msg
        or "too many requests" in error_msg
    )


def _backoff_delay(attempt: int, cfg: RetryConfig) -> float:
    """Tính delay (giây) theo exponential backoff.

    Tương đương backoffDelay trong Go.
    """
    base_ms = cfg.base_delay_ms if cfg.base_delay_ms > 0 else 500
    max_ms = cfg.max_delay_ms if cfg.max_delay_ms > 0 else 30_000

    ms = float(base_ms) * math.pow(2, attempt)
    ms = min(ms, float(max_ms))
    return ms / 1000.0
