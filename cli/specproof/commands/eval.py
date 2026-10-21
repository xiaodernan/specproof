
"""specproof eval — Run evaluation across golden cases (v2).

Each case runs the FULL verification pipeline against its own scenario refs
(scenario.json), with the LLM disabled by default so numbers are
reproducible. Findings are matched against ground truth by contract id.
Worktrees created by the pipeline are cleaned up after each case.

Each case record carries duration_ms: whole-pipeline wall clock measured
around the graph invocation. The Phase 0 graph exposes no per-stage
timestamps, so timings are honest at the case level only (SLO stats are
computed by scripts/bench_latency.py).
"""
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import click

from cli.specproof.case_set import (
    empty_pool_message,
    plan_case_dirs,
)
from evidence.acceptance import (
    AcceptanceCriteria,
    MetricCounts,
    acceptance_verdict_text,
    evaluate,
    fmt_metric,
    severity_match_of,
    severity_reconciliation,
)
from evidence.report import render_eval_report


def _schema_reachable(database: str) -> bool:
    """Can this schema be written? A read-only probe: it never creates
    anything and never touches a row."""
    if not database:
        return False
    try:
        import pymysql

        from storage.mysql import MySQLConfig

        config = MySQLConfig.from_env()
        connection = pymysql.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=database,
            charset="utf8mb4",
            connect_timeout=3,
        )
        connection.close()
        return True
    except Exception:  # noqa: BLE001 — unreachable is a fact, not a crash
        return False


def _choose_write_schema(
    env: dict[str, str], probe: Any,
) -> tuple[str, str]:
    """Where this evaluation's rows go — and why.

    An evaluation is a MEASUREMENT: what it writes (object-metadata
    rows keyed ``eval-*``) belongs in the TEST schema, not in the
    product's. When a test schema is configured AND reachable, that is
    where the rows go; otherwise the ambient schema is used — and the
    caller SAYS which one it used, because a run that writes into the
    product's tables without saying so is a hygiene problem nobody
    sees.

    A test schema that is configured but NOT reachable is not used: a
    run that cannot write anywhere must say so, not pretend.
    """
    ambient = (env.get("MYSQL_DATABASE") or "").strip()
    test_schema = (env.get("SPECPROOF_TEST_MYSQL_DATABASE") or "").strip()
    if test_schema and test_schema != ambient:
        if probe(test_schema):
            return test_schema, (
                "the evaluation writes to the TEST schema — its rows are "
                "measurements, not production records"
            )
        return ambient, (
            f"the configured test schema {test_schema!r} is NOT reachable "
            f"— the evaluation writes to {ambient or 'the ambient schema'} "
            "instead, and says so"
        )
    return ambient, (
        "no test schema is configured (SPECPROOF_TEST_MYSQL_DATABASE) — "
        f"the evaluation writes to {ambient or 'the ambient schema'}"
    )


def _cleanup_worktrees(repo: str, final: dict[str, Any]) -> None:
    from contextlib import suppress

    for key in ("base_workspace", "head_workspace"):
        ws = final.get(key, "")
        if not ws:
            continue
        with suppress(Exception):
            subprocess.run(
                ["git", "-C", repo, "worktree", "remove", "--force", ws],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
            )


_EVIDENCE_FIELDS = (
    "contract_id",
    "severity",
    "confidence",
    "evidence_type",
    "db_state_verdict",
)


def _finding_evidence(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact evidence per finding, for the report the reader actually gets.

    A severity mismatch must be diagnosable from the report alone. The matched
    finding already carries the reason its severity is what it is -- most
    sharply ``db_state_verdict`` (did the differential capture a DB mutation, or
    none at all?) and ``confidence``. Without it the report says "MAJOR where
    BLOCKER was expected" and leaves the reader to re-run the pipeline to learn
    why. No new claims: only fields the finding already set are copied.
    """
    out: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        summary = {
            key: finding[key]
            for key in _EVIDENCE_FIELDS
            if finding.get(key) is not None
        }
        if summary:
            out.append(summary)
    return out


def _load_json(path: Path) -> tuple[dict[str, Any], str]:
    """Read a case JSON file, returning (data, error). An EMPTY error means OK.

    A case file that cannot be read is NOT a crash: a real four-case eval died
    with a raw `PermissionError` traceback when one `ground-truth.json` hit a
    transient Windows file lock, and every case after it never ran. The eval
    measures many cases, so one unreadable file must cost that case, not the
    whole run. The caller turns the error into a per-case skip with the reason
    stated out loud.
    """
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "file not found"
    except PermissionError as exc:
        return {}, f"permission denied: {exc}"
    except (OSError, ValueError) as exc:
        return {}, f"cannot read: {exc}"
    if not isinstance(loaded, dict):
        return {}, "not a JSON object"
    return loaded, ""


def _repo_head_sha(repo: str) -> str:
    """Best-effort revision of the code under test; 'unknown' if not a git checkout.

    The repo revision is part of the pool snapshot: a reading taken against one
    commit is not comparable to a reading taken against another, and a sidecar
    without it can be diffed against the wrong build (#77, #251).
    """
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _pool_snapshot(
    repo: str,
    case_dirs: list[Path],
    *,
    min_recall: float | None,
    min_precision: float | None,
    min_f1: float | None,
    max_false_positives: int | None,
    min_positive_cases: int,
    min_negative_cases: int,
) -> dict[str, Any]:
    """A fingerprint of exactly what a measurement run covered.

    #252 requires every reading to be labelled with a pool snapshot so a 4-case
    CI run can never be diffed against / read as a 90-case full-pool run. The
    snapshot records the repo revision under test, the exact kept case list, the
    positive/negative split (from each case's ground-truth ``should_detect``),
    and the floors the verdict was judged against. A sidecar without this lets
    two numbers from different pools look identical (#77, #251).

    The split mirrors the run loop: a case with no / unreadable ground truth is
    treated as negative (should_detect defaults to False), exactly as the loop
    counts it after the run.
    """
    positive = 0
    negative = 0
    case_names: list[str] = []
    for d in case_dirs:
        case_names.append(d.name)
        should_detect = False
        gt_file = d / "ground-truth.json"
        if gt_file.exists():
            gt, gt_error = _load_json(gt_file)
            if not gt_error:
                should_detect = bool(gt.get("should_detect", False))
        if should_detect:
            positive += 1
        else:
            negative += 1
    return {
        "repo_sha": _repo_head_sha(repo),
        "total_kept": len(case_dirs),
        "positive_cases": positive,
        "negative_cases": negative,
        "case_names": sorted(case_names),
        "floors": {
            "min_recall": min_recall,
            "min_precision": min_precision,
            "min_f1": min_f1,
            "max_false_positives": max_false_positives,
            "min_positive_cases": min_positive_cases,
            "min_negative_cases": min_negative_cases,
        },
    }


def _ref_problems(repo: str, case_dirs: list[Path]) -> list[str]:
    """Scenario refs that do not resolve in `repo`, one line each.

    A missing ref is a SETUP problem, not a detection result: the pipeline's
    base-prepare node cannot create a worktree from a ref that is not there, so
    the case would come back `NOT_RUN` (or worse, be mistaken for a detection
    failure) for a reason the operator has to reverse-engineer out of a
    mid-pipeline message. Resolving the refs first turns that into an up-front,
    named, actionable failure — the same honesty the rest of this command
    enforces for "did not run" vs "ran and missed".

    Only cases that will actually run are checked (a case without `spec.md` is
    skipped by the loop below, so its refs are irrelevant).
    """
    problems: list[str] = []
    for case_dir in case_dirs:
        if not (case_dir / "spec.md").exists():
            continue
        scenario: dict[str, Any] = {}
        sc_file = case_dir / "scenario.json"
        if sc_file.exists():
            try:
                scenario = json.loads(sc_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                scenario = {}  # a malformed scenario is not a ref problem
        # Same defaults the run below uses, so the preflight and the run agree.
        for key, ref in (
            ("base_ref", scenario.get("base_ref", "base")),
            ("head_ref", scenario.get("head_ref", "head-v1")),
        ):
            if not ref:
                continue
            probe = subprocess.run(
                ["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            )
            if probe.returncode != 0:
                problems.append(f"  {case_dir.name}: {key} = {ref!r}")
    return problems


def _ensure_scenario_refs(repo: str, case_dirs: list[Path]) -> None:
    """Fail loud, before the run, when `--repo` cannot resolve a case's refs.

    Skipped when `--repo` is not itself a git repository: in that case the
    pipeline reports the real problem, and a "ref missing" message would only
    add noise on top of it.
    """
    is_git = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--git-dir"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if is_git.returncode != 0:
        return
    problems = _ref_problems(repo, case_dirs)
    if not problems:
        return
    raise click.ClickException(
        "以下场景引用的 git ref 在 --repo 里解析不到，评测无法在这些案例上运行：\n"
        + "\n".join(problems)
        + f"\n\n请确认 --repo ({repo}) 是这些 ref 所在的仓库；"
        "golden 场景的 ref 由 scripts/build_golden_scenarios.py 生成。"
    )


@click.command("eval")
@click.option(
    "--cases",
    "cases_dir",
    required=True,
    help="Path to golden-cases directory",
)
@click.option(
    "--repo",
    "repo_path",
    default=None,
    help="Path to demo repo (full-pipeline cases need it)",
)
@click.option("--output", default="docs/eval/eval-report.html", help="Output report path")
@click.option(
    "--llm/--no-llm",
    "use_llm",
    default=False,
    help="Enable LLM-assisted nodes (default: deterministic only)",
)
@click.option(
    "--gate",
    is_flag=True,
    default=False,
    help="Exit non-zero unless the acceptance status is PASS "
    "(enforces the sample/floor criteria below as a CI gate).",
)
@click.option("--min-recall", type=float, default=None,
              help="Recall floor (0-100); unset = only sample sufficiency is enforced")
@click.option("--min-precision", type=float, default=None,
              help="Precision floor (0-100); unset = only sample sufficiency is enforced")
@click.option("--min-f1", type=float, default=None,
              help="F1 floor (0-100)")
@click.option("--max-false-positives", type=int, default=None,
              help="上限：负例上最多允许多少个已确认误报"
                   "（0 = 零误报；unset = 误报不参与判定）")
@click.option("--min-positive-cases", type=int, default=10,
              help="Fewest should-detect cases required before a verdict is trusted")
@click.option("--min-negative-cases", type=int, default=5,
              help="Fewest negative cases required before a verdict is trusted")
@click.option("--include-holdout", is_flag=True, default=False,
              help="关闭 holdout 隔离，隐藏案例一起跑（报告会标明本轮未隔离）")
@click.option("--only-holdout", is_flag=True, default=False,
              help="只跑 manifest 声明的 holdout 案例，单独报告隐藏集上的指标")
@click.option("--holdout-manifest", default=None,
              help="holdout manifest 路径（默认 docs/eval/holdout-manifest.json）")
def eval_cmd(
    cases_dir: str,
    repo_path: str | None,
    output: str,
    use_llm: bool,
    gate: bool,
    min_recall: float | None,
    min_precision: float | None,
    min_f1: float | None,
    max_false_positives: int | None,
    min_positive_cases: int,
    min_negative_cases: int,
    include_holdout: bool,
    only_holdout: bool,
    holdout_manifest: str | None,
) -> None:
    """Evaluate SpecProof against golden cases.

    Runs the full verification pipeline per case using that case's
    scenario.json refs, then compares confirmed findings with the
    ground truth (contract-id matching).

    The case set is isolated by default: cases declared in
    docs/eval/holdout-manifest.json are dropped from the run, since a
    metric computed while the hidden cases sit in the pool is not a
    held-out metric (#77). Every run labels the pool it measured —
    header and sidecar — so tuning and holdout numbers can never be
    diffed against each other by accident.
    """
    if include_holdout and only_holdout:
        raise click.ClickException("--include-holdout 与 --only-holdout 互斥")
    cases_path = Path(cases_dir)
    if not cases_path.exists():
        click.echo(f"ERROR: Cases directory not found: {cases_path}", err=True)
        raise SystemExit(1)

    if not repo_path:
        click.echo("ERROR: --repo is required for pipeline evaluation", err=True)
        raise SystemExit(1)
    repo_resolved = str(Path(repo_path).resolve())

    # Where this run's rows go — said out loud, before anything is
    # written (#370). An evaluation's records are measurements; they
    # belong in the test schema when there is one.
    schema, schema_reason = _choose_write_schema(
        dict(os.environ), _schema_reachable,
    )
    if schema:
        os.environ["MYSQL_DATABASE"] = schema
    click.echo(f"Evaluation schema: {schema or '(unset)'} — {schema_reason}")

    discovered = sorted(
        d for d in cases_path.iterdir()
        if d.is_dir() and d.name.startswith("case-")
    )

    plan = plan_case_dirs(
        discovered,
        include_holdout=include_holdout,
        only_holdout=only_holdout,
        manifest_path=holdout_manifest,
    )
    case_dirs = plan.kept
    for line in plan.header_lines():
        click.echo(line)

    snapshot = _pool_snapshot(
        repo_resolved,
        case_dirs,
        min_recall=min_recall,
        min_precision=min_precision,
        min_f1=min_f1,
        max_false_positives=max_false_positives,
        min_positive_cases=min_positive_cases,
        min_negative_cases=min_negative_cases,
    )
    click.echo(
        f"池快照: repo={snapshot['repo_sha'][:12]} "
        f"kept={snapshot['total_kept']} "
        f"(正例 {snapshot['positive_cases']} / 负例 {snapshot['negative_cases']}) "
        f"floors=召回{min_recall}/精确{min_precision}/F1{min_f1}/"
        f"误报{max_false_positives}/正例≥{min_positive_cases}/负例≥{min_negative_cases}"
    )

    if not case_dirs:
        # Zero measured cases never earns a green exit, whether the
        # directory was empty or isolation emptied it — but the two
        # need different fixes, so the message must not conflate them.
        click.echo(empty_pool_message(len(discovered), plan, cases_path))
        raise SystemExit(1)

    # Fail loud BEFORE the run: a scenario ref that does not resolve in --repo
    # is a setup error, and discovering it mid-pipeline reads as a detection
    # result. (Skipped when --repo is not a git repository.)
    _ensure_scenario_refs(repo_resolved, case_dirs)

    click.echo(f"Running evaluation across {len(case_dirs)} golden cases "
               f"(LLM: {'on' if use_llm else 'off'})...\n")

    from agent.graph import build_phase0_graph
    from agent.state import initial_state

    graph = build_phase0_graph()

    results: list[dict[str, Any]] = []
    detected = 0
    total_should_detect = 0
    false_positives = 0
    negative_cases = 0
    not_run = 0

    for case_dir in case_dirs:
        spec_file = case_dir / "spec.md"
        gt_file = case_dir / "ground-truth.json"
        sc_file = case_dir / "scenario.json"

        if not spec_file.exists():
            click.echo(f"  SKIP {case_dir.name}: no spec.md")
            continue

        gt: dict[str, Any] = {}
        if gt_file.exists():
            gt, gt_error = _load_json(gt_file)
            if gt_error:
                # An unreadable ground truth costs THIS case, not the run: the
                # case is skipped with the reason stated, and the rest of the
                # pool is still measured.
                click.echo(f"  SKIP {case_dir.name}: ground-truth.json 无法读取 ({gt_error})")
                # The case was selected but never measured, so it belongs in the
                # not_run column (and the sidecar's not_run), not in nowhere: a
                # silently shrinking denominator is what makes a small eval read
                # as clean.
                not_run += 1
                continue
        scenario: dict[str, Any] = {}
        if sc_file.exists():
            scenario, sc_error = _load_json(sc_file)
            if sc_error:
                click.echo(f"  SKIP {case_dir.name}: scenario.json 无法读取 ({sc_error})")
                not_run += 1
                continue

        base_ref = scenario.get("base_ref", "base")
        head_ref = scenario.get("head_ref", "head-v1")
        should_detect = gt.get("should_detect", False)
        expected_contract = gt.get("expected_contract")
        expected_evidence = gt.get("expected_evidence_type", "UNKNOWN")
        min_findings = gt.get("expected_min_findings", 1)

        # NOTE: should_detect / negative_cases are counted AFTER the run, not
        # here. A case whose pipeline aborted never compared anything, so it
        # belongs in neither the numerator nor the denominator (see the
        # NOT_RUN branch below).

        click.echo(
            f"\n=== {case_dir.name} (base={base_ref}, head={head_ref}) ==="
        )

        state = initial_state(
            repo_path=repo_resolved,
            base_ref=base_ref,
            head_ref=head_ref,
            spec_path=str(spec_file),
            depth="FAST",
        )
        state["use_llm"] = use_llm
        state["output_dir"] = str(Path("reports").resolve())
        state["app_dir"] = "demo/spring-backend"
        # §A task 7: every artifact this job writes is recorded under
        # this job id — and the evidence pack is keyed by it too. Without
        # a job id the collector refuses to write a pack (a pack nobody
        # could find later is worse than no pack), so an evaluation
        # without one silently produced NO evidence chain at all.
        state["job_id"] = f"eval-{case_dir.name}"
        # The evidence pack is the AUDIT TRAIL of a real verification job.
        # An evaluation is a measurement: its packs would be `eval-*` rows
        # in the product's MongoDB that nobody can delete by job id. So
        # the evaluation writes them ONLY when the environment names a
        # database explicitly (the operator then chose where they go).
        state["write_evidence_pack"] = bool(
            os.getenv("MONGODB_DATABASE", "").strip()
        )

        final: dict[str, Any] = {}
        # Case-level timing: wall clock around the whole pipeline. The graph
        # exposes no per-stage timestamps, so duration_ms is honest at the
        # case level only (see scripts/bench_latency.py).
        started_at = time.perf_counter()
        try:
            final = graph.invoke(state)
        except Exception as exc:  # noqa: BLE001
            click.echo(f"  WARNING: pipeline failed for {case_dir.name}: {exc}")
        duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))

        # A node that recorded an error short-circuits the graph
        # (agent/graph.py: guard_errors), so the comparison never happened.
        # Scoring that as a MISS would say "the tool failed to detect the
        # defect" about a run that never looked — and it silently drags Recall
        # down, which can fail the recall gate for a reason unrelated to
        # detection quality (a local untracked .env tripping the repo-safety
        # check is exactly how this was found). Not-run is its own verdict, it
        # is excluded from both sides of the ratio, and it is stated out loud.
        pipeline_errors = final.get("errors") or []
        if pipeline_errors:
            not_run += 1
            for message in pipeline_errors:
                click.echo(f"  NOT RUN: {message}")
            record = {
                "case": case_dir.name,
                "verdict": "NOT_RUN",
                "should_detect": should_detect,
                "duration_ms": duration_ms,
                "expected_severity": gt.get("expected_severity"),
                "expected_evidence": expected_evidence,
                "matched_findings": 0,
                "matched_severities": "—",
                "contracts_found": "",
                "expected_contract": expected_contract or "—",
                "errors": "; ".join(str(e) for e in pipeline_errors),
                "finding_evidence": [],
            }
            record["severity_match"] = severity_match_of(record)
            results.append(record)
            click.echo(
                f"  [NOT_RUN] pipeline aborted before any comparison "
                f"({duration_ms} ms) — excluded from recall, not counted as a miss"
            )
            _cleanup_worktrees(repo_resolved, final)
            continue

        if should_detect:
            total_should_detect += 1
        else:
            negative_cases += 1

        findings = final.get("confirmed_findings", [])

        # The evidence chain is part of what this run produced. If the
        # pack was not written, the run has NO archived evidence — and
        # saying nothing about it would let a broken chain look like a
        # clean one. The state is reported per case, with the reason.
        pack_state = final.get("evidence_pack_saved")
        pack_error = final.get("evidence_pack_error") or ""
        if pack_state is True:
            click.echo(
                f"  evidence pack: saved ({final.get('fragments_collected', 0)} "
                f"fragment(s))"
            )
        else:
            click.echo(
                "  evidence pack: NOT SAVED"
                + (f" — {pack_error}" if pack_error else "")
            )

        matched: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for f in findings:
            fid = f.get("contract_id", "")
            if expected_contract and fid == expected_contract or expected_evidence and (
                expected_evidence in f.get("evidence_type", "")
                or expected_evidence in fid.lower()
            ):
                matched.append(f)
        deduped = []
        for f in matched:
            fid = f.get("id", "")
            if fid not in seen_ids:
                seen_ids.add(fid)
                deduped.append(f)
        matched = deduped

        if should_detect:
            if len(matched) >= min_findings:
                detected += 1
                verdict = "PASS"
            elif matched:
                detected += 1
                verdict = "PARTIAL"
            else:
                verdict = "MISS"
        else:
            # Negative cases must produce ZERO confirmed findings of any
            # kind — not just zero matches against the expected contract
            # (split.json: max_findings = 0).
            if findings:
                false_positives += 1
                verdict = "FALSE_POSITIVE"
            else:
                verdict = "PASS"

        matched_severities = sorted(
            {str(f.get("severity") or "") for f in matched}
        )
        contracts_found = sorted(
            {str(f.get("contract_id") or "") for f in findings}
        )

        record = {
            "case": case_dir.name,
            "verdict": verdict,
            "should_detect": should_detect,
            "duration_ms": duration_ms,
            "expected_severity": gt.get("expected_severity"),
            "expected_evidence": expected_evidence,
            "matched_findings": len(matched),
            "matched_severities": ", ".join(matched_severities) or "—",
            "contracts_found": ", ".join(contracts_found),
            "expected_contract": expected_contract or "—",
        }
        # The finding's own evidence, so a severity mismatch is diagnosable
        # from the report alone (see _finding_evidence). When nothing matched,
        # fall back to every finding so a MISS is diagnosable too.
        record["finding_evidence"] = _finding_evidence(matched or findings)
        # Ground-truth level call: True = exact match, False = drift,
        # None = no level call (recall miss or negative case).
        record["severity_match"] = severity_match_of(record)
        results.append(record)
        click.echo(
            f"  [{verdict}] matched {len(matched)} finding(s), "
            f"contracts found: {contracts_found} ({duration_ms} ms)"
        )

        _cleanup_worktrees(repo_resolved, final)

    # ── Summary statistics (single honest source: evidence.acceptance) ──
    counts = MetricCounts(
        should_detect=total_should_detect,
        detected=detected,
        false_positives=false_positives,
        negative_cases=negative_cases,
    )
    criteria = AcceptanceCriteria(
        min_recall=min_recall,
        min_precision=min_precision,
        min_f1=min_f1,
        max_false_positives=max_false_positives,
        min_positive_cases=min_positive_cases,
        min_negative_cases=min_negative_cases,
    )
    acceptance = evaluate(counts, criteria)
    metrics = acceptance.metrics

    click.echo(f"\n{'=' * 50}")
    click.echo("Evaluation Results")
    click.echo(f"{'=' * 50}")
    click.echo(f"Total cases:        {len(results)}")
    click.echo(f"Not run:            {not_run}")
    click.echo(f"Should detect:      {total_should_detect}")
    click.echo(f"Detected:           {detected}")
    click.echo(f"False positives:    {false_positives}")
    click.echo(f"Negative cases:     {negative_cases}")
    click.echo(f"Precision:          {fmt_metric(metrics.precision)}")
    click.echo(f"Recall:             {fmt_metric(metrics.recall)}")
    click.echo(f"F1 Score:           {fmt_metric(metrics.f1)}")
    severity = severity_reconciliation(results)
    click.echo(
        f"Severity agreement: {fmt_metric(severity['severity_agreement'])} "
        f"({severity['matched_positive_cases']} matched positive cases)"
    )
    click.echo(
        f"Severe precision:   {fmt_metric(severity['severe_precision'])} "
        f"(severe calls: {severity['severe_call_positives']} positive / "
        f"{severity['severe_false_positives']} negative)"
    )
    for m in severity["mismatches"]:
        click.echo(
            f"  ! severity drift: {m['case']} "
            f"expected {m['expected']}, got {m['actual']}"
        )
    click.echo(f"Acceptance:         {acceptance_verdict_text(acceptance)}")
    for line in acceptance.insufficient:
        click.echo(f"  ! 样本不足: {line}")
    for line in acceptance.failures:
        click.echo(f"  x 未达下限: {line}")
    if acceptance.status != "PASS":
        click.echo(
            "  提示: 空/过小的评测集不会给出可信结论 —— 它记为 INSUFFICIENT/"
            "FAIL 而非默认满分。"
        )

    html = render_eval_report(results, acceptance)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    click.echo(f"\nHTML report written to {out}")

    # Machine-readable sidecar consumed by the specproof baseline command
    # (P6: "model reads the diff" comparison) and CI gates. precision/recall/
    # f1 may be null (undefined for this sample) — never a fake 100.0.
    sidecar = out.with_suffix(".results.json")
    sidecar.write_text(
        json.dumps(
            {
                "case_set": plan.as_json(),
                "pool_snapshot": snapshot,
                "total_cases": len(results),
                "not_run": not_run,
                "should_detect": total_should_detect,
                "detected": detected,
                "false_positives": false_positives,
                "negative_cases": negative_cases,
                "precision": metrics.precision,
                "recall": metrics.recall,
                "f1": metrics.f1,
                "acceptance": acceptance.to_dict(),
                "severity_reconciliation": severity,
                "timing_note": (
                    "Per-case duration_ms is whole-pipeline wall clock measured "
                    "around the graph invocation; the Phase 0 graph exposes no "
                    "per-stage timestamps, so stage-level timings are not available."
                ),
                "cases": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    click.echo(f"Results JSON written to {sidecar}")

    if gate and not acceptance.passed:
        raise SystemExit(1)
