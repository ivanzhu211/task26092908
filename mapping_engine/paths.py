"""Source field path extraction (nested objects and array indices)."""

from __future__ import annotations

from typing import Any

MISSING = object()  # sentinel: value absent (dangling path, null, or blank)


def _tokens(path: str) -> list[str]:
    """Split a dotted path; numeric segments index into lists."""
    return [seg for seg in path.split(".") if seg != ""]


def extract(source: Any, path: str) -> Any:
    """Extract a value from ``source`` by dotted path.

    Path segments are dict keys; integer segments index into lists.
    Returns MISSING when the path dangles at any point.
    """
    current = source
    for seg in _tokens(path):
        if isinstance(current, dict):
            if seg not in current:
                return MISSING
            current = current[seg]
        elif isinstance(current, (list, tuple)):
            if not seg.isdigit():
                return MISSING
            idx = int(seg)
            if idx >= len(current):
                return MISSING
            current = current[idx]
        else:
            return MISSING
    return current


def is_missing(value: Any) -> bool:
    """A value is missing if absent, None, or a blank/whitespace-only string."""
    if value is MISSING or value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False
