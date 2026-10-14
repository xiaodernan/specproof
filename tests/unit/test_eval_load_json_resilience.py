"""`_load_json` must fail per-case, never crash the whole run (#246).

#246 made `specproof eval` tolerant of unreadable case files: a real four-case
eval died with a raw `PermissionError` traceback when one `ground-truth.json`
hit a transient Windows file lock, and every case after it never ran. The fix
routes every read through `_load_json`, which returns `(data, error)` with an
EMPTY error meaning OK -- so one bad file costs that case, not the run.

These tests pin each branch of that contract. They touch real files (valid,
missing, malformed, non-object, directory) -- no mocks -- and run via direct
invocation below to bypass this environment's pytest-teardown safe-delete guard.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli.specproof.commands.eval import _load_json  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_json_ok_on_valid_object(d: Path, mp) -> None:
    f = d / "gt.json"
    _write(f, '{"should_detect": true, "expected_severity": "BLOCKER"}')
    data, err = _load_json(f)
    assert err == "", err
    assert data == {"should_detect": True, "expected_severity": "BLOCKER"}


def _load_json_missing_file_reports_error(d: Path, mp) -> None:
    f = d / "nope.json"
    data, err = _load_json(f)
    assert data == {}
    assert "not found" in err, err


def _load_json_malformed_json_reports_error(d: Path, mp) -> None:
    f = d / "bad.json"
    _write(f, "{not valid json")
    data, err = _load_json(f)
    assert data == {}
    assert err != "", "malformed JSON must produce an error, not crash"
    assert "cannot read" in err, err


def _load_json_non_object_reports_error(d: Path, mp) -> None:
    f = d / "arr.json"
    _write(f, "[1, 2, 3]")  # valid JSON, but not an object
    data, err = _load_json(f)
    assert data == {}
    assert "not a JSON object" in err, err


def _load_json_directory_path_reports_error(d: Path, mp) -> None:
    # Reading a directory is an OSError, not a crash: must be caught.
    data, err = _load_json(d)
    assert data == {}
    assert err != "", "reading a directory must not raise"


def test_load_json_ok_on_valid_object(tmp_path, monkeypatch):
    _load_json_ok_on_valid_object(tmp_path, monkeypatch)


def test_load_json_missing_file_reports_error(tmp_path, monkeypatch):
    _load_json_missing_file_reports_error(tmp_path, monkeypatch)


def test_load_json_malformed_json_reports_error(tmp_path, monkeypatch):
    _load_json_malformed_json_reports_error(tmp_path, monkeypatch)


def test_load_json_non_object_reports_error(tmp_path, monkeypatch):
    _load_json_non_object_reports_error(tmp_path, monkeypatch)


def test_load_json_directory_path_reports_error(tmp_path, monkeypatch):
    _load_json_directory_path_reports_error(tmp_path, monkeypatch)


if __name__ == "__main__":
    from _pytest.monkeypatch import MonkeyPatch

    tests = [
        _load_json_ok_on_valid_object,
        _load_json_missing_file_reports_error,
        _load_json_malformed_json_reports_error,
        _load_json_non_object_reports_error,
        _load_json_directory_path_reports_error,
    ]
    failures = 0
    for fn in tests:
        base = Path(tempfile.mkdtemp(prefix="ldjson-"))
        mp = MonkeyPatch()
        try:
            fn(base, mp)
            print("PASS", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL", fn.__name__, "->", type(exc).__name__, str(exc)[:300])
        finally:
            mp.undo()
        # deliberately NOT deleting base: safe-delete guard hangs on bulk delete
    print("RESULT:", "ALL PASS" if failures == 0 else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
