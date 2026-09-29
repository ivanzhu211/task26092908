"""路径解析与取值测试。"""

import pytest

from field_mapper.paths import MISSING, extract, parse_path


class TestParsePath:
    @pytest.mark.parametrize("path,expected", [
        ("a", ["a"]),
        ("a.b.c", ["a", "b", "c"]),
        ("a[0]", ["a", 0]),
        ("a.b[2].c", ["a", "b", 2, "c"]),
        ("items[10]", ["items", 10]),
    ])
    def test_valid(self, path, expected):
        assert parse_path(path) == expected

    @pytest.mark.parametrize("path", ["", "  ", ".a", "a..b", "a[]", "a[x]", "a[", None])
    def test_invalid(self, path):
        with pytest.raises((ValueError, TypeError)):
            parse_path(path)


class TestExtract:
    SOURCE = {
        "emp": {
            "name": {"first": "Ada"},
            "tags": ["x", "y"],
            "nil": None,
            "blank": "   ",
            "zero": 0,
            "no": False,
        },
    }

    def test_nested_and_index(self):
        assert extract(self.SOURCE, "emp.name.first") == "Ada"
        assert extract(self.SOURCE, "emp.tags[1]") == "y"

    def test_falsy_but_present_values_kept(self):
        assert extract(self.SOURCE, "emp.zero") == 0
        assert extract(self.SOURCE, "emp.no") is False

    @pytest.mark.parametrize("path", [
        "emp.missing",          # 键不存在
        "emp.name.first.deep",  # 中途穿过非对象
        "emp.tags[5]",          # 下标越界
        "emp.nil",              # null
        "emp.blank",            # 只有空白字符
        "emp.nil.x",            # 穿过 null
    ])
    def test_missing(self, path):
        assert extract(self.SOURCE, path) is MISSING
