from __future__ import annotations

from enum import Enum
from typing import Any


def to_json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(item) for item in value]
    if hasattr(value, "value") and value.__class__.__name__ == "Interrupt":
        return {"type": "interrupt", "value": to_json_safe(getattr(value, "value"))}
    if hasattr(value, "dict") and callable(value.dict):
        return to_json_safe(value.dict())
    if hasattr(value, "__dict__"):
        return {
            "__class__": value.__class__.__name__,
            **{key: to_json_safe(item) for key, item in vars(value).items()},
        }
    return str(value)
