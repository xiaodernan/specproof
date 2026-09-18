"""A completed pipeline with no coverage is not a verified change."""
import pytest

from agent.worker import _state_summary, _terminal_status_from_state
from evidence.report import render_verification_report


@pytest.mark.parametrize("matrix", [
    {}, {"passed": 0, "failed": 0, "unverified": 0, "rows": []},
    {"rows": [{}]}, {"rows": [{"result": "FAIL"}], "failed": 0},
    {"rows": [{"result": "PASS"}], "failed": 1},
])
def test_incomplete_or_failed_checks_never_pass(matrix):
    assert _terminal_status_from_state({"matrix": matrix}) == "BLOCKED"


def test_actual_passing_rows_can_verify():
    row = {"contract_id": "C-1", "result": "PASS", "experiment": "test", "evidence": "e-1"}
    assert _terminal_status_from_state({"matrix": {"rows": [row]}}) == "VERIFIED"


def test_summary_explains_zero_coverage():
    assert "零检查" in _state_summary({"matrix": {}}, "BLOCKED")["coverage_reason"]


def test_empty_html_report_requires_review_and_escapes_inputs():
    html = render_verification_report("<script>alert(1)</script>", "base", "head", {}, [])
    assert '<div class="verdict blocked">NEEDS REVIEW</div>' in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_report_blocks_findings_even_without_matrix_failures():
    html = render_verification_report("repo", "base", "head", {}, [
        {"severity": "BLOCKER", "description": '<img src=x onerror="alert(1)">'}
    ])
    assert '<div class="verdict blocked">BLOCKED</div>' in html
    assert '<img src=x' not in html

def test_heartbeat_renews_lease_during_slow_stage():
    import threading
    from types import SimpleNamespace

    from agent.worker import Worker

    renewed = threading.Event()
    stop, lost = threading.Event(), threading.Event()
    class Redis:
        def renew_lease(self, job_id, worker_id, ttl):
            renewed.set()
            return True
    worker = object.__new__(Worker)
    worker.redis = Redis()
    worker.mysql = SimpleNamespace(get_job=lambda _id: {"status": "RUNNING"})
    worker.worker_id, worker.lease_ttl = "worker", 0.15
    thread = threading.Thread(target=worker._keep_lease, args=("job", stop, lost))
    thread.start()
    try:
        assert renewed.wait(1)
        assert not lost.is_set()
    finally:
        stop.set()
        thread.join(1)
    assert not thread.is_alive()
