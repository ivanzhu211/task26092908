"""类型转换边界测试。"""

import pytest

from field_mapper.types import to_bool, to_date, to_id_string, to_int, to_status


class TestToDate:
    @pytest.mark.parametrize("value,expected", [
        ("2024-02-29", "2024-02-29"),      # 闰年 2 月 29 日
        ("2000-02-29", "2000-02-29"),      # 整百年闰年
        (" 2024-01-15 ", "2024-01-15"),    # 首尾空白
        ("2/3/2024", "2024-02-03"),        # 月日省前导零
        ("02/03/2024", "2024-02-03"),
        ("12/31/2024", "2024-12-31"),
        ("20240229", "2024-02-29"),        # 8 位数字字符串
        (20240229, "2024-02-29"),          # 8 位整数
        ("2024-03-01T00:30:00+08:00", "2024-02-29"),  # 跨日：东八区 -> UTC 前一天
        ("2024-02-29T23:30:00-02:00", "2024-03-01"),  # 跨日：西二区 -> UTC 后一天
        ("2024-06-15T12:00:00Z", "2024-06-15"),
        ("2024-06-15T12:00:00+00:00", "2024-06-15"),
    ])
    def test_valid(self, value, expected):
        assert to_date(value) == expected

    @pytest.mark.parametrize("value", [
        "2023-02-29",      # 非闰年 2 月 29 日
        "1900-02-29",      # 整百年非闰年
        "2024-13-01",      # 不存在的月份
        "2024-04-31",      # 不存在的日
        "20240230",        # 8 位但不存在的日期
        "13/01/2024",      # 美式格式月超界
        "2024-03-01T10:00:00",   # 不带时区的时间
        "2024-03-01 10:00:00",
        "2024/01/15",      # 不支持的格式
        "yesterday",
        2024,              # 非 8 位整数
        20240229.5,
        True,
        None,
        ["2024-01-01"],
    ])
    def test_invalid(self, value):
        with pytest.raises(ValueError):
            to_date(value)


class TestToBool:
    @pytest.mark.parametrize("value,expected", [
        (True, True), (False, False),
        (0, False), (1, True),
        ("true", True), ("FALSE", False),
        (" Yes ", True), ("nO", False),
        ("1", True), (" 0 ", False),
    ])
    def test_valid(self, value, expected):
        assert to_bool(value) is expected

    @pytest.mark.parametrize("value", [2, -1, 100, "2", "on", "off", "y", "n", "", 0.0, 1.0, None, []])
    def test_invalid_not_silently_false(self, value):
        with pytest.raises(ValueError):
            to_bool(value)


class TestToInt:
    @pytest.mark.parametrize("value,expected", [
        ("0042", 42),      # 前导零
        (" 7 ", 7),
        ("3.0", 3),        # 整数值的小数字符串
        (3.0, 3),
        (0, 0),
        (-5, -5),
        ("-5", -5),
    ])
    def test_valid(self, value, expected):
        assert to_int(value) == expected

    @pytest.mark.parametrize("value", [
        "3.5", 3.5,        # 非整数
        True, False,       # 布尔不能当整数
        "abc", "", None, [1],
    ])
    def test_invalid(self, value):
        with pytest.raises(ValueError):
            to_int(value)


class TestToIdString:
    @pytest.mark.parametrize("value,expected", [
        ("007", "007"),        # 保留前导零
        (" 007 ", "007"),
        (1001, "1001"),        # 数字转字符串
        (1001.0, "1001"),
        (0, "0"),
    ])
    def test_valid(self, value, expected):
        assert to_id_string(value) == expected

    @pytest.mark.parametrize("value", [1001.5, True, None, {"a": 1}])
    def test_invalid(self, value):
        with pytest.raises(ValueError):
            to_id_string(value)


class TestToStatus:
    @pytest.mark.parametrize("value", ["active", "inactive", "terminated", "on_leave"])
    def test_valid(self, value):
        assert to_status(value) == value

    @pytest.mark.parametrize("value", ["Active", "ACTIVE", "quit", "", 1, None])
    def test_invalid(self, value):
        with pytest.raises(ValueError):
            to_status(value)
