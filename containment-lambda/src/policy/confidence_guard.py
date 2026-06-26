"""
confidence_guard.py — Guard dựa trên data_confidence từ AI Engine.

Theo NOTES.md §1 và ai-api-contract.md:
  - data_confidence = LOW khi CUR delay > 36h hoặc CE fallback
  - Khi LOW: lock containment sang dry-run/alert-only
  - Khi LOW: đây là tín hiệu telemetry không đủ độ tin cậy

File này tách riêng khỏi boundary.py để dễ test và maintain độc lập.
"""
from __future__ import annotations

from src.model.input import DATA_CONFIDENCE_HIGH, DATA_CONFIDENCE_LOW


def is_confidence_sufficient(data_confidence: str) -> bool:
    """
    Kiểm tra data_confidence có đủ để thực thi real action không.

    Returns:
        True nếu HIGH — cho phép apply/tag/suggest
        False nếu LOW — chỉ dry-run
    """
    return data_confidence == DATA_CONFIDENCE_HIGH


def get_confidence_override_reason(data_confidence: str) -> str:
    """Trả về lý do override nếu confidence không đủ."""
    if data_confidence == DATA_CONFIDENCE_LOW:
        return (
            "data_confidence=LOW: CUR data may be delayed or incomplete "
            "(telemetry_delay_event=true). Containment locked to dry-run "
            "to prevent incorrect actions on lagged billing data."
        )
    return ""
