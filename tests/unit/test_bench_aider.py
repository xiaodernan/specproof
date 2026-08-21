"""Offline unit tests for the Aider polyglot harness (no network, no Docker, no LLM).

The real LLMClient is replaced by a deterministic FAKE client (subclass of
craft.llm.LLMClient with chat_sync overridden), injected through the harness's
`_build_llm_client` factory. Everything else — task scanning, workdir reset,
prompt writing, craft loop, test-file integrity guard, per-language test run —
is the real harness code.

Covered here:
- llm mode with the fake: one task resolves (fake proposes the right edit),
  one stays honestly unresolved with a non-empty reason;
- an unsupported language (go) is an honest unresolved record, never faked;
- missing LLM_* env vars (or the placeholder key) are an honest exit with the
  exact required message, before any task work;
- download failure raises HarnessError with the documented offline fallback;
- task schema validation, benchmark scanning, .meta exclusion and the
  test-file integrity guard are checked directly.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import urllib.error
import zipfile
from pathlib import Path
from typing import Any

import pytest

from craft.llm import LLMClient
from providers.base import LLMMessage, LLMResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_SCRIPT = REPO_ROOT / "scripts" / "bench_aider.py"
SAMPLE_REPO = REPO_ROOT / "scripts" / "aider_sample" / "repo"

RESOLVED_ID = "python/toycalc-double"
UNRESOLVED_ID = "python/toycalc-multiply"
GO_ID = "go/toycalc-sum"

# Concatenated on purpose: the security gate forbids literal key prefixes anywhere.
FAKE_API_KEY = "fake-" + "key-not-a-secret"
FAKE_BASE_URL = "http://127.0.0.1:9"
FAKE_MODEL = "fake-model"
ENV_EXIT_MESSAGE = "LLM mode requires LLM_API_KEY/LLM_BASE_URL/LLM_MODEL env vars"

# A VALID llm plan per craft/planner.py's output contract: the fake model is a
# real M2 planner — plan -> execute -> verify with the M2 diagnose/edit path.
_FAKE_LLM_PLAN: dict[str, Any] = {
    "steps": [
        {
            "id": "s1",
            "kind": "understand",
            "target_files": ["toycalc.py"],
            "intent": "read the module before touching it",
            "success_criteria": {"type": "grep", "value": ""},
            "deps": [],
        },
        {
            "id": "s2",
            "kind": "modify",
            "target_files": ["toycalc.py"],
            "intent": "fix the arithmetic bug",
            "success_criteria": {"type": "compile", "value": ""},
            "deps": ["s1"],
        },
        {
            "id": "s3",
            "kind": "test",
            "target_files": [],
            "intent": "run the test suite and make it green",
            "success_criteria": {"type": "test_green", "value": ""},
            "deps": ["s2"],
        },
    ],
    "risk_classification": {"auth": False, "migration": False, "mq": False, "public_api": False},
}


class _FakeLLMClient(LLMClient):
    """Deterministic fake: a valid llm plan for every task, then a per-job
    diagnose reply. Jobs in the resolve set get the correct toycalc.py edit;
    every other job gets an empty edit list (honest failure). No network,
    no real provider — chat_sync is overridden entirely."""

    def __init__(self, resolve_jobs: frozenset[str], *, job_id: str = "fake-client") -> None:
        super().__init__(provider=None, token_budget=10_000, job_id=job_id)
        self._resolve_jobs = resolve_jobs
        self.plan_calls = 0
        self.diagnose_calls = 0

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
        del messages, kind, thinking, response_format, estimated_prompt_tokens, timeout
        if label == "plan":
            self.plan_calls += 1
            content = json.dumps(_FAKE_LLM_PLAN)
            model = "fake-planner"
            usage = {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50}
        else:
            self.diagnose_calls += 1
            if job_id in self._resolve_jobs:
                edits: list[dict[str, str]] = [
                    {
                        "action": "apply_edit",
                        "path": "toycalc.py",
                        "old": "return value / 2",
                        "new": "return value * 2",
                    }
                ]
                diagnosis = "double() must multiply its input by two"
            else:
                edits = []
                diagnosis = "no reliable fix from the evidence"
            content = json.dumps({"diagnosis": diagnosis, "edits": edits})
            model = "fake-diagnoser"
            usage = {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
        # Mirror LLMClient._journal bookkeeping so the harness stats_report
        # (llm_usage) reflects the fake calls realistically.
        entry = self.budget.record(usage, label=label)
        self.calls.append(
            {
                **entry,
                "job_id": job_id or self.job_id,
                "step_id": step_id,
                "model": model,
            }
        )
        return LLMResponse(content=content, usage=usage, model=model)


def _load_harness() -> Any:
    """Import scripts/bench_aider.py as a fresh module for in-process runs."""
    spec = importlib.util.spec_from_file_location("bench_aider_under_test", BENCH_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_fake_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", FAKE_API_KEY)
    monkeypatch.setenv("LLM_BASE_URL", FAKE_BASE_URL)
    monkeypatch.setenv("LLM_MODEL", FAKE_MODEL)


def _install_fake_factory(
    module: Any, resolve_jobs: frozenset[str]
) -> list[_FakeLLMClient]:
    """Monkeypatch the harness's client factory; return the built clients."""
    built: list[_FakeLLMClient] = []

    def factory(job_id: str) -> _FakeLLMClient:
        client = _FakeLLMClient(resolve_jobs, job_id=job_id)
        built.append(client)
        return client

    module._build_llm_client = factory
    return built


def _load_results(output: Path) -> dict[str, Any]:
    payload: Any = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_llm_mode_fake_client_resolved_and_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """llm 模式 + 假客户端: double 任务 resolved, multiply 任务诚实 unresolved。

    假模型产出合法 llm 计划 + 正确的 toycalc.py 编辑 (仅对 double 的 job);
    multiply 收到空编辑 → craft STUCK → unresolved + 非空 reason。
    """
    module = _load_harness()
    _set_fake_llm_env(monkeypatch)
    built = _install_fake_factory(module, frozenset({"aider-python_toycalc-double"}))
    output = tmp_path / "results.json"
    md_output = tmp_path / "results.md"
    code = module.main(
        [
            "--offline",
            "--no-venv",
            "--tasks", "2",
            "--max-iterations", "8",
            "--output", str(output),
            "--md-output", str(md_output),
        ]
    )
    assert code == 0
    payload = _load_results(output)
    assert payload["schema_version"] == "1.0"
    assert payload["benchmark"]["source"]["kind"] == "offline-sample"
    assert payload["llm"]["model"] == FAKE_MODEL
    assert payload["llm"]["base_url"] == "http://127.0.0.1:9"
    assert payload["llm"]["key_recorded"] is False
    summary = payload["summary"]
    assert summary["total"] == 2
    assert summary["resolved"] == 1
    assert summary["unresolved"] == 1
    assert summary["resolved_rate_pct"] == 50.0
    assert "harness 口径" in summary["note"]

    tasks = payload["tasks"]
    by_id = {str(entry["task_id"]): entry for entry in tasks}
    assert set(by_id) == {RESOLVED_ID, UNRESOLVED_ID}

    resolved = by_id[RESOLVED_ID]
    assert resolved["resolved"] is True
    assert resolved["status"] == "resolved"
    assert resolved["reason"] == ""
    assert resolved["language"] == "python"
    assert resolved["runner"] == "pytest"
    assert resolved["test_file"] == "toycalc_test.py"
    assert resolved["prompt"]["path"].endswith("PROMPT.md")
    assert resolved["craft"]["result"] == "DONE"
    assert resolved["craft"]["mode"] == "llm"
    assert resolved["craft"]["edits"] == ["toycalc.py"]
    assert isinstance(resolved["craft"]["llm_usage"], dict)
    assert resolved["craft"]["llm_usage"]["calls"] >= 2
    assert resolved["test_run"]["runner"] == "pytest"
    assert resolved["test_run"]["outcome"] == "passed"
    assert resolved["deps"]["installed"] is False

    unresolved = by_id[UNRESOLVED_ID]
    assert unresolved["resolved"] is False
    assert unresolved["status"] == "unresolved"
    assert "no edit produced" in unresolved["reason"]
    assert unresolved["craft"]["result"] == "STUCK"
    assert unresolved["test_run"] is None

    # Honesty invariant: reason non-empty iff unresolved.
    for entry in tasks:
        if entry["resolved"]:
            assert entry["reason"] == ""
        else:
            assert entry["reason"].strip()

    # The fake really drove the run: one client per task, one plan call each.
    assert len(built) == 2
    assert sum(client.plan_calls for client in built) == 2
    by_job = {client.job_id: client for client in built}
    assert by_job["aider-python_toycalc-double"].diagnose_calls >= 1
    assert by_job["aider-python_toycalc-multiply"].diagnose_calls >= 3

    # md 汇总与 JSON 一致。
    md_text = md_output.read_text(encoding="utf-8")
    assert "50.0" in md_text
    assert RESOLVED_ID in md_text


def test_llm_mode_missing_env_honest_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """缺少 LLM_* 环境变量 → 诚实退出 (exit 2 + 精确信息), 不产出任何结果。"""
    module = _load_harness()
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    output = tmp_path / "results.json"
    code = module.main(["--offline", "--output", str(output)])
    assert code == 2
    assert ENV_EXIT_MESSAGE in capsys.readouterr().err
    assert not output.exists()


def test_llm_mode_placeholder_key_honest_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """LLM_API_KEY 为占位符 'replace_me' → 同样的诚实退出。"""
    module = _load_harness()
    _set_fake_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "replace_me")
    output = tmp_path / "results.json"
    code = module.main(["--offline", "--output", str(output)])
    assert code == 2
    assert ENV_EXIT_MESSAGE in capsys.readouterr().err
    assert not output.exists()


def test_unsupported_language_honest_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """go 任务: runner 未支持 → 诚实 unresolved (stage=tests), craft 不运行。"""
    module = _load_harness()
    _set_fake_llm_env(monkeypatch)
    built = _install_fake_factory(module, frozenset({"aider-python_toycalc-double"}))
    output = tmp_path / "results.json"
    code = module.main(
        [
            "--offline",
            "--no-venv",
            "--tasks", "3",
            "--max-iterations", "8",
            "--output", str(output),
        ]
    )
    assert code == 0
    payload = _load_results(output)
    assert payload["summary"]["total"] == 3
    assert payload["summary"]["resolved"] == 1
    by_id = {str(entry["task_id"]): entry for entry in payload["tasks"]}
    go_record = by_id[GO_ID]
    assert go_record["resolved"] is False
    assert go_record["stage"] == "tests"
    assert go_record["runner"] == "unsupported-go"
    assert go_record["craft"] is None
    assert "runner 未支持" in go_record["reason"]
    # 假客户端只被 python 任务使用 — go 任务绝不调用 LLM。
    assert len(built) == 2


def test_task_schema_validation(tmp_path: Path) -> None:
    """_validate_task: 合法条目通过; 各类非法条目返回 (None, 具体原因)。"""
    module = _load_harness()
    tasks = module._order_tasks(module._scan_benchmark(SAMPLE_REPO))
    valid, error = module._validate_task(tasks[0], 0)
    assert valid is not None and error == ""
    source_dir = str(SAMPLE_REPO / "python" / "exercises" / "practice" / "toycalc-double")
    base = {
        "task_id": "python/toycalc-double",
        "language": "python",
        "runner": "pytest",
        "source_dir": source_dir,
        "test_file": "toycalc_test.py",
        "description": "fix it",
    }
    cases: list[tuple[object, str]] = [
        ("not-a-dict", "不是 JSON 对象"),
        ({**base, "task_id": ""}, "task_id"),
        ({**base, "language": "lisp"}, "language"),
        ({**base, "test_file": ""}, "test_file"),
        ({**base, "source_dir": str(tmp_path / "no-such-dir")}, "source_dir"),
        ({**base, "description": ""}, "description"),
    ]
    for entry, fragment in cases:
        checked, problem = module._validate_task(entry, 0)
        assert checked is None, entry
        assert fragment in problem, (entry, problem)


def test_scanner_detects_languages_and_descriptions() -> None:
    """捆绑样例扫描: python → pytest, go → unsupported-go, 描述非空。"""
    module = _load_harness()
    tasks = module._scan_benchmark(SAMPLE_REPO)
    ordered = module._order_tasks(tasks)
    assert [str(task["task_id"]) for task in ordered] == [
        RESOLVED_ID,
        UNRESOLVED_ID,
        GO_ID,
    ]
    by_id = {str(task["task_id"]): task for task in tasks}
    assert by_id[RESOLVED_ID]["runner"] == "pytest"
    assert by_id[RESOLVED_ID]["test_file"] == "toycalc_test.py"
    assert by_id[UNRESOLVED_ID]["runner"] == "pytest"
    assert by_id[GO_ID]["runner"] == "unsupported-go"
    assert by_id[GO_ID]["test_file"] == "toycalc_test.go"
    assert all(str(task["description"]).strip() for task in tasks)
    assert "double" in str(by_id[RESOLVED_ID]["description"]).lower()


def test_copy_exercise_excludes_reference_solution(tmp_path: Path) -> None:
    """.meta/ (参考解) 绝不进入工作区 — 防泄漏。"""
    module = _load_harness()
    source = SAMPLE_REPO / "python" / "exercises" / "practice" / "toycalc-double"
    dest = tmp_path / "work"
    module._copy_exercise(source, dest)
    assert (dest / "toycalc.py").is_file()
    assert (dest / "toycalc_test.py").is_file()
    assert not (dest / ".meta").exists()


def test_protected_files_snapshot_and_violations(tmp_path: Path) -> None:
    """防作弊基线: 改测试文件/新增测试文件 = 违规; 改实现文件 = 不违规。"""
    module = _load_harness()
    source = SAMPLE_REPO / "python" / "exercises" / "practice" / "toycalc-double"
    dest = tmp_path / "work"
    module._copy_exercise(source, dest)
    before = module._snapshot_protected(dest)
    assert "toycalc_test.py" in before

    (dest / "toycalc_test.py").write_text(
        "def test_fake():\n    assert True\n", encoding="utf-8"
    )
    violations = module._protected_violations(before, dest)
    assert any("toycalc_test.py" in entry for entry in violations)

    before2 = module._snapshot_protected(dest)
    (dest / "toycalc.py").write_text(
        "def double(value):\n    return value * 2\n", encoding="utf-8"
    )
    assert module._protected_violations(before2, dest) == []

    (dest / "test_evil.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    violations = module._protected_violations(before2, dest)
    assert any("test_evil.py" in entry for entry in violations)


def test_fetch_failure_honest_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """下载失败 → HarnessError 带 --benchmark-dir / --offline 回退提示。"""
    module = _load_harness()

    def blocked(url: str, timeout: int) -> object:
        del url, timeout
        raise urllib.error.URLError("network blocked in test")

    monkeypatch.setattr(module.urllib.request, "urlopen", blocked)
    with pytest.raises(module.HarnessError) as excinfo:
        module._fetch_benchmark(tmp_path / "cache", 5)
    message = str(excinfo.value)
    assert "--benchmark-dir" in message
    assert "--offline" in message


def test_safe_extract_rejects_traversal(tmp_path: Path) -> None:
    """zip-slip 防护: .. 越界条目 → BadZipFile。"""
    module = _load_harness()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.txt", "x")
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as archive, pytest.raises(zipfile.BadZipFile):
        module._safe_extract_zip(archive, tmp_path)


def test_cli_help_lists_flags() -> None:
    """--help 暴露全部开关。"""
    proc = subprocess.run(
        [sys.executable, str(BENCH_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for flag in (
        "--offline", "--tasks", "--benchmark-dir", "--languages", "--md-output", "--no-venv",
    ):
        assert flag in proc.stdout
