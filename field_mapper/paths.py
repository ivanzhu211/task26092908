"""源数据路径提取：支持嵌套对象与数组下标，路径中途断掉算缺值。"""

from __future__ import annotations

import re

MISSING = object()  # 哨兵：表示缺值

_SEGMENT_RE = re.compile(r"([^.[\]]+)|\[(\d+)\]")


def parse_path(path: str) -> list[str | int]:
    """把 "a.b[0].c" 解析为 ["a", 0, "c"]。空路径或非法格式抛 ValueError。"""
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"invalid path: {path!r}")
    segments: list[str | int] = []
    for part in path.split("."):
        if not part:
            raise ValueError(f"invalid path: {path!r}")
        pos = 0
        for match in _SEGMENT_RE.finditer(part):
            if match.start() != pos:
                raise ValueError(f"invalid path: {path!r}")
            name, index = match.groups()
            segments.append(name if name is not None else int(index))
            pos = match.end()
        if pos != len(part) or pos == 0:
            raise ValueError(f"invalid path: {path!r}")
    return segments


def extract(source: dict, path: str):
    """按路径取值；不存在、为 None、或去首尾空白后为空的字符串都返回 MISSING。"""
    current = source
    for segment in parse_path(path):
        if isinstance(segment, int):
            if not isinstance(current, list) or segment >= len(current):
                return MISSING
            current = current[segment]
        else:
            if not isinstance(current, dict) or segment not in current:
                return MISSING
            current = current[segment]
    if current is None:
        return MISSING
    if isinstance(current, str) and not current.strip():
        return MISSING
    return current
