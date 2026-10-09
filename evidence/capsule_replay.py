"""Capsule replay execution — run a Bug Capsule's run.sh inside the sandbox (#183).

Declared execution surface contract: a capsule's contents (generated tests,
run.sh) AND the target repository's code are UNTRUSTED. On the host this
module runs exactly one thing — ``git clone`` — shelling out to the git
binary, never repo code. Every execution of capsule/repo code happens inside
the hardened sandbox (sandbox/runner.py: non-root, --network none, read-only
workspace, no docker.sock), with mode="docker" pinned so Docker being
unavailable is an honest error instead of a silent local fallback running
untrusted code on the host (same discipline as the Node/Python adapters in
experiments/adapters.py).

Honesty rules:
- run.sh's verdict is text on stdout; its exit code is 0 by template design
  (agent/nodes/create_capsule.py), so a verdict is counted ONLY when the
  sandbox completed (error empty) AND the exit code is 0 AND stdout parses
  against the closed template vocabulary. Unparsable output counts no
  verdict bucket: honest absence beats a fabricated one.
- A clone failure never reaches the sandbox, so it counts no run — the
  counter family measures executions, not requests.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from observability.metrics import incr
from sandbox.runner import REPLAY_PROFILE, run_sandboxed

#: run.sh's verdict markers (the create_capsule replay template prints
#: ">> <MARKER> <<" and always exits 0) mapped to their lowercase family
#: words. Closed vocabulary — a new verdict word must change the template,
#: this table and the parity gate's family together.
VERDICTS: dict[str, str] = {
    "REGRESSION CONFIRMED": "regression_confirmed",
    "UNEXPECTED FIX": "unexpected_fix",
    "AMBIGUOUS": "ambiguous",
    "COMPLIANT": "compliant",
}

#: How much of run.sh's output the replay report retains (the sandbox runner
#: already bounds its own retention; this second bound keeps the JSON report
#: bounded even if the runner's budget is raised).
_TAIL_CHARS = 256_000

#: Host-side git clone budget — the sandbox timeout governs run.sh, not the clone.
_CLONE_TIMEOUT = 300


def _parse_verdict(stdout: str) -> str | None:
    """The first template marker present in stdout, as its family word."""
    for marker, word in VERDICTS.items():
        if marker in stdout:
            return word
    return None


def _clone_repo(repo: Path, work_dir: Path) -> tuple[bool, str]:
    """Host-side ``git clone <repo> repo`` into the work dir.

    Returns (ok, error). Cloning is the ONLY host execution: it shells out
    to the git binary (never repo code) and the clone result is what the
    sandbox gets mounted — untrusted code execution belongs inside it.
    """
    try:
        proc = subprocess.run(
            ["git", "clone", str(repo), "repo"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            # #92: `text=True` alone decodes with the OS locale — cp936 on this
            # host. A failed decode does not raise here, it hands back
            # `CompletedProcess.stderr is None`, so the branch below would read
            # a CJK clone failure as `detail = ""` and report "git clone failed
            # (exit 128)" with no reason attached. errors="replace" keeps the
            # text even when the bytes are not UTF-8, which is strictly better
            # than a silent empty detail.
            encoding="utf-8",
            timeout=_CLONE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"git clone failed: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:2000]
        return False, f"git clone failed (exit {proc.returncode}): {detail}"
    return True, ""


def run_capsule_replay(
    work_dir: Path, repo: Path, timeout: int = 900,
) -> dict[str, Any]:
    """Clone ``repo`` host-side, then execute run.sh inside the sandbox.

    ``work_dir`` must already contain the extracted capsule (run.sh at its
    root); the clone lands at ``work_dir/repo``, which the replay profile
    sub-mounts read-write at /work/repo — run.sh checks out base/head refs
    there while the rest of the workspace stays read-only.

    Counters (#183): capsule_replay_runs_total counts every execution that
    reaches the sandbox (a failed one is still a run);
    capsule_replay_exec_errors_total counts the sandbox runner's non-empty
    error contract; capsule_replay_timeouts_total uses the same public
    substring "timed out after" both sandbox backends emit (spawn errors
    count as failures, never as timeouts); capsule_replay_verdict_<word>_total
    counts the parsed verdict on a completed run only.
    """
    cloned, clone_error = _clone_repo(repo, work_dir)
    if not cloned:
        # Never reached the sandbox — counts no run, honestly.
        return {
            "status": "clone_failed",
            "error": clone_error,
            "repo": str(repo),
            "replayed_at": datetime.now(UTC).isoformat(),
        }

    result = run_sandboxed(
        ["bash", "run.sh", "repo"],
        workspace=str(work_dir),
        timeout=timeout,
        mode="docker",
        profile=REPLAY_PROFILE,
    )
    # From here on the run reached the sandbox — count it, whatever happened.
    incr("capsule_replay_runs_total")

    error_text = result.error
    if error_text:
        incr("capsule_replay_exec_errors_total")
        if "timed out after" in error_text:
            incr("capsule_replay_timeouts_total")

    verdict: str | None = None
    if not error_text and result.exit_code == 0:
        verdict = _parse_verdict(result.stdout)
        if verdict is not None:
            incr("capsule_replay_verdict_" + verdict + "_total")

    payload: dict[str, Any] = {
        "status": "replayed",
        "exit_code": result.exit_code,
        "stdout_tail": result.stdout[-_TAIL_CHARS:],
        "stderr_tail": result.stderr[-_TAIL_CHARS:],
        "mode": result.mode,
        "error": error_text,
        "verdict": verdict,
        "repo": str(repo),
        "replayed_at": datetime.now(UTC).isoformat(),
    }
    if result.cache_note:
        payload["cache_note"] = result.cache_note
    return payload
