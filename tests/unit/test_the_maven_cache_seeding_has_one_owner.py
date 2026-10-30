"""#529 — the Maven cache seeding has ONE owner: scripts/seed_maven_cache.sh.

WHY THIS EXISTS. Three workflow steps inlined the same five commands (both
evaluating jobs in ci.yml, and nightly-eval.yml). The copies were kept in
step by hand, and both incidents in that step were one-copy-only fixes:
#499's "the comment sits ABOVE the command" note existed in ci.yml only, and
#521 had to move nightly's note above the backslash after the nightly run
died with rc 127 before its evaluation ever started. A fourth copy would
inherit the same trap, and nothing would notice — the workflow still parses
and the step only runs on the runner.

THE RULERS, each one sentence:

  R1 no workflow inlines a stage of the seeding, and every job that runs a
     cache-consuming command has exactly one seeding step that calls the
     script before that command;
  R2 the script owns each stage once and reads the SAME volume knob the
     sandbox reads (SPECPROOF_SANDBOX_M2_VOLUME), and the Windows and Linux
     seeders name the same default volume and image;
  R3 the detector behind R1 flags a synthetic inline copy, and the jobs that
     set the knob are exactly the jobs that run a cache-consuming command.

WHAT IS DELIBERATELY OUT OF SCOPE. Proving the script's docker sequence
works: that needs a Docker host and the demo backend, and it is exactly what
the CI steps run on every push. This file binds WHO owns the sequence.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
SCRIPT = ROOT / "scripts" / "seed_maven_cache.sh"
LOCAL_SCRIPT = ROOT / "scripts" / "seed_sandbox_cache.ps1"
SEED_CALL = "bash scripts/seed_maven_cache.sh"
KNOB = "SPECPROOF_SANDBOX_M2_VOLUME"

#: The stages of the seeding as they were inlined, in the order the script
#: runs them. A workflow may contain none of them.
INLINE_STAGES = (
    "docker volume create",
    "dependency:go-offline",
    "maven-wrapper-3.3.2.jar",
    "chown -R 1000:1000",
    "sh mvnw",
)

#: Commands that read the cache the seeding fills.
CACHE_CONSUMERS = (
    "pytest tests/integration",
    "cli.specproof.main eval",
    "build_golden_scenarios.py",
)


def _jobs() -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path in WORKFLOWS:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_id, job in (parsed.get("jobs") or {}).items():
            yield path.name, job_id, job


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return list(job.get("steps") or [])


def _run(step: dict[str, Any]) -> str:
    return str(step.get("run") or "")


def _inline_stages(text: str) -> list[str]:
    return sorted(stage for stage in INLINE_STAGES if stage in text)


def _is_seeding(step: dict[str, Any]) -> bool:
    return "Seed sandbox Maven cache" in str(step.get("name") or "")


def _ps1_assignment(text: str, name: str) -> str:
    match = re.search(rf'^\${name}\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, f"{LOCAL_SCRIPT.name} no longer assigns ${name}"
    return match.group(1)


def _sh_default_volume(text: str) -> str:
    match = re.search(r"VOLUME=\$\{" + KNOB + r":-([^}]+)\}", text)
    assert match, f"{SCRIPT.name} does not default the volume from ${KNOB}"
    return match.group(1)


def _sh_image(text: str) -> str:
    match = re.search(r"^IMAGE=(.+)$", text, re.MULTILINE)
    assert match, f"{SCRIPT.name} no longer assigns IMAGE"
    return match.group(1).strip().strip('"')


def test_no_workflow_inlines_the_seeding_and_every_maven_job_seeds_before_it_runs() -> None:
    problems: list[str] = []
    for name, job_id, job in _jobs():
        steps = _steps(job)
        for step in steps:
            hits = _inline_stages(_run(step))
            if hits:
                problems.append(
                    f"{name}:{job_id} inlines {hits} in step {step.get('name')!r}"
                )
        consumers = [
            index
            for index, step in enumerate(steps)
            if any(needle in _run(step) for needle in CACHE_CONSUMERS)
        ]
        seeds = [index for index, step in enumerate(steps) if _is_seeding(step)]
        if consumers:
            if len(seeds) != 1:
                problems.append(
                    f"{name}:{job_id} has {len(seeds)} Maven-cache seeding steps "
                    f"but runs a cache-consuming command at steps {consumers}"
                )
                continue
            run = _run(steps[seeds[0]]).strip()
            if run != SEED_CALL:
                problems.append(
                    f"{name}:{job_id} seeds via {run!r}, not {SEED_CALL!r}; "
                    "the sequence has one owner"
                )
            if seeds[0] > consumers[0]:
                problems.append(
                    f"{name}:{job_id} seeds at step {seeds[0]}, after the first "
                    f"cache-consuming command at step {consumers[0]}"
                )
        elif seeds:
            problems.append(
                f"{name}:{job_id} seeds the Maven cache but runs no "
                f"cache-consuming command {CACHE_CONSUMERS}"
            )
    assert not problems, "\n".join(problems)


def test_the_script_owns_each_stage_once_and_reads_the_sandbox_knob() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    commands = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    for stage in INLINE_STAGES:
        count = commands.count(stage)
        assert count == 1, (
            f"{SCRIPT.name} must run {stage!r} exactly once, found {count}"
        )
    assert commands.count(KNOB) == 1, (
        f"{SCRIPT.name} must read {KNOB} exactly once (the same knob "
        "sandbox/runner.py mounts), found "
        f"{commands.count(KNOB)}"
    )
    assert "set -eu" in text


def test_both_plane_seeders_name_the_same_volume_and_image() -> None:
    sh = SCRIPT.read_text(encoding="utf-8")
    ps1 = LOCAL_SCRIPT.read_text(encoding="utf-8")
    assert _ps1_assignment(ps1, "defaultVolume") == _sh_default_volume(sh), (
        "the local (Windows) and CI (Linux) seeders name different default "
        "volumes; one plane would seed a cache the other never mounts"
    )
    assert _ps1_assignment(ps1, "image") == _sh_image(sh), (
        "the two seeders pull different Maven images; the cache layouts they "
        "produce would diverge"
    )
    assert "$env:" + KNOB in ps1, (
        f"{LOCAL_SCRIPT.name} ignores {KNOB}; a local run that renames the "
        "volume would seed one cache and build from another"
    )


def test_the_inline_detector_flags_a_copy_and_the_knob_jobs_are_the_maven_jobs() -> None:
    synthetic = (
        "docker volume create specproof-maven-cache-1000\n"
        "docker run --rm --user 1000:1000 ... mvn -q -DskipTests dependency:go-offline\n"
        "curl -fsSL -o demo/spring-backend/.mvn/wrapper/maven-wrapper.jar "
        "https://example.invalid/maven-wrapper-3.3.2.jar\n"
        "docker run --rm -v vol:/m2 maven sh -c \"chown -R 1000:1000 /m2\"\n"
        "docker run --rm --user 1000:1000 ... sh mvnw -q -v\n"
    )
    assert _inline_stages(synthetic) == sorted(INLINE_STAGES), (
        "the detector no longer sees an inline copy of the sequence; R1 "
        "would pass on any workflow that reintroduced one"
    )
    assert _inline_stages(SEED_CALL) == []

    maven = {
        (name, job_id)
        for name, job_id, job in _jobs()
        if any(needle in _run(step) for step in _steps(job) for needle in CACHE_CONSUMERS)
    }
    knob = {(name, job_id) for name, job_id, job in _jobs() if KNOB in (job.get("env") or {})}
    assert maven, "no job runs a cache-consuming command; this scan is blind"
    assert maven == knob, (
        "jobs that mount the sandbox cache and jobs that name its volume must "
        f"be the same set; only in one: {sorted(maven ^ knob)}"
    )
