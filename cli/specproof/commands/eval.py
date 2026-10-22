
"""specproof eval — Run evaluation across golden cases (v2).

Each case runs the FULL verification pipeline against its own scenario refs
(scenario.json), with the LLM disabled by default so numbers are
reproducible. Findings are matched against ground truth by contract id.
Worktrees created by the pipeline are cleaned up after each case.

Each case record carries duration_ms: whole-pipeline wall clock measured
around the graph invocation. The Phase 0 graph exposes no per-stage
timestamps, so timings are honest at the case level only (SLO stats are
computed by scripts/bench_latency.py).

Every case is ALSO appended to an incremental JSONL sidecar the moment
it finishes. The full report is written at the END of the run, so a run
that is killed (a CI job that hits its timeout, a machine that is
rebooted) leaves NOTHING behind - the hours it measured are gone and
the only way to learn them is to run them again. The JSONL is written
and flushed per case, so what was measured survives the kill.
"""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, TextIO

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


def incremental_results_path(output: str | Path) -> Path:
    """Where the per-case records of a run are appended as they finish."""
    return Path(output).with_suffix(".results.jsonl")


def append_incremental_result(handle: TextIO, record: dict[str, Any]) -> None:
    """Append one case record and make it durable immediately.

    The flush and the fsync are the point: a record that only sits in
    the buffer is a record that a kill takes away.
    """
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def read_incremental_results(path: str | Path) -> list[dict[str, Any]]:
    """Read the records a (possibly killed) run left behind.

    A torn last line - the run was killed in the middle of a write - is
    SKIPPED, not fatal: half a record is not a record, and the cases
    before it are still worth having. Unreadable lines in the middle
    are skipped for the same reason.
    """
    target = Path(path)
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def case_fingerprint(case_dir: str | Path) -> str:
    """What a measurement of this case depended on, as one hash.

    A record is only worth re-using if the case it measured is still the
    SAME case: the same spec, the same ground truth, the same scenario
    refs. The fingerprint is a hash of exactly those three files, so a
    ground truth that was corrected between two runs makes the old record
    stale instead of silently wrong. A missing file and an empty file hash
    differently, so "the scenario appeared" is also a change.
    """
    directory = Path(case_dir)
    digest = hashlib.sha256()
    for name in ("spec.md", "ground-truth.json", "scenario.json"):
        digest.update(name.encode("utf-8"))
        path = directory / name
        try:
            digest.update(path.read_bytes() if path.exists() else b"<absent>")
        except OSError:
            digest.update(b"<unreadable>")
    return digest.hexdigest()


def resume_index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The newest record per case.

    The sidecar is append-only, so a case that was measured twice (the
    ground truth was corrected, the case was re-run) has two lines. The
    later line is the one that describes the case as it is now, so the
    later line wins.
    """
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        name = record.get("case")
        if isinstance(name, str) and name:
            index[name] = record
    return index


def select_resumable(
    records: list[dict[str, Any]],
    fingerprints: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Split a previous run's records into re-usable and stale.

    A record is re-usable only when it carries a fingerprint that still
    matches the case on disk. A record WITHOUT a fingerprint - written by
    an older build, before the fingerprint existed - is NOT re-usable: we
    cannot prove it measured this case as it is now, so the case is
    measured again. Guessing "probably the same" is how a stale number
    becomes a fresh number.
    """
    reusable: dict[str, dict[str, Any]] = {}
    stale: list[str] = []
    for name, record in resume_index(records).items():
        current = fingerprints.get(name)
        if current and record.get("fingerprint") == current:
            reusable[name] = record
        else:
            stale.append(name)
    return reusable, sorted(stale)


def counter_deltas(record: dict[str, Any]) -> tuple[int, int, int, int, int]:
    """What one case record contributes to the run's counters.

    (detected, should_detect, false_positives, negative_cases, not_run)

    The counting rules are the ones the run loop applies to a fresh
    measurement, written down once so a re-used record is counted exactly
    like a re-measured one. A case whose pipeline aborted belongs to
    neither side of the ratio: it is not_run, and it is not a miss.
    """
    verdict = str(record.get("verdict") or "")
    if verdict == "NOT_RUN":
        return (0, 0, 0, 0, 1)
    if record.get("should_detect"):
        detected = 1 if verdict in ("PASS", "PARTIAL") else 0
        return (detected, 1, 0, 0, 0)
    false_positive = 1 if verdict == "FALSE_POSITIVE" else 0
    return (0, 0, false_positive, 1, 0)


def matched_findings(
    findings: list[dict[str, Any]],
    expected_contract: str,
    expected_evidence: str,
) -> list[dict[str, Any]]:
    """The findings that answer THIS case's expectation.

    Two ways a finding can answer it: it carries the expected contract id,
    or its evidence type (or its id) names the expected evidence. The
    second way is why a case whose findings do not carry the expected
    contract id is not automatically a miss.
    """
    matched: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for f in findings:
        fid = f.get("contract_id", "")
        answers = bool(
            expected_contract and fid == expected_contract
            or expected_evidence and (
                expected_evidence in f.get("evidence_type", "")
                or expected_evidence in fid.lower()
            )
        )
        if not answers:
            continue
        finding_id = f.get("id", "")
        if finding_id in seen_ids:
            continue
        seen_ids.add(finding_id)
        matched.append(f)
    return matched


def verdict_for(
    should_detect: bool,
    findings: list[dict[str, Any]],
    matched: list[dict[str, Any]],
    min_findings: int,
) -> str:
    """The verdict ONE measurement earns.

    A positive case is detected when the expected contract was found; a
    negative case is a false positive when the pipeline confirmed
    ANYTHING at all (not just a match against an expectation it does not
    have — see split.json: max_findings = 0).
    """
    if should_detect:
        if len(matched) >= min_findings:
            return "PASS"
        if matched:
            return "PARTIAL"
        return "MISS"
    return "FALSE_POSITIVE" if findings else "PASS"


#: The verdict the differential/probe uses when it LOOKED and could not
#: decide. It is not a "no defect" verdict and it is not a "defect
#: found" verdict: nothing was concluded (ADR-004's evidence ladder
#: refuses to conclude without a comparable observation).
UNJUDGEABLE_VERDICT = "NON_REPRODUCIBLE"

#: The contract id the differential puts on an entry that stands for the
#: WHOLE run rather than for one contract (the run never started, or the
#: whole-run comparison could not be made).
WHOLE_RUN_CONTRACT = "DIFF-01"


def unjudgeable_reason(
    diff_results: list[dict[str, Any]],
    expected_contract: str,
) -> str:
    """Why this case's evidence could not judge it — or "" when it could.

    A case whose evidence path came back NON_REPRODUCIBLE was NOT
    MEASURED: the pipeline looked and could not decide. Scoring that as
    a MISS would say "the tool failed to detect the defect" about a run
    that never compared anything — the exact mistake the NOT_RUN branch
    exists to prevent (ledger #397).

    Only the evidence path for THIS case's contract counts: another
    contract's unjudgeable entry says nothing about this one.
    """
    wanted = str(expected_contract or "")
    for entry in diff_results:
        if str(entry.get("verdict") or "") != UNJUDGEABLE_VERDICT:
            continue
        contract_id = str(entry.get("contract_id") or "")
        if contract_id not in (wanted, WHOLE_RUN_CONTRACT):
            continue
        experiment = str(entry.get("experiment_id") or "DIFF-01")
        detail = str(entry.get("detail") or "").strip()
        subject = contract_id or wanted or "the contract"
        return (
            f"{experiment} could not judge {subject}"
            + (f": {detail}" if detail else "")
        )
    return ""


def unjudgeable_output_tails(
    diff_results: list[dict[str, Any]],
    expected_contract: str,
) -> dict[str, str]:
    """The base/head output tails of the evidence path that could not judge.

    "The probe could not judge this case" is a symptom; the surefire
    output of the side that failed is the diagnosis. Without it, the
    question "why did the base side fail?" has no answer at all — the
    report never carried it (ledger #399).
    """
    wanted = str(expected_contract or "")
    for entry in diff_results:
        if str(entry.get("verdict") or "") != UNJUDGEABLE_VERDICT:
            continue
        contract_id = str(entry.get("contract_id") or "")
        if contract_id not in (wanted, WHOLE_RUN_CONTRACT):
            continue
        return {
            "base_output": str(entry.get("base_output") or ""),
            "head_output": str(entry.get("head_output") or ""),
        }
    return {}


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
@click.option(
    "--resume",
    is_flag=True,
    default=False,
    help="接着上次已量过的案例继续：读回上次落盘的逐案例记录，"
         "输入未变的案例直接复用，只重测变了的和新出现的",
)
@click.option(
    "--attempts",
    type=int,
    default=1,
    help="每个案例最多量几次（默认 1）。有些案例的检出**不稳**："
         "同一份代码、同一个案例，两次测量一次有一次会漏（见账本 #391）"
         "⇒ ⇒ ⇒ >1 时，正例在**第一次检出**就停，负例仍然只量一次"
         "（误报是硬信号，出现就报）⇒ ⇒ ⇒ 于是「这个缺陷能不能被检出」"
         "不再取决于当天的运气，而「第一次就检出」的比例被**单独记下来**",
)
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
    resume: bool,
    attempts: int,
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
    # The FIRST-try numbers: what the pool looks like when every case is
    # measured exactly once. With --attempts > 1 the headline recall
    # answers "can this defect be found", and these answer "was it found
    # the first time" — the reliability of the detection, which is a
    # different question from the capability (ledger #391).
    first_try_detected = 0
    first_try_should_detect = 0
    retried_cases = 0

    # The incremental sidecar: one line per case, written the moment the
    # case finishes. The report at the end of the run is the summary; this
    # is the evidence, and it survives a run that is killed half way.
    incremental_path = incremental_results_path(output)
    incremental_path.parent.mkdir(parents=True, exist_ok=True)

    # What a previous run already measured. Read BEFORE the sidecar is
    # opened: a resumed run appends to the same file, so the records
    # already in it are the ones worth re-using.
    reusable: dict[str, dict[str, Any]] = {}
    stale_cases: list[str] = []
    if resume:
        prior_records = read_incremental_results(incremental_path)
        fingerprints = {d.name: case_fingerprint(d) for d in case_dirs}
        reusable, stale_cases = select_resumable(prior_records, fingerprints)
        click.echo(
            f"续跑：读回 {incremental_path}（{len(prior_records)} 条记录），"
            f"可复用 {len(reusable)} 个案例"
            + (f"，{len(stale_cases)} 个案例的输入变了，要重测" if stale_cases else "")
        )
    # A resumed run APPENDS: the records it re-uses are part of the
    # evidence of the whole pool, and the file is the audit trail.
    incremental_handle = incremental_path.open(
        "a" if resume else "w", encoding="utf-8"
    )
    click.echo(f"Incremental per-case results: {incremental_path}")
    reused_cases = 0

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
        expected_contract = str(gt.get("expected_contract") or "")
        expected_evidence = str(gt.get("expected_evidence_type") or "UNKNOWN")
        min_findings = gt.get("expected_min_findings", 1)

        # What this measurement depends on. A previous run's record for
        # this case is re-used ONLY if this fingerprint still matches.
        fingerprint = case_fingerprint(case_dir)
        prior = reusable.get(case_dir.name)
        if prior is not None:
            # The case was already measured against exactly these inputs.
            # The record is re-used as it was written - the same counting
            # rules a fresh measurement gets - and the run says so.
            results.append(prior)
            (
                delta_detected,
                delta_should,
                delta_false_positives,
                delta_negative,
                delta_not_run,
            ) = counter_deltas(prior)
            detected += delta_detected
            total_should_detect += delta_should
            false_positives += delta_false_positives
            negative_cases += delta_negative
            not_run += delta_not_run
            reused_cases += 1
            click.echo(
                f"  REUSE {case_dir.name}: {prior.get('verdict')} "
                f"（上次已量过，输入未变）"
            )
            continue

        # NOTE: should_detect / negative_cases are counted AFTER the run, not
        # here. A case whose pipeline aborted never compared anything, so it
        # belongs in neither the numerator nor the denominator (see the
        # NOT_RUN branch below).

        click.echo(
            f"\n=== {case_dir.name} (base={base_ref}, head={head_ref}) ==="
        )

        # How many times this case may be measured. A case whose DETECTION
        # is unstable (same code, same case, one run finds the defect and
        # the next does not - ledger #391) would otherwise decide the
        # pool's recall by luck. With --attempts > 1 a positive case is
        # measured again until it is detected, so the number that gets
        # reported answers "CAN this defect be found", and "was it found
        # the FIRST time" is recorded separately instead of being lost.
        attempts_made = 0
        first_attempt_verdict = ""
        final: dict[str, Any] = {}
        duration_ms = 0
        for attempt in range(1, max(1, attempts) + 1):
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
            #
            # The question is the PRESENCE of the variable, not its value, and
            # it is asked that way on purpose (#383): a defaulted read here
            # would declare a SECOND default for MONGODB_DATABASE (the
            # product's own connection declares "specproof_phase0") ⇒ two
            # readers, two defaults ⇒ the drift the env-knob gate exists to
            # catch. Reading the variable without declaring a default says
            # "there is no default here" ⇒ which is the truth.
            state["write_evidence_pack"] = bool(
                "MONGODB_DATABASE" in os.environ
                and os.environ["MONGODB_DATABASE"].strip()
            )
            # Case-level timing: wall clock around the whole pipeline. The graph
            # exposes no per-stage timestamps, so duration_ms is honest at the
            # case level only (see scripts/bench_latency.py).
            started_at = time.perf_counter()
            try:
                final = graph.invoke(state)
            except Exception as exc:  # noqa: BLE001
                click.echo(
                    f"  WARNING: pipeline failed for {case_dir.name}: {exc}"
                )
            duration_ms += max(
                0, round((time.perf_counter() - started_at) * 1000)
            )

            attempts_made = attempt
            if final.get("errors"):
                # The comparison never happened; a retry would not change
                # that, and the case is NOT_RUN either way.
                break
            attempt_findings = list(final.get("confirmed_findings", []))
            attempt_matched = matched_findings(
                attempt_findings, expected_contract, expected_evidence
            )
            attempt_verdict = verdict_for(
                should_detect, attempt_findings, attempt_matched, min_findings
            )
            # An attempt whose evidence path could not JUDGE it did not
            # miss the defect: it never compared anything. Calling that a
            # MISS would put a false statement in the record
            # ("first_attempt_verdict": MISS for a run that never looked),
            # and it is exactly the word the NOT_RUN branch exists to
            # avoid (ledger #397, #399).
            if not attempt_findings and unjudgeable_reason(
                list(final.get("diff_results") or []), expected_contract
            ):
                attempt_verdict = "NOT_RUN"
            if not first_attempt_verdict:
                first_attempt_verdict = attempt_verdict
            # A negative case that found nothing is DECIDED: a false
            # positive is a hard signal and is reported the moment it
            # appears, and hunting for more would cost one full
            # measurement per negative case.
            decisive = (
                bool(attempt_findings)
                if not should_detect
                else bool(attempt_matched)
            )
            if decisive:
                if attempt > 1:
                    click.echo(
                        f"  attempt {attempt}: {attempt_verdict} "
                        f"(the first attempt said {first_attempt_verdict})"
                    )
                break
            click.echo(
                f"  attempt {attempt}: {attempt_verdict} - measuring again "
                f"(up to {attempts} attempts)"
            )

        # A node that recorded an error short-circuits the graph
        # (agent/graph.py: guard_errors), so the comparison never happened.
        # Scoring that as a MISS would say "the tool failed to detect the
        # defect" about a run that never looked — and it silently drags Recall
        # down, which can fail the recall gate for a reason unrelated to
        # detection quality (a local untracked .env tripping the repo-safety
        # check is exactly how this was found). Not-run is its own verdict, it
        # is excluded from both sides of the ratio, and it is stated out loud.
        pipeline_errors = final.get("errors") or []
        findings = final.get("confirmed_findings", [])
        # A case whose evidence path could not JUDGE it was never
        # measured. The pipeline looked and could not conclude; scoring
        # that as a MISS would say "the tool failed to detect the
        # defect" about a run that never compared anything — the same
        # mistake this branch already exists to prevent for a pipeline
        # abort, and the reason the pool's recall used to move with the
        # weather (ledger #397).
        unjudgeable = ""
        tails: dict[str, str] = {}
        if not pipeline_errors and not findings:
            diff_results = list(final.get("diff_results") or [])
            unjudgeable = unjudgeable_reason(diff_results, expected_contract)
            if unjudgeable:
                tails = unjudgeable_output_tails(diff_results, expected_contract)
        if pipeline_errors or unjudgeable:
            not_run += 1
            reasons = [str(e) for e in pipeline_errors] or [unjudgeable]
            for message in reasons:
                click.echo(f"  NOT RUN: {message}")
            # The side that failed, and its own output: without them,
            # "the evidence could not judge this case" is a symptom with
            # no diagnosis attached (ledger #399).
            for side, tail in tails.items():
                if tail:
                    click.echo(f"      {side} output: {tail[-400:]}")
            record = {
                "case": case_dir.name,
                "verdict": "NOT_RUN",
                "should_detect": should_detect,
                "duration_ms": duration_ms,
                "attempts": attempts_made,
                "first_attempt_verdict": first_attempt_verdict or "NOT_RUN",
                "fingerprint": fingerprint,
                "repo_sha": snapshot["repo_sha"],
                "expected_severity": gt.get("expected_severity"),
                "expected_evidence": expected_evidence,
                "matched_findings": 0,
                "matched_severities": "—",
                "contracts_found": "",
                "expected_contract": expected_contract or "—",
                "errors": "; ".join(reasons),
                "finding_evidence": [],
                "base_output": tails.get("base_output", ""),
                "head_output": tails.get("head_output", ""),
            }
            record["severity_match"] = severity_match_of(record)
            results.append(record)
            append_incremental_result(incremental_handle, record)
            click.echo(
                "  [NOT_RUN] "
                + (
                    "pipeline aborted before any comparison"
                    if pipeline_errors
                    else "the evidence path could not judge this case"
                )
                + f" ({duration_ms} ms) — excluded from recall, not counted as a miss"
            )
            _cleanup_worktrees(repo_resolved, final)
            continue

        if should_detect:
            total_should_detect += 1
        else:
            negative_cases += 1

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

        matched = matched_findings(findings, expected_contract, expected_evidence)

        # The verdict of the LAST attempt is the capability verdict: a
        # positive case is detected if ANY attempt found the defect (the
        # loop stops at the first detection), and a negative case is a
        # false positive if any attempt confirmed anything at all.
        verdict = verdict_for(should_detect, findings, matched, min_findings)
        if should_detect:
            if verdict in ("PASS", "PARTIAL"):
                detected += 1
            first_try_should_detect += 1
            if first_attempt_verdict in ("PASS", "PARTIAL"):
                first_try_detected += 1
        else:
            if verdict == "FALSE_POSITIVE":
                false_positives += 1
        if attempts_made > 1:
            retried_cases += 1

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
            "attempts": attempts_made,
            "first_attempt_verdict": first_attempt_verdict or verdict,
            "fingerprint": fingerprint,
            "repo_sha": snapshot["repo_sha"],
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
        append_incremental_result(incremental_handle, record)
        click.echo(
            f"  [{verdict}] matched {len(matched)} finding(s), "
            f"contracts found: {contracts_found} ({duration_ms} ms)"
        )

        _cleanup_worktrees(repo_resolved, final)

    incremental_handle.close()

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
    if reused_cases:
        reused_shas = sorted({
            str(rec.get("repo_sha") or "")
            for rec in reusable.values()
            if rec.get("repo_sha")
        })
        click.echo(f"Reused from earlier: {reused_cases} (measured under "
                   f"{', '.join(s[:12] for s in reused_shas) or 'unknown'})")
    click.echo(f"Not run:            {not_run}")
    click.echo(f"Should detect:      {total_should_detect}")
    click.echo(f"Detected:           {detected}")
    click.echo(f"False positives:    {false_positives}")
    click.echo(f"Negative cases:     {negative_cases}")
    click.echo(f"Precision:          {fmt_metric(metrics.precision)}")
    click.echo(f"Recall:             {fmt_metric(metrics.recall)}")
    click.echo(f"F1 Score:           {fmt_metric(metrics.f1)}")
    if attempts > 1:
        # The two numbers answer two different questions, and the run says
        # which is which: recall above is "CAN this defect be found (in up
        # to N attempts)", this is "was it found the FIRST time". A case
        # that needed a second attempt is a detection whose reliability is
        # not 100% (ledger #391) — the pool number stops depending on the
        # day's luck, and the luck is still reported.
        first_try_recall = (
            round(100.0 * first_try_detected / first_try_should_detect, 1)
            if first_try_should_detect else None
        )
        click.echo(
            f"First-try recall:   {fmt_metric(first_try_recall)} "
            f"({first_try_detected}/{first_try_should_detect} positive cases "
            f"found on the first attempt)"
        )
        click.echo(
            f"Cases measured more than once: {retried_cases} "
            f"(up to {attempts} attempts each)"
        )
        for rec in results:
            if int(rec.get("attempts") or 1) > 1:
                click.echo(
                    f"  ! unstable detection: {rec['case']} needed "
                    f"{rec['attempts']} attempts "
                    f"(first attempt said {rec.get('first_attempt_verdict')}, "
                    f"final: {rec.get('verdict')})"
                )
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
        # The level comes from the EVIDENCE the tool took (ADR-004: BLOCKER
        # needs execution + DB evidence), so a drift is a statement about
        # the evidence, not a wrong guess about the defect. Say which
        # evidence it was, or the reader can only see a bare mismatch.
        if m.get("evidence_kinds"):
            click.echo(
                f"      (strongest level {m.get('strongest') or '—'}; "
                f"evidence: {m['evidence_kinds']})"
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
                # The per-case records were ALSO written incrementally, one
                # line per case, as the run went: a run that was killed
                # leaves that file behind, so the hours it measured are
                # still readable. The pointer is here so a reader knows
                # where to look.
                "incremental_results": str(incremental_path),
                "incremental_cases": len(
                    resume_index(read_incremental_results(incremental_path))
                ),
                # A resumed run is a mix of two builds' measurements. The
                # sidecar says which sha each part was measured under, so
                # a reader never has to guess whether the number is
                # comparable with the one before it.
                "resumed_cases": reused_cases,
                "resumed_repo_shas": sorted({
                    str(r.get("repo_sha") or "")
                    for r in results
                    if r.get("repo_sha") and r.get("case") in reusable
                }),
                "cases": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    click.echo(f"Results JSON written to {sidecar}")

    if gate and not acceptance.passed:
        raise SystemExit(1)
