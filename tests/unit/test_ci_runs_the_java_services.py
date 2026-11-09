"""Gate: CI must build and TEST every Java service this repository ships.

WHAT WAS MEASURED (before this gate existed).  On 2026-11-09
``.github/workflows/ci.yml`` had **7** jobs — ``lint-type``, ``web``,
``openapi-schema-diff``, ``security``, ``tests-no-infra``, ``tests-with-infra``
and ``eval-golden-cases`` — and **not one of them ran Maven**.  The
repository owns two Java services:

===========================  ==========  ==========  ===============
module                       main java   test java   java.version
===========================  ==========  ==========  ===============
``services/control-plane``   22          3 (9 tests)  21
``services/gateway``          1          0           21
===========================  ==========  ==========  ===============

Both are Spring Boot **3.4.3** projects targeting Java **21**, and neither was
compiled or tested by any automated path.  A Java build could break on master
with every CI job green — the same shape #507 found on the frontend, and the
same shape the ledger's own #1544 honest-boundary line recorded ("CI has no
Java leg").

The third Maven module in the repository, ``demo/spring-backend``, is NOT a
shipped service: it is the *subject under test* of the golden-case
differential, and it is built by the sandbox with the seeded offline Maven
cache (``scripts/seed_maven_cache.sh``).  That is a different coverage
story, and this gate does not claim it.

THE RULES, each one sentence:

  R1  the census is not collapsed — a census that finds nothing reads as
      "no problem", and this repository has been bitten by that shape before;
  R2  every Maven module under ``services/`` is built by some job that runs
      Maven — a new service that nobody compiles is a service that rots
      silently;
  R3  the Maven step really runs the tests — ``package -DskipTests`` compiles
      and asserts nothing, which is the whole point of a test leg;
  R4  the job pins a JDK at least as new as the poms declare — the version is
      read from the poms, never typed here;
  R5  the job checks the code out and pins the JDK BEFORE it builds — a
      ``setup-java`` after the build means the build used whatever JDK the
      runner happened to have;
  R6  a module with ZERO Java test classes is declared here, with a reason —
      an exemption without a reason is a hole with a name on it — and the
      declaration must not be stale;
  R7  the Maven step may not pipe its output into something that swallows the
      exit code — a pipeline reports its LAST command's status (#537);
  R8  the job is not a name: the working directory it builds must exist and
      hold the module's pom.

WHAT THIS GATE DOES NOT SAY.  It says nothing about whether the Java tests
pass — it says that some job runs them.  The build itself is measured by
running it, not by reading a YAML file.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_REL = ".github/workflows/ci.yml"

#: Modules whose Java test classes are ZERO must be declared here, with a
#: reason.  The module is still BUILT by CI — that is what makes the
#: declaration an exemption from "runs tests", not from "is watched".
NO_JAVA_TESTS: dict[str, str] = {
    "services/gateway": (
        "the edge has no Java test class yet: its route table is held by the "
        "Python gate tests/unit/test_gateway_route_table_covers_every_plane_"
        "route.py (#1544).  The module IS compiled by CI — this declaration "
        "says \"nothing to assert yet\", not \"not watched\"."
    ),
}

#: A Maven invocation: the command word and everything after it.
_MVN = re.compile(r"(?:^|[\s;&|(])(?:\./)?mvnw?\b")
#: The Maven goals that actually execute tests.
_TEST_GOALS = {"test", "verify", "integration-test"}
#: Flags that make a Maven run skip the tests.
_SKIP_FLAGS = ("-DskipTests", "-Dmaven.test.skip", "-Dsurefire.skip", "-DskipITs")


# ---------------------------------------------------------------------------
# the repository's Java modules, read from the INDEX
# ---------------------------------------------------------------------------


def _tracked(pathspec: str) -> list[str]:
    raw = subprocess.run(["git", "ls-files", "-z", "--", pathspec], cwd=ROOT,
                         capture_output=True).stdout
    return [p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p]


def _modules() -> list[str]:
    """Every Maven module under ``services/``, from the index.

    The index, not the working tree: a developer's untracked scratch module
    must not change what the gate demands of CI.
    """
    out = [rel[: -len("/pom.xml")] for rel in _tracked("services")
           if rel.endswith("/pom.xml")]
    return sorted(out)


def _java_version(module: str) -> int | None:
    """The Java version the module's pom declares, or None."""
    text = (ROOT / module / "pom.xml").read_text(encoding="utf-8")
    match = re.search(r"<java\.version>([^<]+)</java\.version>", text)
    return int(match.group(1)) if match else None


def _test_class_count(module: str) -> int:
    root = ROOT / module / "src" / "test" / "java"
    if not root.is_dir():
        return 0
    return len(list(root.rglob("*.java")))


# ---------------------------------------------------------------------------
# the workflow, read from disk
# ---------------------------------------------------------------------------


def _workflow() -> dict:
    return yaml.safe_load((ROOT / WORKFLOW_REL).read_text(encoding="utf-8"))


def _strip_comments(script: str) -> str:
    """Remove the shell's comments — a comment that MENTIONS a module does
    not build it."""
    out: list[str] = []
    for line in script.splitlines():
        quote = ""
        cut = len(line)
        for index, char in enumerate(line):
            if quote:
                if char == quote:
                    quote = ""
                continue
            if char in "'\"":
                quote = char
                continue
            if char == "#" and (index == 0 or line[index - 1].isspace()):
                cut = index
                break
        out.append(line[:cut])
    return "\n".join(out)


def _maven_lines(script: str) -> list[tuple[str, bool]]:
    """``(command text, is_piped)`` for every Maven invocation in a block."""
    out: list[tuple[str, bool]] = []
    for raw in _strip_comments(script).splitlines():
        line = raw.strip()
        if not line:
            continue
        if not _MVN.search(line):
            continue
        head, sep, _tail = line.partition("|")
        out.append((head.strip(), bool(sep)))
    return out


def _maven_args(command: str) -> str:
    match = re.search(r"(?:^|[\s;&|(])(?:\./)?mvnw?\s+(.*)$", command)
    return match.group(1).strip() if match else ""


def _maven_jobs() -> dict[str, list[dict]]:
    """The jobs that run Maven, with their steps."""
    out: dict[str, list[dict]] = {}
    for job_id, job in (_workflow().get("jobs") or {}).items():
        steps = list(job.get("steps") or [])
        if any(_maven_lines(str(step.get("run", ""))) for step in steps):
            out[job_id] = steps
    return out


def _covers(step: dict, module: str) -> bool:
    """Whether this step builds THAT module."""
    working = str(step.get("working-directory", "")).strip()
    working = working.replace("\\", "/").strip("/")
    if working.endswith("/pom.xml"):
        working = working[: -len("/pom.xml")]
    if working == module:
        return True
    script = _strip_comments(str(step.get("run", "")))
    return module in script


# ---------------------------------------------------------------------------
# the rules
# ---------------------------------------------------------------------------


def test_the_module_census_is_not_collapsed() -> None:
    """R1 — a census that finds nothing is greener than a bug."""
    modules = _modules()
    assert len(modules) >= 2, (
        f"the Java module census collapsed: {modules} — services/ carries "
        "fewer Maven modules than it should, so the legs below would pass "
        "without looking at anything"
    )


def test_the_workflow_census_is_not_collapsed() -> None:
    """R1 (the other side) — the workflow was parsed, not truncated."""
    jobs = _workflow().get("jobs") or {}
    assert len(jobs) >= 5, (
        f"the workflow carries {len(jobs)} job(s): {sorted(jobs)} — the "
        "workflow was not read"
    )


def test_every_java_service_is_built_by_a_job_that_runs_maven() -> None:
    """R2 — a service nobody compiles is a service that rots silently."""
    modules = _modules()
    jobs = _maven_jobs()
    assert jobs, (
        "no job in ci.yml runs Maven.  The repository ships "
        f"{len(modules)} Java service(s) ({', '.join(modules)}) and neither "
        "is compiled or tested by any automated path — a broken Java build "
        "can sit on master with every job green"
    )
    uncovered = [
        module for module in modules
        if not any(_covers(step, module) for steps in jobs.values() for step in steps)
    ]
    assert not uncovered, (
        "these Java services are not built by any job that runs Maven:\n  "
        + "\n  ".join(uncovered)
        + "\nEvery module under services/ must be built by CI — a new service "
          "that nobody compiles rots without anyone noticing"
    )


def test_the_java_leg_really_runs_the_tests() -> None:
    """R3 — a build that compiles and asserts nothing is not a test leg."""
    for job_id, steps in _maven_jobs().items():
        for index, step in enumerate(steps):
            for command, _piped in _maven_lines(str(step.get("run", ""))):
                args = _maven_args(command)
                goals = [tok for tok in args.split()
                         if not tok.startswith("-")]
                assert any(goal in _TEST_GOALS for goal in goals), (
                    f"{job_id} step {index} runs Maven without a test phase: "
                    f"{command!r} — 'package' without the tests compiles the "
                    "code and asserts nothing about it"
                )
                skipped = next((flag for flag in _SKIP_FLAGS
                                for tok in args.split() if tok.startswith(flag)),
                               None)
                assert skipped is None, (
                    f"{job_id} step {index} skips the tests ({skipped}): "
                    f"{command!r}"
                )


def test_the_java_leg_pins_a_jdk_as_new_as_the_poms_declare() -> None:
    """R4 — the version comes from the poms, never from here."""
    for job_id, steps in _maven_jobs().items():
        required = 0
        for module in _modules():
            if not any(_covers(step, module) for step in steps):
                continue
            version = _java_version(module)
            if version:
                required = max(required, version)
        assert required, (
            f"{job_id} builds no module that declares a java.version — the "
            "requirement cannot be derived"
        )
        setups = [step for step in steps
                  if str(step.get("uses", "")).startswith("actions/setup-java")]
        assert setups, (
            f"{job_id} pins no JDK.  Without setup-java the build runs on "
            "whatever JDK the runner happens to have, and the poms declare "
            f"Java {required}"
        )
        pinned = setups[0].get("with", {}).get("java-version")
        assert pinned is not None, (
            f"{job_id}'s setup-java step names no java-version"
        )
        assert int(str(pinned)) >= required, (
            f"{job_id} pins JDK {pinned} but the poms it builds declare "
            f"Java {required}"
        )


def test_the_java_leg_checks_out_and_pins_the_jdk_before_it_builds() -> None:
    """R5 — a setup-java AFTER the build pins nothing."""
    for job_id, steps in _maven_jobs().items():
        checkouts = [index for index, step in enumerate(steps)
                     if str(step.get("uses", "")).startswith("actions/checkout")]
        setups = [index for index, step in enumerate(steps)
                  if str(step.get("uses", "")).startswith("actions/setup-java")]
        builds = [index for index, step in enumerate(steps)
                  if _maven_lines(str(step.get("run", "")))]
        assert checkouts, (
            f"{job_id} runs Maven but never checks the repository out — "
            "there is no source to build"
        )
        assert setups, f"{job_id} runs Maven but pins no JDK"
        assert min(checkouts) < min(builds), (
            f"{job_id} builds before it checks the code out"
        )
        assert min(setups) < min(builds), (
            f"{job_id} builds before it pins the JDK — the build used "
            "whatever JDK the runner happened to have"
        )


def test_a_module_without_java_tests_is_declared_with_a_reason() -> None:
    """R6 — an exemption without a reason is a hole with a name on it."""
    modules = _modules()
    for module in modules:
        count = _test_class_count(module)
        if count:
            continue
        assert module in NO_JAVA_TESTS, (
            f"{module} has ZERO Java test classes and is not declared in "
            "NO_JAVA_TESTS — declare it, with the reason, or write the test"
        )
        assert NO_JAVA_TESTS[module].strip(), (
            f"{module} is declared as having no Java tests, with no reason"
        )
    for module, reason in NO_JAVA_TESTS.items():
        assert module in modules, (
            f"{module} is declared as having no Java tests, but it is not a "
            "module of services/ any more — the declaration is stale"
        )
        assert reason.strip(), (
            f"{module} is declared as having no Java tests, with no reason — "
            "an exemption without a reason is a hole with a name on it"
        )
        count = _test_class_count(module)
        assert count == 0, (
            f"{module} is declared as having no Java tests, but it now has "
            f"{count} — the declaration is stale"
        )


def test_the_java_leg_cannot_swallow_the_exit_code() -> None:
    """R7 — a pipeline reports its LAST command's status (#537)."""
    for job_id, steps in _maven_jobs().items():
        for index, step in enumerate(steps):
            script = str(step.get("run", ""))
            for _command, piped in _maven_lines(script):
                if not piped:
                    continue
                assert "pipefail" in script, (
                    f"{job_id} step {index} pipes Maven's output into "
                    "something that swallows its exit code — the step would "
                    "go green on a failed build.  Use `set -o pipefail`, or "
                    "do not pipe"
                )


def test_the_java_leg_builds_a_directory_that_holds_the_module() -> None:
    """R8 — the job is not a name: the pom is really there."""
    for job_id, steps in _maven_jobs().items():
        for index, step in enumerate(steps):
            working = str(step.get("working-directory", "")).strip()
            if not working:
                continue
            if not (ROOT / working).is_dir():
                continue          # the module path is inside the command
            assert (ROOT / working / "pom.xml").is_file() or working in _modules(), (
                f"{job_id} step {index} works in {working!r}, which holds no "
                "pom.xml — Maven would fail there, or worse, build nothing"
            )
