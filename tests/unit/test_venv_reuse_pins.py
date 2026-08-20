"""Offline regression tests for era-pin application to a REUSED shared
venv (no network, no Docker, no real LLM).

Real SWE-bench LLM run evidence (docs/eval/swebench-llm-results-v7.json):
after the W140 flask pin (_REPO_DEP_PINS = {'flask': ['werkzeug<3.0']}),
both pallets__flask instances cleared understand+verify but STUCK in the
TEST step with "ImportError: cannot import name url_quote from
werkzeug.urls". The pin only took effect when the instance deps were
installed into a FRESH venv; the harness REUSES the shared venv from
earlier runs (v5/v6 already installed werkzeug 3.x into it) and the
reuse path never re-applied the pins. Fix under test: on a REUSED venv
the repo's era pins are installed explicitly (idempotent downgrade)
BEFORE the deps install, recorded per instance as deps.pins_applied;
a pin-application failure is recorded in deps.install_error and never
fatal.

Covers:
  (a) reused venv + flask pins -> the pin specs pip install runs with the
      venv python (before the deps install) and deps.pins_applied records
      the applied specs;
  (b) reused venv + no pins -> no extra pip call, deps.pins_applied empty;
  (c) pin-application failure is recorded (deps.install_error) and not
      fatal — craft still runs (the record fails at the craft stage,
      never at the deps stage).
"""

from __future__ import annotations

import importlib.util
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_SCRIPT = REPO_ROOT / "scripts" / "bench_swebench.py"

_REUSED_NOTE_SUFFIX = " (pytest --version 验证通过)"


def _load_harness() -> Any:
    """Import scripts/bench_swebench.py as a fresh module (in-process)."""
    spec = importlib.util.spec_from_file_location(
        "bench_swebench_venv_reuse_under_test", BENCH_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _StubSubprocess(SimpleNamespace):
    """Fake subprocess module (no real pip/git); records every command."""

    def __init__(self) -> None:
        super().__init__(TimeoutExpired=subprocess.TimeoutExpired)
        self.commands: list[list[str]] = []
        self.returncode = 0
        self.fail_rule: Callable[[list[str]], bool] | None = None

    def run(self, command: list[str], **kwargs: Any) -> Any:
        del kwargs
        self.commands.append(list(command))
        failed = self.returncode != 0 or (
            self.fail_rule is not None and self.fail_rule(command)
        )
        return subprocess.CompletedProcess(
            list(command),
            1 if failed else 0,
            "",
            "stub failure" if failed else "",
        )


def _flask_instance() -> dict[str, Any]:
    return {
        "instance_id": "pallets__flask-4045",
        "repo": "pallets/flask",
        "base_commit": "0123456789abcdef",
        "problem_statement": "修复 werkzeug 3.0 的 url_quote 导入",
        "test_patch": "",
        "FAIL_TO_PASS": ["tests/test_import.py::test_url_quote"],
        "PASS_TO_PASS": [],
    }


def _django_instance() -> dict[str, Any]:
    return {
        "instance_id": "django__django-1",
        "repo": "django/django",
        "base_commit": "0123456789abcdef",
        "problem_statement": "无 flask pins 的控制实例",
        "test_patch": "",
        "FAIL_TO_PASS": ["tests/test_x.py::test_x"],
        "PASS_TO_PASS": [],
    }


def _run_reused_venv_instance(
    harness: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    instance: dict[str, Any],
    stub: _StubSubprocess,
) -> tuple[dict[str, Any], str]:
    """Drive run_instance (llm mode) with a REUSED venv, stubbed git/pip.

    _checkout_instance is stubbed to a plain copy of the prepared repo
    dir; _run_craft is stubbed to a STUCK report so the record fails at
    the CRAFT stage — proving the deps stage (pin application included)
    never blocks the craft run.
    """
    workdir = tmp_path / "repo"
    workdir.mkdir()
    (workdir / "setup.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(harness, "subprocess", stub)

    def fake_checkout(
        instance: Any, repo_dir: Path, work_root: Path
    ) -> tuple[Path, dict[str, str]]:
        del repo_dir, work_root
        return (
            workdir,
            {
                "method": "copy",
                "source": str(workdir),
                "base_commit": str(instance["base_commit"]),
                "detail": "非 git 目录直接拷贝",
            },
        )

    monkeypatch.setattr(harness, "_checkout_instance", fake_checkout)

    def fake_run_craft(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        return {"result": "STUCK", "steps": []}

    monkeypatch.setattr(harness, "_run_craft", fake_run_craft)

    def dummy_client_factory(job_id: str) -> object:
        del job_id
        return object()

    venv_python = str(tmp_path / "shared-venv" / "python.exe")
    venv = {
        "python": venv_python,
        "error": "",
        "note": harness._VENV_REUSED_NOTE + _REUSED_NOTE_SUFFIX,
    }
    record = harness.run_instance(
        instance,
        repo_dir=tmp_path / "repos",
        work_root=tmp_path / "work",
        logs_dir=tmp_path / "logs",
        fix_registry={},
        exec_timeout=30,
        max_iterations=1,
        mode="llm",
        llm_client_factory=dummy_client_factory,
        venv=venv,
        deps_timeout=30,
    )
    return record, venv_python


# -- (a) reused venv + flask pins -----------------------------------------


def test_reused_venv_flask_pins_applied_before_deps_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _load_harness()
    stub = _StubSubprocess()
    record, venv_python = _run_reused_venv_instance(
        harness, monkeypatch, tmp_path, _flask_instance(), stub
    )
    pin_cmd = [
        venv_python, "-m", "pip", "install", "--no-input",
        "--disable-pip-version-check", "werkzeug<3.0",
    ]
    assert stub.commands[0] == pin_cmd
    # the ordinary deps install follows and still appends the pin
    assert len(stub.commands) == 2
    assert stub.commands[1][:2] == [venv_python, "-m"]
    assert stub.commands[1][-2:] == [".", "werkzeug<3.0"]
    deps = record["deps"]
    assert deps["pins_applied"] == ["werkzeug<3.0"]
    assert deps["pins"] == ["werkzeug<3.0"]
    assert deps["installed"] is True
    assert deps["install_error"] == ""
    # the deps stage never blocked craft
    assert record["stage"] == "craft"


# -- (b) reused venv + no pins --------------------------------------------


def test_reused_venv_without_pins_makes_no_extra_pip_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _load_harness()
    stub = _StubSubprocess()
    record, venv_python = _run_reused_venv_instance(
        harness, monkeypatch, tmp_path, _django_instance(), stub
    )
    # only the ordinary deps install runs — no pin-application call
    assert len(stub.commands) == 1
    assert stub.commands[0][0] == venv_python
    assert stub.commands[0][-1] == "."
    deps = record["deps"]
    assert deps["pins_applied"] == []
    assert deps["pins"] == []
    assert record["stage"] == "craft"


# -- (c) pin-apply failure recorded, never fatal --------------------------


def test_pin_apply_failure_recorded_and_never_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _load_harness()
    stub = _StubSubprocess()

    def fail_only_pin(command: list[str]) -> bool:
        # the pin-application command carries the pin spec but no "."
        # argument; the ordinary deps install (".", *pins) still succeeds.
        return command[-1] == "werkzeug<3.0" and command[-2] != "."

    stub.fail_rule = fail_only_pin
    record, venv_python = _run_reused_venv_instance(
        harness, monkeypatch, tmp_path, _flask_instance(), stub
    )
    # the pin application was attempted with the venv python, then failed
    assert stub.commands[0][0] == venv_python
    assert stub.commands[0][-1] == "werkzeug<3.0"
    assert len(stub.commands) == 2
    deps = record["deps"]
    assert deps["pins_applied"] == []
    assert "era pin 应用失败" in deps["install_error"]
    assert deps["installed"] is True
    assert deps["pins"] == ["werkzeug<3.0"]
    # never fatal: craft still ran; the record failed at the craft stage
    assert record["stage"] == "craft"
    assert "craft 未收敛" in record["reason"]
