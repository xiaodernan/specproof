"""Unit tests for scripts/seed_demo.py (W43 local experience seeding).

Runs without Docker and without a network: the agent-store SQLite fallback
is exercised twice to prove idempotency (same counts, no duplicates), the
plan-attach guard for terminal jobs is checked, and every seeded payload is
asserted free of secret-shaped content.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import seed_demo  # noqa: E402

from storage.agent_jobs import SqliteAgentJobStore  # noqa: E402

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}"),
    re.compile(r"api[f_]?key\s*[:=]\s*[\"'][^\"']{16,}[\"']", re.IGNORECASE),
]


def _assert_no_secrets(payload: object) -> None:
    """Fail when a serialized payload contains secret-shaped content."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    for pattern in _SECRET_PATTERNS:
        assert pattern.search(text) is None, (
            f"secret-shaped content matched {pattern.pattern!r}: {text[:200]}"
        )


def test_agent_store_seeding_twice_is_idempotent(tmp_path: Path) -> None:
    """Two runs -> same job id, one row, no duplicates, plan attached."""
    store = SqliteAgentJobStore(tmp_path / "agent_jobs.db")
    try:
        first, created_first = seed_demo.seed_agent_job_in_store(store)
        second, created_second = seed_demo.seed_agent_job_in_store(store)

        assert created_first is True
        assert created_second is False
        assert first.id == second.id
        assert len(store.list()) == 1

        assert first.status == "pending"  # AWAITING_APPROVAL in console terms
        assert first.plan_json is not None
        plan = json.loads(first.plan_json)
        assert len(plan["steps"]) == 4
        assert all(step["status"] == "pending" for step in plan["steps"])
    finally:
        store.close()


def test_agent_seed_content_is_demo_marked_and_secret_free(tmp_path: Path) -> None:
    """The seeded agent job carries the demo marker and no secrets."""
    store = SqliteAgentJobStore(tmp_path / "agent_jobs.db")
    try:
        job, _created = seed_demo.seed_agent_job_in_store(store)
        assert seed_demo.DEMO_MARK in seed_demo.SEED_AGENT_TASK_NAME
        _assert_no_secrets(
            {
                "task_name": seed_demo.SEED_AGENT_TASK_NAME,
                "spec_text": job.spec_text,
                "plan": json.loads(job.plan_json or "null"),
            }
        )
    finally:
        store.close()


def test_plan_attach_is_refused_for_terminal_jobs(tmp_path: Path) -> None:
    """A terminal projection is closed: the demo plan must not overwrite it."""
    store = SqliteAgentJobStore(tmp_path / "agent_jobs.db")
    try:
        store.create("job-1", "spec text")
        store.update_status("job-1", "succeeded")
        attached = seed_demo.attach_agent_plan(
            store, "job-1", seed_demo.demo_agent_plan()
        )
        assert attached is False
        job = store.get("job-1")
        assert job is not None
        assert job.plan_json is None  # untouched, honest no-op
    finally:
        store.close()


def test_verify_demo_templates_have_stable_keys_and_no_secrets() -> None:
    """3 demo jobs, deterministic uuid5 keys, mixed verdicts, secret-free."""
    templates = seed_demo.demo_verify_templates()
    assert len(templates) == 3

    ids = {
        seed_demo.stable_demo_uuid(f"verify:{template['key']}")
        for template in templates
    }
    assert len(ids) == 3  # stable, unique seed keys
    assert (
        seed_demo.stable_demo_uuid("verify:verify-auth-regression")
        == seed_demo.stable_demo_uuid("verify:verify-auth-regression")
    )

    statuses = {template["status"] for template in templates}
    assert statuses == {"BLOCKED", "VERIFIED"}  # dashboard shows both outcomes

    for template in templates:
        assert seed_demo.DEMO_MARK in template["title"]
        assert template["base_ref"] and template["head_ref"]
        assert template["contracts"], "demo jobs must carry a matrix"
        _assert_no_secrets(template)


def test_verify_summary_matches_template_counts() -> None:
    """The persisted summary mirrors the template matrix (nothing fabricated)."""
    template = seed_demo.demo_verify_templates()[0]
    job_id = seed_demo.stable_demo_uuid(f"verify:{template['key']}")
    summary = seed_demo._summary_for(template, job_id)  # noqa: SLF001

    assert summary["verdict"] == "BLOCKED"
    assert summary["contracts_total"] == len(template["contracts"])
    assert summary["matrix_passed"] == 1
    assert summary["matrix_failed"] == 1
    assert summary["matrix_unverified"] == 0
    assert len(summary["findings"]) == len(template["findings"])
    _assert_no_secrets(summary)
