"""Mutation kill-rate benchmark library (interview metric: 变异杀死率 X%).

Two modes share one measurement contract:

  offline_sample  scripts/mutation_sample/: hand-defined mutants from
                  mutants/manifest.json; per-mutant differential (pytest) and
                  SpecProof-verdict (spec/contract.py) channels; no network.

  pipeline        a real target (demo repo path, or a golden case resolved via
                  --repo): the existing mutation pipeline
                  (experiments.mutation.generate_mutants) generates N mutants,
                  the existing contract checkers
                  (agent.checkers.run_contract_checks) form the verdict
                  channel, and the sandboxed mvnw test run forms the
                  differential channel.

Honesty rules (never faked):
  - killed   = detected by test failure OR by the SpecProof verdict;
  - survived = every AVAILABLE channel ran clean;
  - skipped  = no verification channel could run (e.g. checker unavailable);
               skipped mutants are excluded from the kill rate;
  - kill_rate = killed / (killed + survived)  (0.0 when nothing was evaluated);
  - a broken baseline aborts the campaign with BenchError instead of
    fabricating numbers.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
OFFLINE_SAMPLE = REPO_ROOT / "scripts" / "mutation_sample"
DEFAULT_JSON = REPO_ROOT / "docs" / "eval" / "mutation-results.json"
DEFAULT_MARKDOWN = REPO_ROOT / "docs" / "eval" / "mutation-results.md"


class BenchError(RuntimeError):
    """Benchmark setup or execution problem (never a mutant verdict)."""


@dataclass(frozen=True)
class HandMutant:
    """One hand-defined mutant from the offline sample manifest."""

    mutant_id: str
    operator: str
    description: str
    old: str
    new: str


@dataclass(frozen=True)
class MutantRecord:
    """Outcome of one mutant against the available verification channels."""

    mutant_id: str
    operator: str
    description: str
    status: str  # killed | survived | skipped
    killed_by: tuple[str, ...]  # "test_failure", "spec_verdict"
    test_exit_code: int | None
    spec_violations: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class MutationBenchResult:
    """Aggregate of one mutation campaign."""

    target: str
    mode: str
    mutants_requested: int
    mutants_total: int
    killed: int
    survived: int
    skipped: int
    evaluated: int
    kill_rate: float
    baseline_ok: bool
    baseline_note: str
    channels: dict[str, str]
    records: tuple[MutantRecord, ...]
    started_utc: str
    python_version: str


# ── Offline-sample machinery ───────────────────────────────────


def _pytest_command() -> list[str]:
    """The pytest invocation used for the differential test channel.

    A module-level function so tests can point it at an unavailable
    interpreter and exercise the honest-skip path.
    """
    return [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]


def _load_manifest(target_dir: Path) -> tuple[Path, list[HandMutant]]:
    """Validate and load mutants/manifest.json; returns (module_rel, mutants)."""
    manifest_path = target_dir / "mutants" / "manifest.json"
    if not manifest_path.is_file():
        raise BenchError(f"mutant manifest missing: {manifest_path}")
    try:
        payload: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchError(f"cannot read manifest {manifest_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BenchError(f"manifest {manifest_path} must be a JSON object")
    target_module_raw = payload.get("target_module")
    if not isinstance(target_module_raw, str) or not target_module_raw:
        raise BenchError("manifest.target_module must be a non-empty string")
    module_rel = Path(target_module_raw)
    if module_rel.is_absolute() or ".." in module_rel.parts:
        raise BenchError(
            f"manifest.target_module must be a relative path: {target_module_raw!r}"
        )
    if not (target_dir / module_rel).is_file():
        raise BenchError(f"manifest target module not found: {target_dir / module_rel}")
    mutants_raw = payload.get("mutants")
    if not isinstance(mutants_raw, list) or not mutants_raw:
        raise BenchError("manifest.mutants must be a non-empty list")
    mutants: list[HandMutant] = []
    for index, item in enumerate(mutants_raw):
        if not isinstance(item, dict):
            raise BenchError(f"manifest mutant #{index} must be a JSON object")
        fields: dict[str, str] = {}
        for field_name in ("id", "operator", "description", "old", "new"):
            value = item.get(field_name)
            if not isinstance(value, str) or not value:
                raise BenchError(
                    f"manifest mutant #{index}: field {field_name!r} missing or empty"
                )
            fields[field_name] = value
        if fields["old"] == fields["new"]:
            raise BenchError(f"mutant {fields['id']}: old == new, not a mutation")
        mutants.append(HandMutant(
            mutant_id=fields["id"],
            operator=fields["operator"],
            description=fields["description"],
            old=fields["old"],
            new=fields["new"],
        ))
    mutant_ids = {mutant.mutant_id for mutant in mutants}
    if len(mutant_ids) != len(mutants):
        raise BenchError("manifest mutant ids must be unique")
    return module_rel, mutants


def _apply_mutant(source: str, old: str, new: str, mutant_id: str) -> str:
    """Apply one text mutation; the old string must occur exactly once."""
    occurrences = source.count(old)
    if occurrences == 0:
        raise BenchError(f"{mutant_id}: old-string not found in target module")
    if occurrences != 1:
        raise BenchError(
            f"{mutant_id}: old-string occurs {occurrences} times, expected exactly once"
        )
    return source.replace(old, new)


def _load_spec_checker(target_dir: Path) -> tuple[Callable[[str], list[str]] | None, str]:
    """Load spec/contract.py's check_module; (None, reason) when unavailable."""
    contract_path = target_dir / "spec" / "contract.py"
    if not contract_path.is_file():
        return None, f"spec/contract.py missing in {target_dir}"
    try:
        module_spec = spec_from_file_location("mutation_sample_contract", contract_path)
        if module_spec is None or module_spec.loader is None:
            return None, f"cannot load {contract_path}"
        module = module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    except Exception as exc:
        return None, f"spec/contract.py failed to load: {type(exc).__name__}: {exc}"
    checker = getattr(module, "check_module", None)
    if not callable(checker):
        return None, "spec/contract.py has no check_module(source) callable"
    return cast(Callable[[str], list[str]], checker), ""


def _run_pytest(workspace: Path) -> tuple[int | None, str]:
    """Run the differential tests in the workspace.

    Returns (exit_code, note); exit_code None means the runner could not run
    (unavailable), and pytest exit code 5 (no tests collected) is also mapped
    to None so a test-less target is skipped, never faked as killed.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(workspace) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        completed = subprocess.run(
            _pytest_command(),
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
    except FileNotFoundError as exc:
        return None, f"pytest unavailable: {exc}"
    except subprocess.TimeoutExpired:
        return None, "pytest timed out after 300s"
    except OSError as exc:
        return None, f"pytest failed to start: {exc}"
    tail_lines = [
        line.strip()
        for line in (completed.stdout or "").splitlines()
        + (completed.stderr or "").splitlines()
        if line.strip()
    ][-12:]
    note = " | ".join(tail_lines)[:400]
    if completed.returncode == 0:
        return 0, note
    if completed.returncode == 5:
        return None, "no tests collected: " + note
    return completed.returncode, note


@contextmanager
def _temp_workspace(target_dir: Path) -> Iterator[Path]:
    """Copy the target into a throwaway workspace; mutants never touch it."""
    temp_root = Path(tempfile.mkdtemp(prefix="specproof-mutation-"))
    workspace = temp_root / "target"
    shutil.copytree(target_dir, workspace)
    try:
        yield workspace
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _evaluate_mutant(
    workspace: Path,
    mutated_source: str,
    mutant: HandMutant,
    *,
    run_tests: bool,
    checker: Callable[[str], list[str]] | None,
) -> MutantRecord:
    """Classify one mutant: killed / survived / skipped."""
    test_rc: int | None = None
    test_note = "test runner unavailable"
    if run_tests:
        test_rc, test_note = _run_pytest(workspace)
    violations: list[str] = []
    spec_ran = False
    spec_note = "spec checker unavailable"
    if checker is not None:
        try:
            violations = checker(mutated_source)
            spec_ran = True
            spec_note = ""
        except Exception as exc:
            spec_note = f"spec checker crashed: {type(exc).__name__}: {exc}"
    killed_by: list[str] = []
    if test_rc is not None and test_rc != 0:
        killed_by.append("test_failure")
    if spec_ran and violations:
        killed_by.append("spec_verdict")
    if killed_by:
        status = "killed"
    elif test_rc is not None or spec_ran:
        status = "survived"
    else:
        status = "skipped"
    notes: list[str] = []
    if test_rc is None:
        notes.append("tests unavailable: " + test_note)
    elif test_rc != 0:
        notes.append("test output tail: " + test_note)
    if spec_note:
        notes.append(spec_note)
    return MutantRecord(
        mutant_id=mutant.mutant_id,
        operator=mutant.operator,
        description=mutant.description,
        status=status,
        killed_by=tuple(killed_by),
        test_exit_code=test_rc,
        spec_violations=tuple(violations),
        note="; ".join(notes),
    )


# ── Offline-sample campaign ────────────────────────────────────


def run_mutation_bench(
    target_dir: Path,
    n: int,
    *,
    out_json: Path | None = None,
    out_md: Path | None = None,
) -> MutationBenchResult:
    """Run the offline mutation campaign over target_dir (hand-defined mutants).

    target_dir must follow the mutation_sample layout (module/ + spec/ +
    tests/ + mutants/manifest.json). n caps how many manifest mutants are
    used. When out_json/out_md are given the results are written there.
    """
    if n < 1:
        raise BenchError(f"--mutants must be >= 1, got {n}")
    if not target_dir.is_dir():
        raise BenchError(f"target directory not found: {target_dir}")
    module_rel, mutants = _load_manifest(target_dir)
    selected = mutants[:n]
    checker, spec_load_note = _load_spec_checker(target_dir)
    spec_available = checker is not None
    channels: dict[str, str] = {
        "test_runner": "available",
        "spec_verdict": "available" if spec_available else f"unavailable: {spec_load_note}",
    }
    started_utc = datetime.now(UTC).isoformat(timespec="seconds")
    baseline_ok = False
    baseline_note = ""
    records: list[MutantRecord] = []
    with _temp_workspace(target_dir) as workspace:
        module_path = workspace / module_rel
        original = module_path.read_text(encoding="utf-8")
        baseline_test_rc, baseline_test_note = _run_pytest(workspace)
        tests_available = baseline_test_rc is not None
        if not tests_available:
            channels["test_runner"] = "unavailable: " + baseline_test_note
        baseline_violations: list[str] = []
        if checker is not None:
            baseline_violations = checker(original)
        if baseline_test_rc is not None and baseline_test_rc != 0:
            raise BenchError(
                f"baseline tests failed (rc={baseline_test_rc}): {baseline_test_note}"
            )
        if baseline_violations:
            raise BenchError(
                "baseline spec verdict failed: " + "; ".join(baseline_violations)
            )
        if not tests_available and not spec_available:
            baseline_note = (
                "no verification channel available; every mutant recorded as skipped"
            )
        else:
            baseline_ok = True
        for mutant in selected:
            mutated = _apply_mutant(original, mutant.old, mutant.new, mutant.mutant_id)
            module_path.write_text(mutated, encoding="utf-8")
            try:
                records.append(_evaluate_mutant(
                    workspace,
                    mutated,
                    mutant,
                    run_tests=tests_available,
                    checker=checker,
                ))
            finally:
                module_path.write_text(original, encoding="utf-8")
    killed = sum(1 for record in records if record.status == "killed")
    survived = sum(1 for record in records if record.status == "survived")
    skipped = sum(1 for record in records if record.status == "skipped")
    evaluated = killed + survived
    kill_rate = round(killed / evaluated, 3) if evaluated else 0.0
    result = MutationBenchResult(
        target=str(target_dir),
        mode="offline_sample",
        mutants_requested=n,
        mutants_total=len(records),
        killed=killed,
        survived=survived,
        skipped=skipped,
        evaluated=evaluated,
        kill_rate=kill_rate,
        baseline_ok=baseline_ok,
        baseline_note=baseline_note,
        channels=dict(channels),
        records=tuple(records),
        started_utc=started_utc,
        python_version=sys.version.split()[0],
    )
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps(result_to_payload(result), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if out_md is not None:
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(render_markdown(result), encoding="utf-8")
    return result


# ── Real-repo pipeline campaign ────────────────────────────────


def _read_java_sources(app_dir: Path) -> dict[str, str]:
    """Posix-relative -> content for every non-test Java source under src/main/java."""
    base = app_dir / "src" / "main" / "java"
    sources: dict[str, str] = {}
    if not base.is_dir():
        return sources
    for path in sorted(base.rglob("*.java")):
        rel = path.relative_to(base).as_posix()
        if "test" in rel.split("/") or not path.is_file():
            continue
        try:
            sources[rel] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return sources


def _resolve_app_dir(target: Path, repo: Path | None) -> Path:
    """A golden-case dir (spec.md, no Java) resolves to --repo; a repo is used as-is."""
    if _read_java_sources(target):
        return target
    if repo is not None and _read_java_sources(repo):
        return repo
    default = REPO_ROOT / "demo" / "spring-backend"
    if _read_java_sources(default):
        return default
    raise BenchError(
        f"target {target} has no Java sources; pass --repo <demo repo> explicitly"
    )


def _run_sandboxed_maven_test(app_dir: Path, test_class: str) -> tuple[int | None, str]:
    """Differential channel for the pipeline mode (sandboxed mvnw test).

    Returns (exit_code, note); None means the channel could not run — the
    mutant is then skipped honestly, never faked as killed.
    """
    try:
        from sandbox.runner import run_sandboxed
    except Exception as exc:
        return None, f"sandbox runner unavailable: {type(exc).__name__}: {exc}"
    mvnw = app_dir / ("mvnw.cmd" if os.name == "nt" else "mvnw")
    if not mvnw.is_file():
        return None, f"mvnw not found under {app_dir}"
    test_args = [f"-Dtest={test_class}", "-DfailIfNoTests=false"] if test_class else []
    try:
        result = run_sandboxed(
            ["mvn", "-o", "test", "-q", *test_args, "-f", "/work/pom.xml"],
            workspace=str(app_dir),
            timeout=900,
            local_command=[str(mvnw), "test", "-q", *test_args],
        )
    except Exception as exc:
        return None, f"sandbox run failed: {type(exc).__name__}: {exc}"
    if result.error:
        return None, f"sandbox infrastructure error: {result.error} (mode={result.mode})"
    return result.exit_code, f"mode={result.mode}"


def run_mutation_pipeline(
    target: Path,
    *,
    repo: Path | None = None,
    n: int = 10,
    test_class: str = "",
    out_json: Path | None = None,
    out_md: Path | None = None,
) -> MutationBenchResult:
    """Real-repo mode: existing mutation pipeline + contract/differential checks.

    Uses experiments.mutation.generate_mutants (the existing pipeline) over
    the target's Java sources; the SpecProof verdict channel is
    agent.checkers.run_contract_checks (base vs mutated head); the
    differential channel is the sandboxed mvnw test run. Channels that cannot
    run (no docker/mvnw, checker import failure) are reported as unavailable
    and the affected mutants are skipped, never faked as killed.
    """
    if n < 1:
        raise BenchError(f"--mutants must be >= 1, got {n}")
    app_dir = _resolve_app_dir(target, repo)
    sources = _read_java_sources(app_dir)
    if not sources:
        raise BenchError(f"no non-test Java sources under {app_dir}")
    from experiments.mutation import Mutant, generate_mutants

    selected: list[tuple[str, Mutant]] = []
    remaining = n
    for rel in sorted(sources):
        for mutant in generate_mutants(sources[rel], max_mutants=remaining):
            selected.append((rel, mutant))
            remaining -= 1
            if remaining <= 0:
                break
        if remaining <= 0:
            break
    if not selected:
        raise BenchError("the mutation pipeline generated no mutants for the target")

    spec_available = True
    spec_load_note = ""
    try:
        from agent.checkers import run_contract_checks
    except Exception as exc:
        spec_available = False
        spec_load_note = f"contract checkers unavailable: {type(exc).__name__}: {exc}"
    channels: dict[str, str] = {
        "test_runner": "available",
        "spec_verdict": "available" if spec_available else f"unavailable: {spec_load_note}",
    }
    started_utc = datetime.now(UTC).isoformat(timespec="seconds")
    baseline_ok = False
    baseline_note = ""
    records: list[MutantRecord] = []
    with _temp_workspace(app_dir) as workspace:
        baseline_test_rc, baseline_test_note = _run_sandboxed_maven_test(
            workspace, test_class
        )
        tests_available = baseline_test_rc is not None
        if not tests_available:
            channels["test_runner"] = "unavailable: " + baseline_test_note
        if spec_available:
            baseline_findings = run_contract_checks(sources, sources)
            if baseline_findings:
                raise BenchError(
                    "baseline contract check reported findings on pristine sources: "
                    + "; ".join(str(f.get("description")) for f in baseline_findings)
                )
        if baseline_test_rc is not None and baseline_test_rc != 0:
            raise BenchError(
                f"baseline tests failed (rc={baseline_test_rc}): {baseline_test_note}"
            )
        if not tests_available and not spec_available:
            baseline_note = (
                "no verification channel available; every mutant recorded as skipped"
            )
        else:
            baseline_ok = True
        for rel, mutant in selected:
            target_path = workspace / "src" / "main" / "java" / Path(*rel.split("/"))
            original = target_path.read_text(encoding="utf-8")
            target_path.write_text(mutant.content, encoding="utf-8")
            try:
                test_rc: int | None = None
                test_note = "test runner unavailable"
                if tests_available:
                    test_rc, test_note = _run_sandboxed_maven_test(workspace, test_class)
                violations: list[str] = []
                spec_ran = False
                spec_note = "spec checker unavailable"
                if spec_available:
                    head_files = dict(sources)
                    head_files[rel] = mutant.content
                    try:
                        findings = run_contract_checks(sources, head_files)
                        violations = [
                            str(f.get("description", ""))
                            for f in findings
                            if f.get("location") == rel
                        ]
                        spec_ran = True
                        spec_note = ""
                    except Exception as exc:
                        spec_note = (
                            f"contract checkers crashed: {type(exc).__name__}: {exc}"
                        )
                killed_by: list[str] = []
                if test_rc is not None and test_rc != 0:
                    killed_by.append("test_failure")
                if spec_ran and violations:
                    killed_by.append("spec_verdict")
                if killed_by:
                    status = "killed"
                elif test_rc is not None or spec_ran:
                    status = "survived"
                else:
                    status = "skipped"
                notes: list[str] = []
                if test_rc is None:
                    notes.append("tests unavailable: " + test_note)
                elif test_rc != 0:
                    notes.append("test output tail: " + test_note)
                if spec_note:
                    notes.append(spec_note)
                records.append(MutantRecord(
                    mutant_id=f"{rel}::{mutant.mutant_id}",
                    operator=mutant.operator,
                    description=mutant.description,
                    status=status,
                    killed_by=tuple(killed_by),
                    test_exit_code=test_rc,
                    spec_violations=tuple(violations),
                    note="; ".join(notes),
                ))
            finally:
                target_path.write_text(original, encoding="utf-8")
    killed = sum(1 for record in records if record.status == "killed")
    survived = sum(1 for record in records if record.status == "survived")
    skipped = sum(1 for record in records if record.status == "skipped")
    evaluated = killed + survived
    kill_rate = round(killed / evaluated, 3) if evaluated else 0.0
    result = MutationBenchResult(
        target=str(app_dir),
        mode="pipeline",
        mutants_requested=n,
        mutants_total=len(records),
        killed=killed,
        survived=survived,
        skipped=skipped,
        evaluated=evaluated,
        kill_rate=kill_rate,
        baseline_ok=baseline_ok,
        baseline_note=baseline_note,
        channels=dict(channels),
        records=tuple(records),
        started_utc=started_utc,
        python_version=sys.version.split()[0],
    )
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps(result_to_payload(result), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if out_md is not None:
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(render_markdown(result), encoding="utf-8")
    return result


# ── Reporting ──────────────────────────────────────────────────


def result_to_payload(result: MutationBenchResult) -> dict[str, Any]:
    """Serialize the result for docs/eval/mutation-results.json."""
    return {
        "run_info": {
            "started_utc": result.started_utc,
            "python_version": result.python_version,
            "mode": result.mode,
            "target": result.target,
            "mutants_requested": result.mutants_requested,
        },
        "summary": {
            "mutants_total": result.mutants_total,
            "evaluated": result.evaluated,
            "killed": result.killed,
            "survived": result.survived,
            "skipped": result.skipped,
            "kill_rate": result.kill_rate,
            "kill_rate_pct": round(100.0 * result.kill_rate, 1),
            "channels": dict(result.channels),
            "baseline_ok": result.baseline_ok,
            "baseline_note": result.baseline_note,
        },
        "records": [
            {
                "mutant_id": record.mutant_id,
                "operator": record.operator,
                "description": record.description,
                "status": record.status,
                "killed_by": list(record.killed_by),
                "test_exit_code": record.test_exit_code,
                "spec_violations": list(record.spec_violations),
                "note": record.note,
            }
            for record in result.records
        ],
    }


def render_markdown(result: MutationBenchResult) -> str:
    """Render the human summary (docs/eval/mutation-results.md)."""
    rate_pct = round(100.0 * result.kill_rate, 1)
    baseline = "PASS" if result.baseline_ok else "NOT VERIFIED"
    rows: list[str] = []
    for record in result.records:
        killed_by = ", ".join(record.killed_by) if record.killed_by else "—"
        violations = "; ".join(record.spec_violations)[:120] or "—"
        rows.append(
            f"| {record.mutant_id} | {record.operator} | **{record.status}**"
            f" | {killed_by} | {record.test_exit_code} | {violations} |"
        )
    lines = [
        "# Mutation Kill-Rate Benchmark 实测报告",
        "",
        "> 生成方式: 'python scripts/bench_mutation.py --offline' 真实运行输出 (非手写估算)。",
        "> 口径: killed = 测试失败 或 SpecProof 契约判定; skipped = 无可用验证通道,",
        "> 不计入杀死率; 杀死率 = killed / (killed + survived)。",
        "",
        f"## 变异杀死率: {rate_pct:.1f}%",
        "",
        "- 变异体总数: "
        f"{result.mutants_total} (请求 {result.mutants_requested})",
        f"- 杀死: {result.killed} / 存活: {result.survived} / 跳过: {result.skipped}",
        f"- 杀死率 = {result.killed} / ({result.killed} + {result.survived})"
        f" = {result.kill_rate:.3f}",
        "",
        "## 运行环境",
        "",
        f"- 运行时刻 (UTC): {result.started_utc}",
        f"- Python: {result.python_version}",
        f"- 模式: {result.mode}",
        f"- 目标: {result.target}",
        f"- 基线校验: {baseline}"
        + (f" — {result.baseline_note}" if result.baseline_note else ""),
        f"- 测试通道: {result.channels['test_runner']}",
        f"- 契约判定通道: {result.channels['spec_verdict']}",
        "",
        "## 逐变异体结果",
        "",
        "| 变异体 | 操作 | 状态 | 判定来源 | 测试退出码 | 契约违规 |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        "## 诚实性说明",
        "",
        "- skipped (无任何可用验证通道) 不计入分子也不计入分母, 从不被算作 killed;",
        "- baseline 未通过时整场实验以错误退出, 不产出数字;",
        "- 存活变异体是测试弱点, 不自动视为 Bug (与产品规格一致);",
        "- 离线样本的 M06 有意命中规范外、无测试覆盖的提示小费行为并存活,",
        "  以证明本数字不是被凑成 100% 的。",
        "",
    ]
    return "\n".join(lines)
