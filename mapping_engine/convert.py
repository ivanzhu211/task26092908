"""Type conversions for rule transforms."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from .models import STATUS_VALUES

TRANSFORMS = (
    "string",
    "id_string",
    "int",
    "bool",
    "date",
    "status",
)

_BOOL_STRINGS = {
    "true": True,
    "false": False,
    "yes": True,
    "no": False,
    "1": True,
    "0": False,
}

_RE_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_RE_US_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_RE_COMPACT_DATE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def _to_string(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError(f"cannot convert boolean {value!r} to string")
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    raise ValueError(f"cannot convert {type(value).__name__} to string")


def _to_id_string(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError(f"cannot convert boolean {value!r} to id string")
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            raise ValueError("empty id string")
        return text
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        raise ValueError(f"non-integer number {value!r} cannot be an id")
    raise ValueError(f"cannot convert {type(value).__name__} to id string")


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"boolean {value!r} is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError(f"non-integer number {value!r}")
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            pass
        try:
            num = float(text)
        except ValueError:
            raise ValueError(f"{value!r} is not an integer") from None
        if num.is_integer():
            return int(num)
        raise ValueError(f"non-integer number {value!r}")
    raise ValueError(f"cannot convert {type(value).__name__} to int")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"integer {value!r} is not 0 or 1")
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _BOOL_STRINGS:
            return _BOOL_STRINGS[text]
        raise ValueError(f"{value!r} is not a recognized boolean")
    raise ValueError(f"cannot convert {type(value).__name__} to bool")


def _checked_date(year: int, month: int, day: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid date {year:04d}-{month:02d}-{day:02d}") from exc


def _to_date(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError(f"cannot convert boolean {value!r} to date")
    if isinstance(value, int):
        text = str(value)
        m = _RE_COMPACT_DATE.match(text)
        if not m:
            raise ValueError(f"integer {value!r} is not a YYYYMMDD date")
        return _checked_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if isinstance(value, str):
        text = value.strip()
        m = _RE_ISO_DATE.match(text)
        if m:
            return _checked_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = _RE_US_DATE.match(text)
        if m:
            return _checked_date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        m = _RE_COMPACT_DATE.match(text)
        if m:
            return _checked_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        parsed = _parse_iso_datetime(text)
        if parsed is not None:
            return parsed.astimezone(timezone.utc).date().isoformat()
        raise ValueError(f"{value!r} is not a supported date format")
    raise ValueError(f"cannot convert {type(value).__name__} to date")


def _parse_iso_datetime(text: str) -> datetime | None:
    candidate = text
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        raise ValueError(f"datetime {text!r} has no timezone")
    return parsed


def _to_status(value: Any) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text in STATUS_VALUES:
            return text
        raise ValueError(
            f"{value!r} is not one of {', '.join(STATUS_VALUES)}"
        )
    raise ValueError(f"cannot convert {type(value).__name__} to status")


_CONVERTERS = {
    "string": _to_string,
    "id_string": _to_id_string,
    "int": _to_int,
    "bool": _to_bool,
    "date": _to_date,
    "status": _to_status,
}


def convert(value: Any, transform: str) -> Any:
    """Convert ``value`` according to ``transform``.

    Raises ValueError with a human-readable reason on failure.
    """
    func = _CONVERTERS.get(transform)
    if func is None:
        raise ValueError(f"unknown transform {transform!r}")
    return func(value)
