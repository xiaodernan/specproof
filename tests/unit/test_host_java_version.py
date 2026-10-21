"""The host build is told which JDK it actually has (#370).

The demo's pom pins ``<java.version>21</java.version>``. On a host
whose JDK is 17 the build stops with "release version 21 not supported"
— and a build that cannot START is a blocked verification, not a
verdict. So the host command carries the version the host is really
on.

Two things must stay true:

- the flag is only added when the version is KNOWN (a guess would be
  inventing a build);
- the CONTAINER command does not carry it (the image ships the JDK the
  pom targets, so the sandbox's behaviour is unchanged).
"""

from __future__ import annotations

from pathlib import Path

from experiments.adapters import (
    _host_java_major,
    _host_java_version_flag,
    JavaMavenAdapter,
)
from experiments.adapters import ExecutionRequest, RepositorySnapshot


def _request(goal: str = "run_test") -> ExecutionRequest:
    return ExecutionRequest(
        workspace=".",
        goal=goal,
        test_class="SpecProofGeneratedTest",
        skip_main=False,
        timeout=60,
    )


def test_the_host_java_version_is_measured_not_guessed() -> None:
    """The version comes from the JDK itself; a JDK that cannot be
    asked yields None (and then no flag at all)."""
    major = _host_java_major()
    assert major is None or (isinstance(major, int) and major >= 9)
    flag = _host_java_version_flag()
    assert flag == ([f"-Djava.version={major}"] if major else [])


def test_the_host_command_carries_the_version_and_the_container_does_not() -> None:
    """Only the host build is told: the container runs the JDK its image
    ships, which is the one the pom targets."""
    prepared = JavaMavenAdapter().prepare(_request())
    assert "-Djava.version=" in " ".join(prepared.local_command) or (
        _host_java_major() is None
    )
    assert "-Djava.version=" not in " ".join(prepared.command)


def test_the_test_compile_goal_is_told_too() -> None:
    """The compile step runs before the test step; if only the test
    command were told, the build would still fail first."""
    prepared = JavaMavenAdapter().prepare(_request(goal="test_compile"))
    assert "-Djava.version=" in " ".join(prepared.local_command) or (
        _host_java_major() is None
    )
    assert "-Djava.version=" not in " ".join(prepared.command)


def test_the_repository_snapshot_still_detects() -> None:
    """The change is in the COMMAND, not in the detection."""
    repo = Path("demo/spring-backend")
    if not repo.exists():
        return
    snapshot = RepositorySnapshot(path=str(repo))
    assert snapshot.path
