"""Offline unit tests for the SWE-bench harness LLM mode (no network, no Docker, no LLM).

The real LLMClient is replaced by a deterministic FAKE client (subclass of
craft.llm.LLMClient with chat_sync overridden), injected through the harness's
`_build_llm_client` factory. Everything else — checkout, craft loop, test_patch,
FAIL_TO_PASS / PASS_TO_PASS replay — is the real harness code.

Covered here:
- llm mode with the fake: one instance resolves (fake proposes the right edit),
  one stays honestly unresolved with a non-empty reason;
- missing LLM_* env vars (or the placeholder key) are an honest exit with the
  exact required message, before any instance work;
- the `--instances-file` subset loader validates its schema strictly, filters the
  dataset, and reports ids missing from the dataset honestly;
- the bundled scripts/swebench_subset/python_subset.json obeys the documented
  shape (`owner__name-N` ids, unique, simple-repo whitelist).
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from craft.llm import LLMClient
from providers.base import LLMMessage, LLMResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_SCRIPT = REPO_ROOT / "scripts" / "bench_swebench.py"
SAMPLE_INSTANCES = REPO_ROOT / "scripts" / "swebench_sample" / "instances.json"
SUBSET_FILE = REPO_ROOT / "scripts" / "swebench_subset" / "python_subset.json"

RESOLVED_ID = "specproof__toycalc-double-1"
UNRESOLVED_ID = "specproof__toycalc-multiply-1"

# Concatenated on purpose: the security gate forbids literal key prefixes anywhere.
FAKE_API_KEY = "fake-" + "key-not-a-secret"
FAKE_BASE_URL = "http://127.0.0.1:9"
FAKE_MODEL = "fake-model"
ENV_EXIT_MESSAGE = "LLM mode requires LLM_API_KEY/LLM_BASE_URL/LLM_MODEL env vars"

_EXPECTED_SUBSET_IDS = [
    "pallets__flask-4045",
    "pallets__flask-4992",
    "pallets__flask-5063",
    "pylint-dev__pylint-5859",
    "pylint-dev__pylint-6506",
    "pylint-dev__pylint-7228",
    "pylint-dev__pylint-7993",
    "sphinx-doc__sphinx-7975",
    "sphinx-doc__sphinx-8721",
    "sphinx-doc__sphinx-11445",
]

_INSTANCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+$")

# A VALID llm plan per craft/planner.py's output contract: the fake model is a
# real M2 planner — plan -> execute -> verify with the M2 diagnose/edit path.
_FAKE_LLM_PLAN: dict[str, Any] = {
    "steps": [
        {
            "id": "s1",
            "kind": "understand",
            "target_files": ["calc.py"],
            "intent": "read the module before touching it",
            "success_criteria": {"type": "grep", "value": ""},
            "deps": [],
        },
        {
            "id": "s2",
            "kind": "modify",
            "target_files": ["calc.py"],
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
    """Deterministic fake: a valid llm plan for every instance, then a
    per-job diagnose reply. Jobs in the resolve set get the correct calc.py
    edit; every other job gets an empty edit list (honest failure). No
    network, no real provider — chat_sync is overridden entirely."""

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
                        "path": "calc.py",
                        "old": "return x / 2",
                        "new": "return x * 2",
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
    """Import scripts/bench_swebench.py as a fresh module for in-process runs."""
    spec = importlib.util.spec_from_file_location("bench_swebench_llm_under_test", BENCH_SCRIPT)
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
    """llm 模式 + 假客户端: double 实例 resolved, multiply 实例诚实 unresolved。

    假模型产出合法 llm 计划 + 正确的 calc.py 编辑 (仅对 double 的 job);
    multiply 收到空编辑 → craft STUCK → unresolved + 非空 reason。
    """
    module = _load_harness()
    _set_fake_llm_env(monkeypatch)
    built = _install_fake_factory(module, frozenset({f"swebench-{RESOLVED_ID}"}))
    output = tmp_path / "results.json"
    code = module.main(
        [
            "--mode", "llm",
            "--offline",
            "--no-venv",
            "--max-iterations", "8",
            "--output", str(output),
        ]
    )
    assert code == 0
    payload = _load_results(output)
    assert payload["mode"] == "llm"
    assert payload["schema_version"] == "1.0"
    assert payload["dataset"]["kind"] == "offline-sample"
    assert payload["llm"]["model"] == FAKE_MODEL
    assert payload["llm"]["base_url"] == "http://127.0.0.1:9"
    assert payload["llm"]["key_recorded"] is False
    summary = payload["summary"]
    assert summary["total"] == 2
    assert summary["resolved"] == 1
    assert summary["unresolved"] == 1
    assert summary["resolved_rate_pct"] == 50.0
    assert "LLM 模式" in summary["note"]

    instances = payload["instances"]
    by_id = {str(entry["instance_id"]): entry for entry in instances}
    assert set(by_id) == {RESOLVED_ID, UNRESOLVED_ID}

    resolved = by_id[RESOLVED_ID]
    assert resolved["resolved"] is True
    assert resolved["status"] == "resolved"
    assert resolved["reason"] == ""
    assert resolved["checkout"]["method"] == "copy"
    assert resolved["craft"]["result"] == "DONE"
    assert resolved["craft"]["mode"] == "llm"
    assert resolved["craft"]["edits"] == ["calc.py"]
    assert isinstance(resolved["craft"]["llm_usage"], dict)
    assert resolved["craft"]["llm_usage"]["calls"] >= 2
    assert resolved["test_patch"]["applied"] is True
    assert [test["test"] for test in resolved["fail_to_pass"]] == [
        "test_calc.py::test_double",
        "test_hidden.py::test_double_negative",
    ]
    assert all(test["outcome"] == "passed" for test in resolved["fail_to_pass"])
    assert all(test["outcome"] == "passed" for test in resolved["pass_to_pass"])
    assert resolved["deps"]["install_marker"] is None
    assert resolved["deps"]["installed"] is False
    assert resolved["llm"]["model"] == FAKE_MODEL
    assert resolved["llm"]["key_recorded"] is False

    unresolved = by_id[UNRESOLVED_ID]
    assert unresolved["resolved"] is False
    assert unresolved["status"] == "unresolved"
    assert unresolved["reason"].strip()
    assert "craft 未收敛" in unresolved["reason"]
    assert unresolved["craft"]["result"] == "STUCK"

    # Honesty invariant: reason non-empty iff unresolved.
    for entry in instances:
        if entry["resolved"]:
            assert entry["reason"] == ""
        else:
            assert entry["reason"].strip()

    # The fake really drove the run: one client per instance, one plan call
    # each, diagnose calls only where a step failed.
    assert len(built) == 2
    assert sum(client.plan_calls for client in built) == 2
    by_job = {client.job_id: client for client in built}
    assert by_job[f"swebench-{RESOLVED_ID}"].diagnose_calls >= 1
    assert by_job[f"swebench-{UNRESOLVED_ID}"].diagnose_calls >= 3


def test_llm_mode_missing_env_honest_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """缺少 LLM_* 环境变量 → 诚实退出 (exit 2 + 精确信息), 不产出任何结果。"""
    module = _load_harness()
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    output = tmp_path / "results.json"
    code = module.main(["--mode", "llm", "--offline", "--output", str(output)])
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
    code = module.main(["--mode", "llm", "--offline", "--output", str(output)])
    assert code == 2
    assert ENV_EXIT_MESSAGE in capsys.readouterr().err
    assert not output.exists()


def test_model_override_satisfies_env_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--model 覆盖可满足 LLM_MODEL 校验; 未覆盖时 LLM_MODEL 仍必需。"""
    module = _load_harness()
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key-12345678901234567890123456789012")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert "LLM_MODEL" in module._validate_llm_env(model_override=None)
    assert module._validate_llm_env(model_override="deepseek-v4-pro") == []


def test_subset_file_loader_valid() -> None:
    """捆绑子集可加载且内容与提交一致。"""
    module = _load_harness()
    ids = module._load_subset_file(SUBSET_FILE)
    assert ids == _EXPECTED_SUBSET_IDS


def test_bundled_python_subset_schema() -> None:
    """捆绑子集: 数组、非空、唯一、owner__name-N 形式、仅简单纯 Python 仓库。"""
    payload: Any = json.loads(SUBSET_FILE.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert 5 <= len(payload) <= 20
    assert all(
        isinstance(entry, str) and _INSTANCE_ID_PATTERN.fullmatch(entry) for entry in payload
    )
    assert len(set(payload)) == len(payload)
    repos = {str(entry).split("__", 1)[0] for entry in payload}
    assert repos <= {"pallets", "pylint-dev", "sphinx-doc"}


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"not": "a list"}, "顶层必须是"),
        ([], "为空数组"),
        (["pallets__flask-4045", 123], "应为非空 instance_id"),
        (["pallets__flask-4045", "pallets__flask-4045"], "重复"),
        (["not-an-instance-id"], "不是 SWE-bench instance_id"),
    ],
)
def test_subset_file_loader_rejects_invalid_schema(
    tmp_path: Path, payload: object, fragment: str
) -> None:
    """schema 非法 (顶层类型/空/元素类型/重复/id 形式) → 全部 HarnessError。"""
    module = _load_harness()
    path = tmp_path / "subset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(module.HarnessError, match=re.escape(fragment)):
        module._load_subset_file(path)


def test_subset_file_filters_offline_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--instances-file 只评测列出的实例: 单 id 子集 → total=1 且 resolved。"""
    module = _load_harness()
    _set_fake_llm_env(monkeypatch)
    _install_fake_factory(module, frozenset({f"swebench-{RESOLVED_ID}"}))
    subset = tmp_path / "subset.json"
    subset.write_text(json.dumps([RESOLVED_ID]), encoding="utf-8")
    output = tmp_path / "results.json"
    code = module.main(
        [
            "--mode", "llm",
            "--offline",
            "--no-venv",
            "--instances-file", str(subset),
            "--output", str(output),
        ]
    )
    assert code == 0
    payload = _load_results(output)
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["resolved"] == 1
    assert payload["dataset"]["subset"]["requested"] == 1
    assert payload["dataset"]["subset"]["matched"] == 1
    assert payload["instances"][0]["instance_id"] == RESOLVED_ID


def test_subset_file_missing_ids_honest_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """子集里的 id 不在数据集里 → HarnessError (exit 2), 不产出结果。"""
    module = _load_harness()
    subset = tmp_path / "subset.json"
    subset.write_text(json.dumps(["pallets__flask-4045"]), encoding="utf-8")
    output = tmp_path / "results.json"
    code = module.main(
        ["--offline", "--instances-file", str(subset), "--output", str(output)]
    )
    assert code == 2
    assert "不在数据集里" in capsys.readouterr().err
    assert not output.exists()


def test_cli_help_lists_llm_flags() -> None:
    """--help 暴露 llm 模式的全部新开关。"""
    proc = subprocess.run(
        [sys.executable, str(BENCH_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for flag in ("--mode", "--instances-file", "--no-venv", "--deps-timeout"):
        assert flag in proc.stdout

