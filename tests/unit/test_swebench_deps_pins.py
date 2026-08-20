"""Offline regression tests for era-compatible dependency pins and the
W114 v5 candidate-file union (no network, no Docker, no real LLM).

Real SWE-bench LLM run evidence (docs/eval/swebench-llm-results-v5.json):

- pallets__flask-4045 STUCK with "ImportError: cannot import name url_quote
  from werkzeug.urls": the shared venv resolved werkzeug 3.x for a flask
  2.3-era instance (url_quote was removed in werkzeug 3.1). The deps
  install now appends era pins (_REPO_DEP_PINS, flask -> werkzeug<3.1)
  for matching repo slugs ONLY and records them as deps.pins — everything
  else keeps current behavior (deps failure still recorded, never fatal).
- pallets__flask-4992: the W114 rebuilt verify criterion kept the keyword
  'tomllib' but no candidate source file contained it — the plan targeted
  only test files and the candidate union never reached src/flask/config.py
  at verify time. The union now also includes the SPEC's affected_area_hint
  and the files referenced in the diagnose reply.

Covers:
  (a) a flask repo install appends the werkzeug<3.1 pin and returns it in
      the install result (stubbed pip runner; the harness call site copies
      this list verbatim into deps.pins);
  (b) a non-flask repo install pins nothing (command and result unchanged);
  (c) criterion candidates include files referenced in the diagnose reply
      (scripted loop, offline).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from craft.llm import LLMClient
from craft.loop import CraftLoop
from craft.planner import Plan, Step, SuccessCriteria
from craft.spec import TaskSpec, parse_spec_text
from providers.base import LLMMessage, LLMResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_SCRIPT = REPO_ROOT / "scripts" / "bench_swebench.py"

# 影响行故意留空: (c) 的诊断回复路径必须独立于 affected_area_hint 生效。
PIN_SPEC = (
    "修复 flask 配置模块的 tomllib 加载\n"
    "config 模块需要支持 tomllib 读取\n"
    "验收: tomllib 断言出现\n"
)

S1_FIX_PROPOSAL = json.dumps(
    {
        "diagnosis": (
            "根因在 src/flask/config.py 的 tomllib 加载逻辑; "
            "app.py 缺少 FIX_MARKER_PRESENT 标记"
        ),
        "edits": [
            {
                "action": "apply_edit",
                "path": "src/flask/app.py",
                "old": "def app():\n    return 1\n",
                "new": "FIX_MARKER_PRESENT = 1\n\ndef app():\n    return 1\n",
            }
        ],
    },
    ensure_ascii=False,
)


def _load_harness() -> Any:
    """Import scripts/bench_swebench.py as a fresh module (in-process)."""
    spec = importlib.util.spec_from_file_location(
        "bench_swebench_pins_under_test", BENCH_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _StubSubprocess(SimpleNamespace):
    """Fake subprocess module for _install_instance_deps (no real pip)."""

    def __init__(self) -> None:
        super().__init__(TimeoutExpired=subprocess.TimeoutExpired)
        self.commands: list[list[str]] = []
        self.returncode = 0

    def run(self, command: list[str], **kwargs: Any) -> Any:
        del kwargs
        self.commands.append(list(command))
        return subprocess.CompletedProcess(list(command), self.returncode, "", "")


class _ScriptedClient(LLMClient):
    """chat_sync override replaying canned replies; records every prompt."""

    def __init__(self, replies: list[str], *, job_id: str = "job-pins") -> None:
        super().__init__(provider=None, token_budget=100_000, job_id=job_id)
        self._replies = list(replies)
        self.sent_prompts: list[str] = []

    def chat_sync(
        self,
        messages: list[LLMMessage],
        *,
        label: str,
        kind: str | None = None,
        job_id: str = "",
        step_id: str = "",
        thinking: bool = False,
        response_format: dict[str, Any] | None = None,
        estimated_prompt_tokens: int = 0,
        timeout: float | None = None,
    ) -> LLMResponse:
        del kind, job_id, step_id, thinking, estimated_prompt_tokens, timeout
        del response_format
        self.sent_prompts.append(messages[0].content)
        reply = self._replies[min(len(self.sent_prompts) - 1, len(self._replies) - 1)]
        usage = {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        entry = self.budget.record(usage, label=label)
        self.calls.append({**entry, "job_id": self.job_id, "model": "fake-pins"})
        return LLMResponse(content=reply, usage=usage, model="fake-pins")


# -- (a) flask repo install appends the era pin -------------------------------


def test_flask_repo_install_appends_werkzeug_pin_and_records_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _load_harness()
    assert harness._REPO_DEP_PINS == {"flask": ["werkzeug<3.1"]}
    stub = _StubSubprocess()
    monkeypatch.setattr(harness, "subprocess", stub)
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    result = harness._install_instance_deps(
        sys.executable, tmp_path, "pyproject.toml", 300, "pallets/flask"
    )
    assert result["installed"] is True
    assert result["pins"] == ["werkzeug<3.1"]
    assert len(stub.commands) == 1
    assert stub.commands[0][-2:] == [".", "werkzeug<3.1"]

    # slug normalization: a .git URL repo resolves to the same pin
    assert harness._pins_for_repo("https://github.com/pallets/flask.git") == [
        "werkzeug<3.1"
    ]
    # the requirements.txt marker shape keeps -r and appends the pin
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
    req = harness._install_instance_deps(
        sys.executable, tmp_path, "requirements.txt", 300, "pallets/flask"
    )
    assert req["pins"] == ["werkzeug<3.1"]
    assert stub.commands[1][-3:] == ["-r", "requirements.txt", "werkzeug<3.1"]

    # a FAILED install still records the pins that were attempted
    stub.returncode = 1
    failed = harness._install_instance_deps(
        sys.executable, tmp_path, "pyproject.toml", 300, "pallets/flask"
    )
    assert failed["installed"] is False
    assert failed["pins"] == ["werkzeug<3.1"]
    assert failed["error"]


# -- (b) non-flask repo install pins nothing ----------------------------------


def test_non_flask_repo_install_pins_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _load_harness()
    stub = _StubSubprocess()
    monkeypatch.setattr(harness, "subprocess", stub)
    (tmp_path / "setup.py").write_text("", encoding="utf-8")

    result = harness._install_instance_deps(
        sys.executable, tmp_path, "setup.py", 300, "django/django"
    )
    assert result["installed"] is True
    assert result["pins"] == []
    assert len(stub.commands) == 1
    assert stub.commands[0][-1] == "."
    assert "werkzeug<3.1" not in stub.commands[0]


# -- (c) criterion candidates include diagnose-reply files --------------------


def _config_repo(tmp_path: Path) -> None:
    (tmp_path / "src" / "flask").mkdir(parents=True)
    (tmp_path / "src" / "flask" / "app.py").write_text(
        "def app():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "src" / "flask" / "config.py").write_text(
        "import tomllib\n\n\ndef load_config(path):\n"
        "    with open(path, 'rb') as handle:\n"
        "        return tomllib.load(handle)\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_config.py").write_text(
        "def test_config():\n    return None\n", encoding="utf-8"
    )


def _pins_plan() -> Plan:
    return Plan(
        task_title="flask config tomllib 修复",
        mode="llm",
        steps=[
            Step(
                id="s1",
                kind="modify",
                target_files=["src/flask/app.py"],
                intent="补上 FIX_MARKER_PRESENT 标记",
                success_criteria=SuccessCriteria("grep", "FIX_MARKER_PRESENT"),
            ),
            Step(
                id="s2",
                kind="verify",
                target_files=["tests/test_config.py"],
                intent="机械核验 tomllib 断言出现在源文件",
                success_criteria=SuccessCriteria("grep", "."),
            ),
        ],
        risk_classification={
            "auth": False,
            "migration": False,
            "mq": False,
            "public_api": False,
        },
        budget_alloc={"iterations": 4, "tokens": 50_000},
    )


def test_criterion_candidates_include_diagnosis_referenced_files(
    tmp_path: Path,
) -> None:
    _config_repo(tmp_path)
    spec = parse_spec_text(PIN_SPEC)
    plan = _pins_plan()
    client = _ScriptedClient([S1_FIX_PROPOSAL])
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-pins-candidates",
        fix_registry={},
        exec_mode="local",
        client=client,
    )
    report = loop.run()
    assert report["result"] == "DONE"
    assert report["steps"][1]["status"] == "green"
    # only s1 entered the diagnose loop; s2 greened on the first check
    assert len(client.sent_prompts) == 1
    # the union now reaches src/flask/config.py via the diagnose reply
    assert "src/flask/config.py" in loop._candidate_source_files()

    # control: without a diagnose reply, config.py is not a candidate
    loop2 = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-pins-no-diagnosis",
        fix_registry={},
        exec_mode="local",
    )
    assert "src/flask/config.py" not in loop2._candidate_source_files()
    assert "src/flask/app.py" in loop2._candidate_source_files()

    # the SPEC's affected_area_hint joins the union the same way
    hinted_spec = TaskSpec(
        title="修复配置",
        description="tomllib 加载",
        acceptance_criteria=["tomllib 断言出现"],
        forbidden_changes=[],
        affected_area_hint="src/flask/config.py",
    )
    loop3 = CraftLoop(
        hinted_spec,
        plan,
        tmp_path,
        job_id="job-pins-hint",
        fix_registry={},
        exec_mode="local",
    )
    assert "src/flask/config.py" in loop3._candidate_source_files()
