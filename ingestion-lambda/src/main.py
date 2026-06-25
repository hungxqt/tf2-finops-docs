"""
main.py — Lambda handler entrypoint.
Port từ cmd/main.go (Go).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from src import config
from src.model import IngestionInput, IngestionOutput
from src.puller.puller import Puller


def _make_logger() -> logging.Logger:
    """Tạo structured JSON logger tương đương log/slog.NewJSONHandler trong Go."""
    logger = logging.getLogger("ingestion-lambda")
    logger.setLevel(logging.INFO)
    return logger


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint.

    Tương đương handler() + main() trong cmd/main.go (Go).
    """
    logger = _make_logger()

    # Parse input payload
    try:
        # event có thể là dict (Lambda JSON) hoặc string thô
        if isinstance(event, str):
            event = json.loads(event)
        input_data = IngestionInput.from_dict(event)
    except Exception as exc:
        logger.error("invalid input payload", extra={"error": str(exc)})
        raise

    logger.info(
        "ingestion lambda started",
        extra={
            "run_id": input_data.run_id,
            "cost_period_start": input_data.cost_period_start,
            "cost_period_end": input_data.cost_period_end,
            "accounts": len(input_data.accounts),
            "cur_sources": len(input_data.cur_sources),
        },
    )

    # Load AWS session
    session = config.load()

    # Chạy ingestion
    puller = Puller(session, logger)
    try:
        output: IngestionOutput = puller.run(input_data)
    except RuntimeError as exc:
        # partial hoặc all-failed — args[1] là IngestionOutput nếu có
        if len(exc.args) >= 2 and isinstance(exc.args[1], IngestionOutput):
            return exc.args[1].to_dict()
        raise

    return output.to_dict()
