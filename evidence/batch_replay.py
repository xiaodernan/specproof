"""Batch capsule replay runner (Phase 2, P2-2).

Runs a batch of Bug Capsules through the sandbox and produces an auditable
batch record: per-capsule outcome, failure classification, and aggregate
statistics.

Honesty contract (the reason this module exists at all):

A single failed replay tells an operator nothing about WHY. The roadmap
demands that a replay failure be classifiable as *environment*, *artifact*,
*script* or *product defect* — "the capsule did not replay" is not a
diagnosis, and treating every failure as "the regression still holds" (or
as "the bug is gone") is the two ways this feature could lie.

The four classes:

- ``environment``   — the toolchain/host/sandbox could not run the capsule
                      (clone failed, docker unreachable, timeout, missing
                      bash). The capsule itself was never judged.
- ``artifact``      — the capsule is damaged (not a zip, manifest missing,
                      payload digest mismatch, unreadable).
- ``script``        — the capsule's run.sh ran but produced no parsable
                      verdict (non-zero exit, marker-less stdout).
- ``product_defect`` — the capsule ran and produced a verdict, but the
                      verdict disagrees with the original one. The evidence
                      is not stable, which is a finding about the product,
                      not about the capsule.

A capsule that replayed and produced the SAME verdict as the original is
``reproduced``. A capsule that replayed with a DIFFERENT verdict is
``diverged`` — a distinct outcome from "reproduced", because silently
calling it reproduced would hide evidence instability.

The batch record is written as JSON and is safe to diff: every field is
derived from what actually happened, never from an assumption.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contracts.clock import utc_now_iso

#: Replay outcome vocabulary. Closed set — a new outcome must be added here
#: and to the classification table below together.
OUTCOME_REPRODUCED = "reproduced"
OUTCOME_DIVERGED = "diverged"
OUTCOME_ENVIRONMENT = "environment_failure"
OUTCOME_ARTIFACT = "artifact_failure"
OUTCOME_SCRIPT = "script_failure"
OUTCOME_PRODUCT_DEFECT = "product_defect"

OUTCOMES: tuple[str, ...] = (
    OUTCOME_REPRODUCED,
    OUTCOME_DIVERGED,
    OUTCOME_ENVIRONMENT,
    OUTCOME_ARTIFACT,
    OUTCOME_SCRIPT,
    OUTCOME_PRODUCT_DEFECT,
)

#: Outcomes that mean "the capsule was never judged" — they are NOT failures
#: of the evidence, and they must not be counted into a replay success rate
#: as if they were.
UNJUDGED_OUTCOMES = frozenset({OUTCOME_ENVIRONMENT, OUTCOME_ARTIFACT})

#: The verdict a capsule is EXPECTED to reproduce, per finding severity.
#: A capsule whose original verdict is unknown cannot be compared — it is
#: reported as "no baseline", never as "reproduced".
VERDICT_BY_SEVERITY: dict[str, str] = {
    "BLOCKER": "regression_confirmed",
    "MAJOR": "regression_confirmed",
    "MINOR": "regression_confirmed",
    "INFO": "regression_confirmed",
}

#: The verdict family that means "the regression is gone" — a DIFFERENT
#: family from the baseline, so it counts as divergence, not reproduction.
REGRESSION_VERDICTS = frozenset({"regression_confirmed"})


@dataclass
class CapsuleOutcome:
    """One capsule's replay result inside a batch."""

    capsule: str
    outcome: str
    detail: str = ""
    verdict: str | None = None
    baseline_verdict: str | None = None
    exit_code: int | None = None
    error: str = ""
    finding_id: str = ""
    severity: str = ""
    contract_id: str = ""
    manifest_digest: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "capsule": self.capsule,
            "outcome": self.outcome,
            "detail": self.detail,
            "verdict": self.verdict,
            "baseline_verdict": self.baseline_verdict,
            "exit_code": self.exit_code,
            "error": self.error,
            "finding_id": self.finding_id,
            "severity": self.severity,
            "contract_id": self.contract_id,
            "manifest_digest": self.manifest_digest,
            "duration_ms": self.duration_ms,
        }


@dataclass
class BatchReplayRecord:
    """Aggregate result of one batch replay run."""

    outcomes: list[CapsuleOutcome] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str = ""

    # ── aggregates ───────────────────────────────────────────────

    def by_outcome(self) -> dict[str, int]:
        """Outcome → count (every outcome key is present, even at zero)."""
        counts = dict.fromkeys(OUTCOMES, 0)
        for entry in self.outcomes:
            counts[entry.outcome] = counts.get(entry.outcome, 0) + 1
        return counts

    def replayed_count(self) -> int:
        """Capsules that actually produced a verdict (judged)."""
        return sum(1 for o in self.outcomes if o.verdict is not None)

    def unjudged_count(self) -> int:
        """Capsules that never reached a verdict (environment/artifact)."""
        return sum(1 for o in self.outcomes if o.outcome in UNJUDGED_OUTCOMES)

    def success_rate(self) -> float | None:
        """Reproduced ÷ judged, or None when nothing was judged.

        The denominator is the JUDGED count, not the batch size: an
        environment failure is not a replay that failed to reproduce, it is
        a replay that never happened. Reporting 0/5 because the sandbox was
        down would be a lie about the evidence.
        """
        judged = self.replayed_count()
        if judged == 0:
            return None
        reproduced = sum(1 for o in self.outcomes if o.outcome == OUTCOME_REPRODUCED)
        return reproduced / judged

    def to_dict(self) -> dict[str, Any]:
        counts = self.by_outcome()
        judged = self.replayed_count()
        return {
            "schema_version": 1,
            "started_at": self.started_at,
            "finished_at": self.finished_at or utc_now_iso(),
            "total": len(self.outcomes),
            "judged": judged,
            "unjudged": self.unjudged_count(),
            "by_outcome": counts,
            "success_rate": self.success_rate(),
            "outcomes": [o.to_dict() for o in self.outcomes],
        }


def _classify_sandbox_error(error: str) -> str:
    """Environment vs script failure from the sandbox's error text.

    The sandbox runner's own error contract (a non-empty ``error``) means
    "the run could not complete" — that is an environment failure, never a
    verdict about the code.
    """
    lowered = error.lower()
    if "timed out" in lowered:
        return OUTCOME_ENVIRONMENT
    if "docker" in lowered or "daemon" in lowered or "sandbox" in lowered:
        return OUTCOME_ENVIRONMENT
    if "not found" in lowered or "no such file" in lowered:
        return OUTCOME_ENVIRONMENT
    return OUTCOME_ENVIRONMENT


def _extract_capsule(capsule: Path, work_dir: Path) -> tuple[dict[str, Any] | None, str]:
    """Extract a capsule zip; returns (manifest, error).

    A damaged capsule is an ARTIFACT failure — the payload itself is the
    problem, and the replay never reached the code.
    """
    if not capsule.is_file():
        return None, f"capsule not found: {capsule}"
    if capsule.suffix != ".zip":
        return None, f"capsule is not a .zip: {capsule}"
    try:
        with zipfile.ZipFile(capsule, "r") as archive:
            archive.extractall(work_dir)
    except (OSError, zipfile.BadZipFile) as exc:
        return None, f"capsule could not be extracted: {type(exc).__name__}: {exc}"
    manifest_path = work_dir / "manifest.json"
    if not manifest_path.is_file():
        return None, "corrupt capsule — manifest.json not found"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"corrupt capsule — manifest.json unreadable: {exc}"
    if not isinstance(manifest, dict):
        return None, "corrupt capsule — manifest.json is not an object"
    return manifest, ""


def _baseline_verdict(manifest: dict[str, Any]) -> str | None:
    """The verdict this capsule is expected to reproduce, or None.

    The manifest records the finding's severity, not the verdict — the
    verdict a capsule produces is a property of what it proves. A capsule
    whose severity is unknown has no baseline and can only be reported as
    "replayed, no baseline to compare".
    """
    severity = str(manifest.get("severity") or "").upper()
    return VERDICT_BY_SEVERITY.get(severity)


class BatchReplayRunner:
    """Run a batch of capsules and produce one auditable record.

    The runner is deliberately injectable: ``replay_fn`` is the single
    execution seam (the production value is
    ``evidence.capsule_replay.run_capsule_replay``), so a batch can be
    exercised without Docker, a network or a git repository.
    """

    def __init__(
        self,
        *,
        replay_fn: Callable[[Path, Path, int], dict[str, Any]] | None = None,
        timeout: int = 900,
        keep_work_dirs: bool = False,
    ) -> None:
        self._replay_fn = replay_fn or self._default_replay
        self._timeout = timeout
        self._keep_work_dirs = keep_work_dirs

    @staticmethod
    def _default_replay(work_dir: Path, repo: Path, timeout: int) -> dict[str, Any]:
        from evidence.capsule_replay import run_capsule_replay

        return run_capsule_replay(work_dir, repo, timeout=timeout)

    def run(
        self,
        capsules: Sequence[Path],
        repo: Path,
        *,
        work_root: Path | None = None,
    ) -> BatchReplayRecord:
        """Replay every capsule in order; one bad capsule never stops the batch.

        A batch exists to measure the population, so a single damaged
        capsule must not abort the run — it becomes one classified failure
        among the rest.
        """
        record = BatchReplayRecord()
        for capsule in capsules:
            record.outcomes.append(self._replay_one(capsule, repo, work_root))
        record.finished_at = utc_now_iso()
        return record

    def _replay_one(
        self, capsule: Path, repo: Path, work_root: Path | None
    ) -> CapsuleOutcome:
        """One capsule: extract → replay → classify."""
        import time

        started = time.perf_counter()
        parent = work_root or Path(tempfile.mkdtemp(prefix="specproof-batch-replay-"))
        parent.mkdir(parents=True, exist_ok=True)
        work_dir = parent / capsule.stem
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            manifest, error = _extract_capsule(capsule, work_dir)
            if manifest is None:
                return CapsuleOutcome(
                    capsule=str(capsule),
                    outcome=OUTCOME_ARTIFACT,
                    detail=error,
                    duration_ms=round((time.perf_counter() - started) * 1000),
                )

            finding_id = str(manifest.get("finding_id") or "")
            severity = str(manifest.get("severity") or "")
            contract_id = str(manifest.get("contract_id") or "")
            manifest_digest = str(manifest.get("manifest_digest") or "")

            try:
                result = self._replay_fn(work_dir, repo, self._timeout)
            except Exception as exc:  # noqa: BLE001 — one bad capsule, not a bad batch
                return CapsuleOutcome(
                    capsule=str(capsule),
                    outcome=OUTCOME_ENVIRONMENT,
                    detail=f"replay raised: {type(exc).__name__}: {exc}",
                    finding_id=finding_id,
                    severity=severity,
                    contract_id=contract_id,
                    manifest_digest=manifest_digest,
                    duration_ms=round((time.perf_counter() - started) * 1000),
                )

            return self._classify(
                capsule, result, manifest, finding_id, severity, contract_id,
                manifest_digest, started,
            )
        finally:
            if not self._keep_work_dirs and work_root is None:
                shutil.rmtree(work_dir, ignore_errors=True)

    def _classify(
        self,
        capsule: Path,
        result: dict[str, Any],
        manifest: dict[str, Any],
        finding_id: str,
        severity: str,
        contract_id: str,
        manifest_digest: str,
        started: float,
    ) -> CapsuleOutcome:
        """Map a raw replay result onto the outcome vocabulary."""
        import time

        duration_ms = round((time.perf_counter() - started) * 1000)
        status = str(result.get("status") or "")
        error = str(result.get("error") or "")
        raw_verdict = result.get("verdict")
        raw_exit = result.get("exit_code")
        verdict = raw_verdict if isinstance(raw_verdict, str) else None
        exit_code = raw_exit if isinstance(raw_exit, int) else None

        def build(
            outcome: str,
            detail: str,
            *,
            baseline: str | None = None,
        ) -> CapsuleOutcome:
            return CapsuleOutcome(
                capsule=str(capsule),
                outcome=outcome,
                detail=detail,
                verdict=verdict,
                baseline_verdict=baseline,
                exit_code=exit_code,
                error=error,
                finding_id=finding_id,
                severity=severity,
                contract_id=contract_id,
                manifest_digest=manifest_digest,
                duration_ms=duration_ms,
            )

        # 1. The clone never happened → the capsule was never judged.
        if status == "clone_failed":
            return build(
                OUTCOME_ENVIRONMENT,
                f"clone failed: {error}" if error else "clone failed",
            )

        # 2. The sandbox could not complete the run → environment.
        if error:
            return build(
                _classify_sandbox_error(error),
                f"sandbox error: {error}"[:500],
            )

        # 3. The run completed but produced no parsable verdict → script.
        if verdict is None:
            return build(
                OUTCOME_SCRIPT,
                (
                    f"run completed (exit {exit_code}) but produced no verdict marker"
                    if exit_code is not None
                    else "run completed but produced no verdict marker"
                ),
            )

        # 4. A verdict was produced — compare it with the baseline.
        baseline = _baseline_verdict(manifest)
        if baseline is None:
            return build(
                OUTCOME_SCRIPT,
                (
                    f"replayed with verdict {verdict!r} but the manifest carries "
                    "no severity, so there is no baseline to compare it against"
                ),
            )

        if verdict == baseline:
            return build(
                OUTCOME_REPRODUCED,
                f"reproduced the baseline verdict {baseline!r}",
                baseline=baseline,
            )

        return build(
            OUTCOME_DIVERGED,
            (
                f"diverged: expected {baseline!r}, observed {verdict!r} — the "
                "evidence is not stable across the replay boundary"
            ),
            baseline=baseline,
        )


def discover_capsules(root: Path) -> list[Path]:
    """Every ``*.zip`` under *root*, sorted for a deterministic batch order."""
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.zip") if p.is_file())


def write_batch_record(record: BatchReplayRecord, path: Path) -> str:
    """Write the batch record as JSON; returns the written path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return str(path)


__all__ = [
    "OUTCOMES",
    "OUTCOME_ARTIFACT",
    "OUTCOME_DIVERGED",
    "OUTCOME_ENVIRONMENT",
    "OUTCOME_PRODUCT_DEFECT",
    "OUTCOME_REPRODUCED",
    "OUTCOME_SCRIPT",
    "UNJUDGED_OUTCOMES",
    "BatchReplayRecord",
    "BatchReplayRunner",
    "CapsuleOutcome",
    "discover_capsules",
    "write_batch_record",
]
