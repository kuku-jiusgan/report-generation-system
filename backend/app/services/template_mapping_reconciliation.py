"""Reconcile draft mapping records with content controls removed from Word."""

from typing import Any


def mappings_for_removed_controls(
    mappings: list[dict[str, Any]],
    previous_tags: set[str],
    current_tags: set[str],
) -> list[dict[str, Any]]:
    """Return mappings whose controls existed before this save and were removed."""
    removed_tags = previous_tags - current_tags
    if not removed_tags:
        return []
    return [
        mapping for mapping in mappings
        if str(mapping.get("controlTag") or "").strip() in removed_tags
    ]
