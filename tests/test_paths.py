"""Path extraction and missing-value semantics."""

from mapping_engine.paths import MISSING, extract, is_missing


def test_nested_object():
    src = {"a": {"b": {"c": 1}}}
    assert extract(src, "a.b.c") == 1


def test_array_index():
    src = {"items": [{"v": "x"}, {"v": "y"}]}
    assert extract(src, "items.0.v") == "x"
    assert extract(src, "items.1.v") == "y"


def test_dangling_path_is_missing():
    src = {"a": {"b": 1}, "list": [1]}
    assert extract(src, "a.b.c") is MISSING
    assert extract(src, "a.x.y") is MISSING
    assert extract(src, "nope") is MISSING
    assert extract(src, "list.5") is MISSING
    assert extract(src, "list.x") is MISSING
    assert extract(src, "a.b.0") is MISSING  # index into non-list


def test_missing_semantics():
    assert is_missing(MISSING)
    assert is_missing(None)
    assert is_missing("")
    assert is_missing("   ")
    assert is_missing("\t\n ")
    assert not is_missing(0)
    assert not is_missing(False)
    assert not is_missing("0")
    assert not is_missing(" x ")
