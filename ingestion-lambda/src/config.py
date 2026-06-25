"""
config.py — AWS session configuration.
Port từ internal/config/config.go (Go).
v2.0: Thêm API_VERSION và AI Engine endpoint config.
"""
import os
import boto3


AWS_REGION = "ap-southeast-1"

# API version — "v1" hoặc "v2"
# Dual-run window: hỗ trợ song song trong 30 ngày kể từ 2026-06-25 đến 2026-07-25
API_VERSION = os.environ.get("TELEMETRY_API_VERSION", "v2")

# AI Engine endpoint — v2.0 dùng /v2/detect, v1.0 dùng /v1/detect
AI_ENGINE_ENDPOINT_V2 = os.environ.get(
    "AI_ENGINE_ENDPOINT_V2",
    "https://ai-engine.tf2-finops.internal/v2/detect",
)
AI_ENGINE_ENDPOINT_V1 = os.environ.get(
    "AI_ENGINE_ENDPOINT_V1",
    "https://ai-engine.tf2-finops.internal/v1/detect",
)

# SLA latency targets (ms) theo contract v2.0 §4
SLA_CLOUDTRAIL_P99_MS = 40    # CloudTrail event: P99 < 40ms
SLA_PARQUET_BATCH_P99_MS = 150 # CUR Parquet micro-batch: P99 < 150ms


def load() -> boto3.Session:
    """Trả về boto3 Session với region mặc định ap-southeast-1.

    Tương đương config.LoadDefaultConfig(ctx, config.WithRegion("ap-southeast-1"))
    trong Go. Credentials được lấy tự động từ environment / IAM role.
    """
    return boto3.Session(region_name=AWS_REGION)


def get_ai_engine_endpoint(api_version: str = API_VERSION) -> str:
    """Trả về AI Engine endpoint tương ứng với api_version.

    Dual-run window: CDO phải hoàn thành chuyển đổi trước 2026-07-25.
    Sau đó v1 endpoint sẽ bị ngừng hỗ trợ.
    """
    if api_version == "v1":
        return AI_ENGINE_ENDPOINT_V1
    return AI_ENGINE_ENDPOINT_V2
