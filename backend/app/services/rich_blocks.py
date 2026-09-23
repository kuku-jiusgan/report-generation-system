"""Shared structured field-value contract between extraction and rendering."""

from typing import Any


RICH_BLOCKS = "RICH_BLOCKS"


def is_rich_value(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") == RICH_BLOCKS
