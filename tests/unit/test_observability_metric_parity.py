"""Parity gate: every metric name referenced by alerts/dashboards must trace
to a real emission site (#161).

This project's metrics registry has NO static table — a name appears on
/metrics only after its first emission (docs/operations/OBSERVABILITY.md,
section "已接线指标名", documents the reproducible reconciliation method:
take the incr/set_gauge/observe_duration call sites and resolve constants to
literals). That made stale references invisible: the duration alert kept
querying ``specproof_jobs_duration_seconds_bucket`` after #161 split the
histogram into a ``_fast/_deep`` family, and prometheus.yml's comment claimed
the outbox-relay service "尚未进入 compose.production.yml" long after it did.

This test turns that class of drift red: every ``specproof_*`` name referenced
by alerts-slo.yml, prometheus.yml or the Grafana SLO dashboard must either be
emitted by a scanned call site or match one of the hand-registered
concatenated families (names the code builds at runtime — those cannot be
listed exhaustively, only pattern-matched).

Scope note: the source scan covers the trees that own emission sites —
the list is EMIT_DIRS below, grown by the numbered task that wired each
tree's first meter. Emissions elsewhere would still
work at runtime; they are simply not part of this gate's inventory until they
appear here — which is the same honesty rule OBSERVABILITY.md applies.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _verdict_tokens() -> str:
    """The closed verdict vocabulary, as a regex alternation.

    Derived from the code (`evidence.verdict.VERDICT_VOCABULARY`) so the
    family cannot drift from the words the policy can actually produce —
    and so a NEW verdict word is covered the moment it exists, instead of
    needing this file to be edited by hand.
    """
    from evidence.verdict import VERDICT_VOCABULARY

    words = sorted(word.lower() for word in VERDICT_VOCABULARY)
    assert words, "the verdict vocabulary is empty — the pattern would match "
    "nothing at all"
    return "|".join(words)


_VERDICT_TOKENS = _verdict_tokens()

#: Trees scanned for emission sites (mirrors OBSERVABILITY.md's method note).
#: providers/ joined in #168 (LLM token/charge meters in
#: providers/budget.py, the same choke point the billing listener reads);
#: craft/ joined in #178 (the tool-execution meters live in
#: craft/executor.py's Executor.run choke point); evidence/ joined in #179
#: (certificate issuance/refusal/notice meters in evidence/certificate.py);
#: experiments/ joined in #181 (the sandbox run/failure/timeout counters
#: live at JavaMavenAdapter.run's single run_sandboxed call site);
#: integrations/ joined in #182 (the no-evidence severe-comment refusal
#: counter at the build_review_comments boundary).
EMIT_DIRS = (
    "agent", "api", "craft", "evidence", "experiments", "integrations",
    "storage", "observability", "providers",
)

#: Reference surfaces: the two Prometheus files (plain text — comments are
#: prose but a comment naming a dead metric misleads the same way) and every
#: string inside the Grafana dashboard JSON (exprs, legends, descriptions).
REFERENCE_FILES = (
    Path("infra/prometheus/alerts-slo.yml"),
    Path("infra/prometheus/prometheus.yml"),
    Path("infra/grafana/dashboards/specproof-slo.json"),
)

#: First-arg literal (``incr("x")``) or module constant (``incr(METRIC_X)``),
#: captured WITH the call that owns it — the call is the name's type:
#: incr → counter, set_gauge → gauge, observe_duration → histogram. The type is
#: what decides whether a ``_bucket/_sum/_count`` tail on a referenced name is a
#: legal exposition suffix or a name nobody produces (#296).
_EMIT_CALL = re.compile(
    r"\b(incr|set_gauge|observe_duration)\(\s*"
    r"(?:['\"]([a-z0-9_]+)['\"]\s*[,)]|([A-Z][A-Z0-9_]*)\s*[,)])"
)
#: Same entry points when the name is CONCATENATED at runtime:
#: ``observe_duration("jobs_duration_seconds_" + depth.lower(), …)``. The literal
#: is the family's prefix, so it carries that family's type too — read here
#: instead of being written into each CONCATENATED_FAMILIES entry, which would
#: be a second copy of a fact the call site already states.
_CONCAT_CALL = re.compile(
    r"\b(incr|set_gauge|observe_duration)\(\s*"
    r"([\"'][a-z0-9_]+[\"'])\s*(?:\+|\")"
)
_EMIT_KINDS = {"incr": "counter", "set_gauge": "gauge", "observe_duration": "histogram"}
#: Module-level string constant usable as a metric name.
_MODULE_CONST = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*['\"]([a-z0-9_]+)['\"]", re.M)
_REFERENCE = re.compile(r"specproof_([a-z0-9_]+)")
#: Histogram exposition adds these to the base name; queries must be reduced
#: back to the base before matching (e.g. ..._fast_bucket → ..._fast). The
#: reduction is only legal when the base IS a histogram — see account_name.
_HISTOGRAM_SUFFIXES = ("_bucket", "_sum", "_count")

#: Names the code concatenates at runtime — unlistable, so pattern-matched.
#: Each entry carries its emission-site pointer so a failing match can be
#: traced by hand (same discipline as OBSERVABILITY.md's inventory). The
#: vocabularies themselves are NOT hand-copied here:
#: test_concatenated_families_track_their_vocabularies derives them from the
#: product sources, so a new word fails (or extends) the gate together with
#: the code instead of drifting apart from a copy.
CONCATENATED_FAMILIES: dict[str, tuple[re.Pattern[str], str]] = {
    "verdict": (
        re.compile(rf"^jobs_(?:{_VERDICT_TOKENS})_total$"),
        "agent/worker.py: incr(\"jobs_\" + verdict.lower() + \"_total\") — "
        "the closed verdict vocabulary comes from evidence/verdict.py::"
        "VERDICT_VOCABULARY; a word may contain an underscore (needs_review), "
        "so the pattern is derived from the code rather than hand-written",
    ),
    "stage": (
        re.compile(r"^worker_stage_duration_seconds_[a-z0-9_]+$"),
        "agent/worker.py: \"worker_stage_duration_seconds_\" + str(stage) — "
        "graph node names are Python identifiers",
    ),
    "depth": (
        re.compile(r"^jobs_duration_seconds_(fast|deep|release)$"),
        "agent/worker.py #161: \"jobs_duration_seconds_\" + depth.lower() — "
        "word list derived from the shipped CLI choice in the derivation test",
    ),
    "notify": (
        re.compile(r"^notify_(sent|disabled|failed)_total$"),
        "agent/worker.py: incr(\"notify_\" + status.value + \"_total\") — "
        "SendStatus members; skipped/error are worker literals instead",
    ),
    "es_op": (
        re.compile(
            r"^es_request_seconds_"
            r"(bulk|count|delete_by_query|index|indices|ping|search)$"
        ),
        "storage/elasticsearch.py #169: _timed_es(\"<op>\") — op words are "
        "the Elasticsearch client methods the store calls; the vocabulary "
        "is derived from the self.client.<op> call sites by the derivation "
        "test, so a new ES op forces this gate and the family to move "
        "together",
    ),
    "redis_op": (
        re.compile(
            r"^redis_request_seconds_"
            r"(decrby|eval|exists|expire|get|incr|incrby|ping|set|setex|"
            r"xadd|xlen|xread)$"
        ),
        "storage/redis.py #212: _timed_redis(\"<op>\") — op words are the "
        "Redis client methods the store calls; the vocabulary is derived "
        "from the self.client.<op> call sites by the derivation test, so a "
        "new Redis op forces this gate and the family to move together",
    ),
    "tool_stem": (
        re.compile(r"^tool_run_seconds_(cargo|go|gradle|mvn|npm|pytest|python)$"),
        "craft/executor.py #178: _timed_tool(<stem>) inside Executor.run — "
        "stem words are the ALLOWED_COMMANDS whitelist; the vocabulary is "
        "imported from craft.executor by the derivation test, so a new "
        "whitelisted command forces this gate and the family to move "
        "together",
    ),
    "court_outcome": (
        re.compile(
            r"^findings_court_"
            r"(candidates|confirmed|needs_confirmation|not_attributed|skipped)"
            r"_total$"
        ),
        "agent/nodes/review_court.py #180: findings_court_<word>_total at "
        "the run_review_court node boundary — outcome words are the policy "
        "layer's closed COURT_OUTCOMES plus the candidates entering word; "
        "the vocabulary is imported from agent.nodes.review_court by the "
        "derivation test, so a new policy outcome forces this gate and the "
        "family to move together",
    ),
    "replay_verdict": (
        re.compile(
            r"^capsule_replay_verdict_"
            r"(ambiguous|compliant|regression_confirmed|unexpected_fix)"
            r"_total$"
        ),
        "evidence/capsule_replay.py #183: capsule_replay_verdict_<word>_total "
        "after parsing run.sh's stdout on a completed sandbox run — verdict "
        "words are the replay template's closed four-marker vocabulary; the "
        "vocabulary is imported from evidence.capsule_replay (VERDICTS) by "
        "the derivation test, so a template word change forces this gate "
        "and the family to move together",
    ),
    "attribution_signal": (
        re.compile(
            r"^findings_attribution_signal_"
            r"(exit_code_differs|failure_signature_differs"
            r"|head_db_state_differs|head_extra_failure_count)"
            r"_total$"
        ),
        "agent/nodes/review_court.py #184: findings_attribution_signal_<word>"
        "_total per head-only difference signal on a kept attribution — "
        "the vocabulary is imported from agent.review_court.policy "
        "(HEAD_ONLY_SIGNALS) by the derivation test, so a new signal "
        "forces this gate and the family to move together",
    ),
    "diff_outcome": (
        re.compile(
            r"^differential_outcomes_"
            r"(ambiguous|compliant|regression|skipped|unexpected_fix)"
            r"_total$"
        ),
        "agent/nodes/run_differential.py #185: differential_outcomes_<word>"
        "_total at the run_differential node boundary — outcome words are "
        "the closed set of verdict patterns from running tests on both Base "
        "and Head; the vocabulary is imported from agent.nodes.run_differential "
        "(DIFF_OUTCOMES) by the derivation test, so a new outcome pattern "
        "forces this gate and the family to move together",
    ),
    "intake_validation": (
        re.compile(
            r"^intake_(repo_missing|runs|spec_missing|spec_read)_total$"
        ),
        "agent/nodes/intake.py #186: intake_<word>_total at the intake node "
        "boundary — validation outcomes are repo missing / spec missing / "
        "spec read success; runs counts every intake execution. The repo "
        "and spec checks are independent per-check outcomes — one run can "
        "tick repo_missing AND spec_read (a missing repo does not stop the "
        "spec read; #186b pinned by behavior test). Recorded errors abort "
        "the job at the preflight guard (honest attribution, not silent "
        "drops)",
    ),
    "publish_report": (
        re.compile(r"^publish_report_(runs|success)_total$"),
        "agent/nodes/publish_report.py #187: publish_report_<word>_total at "
        "the publish_report node boundary — runs counts every report "
        "generation attempt, success counts completed artifact generation. "
        "The gap between the two is honest: a render/HTML-write failure "
        "counts runs without success, and a lineage failure lands after "
        "the HTML write, leaving the report without its lineage document "
        "(#187b: pinned by behavior test; metadata plumbing failures are "
        "swallowed and move neither counter)",
    ),
    "preflight": (
        re.compile(
            r"^preflight_(outcomes_"
            r"(blocked|clean|disabled|probe_error|upstream_errors)|runs)"
            r"_total$"
        ),
        "agent/nodes/preflight.py #190: preflight_runs_total + preflight_"
        "outcomes_<word>_total at the preflight node boundary — runs counts "
        "every invocation; the outcome words are how the run ended and the "
        "result's passed=True is true for FOUR of the five, so only the "
        "family separates the fates. The vocabulary is imported from "
        "agent.nodes.preflight (PREFLIGHT_OUTCOMES) by the derivation test, "
        "so a new word forces this gate and the family to move together",
    ),
    "compile_contracts": (
        re.compile(
            r"^compile_contracts_(outcomes_"
            r"(approved_loaded|empty_input|llm_degraded|llm_disabled"
            r"|llm_replaced|llm_unavailable|rules_sufficient)|runs)"
            r"_total$"
        ),
        "agent/nodes/compile_contracts.py #192: compile_contracts_runs_total "
        "+ compile_contracts_outcomes_<word>_total at the compile_contracts "
        "node boundary — runs counts every invocation; the outcome word "
        "names which compiler produced the final contract list, which the "
        "compile report's accepted_count alone cannot tell apart (rules "
        "sufficient / LLM disabled or unavailable / LLM replaced the rules / "
        "LLM degraded back to the rules / registry rows loaded / nothing to "
        "compile). The vocabulary is imported from "
        "agent.nodes.compile_contracts (COMPILE_OUTCOMES) by the derivation "
        "test, so a new word forces this gate and the family to move together",
    ),
    "prepare_base": (
        re.compile(
            r"^prepare_base_(outcomes_"
            r"(checkout_failed|prepare_error|prepared|safety_failed)|runs)"
            r"_total$"
        ),
        "agent/nodes/prepare_base.py #193: prepare_base_runs_total + "
        "prepare_base_outcomes_<word>_total at the prepare_base node "
        "boundary — runs counts every invocation; the outcome word names "
        "who ended the attempt: the shared repo safety check refused, git "
        "worktree add exited non-zero, the git invocation raised, or the "
        "worktree was prepared and handed to the graph. Every failure "
        "returns an empty workspace plus one appended error, so the word "
        "is the only machine-readable record of which layer refused. The "
        "vocabulary is imported from agent.nodes.prepare_base "
        "(PREPARE_OUTCOMES) by the derivation test, which also asserts it "
        "equals the twin node's declaration, so a new word moves both "
        "nodes and both families together",
    ),
    "prepare_head": (
        re.compile(
            r"^prepare_head_(outcomes_"
            r"(checkout_failed|prepare_error|prepared|safety_failed)|runs)"
            r"_total$"
        ),
        "agent/nodes/prepare_head.py #193: the twin of prepare_base — one "
        "job mounts two worktrees (base and head), so the same four-word "
        "PREPARE_OUTCOMES vocabulary is emitted per node and the operator "
        "can see which half failed; the fates mirror the base node's "
        "(safety_failed = the same shared check refused; "
        "checkout_failed/prepare_error = the same git-level fates). The "
        "vocabulary is imported from agent.nodes.prepare_head by the "
        "derivation test and asserted equal to the twin's declaration",
    ),
    "collect_diff": (
        re.compile(
            r"^collect_diff_(outcomes_(diff_failed|no_changes|scanned)|runs)"
            r"_total$"
        ),
        "agent/nodes/collect_diff.py #194: collect_diff_runs_total + "
        "collect_diff_outcomes_<word>_total at the collect_diff node "
        "boundary — runs counts every invocation; the outcome word "
        "separates a real scanned diff from a zero-file diff from a diff "
        "that could not be produced at all. No error guard follows this "
        "node (the graph's only one sits after prepare_head), so a failed "
        "diff does not stop the job and downstream state readers see the "
        "same empty tables as a change-free pair of refs — the word is the "
        "only machine-readable record of which case it was. The vocabulary "
        "is imported from agent.nodes.collect_diff (COLLECT_DIFF_OUTCOMES) "
        "by the derivation test, so a new word forces this gate and the "
        "family to move together",
    ),
    "retrieve_repository_context": (
        re.compile(
            r"^retrieve_repository_context_(outcomes_"
            r"(bm25_graph|es_unavailable|hybrid_rrf|no_java_sources"
            r"|no_workspace|retrieval_failed)|runs)_total$"
        ),
        "agent/nodes/retrieve_repository_context.py #195: "
        "retrieve_repository_context_runs_total + "
        "retrieve_repository_context_outcomes_<word>_total at the "
        "retrieval node boundary — runs counts every invocation; the word "
        "separates a real hybrid/BM25 retrieval (config-dependent "
        "subsystem) from the no-input fates decided before any infra "
        "access, from the documented ES-unavailable degradation and from "
        "an attempt that raised. An empty repo_context alone cannot tell "
        "those apart (retrieval can succeed with zero hits). The "
        "vocabulary is imported from "
        "agent.nodes.retrieve_repository_context (RETRIEVE_OUTCOMES) by "
        "the derivation test, so a new word forces this gate and the "
        "family to move together",
    ),
    "run_static_checks": (
        re.compile(
            r"^run_static_checks_(outcomes_"
            r"(checked|checker_failures|inputs_missing)|runs)_total$"
        ),
        "agent/nodes/run_static_checks.py #196: run_static_checks_runs_total "
        "+ run_static_checks_outcomes_<word>_total at the run_static_checks "
        "node boundary — runs counts every invocation; the outcome word "
        "separates a fully returned check run from one where at least one "
        "checker crashed (CHECKER_FAILED is infrastructure evidence, never "
        "a source verdict — a crash must not read as 'no problems found') "
        "and from the defensive missing-inputs short circuit (the errors "
        "guard precedes this node, so today's graph cannot reach it). An "
        "empty static_findings list looks identical for a clean run and a "
        "short-circuited one. The vocabulary is imported from "
        "agent.nodes.run_static_checks (RUN_STATIC_OUTCOMES) by the "
        "derivation test, so a new word forces this gate and the family "
        "to move together",
    ),
    "generate_counterexamples": (
        re.compile(
            r"^generate_counterexamples_(outcomes_"
            r"(deterministic_template|llm_generated|no_workspace"
            r"|template_unsupported|workspace_not_tempdir)|runs)_total$"
        ),
        "agent/nodes/generate_counterexamples.py #197: "
        "generate_counterexamples_runs_total + "
        "generate_counterexamples_outcomes_<word>_total at the node "
        "boundary — runs counts every invocation; the word separates an "
        "LLM-generated compiled test from the demo fallback template (whose "
        "own head-run compile result rides the record's compile_passed "
        "flag, not the word) from the two honest empty-path refusals "
        "(no workspace / LLM failed on a non-demo repo). An empty "
        "generated_tests_path appears in both refusal cases — the word is "
        "the only countable difference. The vocabulary is imported from "
        "agent.nodes.generate_counterexamples (GENERATE_TEST_OUTCOMES) by "
        "the derivation test, so a new word forces this gate and the "
        "family to move together",
    ),
    "run_deep_experiments": (
        re.compile(
            r"^run_deep_experiments_(outcomes_"
            r"(completed|inputs_missing|not_requested)|runs)_total$"
        ),
        "agent/nodes/run_deep_experiments.py #198: "
        "run_deep_experiments_runs_total + "
        "run_deep_experiments_outcomes_<word>_total at the node boundary — "
        "runs counts every invocation; the word separates the healthy FAST "
        "default (not_requested) from a DEEP request that had nothing to "
        "run on (inputs_missing — the tier is silently empty) from a full "
        "campaign that ran and wrote its report (completed). An empty "
        "deep_results looks identical for the first two. The vocabulary is "
        "imported from agent.nodes.run_deep_experiments "
        "(RUN_DEEP_OUTCOMES) by the derivation test, so a new word forces "
        "this gate and the family to move together",
    ),
    "build_matrix": (
        re.compile(
            r"^build_matrix_(outcomes_"
            r"(built|no_contracts|pass_downgraded)|runs)_total$"
        ),
        "agent/nodes/build_matrix.py #199: build_matrix_runs_total + "
        "build_matrix_outcomes_<word>_total at the node boundary — runs "
        "counts every invocation; the word separates a normal build from "
        "a contract-less state (no_contracts: findings-only matrix) from a "
        "build where this node's own evaluate_verification gate refused at "
        "least one PASS row and rewrote it to UNVERIFIED "
        "(pass_downgraded). Row counts alone cannot separate a "
        "contract-less matrix from a fully-UNVERIFIED one. The vocabulary "
        "is imported from agent.nodes.build_matrix (BUILD_MATRIX_OUTCOMES) "
        "by the derivation test, so a new word forces this gate and the "
        "family to move together",
    ),
    "create_capsule": (
        re.compile(
            r"^create_capsule_(outcomes_"
            r"(filtered_out|no_findings|packed)|runs)_total$"
        ),
        "agent/nodes/create_capsule.py #200: create_capsule_runs_total + "
        "create_capsule_outcomes_<word>_total at the node boundary — runs "
        "counts every invocation; the word separates a run that packed >=1 "
        "capsule from the two empty-list endings: no confirmed findings at "
        "all vs findings that were all below the BLOCKER/MAJOR packaging "
        "threshold. Capsule metadata recording stays best-effort (logged, "
        "no counter — the documented gap shared with publish_report). The "
        "vocabulary is imported from agent.nodes.create_capsule "
        "(CREATE_CAPSULE_OUTCOMES) by the derivation test, so a new word "
        "forces this gate and the family to move together",
    ),
    "run_release_checks": (
        re.compile(
            r"^run_release_checks_(outcomes_"
            r"(failed|not_requested|passed)|runs)_total$"
        ),
        "agent/nodes/run_release_checks.py #201: run_release_checks_runs_total "
        "+ run_release_checks_outcomes_<word>_total at the node boundary — "
        "runs counts every invocation; the word separates the healthy "
        "not-requested default (depth != RELEASE) from a gate aggregate "
        "that held (passed) from one that refused (failed: unreproducible "
        "flip, nothing to re-run, or a capsule digest mismatch). Which "
        "gate refused lives in release_results.gates and the report. The "
        "vocabulary is imported from agent.nodes.run_release_checks "
        "(RUN_RELEASE_OUTCOMES) by the derivation test, so a new word "
        "forces this gate and the family to move together",
    ),
    "tool_denial": (
        re.compile(
            r"^tool_denials_"
            r"(approval_required|command_not_allowed|path_escape"
            r"|path_out_of_range|plane_toolchain_missing)_total$"
        ),
        "craft/tools.py #208: incr(\"tool_denials_\" + code.lower() + "
        "\"_total\") inside _denied(), the single construction point of "
        "every denied ToolResult — the code words are the closed "
        "DENIAL_CODES set (approval gate / command whitelist / path "
        "containment / owned_paths range / pinned-plane toolchain). The "
        "vocabulary is imported from craft.tools (DENIAL_CODES) by the "
        "derivation test, so a new denial code forces this gate and the "
        "family to move together",
    ),
    "tool_error": (
        re.compile(
            r"^tool_errors_"
            r"(ast_parse_failed|edit_rejected|execution_failed|file_not_found"
            r"|invalid_arguments|not_a_git_repo|stale_context"
            r"|tool_version_mismatch|unknown_tool)_total$"
        ),
        "craft/tools.py #209: incr(\"tool_errors_\" + code.lower() + "
        "\"_total\") inside _error(), the single construction point of "
        "every error ToolResult — the code words are the closed "
        "ERROR_CODES set (unknown tool / version mismatch / argument "
        "validation / missing file / not-a-git-repo / stale context / "
        "rejected edit / AST parse failure / handler crash). The "
        "vocabulary is imported from craft.tools (ERROR_CODES) by the "
        "derivation test, so a new error code forces this gate and the "
        "family to move together",
    ),
    "mcp_tool_error": (
        re.compile(
            r"^mcp_tool_errors_"
            r"(invalid_arguments|mcp_connection_error|mcp_protocol_error"
            r"|mcp_server_error|mcp_timeout|unknown_tool|unprefixed)_total$"
        ),
        "craft/mcp_wiring.py #211: incr(f\"mcp_tool_errors_{_error_word("
        "result.summary)}_total\") inside the metered external-tool handler "
        "— the word is the bridge summary's \"[CODE] \" stamp read back and "
        "lowercased, with the declared unprefixed fallback for prefix-less "
        "summaries; the vocabulary derives from mcp.client's stable CODE_* "
        "set plus that fallback word by the derivation test, so a new "
        "client code or a moved fallback declaration forces this gate and "
        "the family to move together",
    ),
}


def _walk_strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _walk_strings(value)]
    if isinstance(node, list):
        return [s for item in node for s in _walk_strings(item)]
    return []


def _referenced_names() -> set[str]:
    names: set[str] = set()
    for rel in REFERENCE_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        if rel.suffix == ".json":
            # Scan every string in the document: exprs, legends and the prose
            # descriptions all quote metric names, and a stale name in prose
            # misleads exactly like a stale one in an expr.
            text = " ".join(_walk_strings(json.loads(text)))
        for match in _REFERENCE.finditer(text):
            names.add(match.group(1))
    # Prose placeholders like jobs_duration_seconds_<depth> capture as a name
    # ending in "_". A real metric never does, and the placeholder names a
    # documented family — drop them rather than widening the families.
    return {n for n in names if not n.endswith("_")}


@lru_cache(maxsize=1)
def _emission_sites() -> tuple[tuple[str, str, str, bool], ...]:
    """(repo-relative file, emit call, resolved name) for every scanned site.

    One walk, three readers (#296): ``_emitted_names``, ``emission_files`` and
    ``emitted_types`` all used to re-implement this scan, which is how the
    suffix rule drifted from the call shapes it is supposed to follow. Cached
    because the accounting helper asks per referenced name; a mutated tree is
    measured in a fresh process, never by re-reading through this cache.
    """
    found: list[tuple[str, str, str, bool]] = []
    for emit_dir in EMIT_DIRS:
        for path in sorted((ROOT / emit_dir).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            constants = dict(_MODULE_CONST.findall(text))
            rel = path.relative_to(ROOT).as_posix()
            for call, literal, const in _EMIT_CALL.findall(text):
                if literal:
                    found.append((rel, call, literal, False))
                elif const in constants:
                    found.append((rel, call, constants[const], False))
            for call, raw in _CONCAT_CALL.findall(text):
                found.append((rel, call, raw.strip("\"'"), True))
    return tuple(found)


def _emitted_names() -> set[str]:
    names = {"up"}  # observability/metrics.py::render_text, unconditional
    names.update(n for _, _, n, concat in _emission_sites() if not concat)
    return names


def emission_files() -> set[str]:
    """Repo-relative paths of the modules that own an emission site (#217).

    Same scan as ``_emitted_names`` — the shared ``_emission_sites`` walk — but
    returns the owning FILES instead of the metric names, so a caller can
    reconcile a per-file inventory (OBSERVABILITY.md 8.10 calls the emission
    sites its only legal source, so its list and this census must be equal).
    A runtime-concatenated emission (``observe_duration("es_request_seconds_"
    + op, …)``) owns its file too: the name is unlistable, the site is not.

    ``observability/metrics.py`` is added explicitly: ``render_text`` emits
    ``up`` unconditionally rather than through incr/set_gauge/
    observe_duration, and the doc's inventory names that entry too ("含
    render_text 自己的条目").
    """
    files = {"observability/metrics.py"}
    for rel, _, _, _ in _emission_sites():
        files.add(rel)
    return files


@lru_cache(maxsize=1)
def emitted_types() -> dict[str, str]:
    """Metric name -> the exposition type its own call site gives it.

    ``incr`` makes a counter, ``set_gauge`` a gauge, ``observe_duration`` a
    histogram (observability/metrics.py keeps three separate stores). Only
    histograms get ``_bucket/_sum/_count`` siblings, so this is what makes the
    suffix reduction in account_name legal or illegal. Runtime-concatenated
    prefixes are NOT names: they are read from concatenated_prefix_types().
    """
    types = {"up": "gauge"}
    for _, call, name, concat in _emission_sites():
        if not concat:
            types[name] = _EMIT_KINDS[call]
    return types


@lru_cache(maxsize=1)
def concatenated_prefix_types() -> dict[str, str]:
    """Runtime name prefixes -> the type of the call that builds them.

    ``observe_duration("jobs_duration_seconds_" + depth.lower(), …)`` gives
    every name in that family a histogram's siblings; ``incr("notify_" + …)``
    gives its names none. Derived from the same walk as emitted_types so a
    family never carries a hand-written type.
    """
    kinds: dict[str, str] = {}
    for _, call, prefix, concat in _emission_sites():
        if concat:
            kinds[prefix] = _EMIT_KINDS[call]
    return kinds


def base_type(name: str) -> str | None:
    """The exposition type of a bare (no-suffix) metric name, or None.

    Literal names read emitted_types(); a runtime-concatenated name reads the
    LONGEST matching prefix from concatenated_prefix_types() — ``jobs_`` (a
    counter family) and ``jobs_duration_seconds_`` (a histogram family) are both
    prefixes of ``jobs_duration_seconds_fast``, and only the longer one owns it.
    """
    types = emitted_types()
    if name in types:
        return types[name]
    prefixes = concatenated_prefix_types()
    owner = max(
        (p for p in prefixes if name.startswith(p)),
        key=len,
        default=None,
    )
    return prefixes[owner] if owner else None


def account_name(name: str) -> str:
    """Why a scraped spelling is (or is not) produced by this codebase.

    Verdicts: ``counter``/``gauge``/``histogram`` for a name an emit site owns
    directly, ``family`` for a runtime-concatenated name, ``histogram-<suffix>``
    for an exposition sibling of a histogram base, ``placeholder`` for the
    ``specproof_x_`` stems the docs quote before a ``<word>``/``*`` wildcard,
    ``unaccounted`` otherwise.

    #296: the suffix reduction used to run UNCONDITIONALLY, so any name ending in
    ``_count`` was matched as if it had lost a histogram sibling. That made
    ``outbox_retry_count`` (a gauge that really is named that) read dead, and
    ``outbox_published_total_count`` (a name no emitter produces) read alive.
    """
    if name.endswith("_"):
        return "placeholder"
    if name in _emitted_names():
        return emitted_types()[name]
    if any(pattern.match(name) for pattern, _ in CONCATENATED_FAMILIES.values()):
        return "family"
    for suffix in _HISTOGRAM_SUFFIXES:
        if not name.endswith(suffix):
            continue
        base = name[: -len(suffix)]
        if base_type(base) == "histogram":
            return f"histogram{suffix}"
    return "unaccounted"


def test_every_referenced_metric_name_traces_to_an_emission_site() -> None:
    referenced = _referenced_names()

    unaccounted: list[str] = []
    for name in sorted(referenced):
        if account_name(name) != "unaccounted":
            continue
        unaccounted.append(name)

    assert not unaccounted, (
        "alerts/dashboards reference metric names with no emission site "
        f"(OBSERVABILITY.md '已接线指标名' is the inventory method): {unaccounted}. "
        "Either the reference is stale (fix the alert/dashboard), or the name "
        "is a new concatenated family (register it in CONCATENATED_FAMILIES "
        "with its emission-site pointer and vocabulary derivation)."
    )


def test_every_emitted_name_has_exactly_one_kind() -> None:
    """A name emitted through two stores is two series with one spelling."""
    kinds: dict[str, set[str]] = {}
    for _, call, name, concat in _emission_sites():
        if not concat:
            kinds.setdefault(name, set()).add(call)
    assert len(kinds) >= 100, f"emission scan collapsed: {len(kinds)} names"
    mixed = {n: sorted(k) for n, k in kinds.items() if len(k) > 1}
    assert not mixed, (
        "the same metric name is emitted through more than one entry point "
        f"(counter/gauge/histogram keep separate stores): {mixed}"
    )


def test_suffix_permission_follows_the_emit_call_kind() -> None:
    """#296: ``_bucket/_sum/_count`` is legal only on a histogram base.

    Before #296 the reduction ran unconditionally, which made a real gauge
    (``outbox_retry_count``) read dead and a name no emitter produces
    (``outbox_published_total_count``) read alive. Both directions are measured
    here from the scanned call shapes, not from a hand list.
    """
    types = emitted_types()
    histogram_bases = sorted(n for n, kind in types.items() if kind == "histogram")
    assert len(histogram_bases) >= 5, (
        f"histogram scan collapsed: {len(histogram_bases)} bases"
    )
    # A concatenation prefix must never be read as a complete name: the
    # literal alternative in _EMIT_CALL requires a closing `,`/`)` exactly so
    # observe_duration("jobs_duration_seconds_" + depth… ) stays a prefix.
    leaked_prefixes = sorted(n for n in types if n.endswith("_"))
    assert not leaked_prefixes, (
        f"emit scan read runtime prefixes as whole names: {leaked_prefixes}"
    )
    for base in histogram_bases:
        for suffix in _HISTOGRAM_SUFFIXES:
            assert account_name(f"{base}{suffix}") == f"histogram{suffix}", (
                f"{base} is emitted by observe_duration, so {base}{suffix} "
                "must be accepted as an exposition sibling"
            )

    # Runtime-concatenated histogram families get the same permission through
    # their prefix's call kind, and only through it. Probed on the names the
    # shipped references actually quote, so the leg cannot pass on a made-up
    # word no family accepts.
    histogram_prefixes = sorted(
        p for p, kind in concatenated_prefix_types().items() if kind == "histogram"
    )
    assert histogram_prefixes, "no concatenated histogram family found"
    exercised = 0
    for prefix in histogram_prefixes:
        for member in sorted(n for n in _referenced_names() if n.startswith(prefix)):
            assert account_name(f"{member}_bucket") == "histogram_bucket", (
                f"family {prefix}* is built by observe_duration, so "
                f"{member}_bucket must be accepted as an exposition sibling"
            )
            exercised += 1
    assert exercised >= 2, (
        f"only {exercised} concatenated histogram reference(s) found — the "
        "family half of the rule is barely exercised"
    )

    # The false-red shape: a name whose own spelling ends in a histogram
    # suffix but whose call is NOT observe_duration. It must be accepted as
    # itself, and the same tail ADDED to it must be refused.
    suffix_tailed_non_histograms = sorted(
        n for n, kind in types.items()
        if kind != "histogram" and n.endswith(_HISTOGRAM_SUFFIXES)
    )
    assert suffix_tailed_non_histograms, (
        "no non-histogram metric ends in a histogram suffix — this leg's "
        "false-red half is vacuous; pick another witness or delete the half"
    )
    for name in suffix_tailed_non_histograms:
        assert account_name(name) != "unaccounted", (
            f"{name} is emitted as a {types[name]} but reads dead: the suffix "
            "reduction is running before the name is looked up"
        )
        for suffix in _HISTOGRAM_SUFFIXES:
            assert account_name(f"{name}{suffix}") == "unaccounted", (
                f"{name} is a {types[name]}; {name}{suffix} is not a series "
                "anyone produces and must not be excused as a sibling"
            )


def test_references_actually_exercise_the_histogram_rule() -> None:
    """Vacuity floor: some shipped reference must need the suffix reduction."""
    exercised = [
        n for n in sorted(_referenced_names()) if account_name(n).startswith("histogram")
    ]
    assert exercised, (
        "no alerts/dashboard reference resolves through the histogram rule — "
        "the rule is untested by the shipped combat surface"
    )


def _alternation_branches(pattern: re.Pattern[str]) -> list[str]:
    """The inside of the family's single (...) group, split on '|'."""
    inside = re.search(r"\(([^()]+)\)", pattern.pattern)
    assert inside is not None, f"family pattern has no (...) group: {pattern.pattern}"
    return inside.group(1).split("|")


def test_concatenated_families_track_their_vocabularies() -> None:
    """Family wildcards must derive from the real vocabulary sources."""

    # notify == SendStatus members (integrations/notify/protocol.py). Derive
    # the expected alternation from the enum so a new member forces this gate
    # and the family to move together.
    from integrations.notify.protocol import SendStatus

    notify_pattern, _ = CONCATENATED_FAMILIES["notify"]
    expected = "^notify_(" + "|".join(m.value for m in SendStatus) + ")_total$"
    assert notify_pattern.pattern == expected, (
        "notify family drifted from SendStatus: "
        f"{notify_pattern.pattern} != {expected}"
    )

    # depth == the shipped CLI choice (the WIDEST enqueue/exec vocabulary:
    # POST /jobs and MCP are currently narrower, and webhook hard-codes FAST —
    # the family must cover what the product can name, not what one gate takes).
    cli_text = (ROOT / "cli" / "specproof" / "commands" / "verify.py").read_text(
        encoding="utf-8"
    )
    choice_match = re.search(r"click\.Choice\(\[([^\]]*)\]\)", cli_text)
    assert choice_match is not None, "CLI verify --depth choice not found"
    depths = [d.lower() for d in re.findall(r'"([A-Z]+)"', choice_match.group(1))]
    depth_pattern, _ = CONCATENATED_FAMILIES["depth"]
    assert sorted(_alternation_branches(depth_pattern)) == sorted(depths), (
        f"depth family {depth_pattern.pattern} != CLI choice {depths}"
    )
    for depth in depths:
        assert depth_pattern.match(f"jobs_duration_seconds_{depth}"), (
            f"family rejects shipped depth {depth}"
        )

    # verdict / stage stay anchored single-token wildcards (their vocabularies
    # are Python-identifier-shaped and enumerated elsewhere); assert the
    # anchoring that keeps them from becoming catch-alls.
    for key in ("verdict", "stage"):
        pattern, _ = CONCATENATED_FAMILIES[key]
        assert pattern.pattern.startswith("^") and pattern.pattern.endswith("$")
        assert "(...)" not in pattern.pattern

    # es_op == the Elasticsearch client methods the store actually calls.
    # Derived from the self.client.<word> call sites in the emission file
    # itself: a new ES client op fails this gate until the family (and the
    # dashboard regex, if the panel is extended) moves with it.
    es_text = (ROOT / "storage" / "elasticsearch.py").read_text(encoding="utf-8")
    es_ops = sorted(set(re.findall(r"self\.client\.(\w+)", es_text)))
    assert es_ops, "no Elasticsearch client call sites found"
    es_pattern, _ = CONCATENATED_FAMILIES["es_op"]
    expected_es = "^es_request_seconds_(" + "|".join(es_ops) + ")$"
    assert es_pattern.pattern == expected_es, (
        f"es_op family {es_pattern.pattern} != client call sites {es_ops}"
    )
    for op in es_ops:
        assert es_pattern.match(f"es_request_seconds_{op}"), (
            f"family rejects shipped es op {op}"
        )

    # redis_op == the Redis client methods the store actually calls (#212).
    # Same derivation shape as es_op: the vocabulary is read from the
    # emission file's self.client.<word> call sites, so a new Redis call
    # fails this gate until the family (and the dashboard panel) moves with
    # it.
    redis_text = (ROOT / "storage" / "redis.py").read_text(encoding="utf-8")
    redis_ops = sorted(set(re.findall(r"self\.client\.(\w+)", redis_text)))
    assert redis_ops, "no Redis client call sites found"
    redis_pattern, _ = CONCATENATED_FAMILIES["redis_op"]
    expected_redis = "^redis_request_seconds_(" + "|".join(redis_ops) + ")$"
    assert redis_pattern.pattern == expected_redis, (
        f"redis_op family {redis_pattern.pattern} != client call sites "
        f"{redis_ops}"
    )
    for op in redis_ops:
        assert redis_pattern.match(f"redis_request_seconds_{op}"), (
            f"family rejects shipped redis op {op}"
        )

    # tool_stem == the executor's command whitelist. Imported, not AST-read:
    # craft.executor is import-safe (its tests import it too) and importing
    # the constant keeps the family pinned to what the product ships —
    # CRAFT_EXTRA_COMMANDS may extend the whitelist at runtime, those runs
    # still emit into the family (the name is built by concatenation and the
    # dashboard selects with a wildcard), but the gate covers the shipped
    # vocabulary only.
    from craft.executor import ALLOWED_COMMANDS

    tool_pattern, _ = CONCATENATED_FAMILIES["tool_stem"]
    expected_tool = "^tool_run_seconds_(" + "|".join(sorted(ALLOWED_COMMANDS)) + ")$"
    assert tool_pattern.pattern == expected_tool, (
        f"tool_stem family {tool_pattern.pattern} != whitelist "
        f"{sorted(ALLOWED_COMMANDS)}"
    )
    for stem in sorted(ALLOWED_COMMANDS):
        assert tool_pattern.match(f"tool_run_seconds_{stem}"), (
            f"family rejects whitelisted stem {stem}"
        )

    # court_outcome == the policy layer's closed outcome vocabulary plus the
    # candidates entering word. Imported, same discipline as tool_stem: a
    # new policy outcome forces the gate and the family to move together.
    from agent.nodes.review_court import FINDINGS_COURT_WORDS

    court_pattern, _ = CONCATENATED_FAMILIES["court_outcome"]
    expected_court = (
        "^findings_court_(" + "|".join(sorted(FINDINGS_COURT_WORDS)) + ")_total$"
    )
    assert court_pattern.pattern == expected_court, (
        f"court_outcome family {court_pattern.pattern} != policy vocabulary "
        f"{sorted(FINDINGS_COURT_WORDS)}"
    )
    for word in sorted(FINDINGS_COURT_WORDS):
        assert court_pattern.match(f"findings_court_{word}_total"), (
            f"family rejects court word {word}"
        )

    # replay_verdict == the capsule replay template's closed verdict
    # markers. Imported from evidence.capsule_replay (VERDICTS maps the
    # template's uppercase stdout markers to the lowercase family words) —
    # same discipline as court_outcome: a template word change forces this
    # gate and the family to move together.
    from evidence.capsule_replay import VERDICTS

    replay_pattern, _ = CONCATENATED_FAMILIES["replay_verdict"]
    expected_replay = (
        "^capsule_replay_verdict_("
        + "|".join(sorted(set(VERDICTS.values())))
        + ")_total$"
    )
    assert replay_pattern.pattern == expected_replay, (
        f"replay_verdict family {replay_pattern.pattern} != template "
        f"vocabulary {sorted(set(VERDICTS.values()))}"
    )
    for word in sorted(set(VERDICTS.values())):
        assert replay_pattern.match(f"capsule_replay_verdict_{word}_total"), (
            f"family rejects replay verdict word {word}"
        )

    # attribution_signal == the policy layer's closed head-only difference
    # signal vocabulary. Imported, same discipline as court_outcome: a new
    # signal in the preexisting-defect comparison forces this gate and the
    # family to move together.
    from agent.review_court.policy import HEAD_ONLY_SIGNALS

    attribution_pattern, _ = CONCATENATED_FAMILIES["attribution_signal"]
    expected_attribution = (
        "^findings_attribution_signal_("
        + "|".join(sorted(HEAD_ONLY_SIGNALS))
        + ")_total$"
    )
    assert attribution_pattern.pattern == expected_attribution, (
        f"attribution_signal family {attribution_pattern.pattern} != policy "
        f"vocabulary {sorted(HEAD_ONLY_SIGNALS)}"
    )
    for word in sorted(HEAD_ONLY_SIGNALS):
        assert attribution_pattern.match(
            f"findings_attribution_signal_{word}_total"
        ), f"family rejects attribution signal {word}"

    # preflight == the node's closed PREFLIGHT_OUTCOMES vocabulary. Imported,
    # same discipline as court_outcome: the result's passed=True covers four
    # of the five words, so the family is the only place the fates separate.
    from agent.nodes.preflight import PREFLIGHT_OUTCOMES

    preflight_pattern, _ = CONCATENATED_FAMILIES["preflight"]
    expected_preflight = (
        "^preflight_(outcomes_("
        + "|".join(sorted(PREFLIGHT_OUTCOMES))
        + ")|runs)_total$"
    )
    assert preflight_pattern.pattern == expected_preflight, (
        f"preflight family {preflight_pattern.pattern} != node vocabulary "
        f"{sorted(PREFLIGHT_OUTCOMES)}"
    )
    for word in sorted(PREFLIGHT_OUTCOMES):
        assert preflight_pattern.match(f"preflight_outcomes_{word}_total"), (
            f"family rejects preflight outcome {word}"
        )

    # compile_contracts == the node's closed COMPILE_OUTCOMES vocabulary.
    # Imported, same discipline as preflight: which compiler produced the
    # final contract list is only visible in the outcome word.
    from agent.nodes.compile_contracts import COMPILE_OUTCOMES

    compile_pattern, _ = CONCATENATED_FAMILIES["compile_contracts"]
    expected_compile = (
        "^compile_contracts_(outcomes_("
        + "|".join(sorted(COMPILE_OUTCOMES))
        + ")|runs)_total$"
    )
    assert compile_pattern.pattern == expected_compile, (
        f"compile_contracts family {compile_pattern.pattern} != node "
        f"vocabulary {sorted(COMPILE_OUTCOMES)}"
    )
    for word in sorted(COMPILE_OUTCOMES):
        assert compile_pattern.match(f"compile_contracts_outcomes_{word}_total"), (
            f"family rejects compile outcome {word}"
        )

    # prepare_base == the prepare nodes' closed PREPARE_OUTCOMES vocabulary,
    # imported from both twin declarations (same discipline as preflight).
    # The two nodes are verbatim twins, so the derivation also asserts the
    # declarations are word-for-word equal: an accidental one-copy edit
    # fails here, and a deliberate divergence must move this gate AND both
    # families, never just one node.
    from agent.nodes.prepare_base import PREPARE_OUTCOMES as BASE_PREPARE_OUTCOMES
    from agent.nodes.prepare_head import PREPARE_OUTCOMES as HEAD_PREPARE_OUTCOMES

    assert BASE_PREPARE_OUTCOMES == HEAD_PREPARE_OUTCOMES, (
        "twin prepare vocabularies drifted: "
        f"{sorted(BASE_PREPARE_OUTCOMES)} != {sorted(HEAD_PREPARE_OUTCOMES)}"
    )
    for node_name in ("prepare_base", "prepare_head"):
        prepare_pattern, _ = CONCATENATED_FAMILIES[node_name]
        expected_prepare = (
            f"^{node_name}_(outcomes_("
            + "|".join(sorted(BASE_PREPARE_OUTCOMES))
            + ")|runs)_total$"
        )
        assert prepare_pattern.pattern == expected_prepare, (
            f"{node_name} family {prepare_pattern.pattern} != node "
            f"vocabulary {sorted(BASE_PREPARE_OUTCOMES)}"
        )
        for word in sorted(BASE_PREPARE_OUTCOMES):
            assert prepare_pattern.match(f"{node_name}_outcomes_{word}_total"), (
                f"family rejects {node_name} outcome {word}"
            )

    # collect_diff == the node's closed COLLECT_DIFF_OUTCOMES vocabulary.
    # Imported, same discipline as preflight: the graph has no error guard
    # after this node, so the outcome word is the only machine-readable
    # record separating a failed diff from a change-free pair of refs.
    from agent.nodes.collect_diff import COLLECT_DIFF_OUTCOMES

    diff_pattern, _ = CONCATENATED_FAMILIES["collect_diff"]
    expected_diff = (
        "^collect_diff_(outcomes_("
        + "|".join(sorted(COLLECT_DIFF_OUTCOMES))
        + ")|runs)_total$"
    )
    assert diff_pattern.pattern == expected_diff, (
        f"collect_diff family {diff_pattern.pattern} != node vocabulary "
        f"{sorted(COLLECT_DIFF_OUTCOMES)}"
    )
    for word in sorted(COLLECT_DIFF_OUTCOMES):
        assert diff_pattern.match(f"collect_diff_outcomes_{word}_total"), (
            f"family rejects collect_diff outcome {word}"
        )

    # retrieve_repository_context == the node's closed RETRIEVE_OUTCOMES
    # vocabulary. Imported, same discipline as preflight: an empty
    # repo_context alone cannot tell "retrieval ran, zero candidates" from
    # "no infra" from "no inputs" from "it raised".
    from agent.nodes.retrieve_repository_context import RETRIEVE_OUTCOMES

    retrieve_pattern, _ = CONCATENATED_FAMILIES["retrieve_repository_context"]
    expected_retrieve = (
        "^retrieve_repository_context_(outcomes_("
        + "|".join(sorted(RETRIEVE_OUTCOMES))
        + ")|runs)_total$"
    )
    assert retrieve_pattern.pattern == expected_retrieve, (
        f"retrieve family {retrieve_pattern.pattern} != node vocabulary "
        f"{sorted(RETRIEVE_OUTCOMES)}"
    )
    for word in sorted(RETRIEVE_OUTCOMES):
        assert retrieve_pattern.match(
            f"retrieve_repository_context_outcomes_{word}_total"
        ), f"family rejects retrieve outcome {word}"

    # run_static_checks == the node's closed RUN_STATIC_OUTCOMES vocabulary.
    # Imported, same discipline as preflight: an empty static_findings list
    # looks identical for a clean checked run and a short-circuited one.
    from agent.nodes.run_static_checks import RUN_STATIC_OUTCOMES

    static_pattern, _ = CONCATENATED_FAMILIES["run_static_checks"]
    expected_static = (
        "^run_static_checks_(outcomes_("
        + "|".join(sorted(RUN_STATIC_OUTCOMES))
        + ")|runs)_total$"
    )
    assert static_pattern.pattern == expected_static, (
        f"run_static_checks family {static_pattern.pattern} != node "
        f"vocabulary {sorted(RUN_STATIC_OUTCOMES)}"
    )
    for word in sorted(RUN_STATIC_OUTCOMES):
        assert static_pattern.match(
            f"run_static_checks_outcomes_{word}_total"
        ), f"family rejects run_static_checks outcome {word}"

    # generate_counterexamples == the node's closed GENERATE_TEST_OUTCOMES
    # vocabulary. Imported, same discipline as preflight: an empty
    # generated_tests_path appears in both honest refusal cases.
    from agent.nodes.generate_counterexamples import GENERATE_TEST_OUTCOMES

    gen_pattern, _ = CONCATENATED_FAMILIES["generate_counterexamples"]
    expected_gen = (
        "^generate_counterexamples_(outcomes_("
        + "|".join(sorted(GENERATE_TEST_OUTCOMES))
        + ")|runs)_total$"
    )
    assert gen_pattern.pattern == expected_gen, (
        f"generate_counterexamples family {gen_pattern.pattern} != node "
        f"vocabulary {sorted(GENERATE_TEST_OUTCOMES)}"
    )
    for word in sorted(GENERATE_TEST_OUTCOMES):
        assert gen_pattern.match(
            f"generate_counterexamples_outcomes_{word}_total"
        ), f"family rejects generate outcome {word}"

    # run_deep_experiments == the node's closed RUN_DEEP_OUTCOMES
    # vocabulary. Imported, same discipline as preflight: an empty
    # deep_results looks identical for "FAST default" and "DEEP requested
    # but nothing to run on".
    from agent.nodes.run_deep_experiments import RUN_DEEP_OUTCOMES

    deep_pattern, _ = CONCATENATED_FAMILIES["run_deep_experiments"]
    expected_deep = (
        "^run_deep_experiments_(outcomes_("
        + "|".join(sorted(RUN_DEEP_OUTCOMES))
        + ")|runs)_total$"
    )
    assert deep_pattern.pattern == expected_deep, (
        f"run_deep_experiments family {deep_pattern.pattern} != node "
        f"vocabulary {sorted(RUN_DEEP_OUTCOMES)}"
    )
    for word in sorted(RUN_DEEP_OUTCOMES):
        assert deep_pattern.match(
            f"run_deep_experiments_outcomes_{word}_total"
        ), f"family rejects DEEP outcome {word}"

    # build_matrix == the node's closed BUILD_MATRIX_OUTCOMES vocabulary.
    # Imported, same discipline as preflight: row counts alone cannot
    # separate a contract-less matrix from a fully-UNVERIFIED one.
    from agent.nodes.build_matrix import BUILD_MATRIX_OUTCOMES

    matrix_pattern, _ = CONCATENATED_FAMILIES["build_matrix"]
    expected_matrix = (
        "^build_matrix_(outcomes_("
        + "|".join(sorted(BUILD_MATRIX_OUTCOMES))
        + ")|runs)_total$"
    )
    assert matrix_pattern.pattern == expected_matrix, (
        f"build_matrix family {matrix_pattern.pattern} != node vocabulary "
        f"{sorted(BUILD_MATRIX_OUTCOMES)}"
    )
    for word in sorted(BUILD_MATRIX_OUTCOMES):
        assert matrix_pattern.match(
            f"build_matrix_outcomes_{word}_total"
        ), f"family rejects matrix outcome {word}"

    # create_capsule == the node's closed CREATE_CAPSULE_OUTCOMES
    # vocabulary. Imported, same discipline as preflight: the two
    # empty-list endings return the same capsules==[] shape.
    from agent.nodes.create_capsule import CREATE_CAPSULE_OUTCOMES

    capsule_pattern, _ = CONCATENATED_FAMILIES["create_capsule"]
    expected_capsule = (
        "^create_capsule_(outcomes_("
        + "|".join(sorted(CREATE_CAPSULE_OUTCOMES))
        + ")|runs)_total$"
    )
    assert capsule_pattern.pattern == expected_capsule, (
        f"create_capsule family {capsule_pattern.pattern} != node "
        f"vocabulary {sorted(CREATE_CAPSULE_OUTCOMES)}"
    )
    for word in sorted(CREATE_CAPSULE_OUTCOMES):
        assert capsule_pattern.match(
            f"create_capsule_outcomes_{word}_total"
        ), f"family rejects capsule outcome {word}"

    # run_release_checks == the node's closed RUN_RELEASE_OUTCOMES
    # vocabulary. Imported, same discipline as preflight: an empty
    # release_results marks the not-requested default, and the per-gate
    # detail lives in release_results.gates, not in more words.
    from agent.nodes.run_release_checks import RUN_RELEASE_OUTCOMES

    release_pattern, _ = CONCATENATED_FAMILIES["run_release_checks"]
    expected_release = (
        "^run_release_checks_(outcomes_("
        + "|".join(sorted(RUN_RELEASE_OUTCOMES))
        + ")|runs)_total$"
    )
    assert release_pattern.pattern == expected_release, (
        f"run_release_checks family {release_pattern.pattern} != node "
        f"vocabulary {sorted(RUN_RELEASE_OUTCOMES)}"
    )
    for word in sorted(RUN_RELEASE_OUTCOMES):
        assert release_pattern.match(
            f"run_release_checks_outcomes_{word}_total"
        ), f"family rejects release outcome {word}"

    # tool_denial == the craft tool gate's closed DENIAL_CODES set: every
    # status="denied" ToolResult rides one of these codes through _denied().
    # The family lowercases the CODE_* literals, so the expected
    # alternation derives from DENIAL_CODES itself (same discipline as
    # tool_stem/court_outcome: imported, not hand-copied). code.lower()
    # keeps the name charset inside [a-z0-9_] — the assertion pins that.
    from craft.tools import DENIAL_CODES

    denial_lower = sorted(code.lower() for code in DENIAL_CODES)
    assert len(set(denial_lower)) == len(DENIAL_CODES), (
        f"DENIAL_CODES collapses under lowercasing: {sorted(DENIAL_CODES)}"
    )
    denial_pattern, _ = CONCATENATED_FAMILIES["tool_denial"]
    expected_denial = "^tool_denials_(" + "|".join(denial_lower) + ")_total$"
    assert denial_pattern.pattern == expected_denial, (
        f"tool_denial family {denial_pattern.pattern} != denial vocabulary "
        f"{denial_lower}"
    )
    for word in denial_lower:
        assert denial_pattern.match(f"tool_denials_{word}_total"), (
            f"family rejects denial code {word}"
        )

    # tool_error == the craft tool gate's closed ERROR_CODES set: every
    # status="error" ToolResult rides one of these codes through _error().
    # Same discipline as tool_denial: the expected alternation derives from
    # ERROR_CODES itself (imported, not hand-copied), code.lower() keeps
    # the name charset inside [a-z0-9_], and the two closed sets must be
    # disjoint — error and denied can never share a word.
    from craft.tools import ERROR_CODES

    error_lower = sorted(code.lower() for code in ERROR_CODES)
    assert len(set(error_lower)) == len(ERROR_CODES), (
        f"ERROR_CODES collapses under lowercasing: {sorted(ERROR_CODES)}"
    )
    assert not (set(ERROR_CODES) & set(DENIAL_CODES)), (
        "ERROR_CODES and DENIAL_CODES overlap: "
        f"{sorted(set(ERROR_CODES) & set(DENIAL_CODES))}"
    )
    error_pattern, _ = CONCATENATED_FAMILIES["tool_error"]
    expected_error = "^tool_errors_(" + "|".join(error_lower) + ")_total$"
    assert error_pattern.pattern == expected_error, (
        f"tool_error family {error_pattern.pattern} != error vocabulary "
        f"{error_lower}"
    )
    for word in error_lower:
        assert error_pattern.match(f"tool_errors_{word}_total"), (
            f"family rejects error code {word}"
        )


    # mcp_tool_error == the external MCP boundary's read-side vocabulary:
    # the six stable CODE_* words mcp.client declares (lowercased — the
    # bridge stamps "[CODE] " into every failure summary and the wiring
    # meter reads it back) plus the wiring's declared unprefixed fallback
    # word for prefix-less summaries. Both halves derive from the product
    # sources, not a hand copy: the codes from mcp.client.__all__, the
    # fallback from the wiring source's own declaration.
    import mcp.client as mcp_client

    mcp_client_words = sorted(
        getattr(mcp_client, name).lower()
        for name in mcp_client.__all__
        if name.startswith("CODE_")
    )
    assert len(mcp_client_words) == 6, (
        f"mcp.client code vocabulary moved: {mcp_client_words}"
    )
    assert len(set(mcp_client_words)) == 6, (
        f"mcp.client codes collapse under lowercasing: {mcp_client_words}"
    )
    wiring_src = (ROOT / "craft" / "mcp_wiring.py").read_text(encoding="utf-8")
    fallback_words = re.findall(r'^_UNSTAMPED_WORD = "([a-z_]+)"$', wiring_src, re.M)
    assert len(fallback_words) == 1, (
        f"mcp_wiring fallback declaration not unique: {fallback_words}"
    )
    mcp_words = sorted([*mcp_client_words, fallback_words[0]])
    mcp_pattern, _ = CONCATENATED_FAMILIES["mcp_tool_error"]
    expected_mcp = "^mcp_tool_errors_(" + "|".join(mcp_words) + ")_total$"
    assert mcp_pattern.pattern == expected_mcp, (
        f"mcp_tool_error family {mcp_pattern.pattern} != mcp vocabulary "
        f"{mcp_words}"
    )
    for word in mcp_words:
        assert mcp_pattern.match(f"mcp_tool_errors_{word}_total"), (
            f"family rejects mcp error word {word}"
        )


def test_rabbitmq_scrape_stays_paired_with_broker_side_alerts() -> None:
    """The #165 broker-side alerts consume rabbitmq_* series that only the
    rabbitmq scrape job provides — and only in its per-object rendering.

    A revert of the scrape job, or a metrics_path back to the aggregate
    /metrics (which has no per-queue series — verified live against the
    container's own endpoint in #165), leaves the queue/DLQ selectors
    matching nothing: absent series never fire, so the rule files stay
    valid and every broker-side signal goes dark silently. The parity gate
    cannot see this drift (its regex only covers specproof_* names), so
    this test pins the pairing at the text level.
    """
    prom = (ROOT / "infra" / "prometheus" / "prometheus.yml").read_text(
        encoding="utf-8"
    )
    alerts = (ROOT / "infra" / "prometheus" / "alerts-slo.yml").read_text(
        encoding="utf-8"
    )

    # The scrape job must exist, on the per-object path, against the plugin
    # port (rabbitmq_prometheus ships enabled in the management image).
    assert "- job_name: rabbitmq" in prom
    assert "metrics_path: /metrics/per-object" in prom
    assert 'targets: ["rabbitmq:15692"]' in prom

    # Both alerts must still reference the plugin's series.
    assert "alert: SpecproofVerifyQueueBacklogHigh" in alerts
    assert "rabbitmq_queue_messages_ready" in alerts
    assert "alert: SpecproofVerifyDlqNonEmpty" in alerts
    # The DLQ selector derives its shape from storage/rabbitmq.py's
    # dlq_suffix='.dlq' rule. Escaping is double: PromQL string literals
    # reject `\.` (promtool: "unknown escape sequence"), so the regex needs
    # `\\.` inside the PromQL source, and the single-quoted YAML passes it
    # through verbatim — a de-escaped variant fails promtool AND matches
    # garbage names.
    assert 'queue=~"q\\\\..+\\\\.dlq"' in alerts

    # The dashboard panels carry the same double-escaped PromQL. No config
    # gate validates Grafana JSON exprs, so a single-backslash literal there
    # fails only at query time (same silent dark). Compare against the
    # JSON-parsed form: json.load unescapes once, leaving the two-backslash
    # PromQL source.
    dashboard = json.loads(
        (ROOT / "infra" / "grafana" / "dashboards" / "specproof-slo.json")
        .read_text(encoding="utf-8")
    )
    rabbit_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "rabbitmq_queue" in target.get("expr", "")
    ]
    assert len(rabbit_exprs) == 3, f"expected 3 rabbitmq panel exprs, got {rabbit_exprs}"
    assert any('queue=~"q\\\\..+"' in expr for expr in rabbit_exprs)
    assert any('queue=~"q\\\\..+\\\\.dlq"' in expr for expr in rabbit_exprs)


def test_stage_duration_panel_selector_tracks_the_stage_family() -> None:
    """#166: the per-stage panel selects the concatenated stage family via a
    __name__ regex. The parity gate drops that reference as a prose
    placeholder (the captured name ends in '_'), so a typo'd family name in
    the selector would go unnoticed and the panel would be silently empty —
    pin the exact selector and the two quantiles instead.
    """
    dashboard = json.loads(
        (ROOT / "infra" / "grafana" / "dashboards" / "specproof-slo.json")
        .read_text(encoding="utf-8")
    )
    stage_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "worker_stage_duration_seconds_" in target.get("expr", "")
    ]
    assert len(stage_exprs) == 2, f"expected p50+p95 stage exprs, got {stage_exprs}"
    expected_selector = (
        '__name__=~"specproof_worker_stage_duration_seconds_[a-z0-9_]+_bucket"'
    )
    for expr in stage_exprs:
        assert expected_selector in expr, expr
    assert any("histogram_quantile(0.95" in expr for expr in stage_exprs)
    assert any("histogram_quantile(0.50" in expr for expr in stage_exprs)

    # Same drift shape for the ES latency panel (#169): the family is
    # concatenated at runtime, the reference regex captures a trailing-
    # underscore placeholder the gate drops, so the exact selector and
    # quantiles are pinned at text level.
    es_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "es_request_seconds_" in target.get("expr", "")
    ]
    assert len(es_exprs) == 2, f"expected p50+p95 es exprs, got {es_exprs}"
    expected_es_selector = (
        '__name__=~"specproof_es_request_seconds_[a-z_]+_bucket"'
    )
    for expr in es_exprs:
        assert expected_es_selector in expr, expr
    assert any("histogram_quantile(0.95" in expr for expr in es_exprs)
    assert any("histogram_quantile(0.50" in expr for expr in es_exprs)

    # Same drift shape for the tool-execution panel (#178): the stem family
    # is concatenated at runtime, the panel's reference is a __name__ regex
    # the gate drops as a placeholder, so the exact selector and both
    # quantiles are pinned at text level.
    tool_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "tool_run_seconds_" in target.get("expr", "")
    ]
    assert len(tool_exprs) == 2, f"expected p50+p95 tool exprs, got {tool_exprs}"
    expected_tool_selector = (
        '__name__=~"specproof_tool_run_seconds_[a-z0-9_]+_bucket"'
    )
    for expr in tool_exprs:
        assert expected_tool_selector in expr, expr
    assert any("histogram_quantile(0.95" in expr for expr in tool_exprs)
    assert any("histogram_quantile(0.50" in expr for expr in tool_exprs)

    # Same drift shape for the tool-gate refusal panel (#208): the denial
    # family reference is a __name__ regex the gate drops as a placeholder,
    # while tool_calls_total is a literal the gate traces by itself. Pin the
    # selector and the calls expr, and require the description to name every
    # DENIAL_CODES word — the reading rule must not drift from the closed
    # vocabulary the derivation test pins.
    denial_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "tool_denials" in target.get("expr", "")
    ]
    assert len(denial_exprs) == 1, f"expected 1 denial selector expr, got {denial_exprs}"
    expected_denial_selector = '__name__=~"specproof_tool_denials_[a-z0-9_]+_total"'
    assert expected_denial_selector in denial_exprs[0], denial_exprs[0]
    calls_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "specproof_tool_calls_total" in target.get("expr", "")
    ]
    # One shared calls denominator per tool-gate panel: #208 refusals and
    # #209 errors each pair their family rate with the same expr.
    expected_calls_expr = "sum(rate(specproof_tool_calls_total[15m]))"
    assert calls_exprs == [expected_calls_expr] * 2, calls_exprs

    from craft.tools import DENIAL_CODES

    refusal_panels = [p for p in dashboard["panels"] if p.get("id") == 45]
    assert len(refusal_panels) == 1, "tool-gate refusal panel (id 45) missing"
    description = refusal_panels[0]["description"]
    for code in sorted(DENIAL_CODES):
        assert code.lower() in description, (
            f"panel description does not name denial word {code.lower()}"
        )

    # Same drift shape for the tool-execution-error panel (#209): the error
    # family reference is a __name__ regex the gate drops as a placeholder,
    # so pin the selector and require the description to name every
    # ERROR_CODES word — the reading rule must not drift from the closed
    # vocabulary the derivation test pins.
    error_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "specproof_tool_errors" in target.get("expr", "")
    ]
    assert len(error_exprs) == 1, f"expected 1 error selector expr, got {error_exprs}"
    expected_error_selector = '__name__=~"specproof_tool_errors_[a-z0-9_]+_total"'
    assert expected_error_selector in error_exprs[0], error_exprs[0]

    from craft.tools import ERROR_CODES

    error_panels = [p for p in dashboard["panels"] if p.get("id") == 46]
    assert len(error_panels) == 1, "tool-error panel (id 46) missing"
    error_description = error_panels[0]["description"]
    for code in sorted(ERROR_CODES):
        assert code.lower() in error_description, (
            f"panel description does not name error word {code.lower()}"
        )
    # #210: LLM 请求三件套 (provider 边界) — requests/errors 是字面名, 由
    # 上方的 trace 门自己核对发点名; 这里 pin 面板的漂移形状: 两条速率表达式
    # 与图例, 以及延迟面板的两条分位数 (bucket 名与 observe_duration 的第一
    # 参数字面一致 — trace 门已按 _bucket 后缀剥回核对)。
    llm_request_panel = [p for p in dashboard["panels"] if p.get("id") == 47]
    assert len(llm_request_panel) == 1, "LLM request panel (id 47) missing"
    llm_request_targets = {
        t["expr"]: t.get("legendFormat")
        for t in llm_request_panel[0].get("targets", [])
    }
    assert llm_request_targets == {
        "sum(rate(specproof_llm_requests_total[15m]))": "requests/s",
        "sum(rate(specproof_llm_request_errors_total[15m]))": "errors/s",
    }, llm_request_targets

    llm_latency_panel = [p for p in dashboard["panels"] if p.get("id") == 48]
    assert len(llm_latency_panel) == 1, "LLM latency panel (id 48) missing"
    llm_latency_exprs = {
        t["expr"] for t in llm_latency_panel[0].get("targets", [])
    }
    assert llm_latency_exprs == {
        "histogram_quantile(0.50, "
        "sum(rate(specproof_llm_request_seconds_bucket[15m])) by (le))",
        "histogram_quantile(0.95, "
        "sum(rate(specproof_llm_request_seconds_bucket[15m])) by (le))",
    }, llm_latency_exprs

    # #211: MCP 外部工具边界三件套 (craft/mcp_wiring.py) — calls 是字面名,
    # 由上方 trace 门自己核对发点名; 错误族选择器是 __name__ 正则 (trace 门
    # 按占位符丢弃), 延迟 bucket 名与 observe_duration 第一参数字面一致。
    # 这里 pin 面板的漂移形状: 面板 49 的两条表达式与图例、面板 50 的两条
    # 分位数, 以及 49 的描述必须挨个点名读侧词表 (六个稳定码 + 声明的回退
    # 词, 两半都派生自产品源码) — 读法与派生门钉的词表不许各走各的。
    mcp_panel = [p for p in dashboard["panels"] if p.get("id") == 49]
    assert len(mcp_panel) == 1, "MCP boundary panel (id 49) missing"
    mcp_targets = {
        t["expr"]: t.get("legendFormat") for t in mcp_panel[0].get("targets", [])
    }
    assert mcp_targets == {
        "sum(rate(specproof_mcp_tool_calls_total[15m]))": "calls/s",
        'sum by (__name__) (rate({__name__=~"specproof_mcp_tool_errors_'
        '[a-z0-9_]+_total"}[15m]))': "{{__name__}}/s",
    }, mcp_targets

    mcp_latency_panel = [p for p in dashboard["panels"] if p.get("id") == 50]
    assert len(mcp_latency_panel) == 1, "MCP latency panel (id 50) missing"
    mcp_latency_exprs = {
        t["expr"] for t in mcp_latency_panel[0].get("targets", [])
    }
    assert mcp_latency_exprs == {
        "histogram_quantile(0.50, "
        "sum(rate(specproof_mcp_tool_seconds_bucket[15m])) by (le))",
        "histogram_quantile(0.95, "
        "sum(rate(specproof_mcp_tool_seconds_bucket[15m])) by (le))",
    }, mcp_latency_exprs

    import mcp.client as mcp_client

    fallback_match = re.search(
        r'^_UNSTAMPED_WORD = "([a-z_]+)"$',
        (ROOT / "craft" / "mcp_wiring.py").read_text(encoding="utf-8"),
        re.M,
    )
    assert fallback_match is not None, "mcp_wiring fallback declaration missing"
    mcp_pin_words = sorted(
        [
            *(
                getattr(mcp_client, name).lower()
                for name in mcp_client.__all__
                if name.startswith("CODE_")
            ),
            fallback_match.group(1),
        ]
    )
    assert len(mcp_pin_words) == 7, mcp_pin_words
    description49 = mcp_panel[0]["description"]
    for word in mcp_pin_words:
        assert word in description49, (
            f"MCP boundary panel description does not name word {word}"
        )

    # Same drift shape for the Redis latency panel (#212): the family is
    # concatenated at runtime, the panel's reference is a __name__ regex the
    # gate drops as a placeholder, so the exact selector and both quantiles
    # are pinned at text level.
    redis_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "redis_request_seconds_" in target.get("expr", "")
    ]
    assert len(redis_exprs) == 2, f"expected p50+p95 redis exprs, got {redis_exprs}"
    expected_redis_selector = (
        '__name__=~"specproof_redis_request_seconds_[a-z_]+_bucket"'
    )
    for expr in redis_exprs:
        assert expected_redis_selector in expr, expr
    assert any("histogram_quantile(0.95" in expr for expr in redis_exprs)
    assert any("histogram_quantile(0.50" in expr for expr in redis_exprs)
