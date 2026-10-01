"""#140: the DEEP tier's cache disclosure must be readable in the archived report.

Backlog #7's guard produced a `SandboxResult.cache_note`; #137 carried it into
`deep_results["cache_integrity"]` and the job-scoped `deep-report.json`. Those
are machine artifacts. This closes the human end: the HTML Verification Report
is what a reviewer opens (and archives, and diffs months later), and until now
it said nothing about the cache the deep runs consumed — so an honest
"NOT VERIFIED" looked exactly like a clean run.

Two ends are pinned here:
  * the renderer (what the reader sees, including the two absences), and
  * `publish_report_node` (the only shipped caller), because a disclosure that
    never reaches the call is a feature of the test file, not of the product.

Witness arms (predicted before running, measured after):
  N1 node stops forwarding deep kwargs      -> 6, 7
  N2 renderer drops the disclosed line      -> 1, 5
  N3 absent disclosure rendered as verified  -> 2
  N4 no-DEEP guard removed                  -> 4
  N5 cache line rendered unescaped          -> 5
  N6 {deep_html} dropped from the document  -> 1, 2, 3, 5
"""

from __future__ import annotations

from typing import Any

from agent.nodes.publish_report import publish_report_node
from evidence.report import render_verification_report

NOT_VERIFIED = "缓存完整性 NOT VERIFIED: cache_dir not supplied"
MATRIX: dict[str, Any] = {"rows": []}


def _render(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "repo": "demo/repo",
        "base_ref": "base-sha",
        "head_ref": "head-sha",
        "matrix": MATRIX,
        "findings": [],
        "generated_at": "2026-10-01 00:00:00 UTC",
    }
    kwargs.update(overrides)
    return render_verification_report(**kwargs)


class TestRendererCarriesTheDisclosure:
    def test_1_merged_note_appears_verbatim(self) -> None:
        html = _render(
            deep={"cache_integrity": NOT_VERIFIED},
            deep_note="deep tier ran",
        )
        assert NOT_VERIFIED in html
        assert "Deep Verification" in html

    def test_2_deep_run_without_a_note_says_absent(self) -> None:
        """The campaign ran but recorded no cache statement: say so."""
        html = _render(deep={"mutation": {"survived": 2}}, deep_note="deep tier ran")
        assert "not disclosed by this run" in html
        assert NOT_VERIFIED not in html

    def test_3_fast_job_says_the_tier_never_ran(self) -> None:
        html = _render(deep={}, deep_note="DEEP tier not requested")
        assert "DEEP tier not requested" in html
        # No cache claim of any kind for runs that never mounted a cache.
        assert "Cache integrity" not in html

    def test_4_caller_that_knows_nothing_gets_no_section(self) -> None:
        """No deep state at all (legacy caller) must not read as 'not requested'."""
        html = _render()
        assert "Deep Verification" not in html

    def test_5_hostile_note_is_escaped(self) -> None:
        payload = '<script>alert("cache")</script>'
        html = _render(deep={"cache_integrity": payload}, deep_note="ran")
        assert "<script>alert" not in html
        assert "&lt;script&gt;alert" in html


def _drive_node(
    monkeypatch, tmp_path, state: dict[str, Any]
) -> dict[str, Any]:
    """Run the shipped node and return the kwargs it passed to the renderer."""
    import evidence.lineage as lineage
    import evidence.report as report
    import storage.object_metadata as metadata

    captured: dict[str, Any] = {}

    def fake_render(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "<html>report</html>"

    monkeypatch.setattr(report, "render_verification_report", fake_render)
    monkeypatch.setattr(
        lineage, "build_lineage", lambda _s, **_k: ({"nodes": [], "edges": []}, "root")
    )
    monkeypatch.setattr(lineage, "lineage_to_json", lambda _d, _r: "{}")
    monkeypatch.setattr(
        metadata, "record_file_object_best_effort", lambda *_a, **_k: None
    )
    out_dir = tmp_path / "reports"
    node_state: dict[str, Any] = {
        "repo_path": "demo/repo",
        "base_ref": "base-sha",
        "head_ref": "head-sha",
        "matrix": MATRIX,
        "confirmed_findings": [],
        "errors": [],
        "preflight": {},
        "job_id": "",
        "output_dir": str(out_dir),
    }
    node_state.update(state)
    publish_report_node(node_state)  # type: ignore[arg-type]
    return captured


class TestNodeFeedsTheRenderer:
    def test_6_node_forwards_deep_state(self, monkeypatch, tmp_path) -> None:
        captured = _drive_node(
            monkeypatch,
            tmp_path,
            {
                "job_id": "1a2b3c4d-5678",
                "deep_results": {"cache_integrity": NOT_VERIFIED},
                "deep_note": "deep tier ran",
            },
        )
        assert captured["deep"] == {"cache_integrity": NOT_VERIFIED}
        assert captured["deep_note"] == "deep tier ran"

    def test_7_absent_deep_state_forwards_empty(self, monkeypatch, tmp_path) -> None:
        """No DEEP keys must forward as empty, not as a fabricated disclosure."""
        captured = _drive_node(monkeypatch, tmp_path, {})
        assert captured["deep"] == {}
        assert captured["deep_note"] == ""
