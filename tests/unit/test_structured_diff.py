"""craft/structured_diff.py unit tests — symbol-level hunks, honest
line-level fallback, and schema serializability (计划书 §14.5)."""

from __future__ import annotations

import json

from craft.structured_diff import compute_structured_diff


def test_python_rename_emits_rename_symbol_hunk() -> None:
    before = (
        "def compute(x):\n"
        "    return compute(x)\n"
        "\n"
        "\n"
        "def other():\n"
        "    return compute(1)\n"
    )
    after = (
        "def calculate(x):\n"
        "    return calculate(x)\n"
        "\n"
        "\n"
        "def other():\n"
        "    return calculate(1)\n"
    )
    diff = compute_structured_diff(before, after, "calc.py")
    assert diff["mode"] == "python"
    rename = next(hunk for hunk in diff["hunks"] if hunk["kind"] == "rename_symbol")
    assert rename["symbols"] == ["compute", "calculate"]
    assert rename["before"] == "def compute(x):\n    return compute(x)"
    assert rename["after"] == "def calculate(x):\n    return calculate(x)"
    modify = next(hunk for hunk in diff["hunks"] if hunk["kind"] == "modify_function")
    assert modify["symbols"] == ["other"]
    assert "calculate(1)" in modify["after"]


def test_python_insert_import_hunk() -> None:
    diff = compute_structured_diff("x = 1\n", "from os.path import join\nx = 1\n", "calc.py")
    assert diff["mode"] == "python"
    hunk = next(h for h in diff["hunks"] if h["kind"] == "insert_import")
    assert hunk["symbols"] == ["os.path.join"]
    assert hunk["before"] == ""
    assert hunk["after"] == "from os.path import join"


def test_python_insert_method_hunk() -> None:
    before = "class Calc:\n    def add(self, a, b):\n        return a + b\n"
    after = (
        "class Calc:\n"
        "    def add(self, a, b):\n"
        "        return a + b\n"
        "\n"
        "    def sub(self, a, b):\n"
        "        return a - b\n"
    )
    diff = compute_structured_diff(before, after, "calc.py")
    hunk = next(h for h in diff["hunks"] if h["kind"] == "insert_method")
    assert hunk["symbols"] == ["Calc.sub"]
    assert "def sub(self, a, b):" in hunk["after"]


def test_python_delete_function_hunk() -> None:
    before = "def keep():\n    return 1\n\n\ndef drop():\n    return 2\n"
    after = "def keep():\n    return 1\n"
    diff = compute_structured_diff(before, after, "calc.py")
    hunk = next(h for h in diff["hunks"] if h["kind"] == "delete_function")
    assert hunk["symbols"] == ["drop"]
    assert hunk["before"] == "def drop():\n    return 2"


def test_class_attribute_change_is_modify_class() -> None:
    before = "class Config:\n    retries = 1\n"
    after = "class Config:\n    retries = 2\n"
    diff = compute_structured_diff(before, after, "cfg.py")
    assert [hunk["kind"] for hunk in diff["hunks"]] == ["modify_class"]
    assert diff["hunks"][0]["symbols"] == ["Config"]


def test_non_python_path_uses_honest_line_level_hunks() -> None:
    diff = compute_structured_diff("a\nb\n", "a\nc\n", "notes.txt")
    assert diff["mode"] == "text"
    kinds = {hunk["kind"] for hunk in diff["hunks"]}
    assert kinds <= {"insert_lines", "delete_lines", "replace_lines"}
    assert all(hunk["symbols"] == [] for hunk in diff["hunks"])
    assert any("b" in hunk["before"] for hunk in diff["hunks"])
    assert any("c" in hunk["after"] for hunk in diff["hunks"])


def test_python_syntax_error_falls_back_to_line_level() -> None:
    diff = compute_structured_diff("def broken(:\n", "def fixed(:\n", "broken.py")
    assert diff["mode"] == "text"
    kinds = {hunk["kind"] for hunk in diff["hunks"]}
    assert kinds <= {"insert_lines", "delete_lines", "replace_lines"}


def test_identical_texts_have_no_hunks() -> None:
    diff = compute_structured_diff("x = 1\n", "x = 1\n", "calc.py")
    assert diff["mode"] == "python"
    assert diff["hunks"] == []


def test_schema_is_json_serializable() -> None:
    diff = compute_structured_diff(
        "def f():\n    return 1\n", "def g():\n    return 1\n", "calc.py"
    )
    payload = json.loads(json.dumps(diff))
    assert set(payload) == {"path", "mode", "hunks"}
    for hunk in payload["hunks"]:
        assert set(hunk) == {"kind", "before", "after", "symbols"}


def test_crlf_input_is_normalized() -> None:
    diff = compute_structured_diff(
        "def f():\r\n    return 1\r\n", "def g():\r\n    return 1\r\n", "calc.py"
    )
    hunk = next(h for h in diff["hunks"] if h["kind"] == "rename_symbol")
    assert hunk["symbols"] == ["f", "g"]
