"""craft/loop.py × storage/agent_jobs.py wiring tests (W35 / W30 Integration note).

Covers the durable-job contract end to end, all in-memory/local:
  - create+lease on start, set_plan once, renew + set_progress per step,
    terminal update_status(result_json=report) at finish;
  - failed runs mark the job failed with the honest report;
  - a supervisor cancel wins over a leased worker: the loop flushes an
    honest 'cancelled' checkpoint entry and finishes CANCELLED without
    fighting the terminal projection;
  - cancel before run ⇒ lease denied ⇒ CraftLoopError (no duplicate run);
  - from_checkpoint re-lease after a mid-run crash resumes to succeeded;
  - store=None keeps the original in-memory behavior (backward compat).

No network, no live LLM, no Docker: the store is InMemoryAgentJobStore
wrapped in a recording spy, and the loop runs in local exec mode.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from craft.editor import Editor
from craft.loop import CraftLoop, CraftLoopError
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text
from storage.agent_jobs import InMemoryAgentJobStore, compute_spec_digest

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"


def write_fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text(
        "def double(x):\n    return x / 2\n\n\ndef greeting(name):\n"
        '    return "hello " + name\n',
        encoding="utf-8",
    )
    (repo / "test_calc.py").write_text(
        "from calc import double, greeting\n\n\n"
        "def test_double():\n    assert double(4) == 8\n\n\n"
        'def test_greeting():\n    assert greeting("a") == "hello a"\n',
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['.']\n", encoding="utf-8"
    )
    return repo


def fix_double(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    return ["calc.py"]


def noop_fix(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit("calc.py", "return x / 2", "return x / 2")
    return ["calc.py"]


class SpyStore:
    """InMemoryAgentJobStore wrapper recording the CraftLoop call sites."""

    def __init__(self, inner: InMemoryAgentJobStore) -> None:
        self.inner = inner
        self.calls: list[str] = []

    def create(self, job_id: str, spec_text: str) -> Any:
        self.calls.append("create")
        return self.inner.create(job_id, spec_text)

    def lease(self, job_id: str, owner: str, ttl_seconds: float) -> bool:
        self.calls.append("lease")
        return self.inner.lease(job_id, owner, ttl_seconds)

    def renew(self, job_id: str, owner: str, ttl_seconds: float) -> bool:
        self.calls.append("renew")
        return self.inner.renew(job_id, owner, ttl_seconds)

    def set_plan(self, job_id: str, plan: dict[str, Any]) -> Any:
        self.calls.append("set_plan")
        return self.inner.set_plan(job_id, plan)

    def set_progress(
        self, job_id: str, current_step: str, progress: dict[str, Any]
    ) -> Any:
        self.calls.append("set_progress:" + current_step)
        return self.inner.set_progress(job_id, current_step, progress)

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        error: str | None = None,
        result_json: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append("update_status:" + status)
        return self.inner.update_status(
            job_id, status, error=error, result_json=result_json
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def make_loop(
    repo: Path,
    *,
    store: Any = None,
    fix_registry: dict[str, object] | None = None,
    job_id: str = "job-1",
) -> CraftLoop:
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    return CraftLoop(
        spec,
        plan,
        repo,
        job_id=job_id,
        fix_registry=fix_registry,
        exec_mode="local",
        store=store,
    )


def expected_spec_text() -> str:
    return json.dumps(parse_spec_text(FIX_SPEC).to_dict())


# -- backward compatibility ---------------------------------------------------


def test_store_none_keeps_original_behavior(tmp_path: Path) -> None:
    repo = write_fixture_repo(tmp_path)
    loop = make_loop(repo, fix_registry={"test": fix_double})
    assert loop.store is None
    report = loop.run()
    assert report["result"] == "DONE"
    assert "job_store_note" not in report
    # W35 gate composition still embedded (informational, non-blocking)
    gates = report.get("gates")
    assert isinstance(gates, dict)
    assert str(gates.get("summary", "")).startswith("GATES: ")


# -- create / lease / renew / progress / terminal write ------------------------


def test_run_creates_leases_projects_and_marks_succeeded(tmp_path: Path) -> None:
    repo = write_fixture_repo(tmp_path)
    store = InMemoryAgentJobStore()
    spy = SpyStore(store)
    loop = make_loop(repo, store=spy, fix_registry={"test": fix_double})
    report = loop.run()
    assert report["result"] == "DONE"

    job = store.get("job-1")
    assert job is not None
    assert job.status == "succeeded"
    assert job.spec_digest == compute_spec_digest(expected_spec_text())
    assert job.started_at is not None and job.finished_at is not None
    # entering the terminal status released the lease automatically
    assert job.lease_owner is None and job.lease_expires_at is None
    stored = json.loads(job.result_json or "{}")
    assert stored["result"] == "DONE"
    assert stored.get("gates") is not None  # result_json carries the gate summary
    assert job.plan_json is not None

    assert "create" in spy.calls
    assert "lease" in spy.calls
    assert spy.calls.count("renew") >= 4  # one per non-green step
    assert "set_plan" in spy.calls
    assert "update_status:succeeded" in spy.calls
    progress_calls = [c for c in spy.calls if c.startswith("set_progress:")]
    assert len(progress_calls) >= 4


def test_failed_run_marks_job_failed(tmp_path: Path) -> None:
    repo = write_fixture_repo(tmp_path)
    store = InMemoryAgentJobStore()
    loop = make_loop(repo, store=store)  # no fix rule: fails honestly
    report = loop.run()
    assert report["result"] == "FAILED"
    job = store.get("job-1")
    assert job is not None and job.status == "failed"
    stored = json.loads(job.result_json or "{}")
    assert stored["result"] == "FAILED"


# -- supervisor cancel wins over a leased worker --------------------------------


def test_supervisor_cancel_wins_over_leased_worker(tmp_path: Path) -> None:
    repo = write_fixture_repo(tmp_path)
    store = InMemoryAgentJobStore()
    spy = SpyStore(store)

    def cancel_fix(editor: Editor, step: Step, diagnosis: str) -> list[str]:
        store.cancel("job-c", "user stopped it")
        editor.apply_edit("calc.py", "return x / 2", "return x * 2")
        return ["calc.py"]

    loop = make_loop(repo, store=spy, fix_registry={"test": cancel_fix}, job_id="job-c")
    report = loop.run()
    assert report["result"] == "CANCELLED"
    assert any("cancel" in str(entry.get("verdict")) for entry in loop.checkpoint_entries)
    job = store.get("job-c")
    assert job is not None and job.status == "cancelled"
    assert job.error == "user stopped it"
    # the worker never fights the supervisor terminal projection
    assert "update_status:cancelled" not in spy.calls
    assert report["job_store_note"]


def test_cancel_before_run_denies_lease(tmp_path: Path) -> None:
    repo = write_fixture_repo(tmp_path)
    store = InMemoryAgentJobStore()
    store.create("job-x", expected_spec_text())
    store.cancel("job-x", "too late")
    loop = make_loop(repo, store=store, job_id="job-x")
    with pytest.raises(CraftLoopError, match="租约"):
        loop.run()


# -- from_checkpoint re-lease ----------------------------------------------------


def test_from_checkpoint_releases_after_midrun_crash(tmp_path: Path) -> None:
    repo = write_fixture_repo(tmp_path)
    store = InMemoryAgentJobStore()
    spy = SpyStore(store)
    calls = {"n": 0}

    def flaky_fix(editor: Editor, step: Step, diagnosis: str) -> list[str]:
        calls["n"] += 1
        if calls["n"] == 1:
            editor.apply_edit("calc.py", "return x / 2", "return x / 2")  # noop
            return ["calc.py"]
        raise RuntimeError("worker crashed mid-run")

    loop = make_loop(repo, store=spy, fix_registry={"test": flaky_fix})
    with pytest.raises(RuntimeError, match="worker crashed"):
        loop.run()
    job = store.get("job-1")
    assert job is not None and job.status == "running"
    assert job.lease_owner  # 租约还在崩溃 worker 名下

    resumed = CraftLoop.from_checkpoint(
        loop.artifact_dir,
        fix_registry={"test": fix_double},
        exec_mode="local",
        store=spy,
    )
    report = resumed.run()
    assert report["result"] == "DONE"
    assert spy.calls.count("lease") == 2  # 恢复路径重新租约
    final = store.get("job-1")
    assert final is not None and final.status == "succeeded"


def test_terminal_job_rejects_rerun(tmp_path: Path) -> None:
    repo = write_fixture_repo(tmp_path)
    store = InMemoryAgentJobStore()
    loop = make_loop(repo, store=store, fix_registry={"test": fix_double}, job_id="job-t")
    loop.run()
    resumed = CraftLoop.from_checkpoint(
        loop.artifact_dir,
        fix_registry={"test": fix_double},
        exec_mode="local",
        store=store,
    )
    with pytest.raises(CraftLoopError, match="租约"):
        resumed.run()

