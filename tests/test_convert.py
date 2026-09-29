"""Boundary tests for every type conversion."""

import pytest

from mapping_engine.convert import convert


class TestInt:
    @pytest.mark.parametrize("raw,expected", [
        ("0042", 42),
        ("3.0", 3),
        (3.0, 3),
        (" -7 ", -7),
        (0, 0),
        ("0", 0),
    ])
    def test_valid(self, raw, expected):
        assert convert(raw, "int") == expected

    @pytest.mark.parametrize("raw", [
        "3.5", 3.5, True, False, "abc", "", "1e3x", None,
    ])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            convert(raw, "int")

    def test_bool_not_int(self):
        with pytest.raises(ValueError):
            convert(True, "int")


class TestBool:
    @pytest.mark.parametrize("raw,expected", [
        (True, True), (False, False),
        (1, True), (0, False),
        ("true", True), ("TRUE", True), (" True ", True),
        ("false", False), ("False", False),
        ("yes", True), ("YES", True), (" yEs ", True),
        ("no", False), ("NO", False),
        ("1", True), ("0", False), (" 1 ", True),
    ])
    def test_valid(self, raw, expected):
        assert convert(raw, "bool") is expected

    @pytest.mark.parametrize("raw", [2, -1, 7, "2", "maybe", "on", "off", "", None, 1.0])
    def test_invalid_not_silently_false(self, raw):
        with pytest.raises(ValueError):
            convert(raw, "bool")


class TestDate:
    @pytest.mark.parametrize("raw,expected", [
        ("2024-02-29", "2024-02-29"),   # leap year
        ("2023-03-05", "2023-03-05"),
        ("3/5/2024", "2024-03-05"),     # no leading zeros
        ("03/05/2024", "2024-03-05"),
        ("12/31/1999", "1999-12-31"),
        (20240305, "2024-03-05"),       # 8-digit int
        ("20240305", "2024-03-05"),     # 8-digit string
        ("2024-03-05T16:00:00+08:00", "2024-03-05"),
        ("2024-03-05T23:30:00-02:00", "2024-03-06"),  # crosses UTC day
        ("2024-03-05T01:30:00+05:00", "2024-03-04"),  # crosses back
        ("2024-03-05T16:00:00Z", "2024-03-05"),
        ("2024-03-05T16:00:00.123+00:00", "2024-03-05"),
    ])
    def test_valid(self, raw, expected):
        assert convert(raw, "date") == expected

    @pytest.mark.parametrize("raw", [
        "2023-02-29",   # not a leap year
        "2024-02-30",
        "2024-13-01",
        "2024-00-10",
        "13/01/2024",   # month 13 in MM/DD/YYYY
        "2024-03-05T16:00:00",  # datetime without timezone
        "2024030",      # 7 digits
        "202403050",    # 9 digits
        20241301,       # invalid month as int
        "not-a-date",
        "",
        None,
        True,
    ])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            convert(raw, "date")


class TestIdString:
    @pytest.mark.parametrize("raw,expected", [
        (1001, "1001"),
        ("0076", "0076"),       # leading zeros preserved
        (" 0042 ", "0042"),
        (0, "0"),
        (1001.0, "1001"),
    ])
    def test_valid(self, raw, expected):
        assert convert(raw, "id_string") == expected

    @pytest.mark.parametrize("raw", [1001.5, True, "", "   ", None])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            convert(raw, "id_string")


class TestStatus:
    @pytest.mark.parametrize("value", ["active", "inactive", "terminated", "on_leave"])
    def test_valid(self, value):
        assert convert(value, "status") == value

    def test_trimmed(self):
        assert convert("  active ", "status") == "active"

    @pytest.mark.parametrize("raw", ["Active", "ACTIVE", "on leave", "A", "", 1, None])
    def test_invalid(self, raw):
        with pytest.raises(ValueError):
            convert(raw, "status")


class TestString:
    @pytest.mark.parametrize("raw,expected", [
        ("  hi ", "hi"),
        (42, "42"),
        (3.0, "3"),
        (3.5, "3.5"),
    ])
    def test_valid(self, raw, expected):
        assert convert(raw, "string") == expected

    def test_unknown_transform(self):
        with pytest.raises(ValueError):
            convert("x", "teleport")
