"""类型转换：date / bool / int / id-string / status 枚举。"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

STATUSES = ("active", "inactive", "terminated", "on_leave")

_DATE_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DATE_US_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DATE_COMPACT_RE = re.compile(r"^\d{8}$")

_BOOL_STRINGS = {
    "true": True,
    "false": False,
    "yes": True,
    "no": False,
    "1": True,
    "0": False,
}


def _checked_date(year: int, month: int, day: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        raise ValueError(f"invalid date: {year:04d}-{month:02d}-{day:02d} does not exist")


def to_date(value) -> str:
    """归一化为 "YYYY-MM-DD"。不支持的格式、不存在的日期、无时区时间报错。"""
    if isinstance(value, bool):
        raise ValueError(f"cannot convert {value!r} to date")
    if isinstance(value, int):
        text = str(value)
        if not _DATE_COMPACT_RE.match(text):
            raise ValueError(f"cannot convert integer {value!r} to date")
        return _checked_date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    if not isinstance(value, str):
        raise ValueError(f"cannot convert {type(value).__name__} to date")
    text = value.strip()
    match = _DATE_ISO_RE.match(text)
    if match:
        return _checked_date(int(match[1]), int(match[2]), int(match[3]))
    match = _DATE_US_RE.match(text)
    if match:
        return _checked_date(int(match[3]), int(match[1]), int(match[2]))
    if _DATE_COMPACT_RE.match(text):
        return _checked_date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"unsupported date format: {value!r}")
    if parsed.tzinfo is None:
        raise ValueError(f"datetime without timezone is not accepted: {value!r}")
    return parsed.astimezone(timezone.utc).date().isoformat()


def to_bool(value) -> bool:
    """整数只认 0/1；字符串去空白后不分大小写只认 true/false/yes/no/1/0。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"integer {value!r} is not 0 or 1")
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _BOOL_STRINGS:
            return _BOOL_STRINGS[key]
        raise ValueError(f"unrecognized boolean string: {value!r}")
    raise ValueError(f"cannot convert {type(value).__name__} to bool")


def to_int(value) -> int:
    """"0042"->42，"3.0"->3，"3.5" 报错，布尔报错。"""
    if isinstance(value, bool):
        raise ValueError("boolean cannot be converted to int")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError(f"non-integer number: {value!r}")
    if isinstance(value, str):
        text = value.strip()
        try:
            number = float(text)
        except ValueError:
            raise ValueError(f"cannot convert string {value!r} to int")
        if number.is_integer():
            return int(number)
        raise ValueError(f"non-integer number: {value!r}")
    raise ValueError(f"cannot convert {type(value).__name__} to int")


def to_id_string(value) -> str:
    """输出字符串，保留前导零；数字 1001 -> "1001"，非整数数字报错。"""
    if isinstance(value, bool):
        raise ValueError("boolean cannot be converted to id string")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        raise ValueError(f"non-integer number for id: {value!r}")
    if isinstance(value, str):
        return value.strip()
    raise ValueError(f"cannot convert {type(value).__name__} to id string")


def to_status(value) -> str:
    """只接受 active/inactive/terminated/on_leave。"""
    if isinstance(value, str):
        text = value.strip()
        if text in STATUSES:
            return text
    raise ValueError(f"invalid status: {value!r}")


CONVERTERS = {
    "date": to_date,
    "bool": to_bool,
    "int": to_int,
    "id": to_id_string,
    "status": to_status,
    "string": lambda v: v.strip() if isinstance(v, str) else str(v),
}
