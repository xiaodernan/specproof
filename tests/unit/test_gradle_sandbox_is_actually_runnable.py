"""The Gradle sandbox must be able to write its own build output, and the
seeding step its adapter names must actually exist.

Both assertions come from one measured failure (#492). With the dependency
home fully seeded and ``--network none``, the first Gradle task died with::

    Execution failed for task ':compileTestJava'.
    > Failed to create parent directory '/work/build' when creating
      directory '/work/build/classes/java/test'

``GRADLE_PROFILE`` mounted the workspace ``:ro`` and listed only ``.gradle``
as writable, so Gradle had nowhere to put task output: it could not complete a
single build, no matter how well the cache volume was seeded. Maven declares
the same requirement as ``("target", ...)``; the Gradle profile simply did not.

The seeding step had the mirror-image problem: ``OFFLINE_POLICY`` and the
architecture doc both named ``scripts/seed_gradle_home.ps1``, and no such file
existed anywhere in the repo — so the documented way to make Gradle work was a
dead pointer, and the volume it was supposed to fill was empty and root-owned.
"""

from __future__ import annotations

import re
from pathlib import Path

from experiments.adapters import (
    COMPATIBILITY_MATRIX,
    GoAdapter,
    GradleAdapter,
    JavaMavenAdapter,
    NodeAdapter,
    PythonAdapter,
)
from sandbox.runner import GRADLE_PROFILE

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SEED_SCRIPT = re.compile(r"scripts/[\w.]+\.ps1")

_ADAPTERS = (JavaMavenAdapter, GradleAdapter, NodeAdapter, PythonAdapter, GoAdapter)


def test_gradle_profile_lets_the_build_write_its_output() -> None:
    """`gradle test` writes under build/; a read-only build dir fails task 1."""
    writable = GRADLE_PROFILE.precreate_dirs

    assert "build" in writable, (
        "GRADLE_PROFILE must sub-mount build/ read-write: the workspace is "
        "mounted :ro, so without it Gradle fails its first task with "
        "\"Failed to create parent directory '/work/build'\". Writable: "
        f"{writable}"
    )
    # .gradle is the other one, and it is a different failure: the file-hash
    # lock lives there ("fileHashes.lock (Permission denied)").
    assert ".gradle" in writable


def test_every_adapter_declared_seed_script_exists() -> None:
    """A declaration that names a script nobody wrote is a dead pointer."""
    missing: list[str] = []
    for adapter in _ADAPTERS:
        declared = set(_SEED_SCRIPT.findall(adapter.OFFLINE_POLICY))
        for limit in adapter.KNOWN_LIMITS:
            declared |= set(_SEED_SCRIPT.findall(limit))
        for rel in sorted(declared):
            if not (_REPO_ROOT / rel).is_file():
                missing.append(f"{adapter.__name__}: {rel}")

    assert not missing, "adapters name seed scripts that do not exist: " + ", ".join(missing)


def test_the_gradle_seed_script_fills_the_volume_the_profile_mounts() -> None:
    """Two hand-copied names must agree, or seeding fills a volume nobody reads."""
    script = (_REPO_ROOT / "scripts" / "seed_gradle_home.ps1").read_text(encoding="utf-8")
    declared = re.search(r'\[string\]\$Volume\s*=\s*"([^"]+)"', script)

    assert declared is not None, "seed_gradle_home.ps1 must declare a default -Volume"
    assert declared.group(1) == GRADLE_PROFILE.cache_volume_default, (
        f"seed script defaults to {declared.group(1)!r} but GRADLE_PROFILE mounts "
        f"{GRADLE_PROFILE.cache_volume_default!r}"
    )


def test_the_gradle_seed_script_verifies_offline_in_the_sandbox_mount_shape() -> None:
    """Seeding without an offline verification proves nothing about the sandbox.

    The verification is only meaningful if it runs cold (the online phase's
    build/ and .gradle/ wiped first), without a network, with the workspace
    read-only and with the same two writable sub-mounts the profile declares.
    """
    script = (_REPO_ROOT / "scripts" / "seed_gradle_home.ps1").read_text(encoding="utf-8")

    for required in ("--network none", "--offline", "/work:ro", "GRADLE_USER_HOME"):
        assert required in script, f"seed script is missing {required!r}"
    # The two sub-mounts must be the profile's, not a hand-copied subset.
    for rel in GRADLE_PROFILE.precreate_dirs:
        assert f"/work/{rel}" in script, (
            f"seed script must mount {rel!r} writable during the offline "
            "verification, like the profile does"
        )
    # Cold start: otherwise every task reports UP-TO-DATE and the verification
    # would pass on an empty volume.
    assert re.search(r'foreach \(\$out in @\("build", "\.gradle"\)\)', script), (
        "seed script must wipe build/ and .gradle/ between the online and "
        "offline phases, or the offline phase proves nothing"
    )


def test_the_matrix_still_claims_gradle_support_now_that_it_runs() -> None:
    """The row exists, so the thing it points at must be runnable.

    This is the anti-regression half: if someone drops Gradle from the matrix
    this test says so, instead of the sandbox contract quietly losing its
    subject.
    """
    rows = {(row.language, row.build_tool): row for row in COMPATIBILITY_MATRIX}

    assert ("Java", "Gradle") in rows
    assert GradleAdapter.IMAGE  # the matrix's image column is derived from it
