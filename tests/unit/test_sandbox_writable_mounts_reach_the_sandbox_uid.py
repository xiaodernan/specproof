"""#533: a writable sub-mount is only writable if the sandbox uid can write it.

Measured on CI (eval-golden-cases; runs 41033998469, 41056790046,
41059283812): all four golden cases ended NOT_RUN with

  maven-resources-plugin ... Cannot create resource output directory:
  /work/target/classes

_ensure_writable_mounts() only mkdir()ed target/, so it belonged to the
runner (uid 1001, mode 0755) while the container runs as SANDBOX_USER
(1000). A bind mount carries the host mode. Docker Desktop's shared mounts
ignore modes, which is why every local run stayed green.

Arms (predicted before running, POSIX plane):
  K1 drop the chmod                 -> fresh-dir + existing-dir cases red
  K2 chmod only the Maven profile   -> every-profile case red
  K3 widen to 0o700                 -> effect cases red
  K4 run the workload as the host uid -> workload-uid case red

The effect cases are POSIX-gated: Windows reports synthetic 0777 modes, so
there the same fixture cannot represent a 1001-owned directory. The uid
contract case is platform-independent.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from sandbox import runner

POSIX_ONLY = pytest.mark.skipif(
    os.name != "posix",
    reason="Windows stat modes are synthetic; the ownership rule is POSIX-only",
)

PROFILES = (
    runner.MAVEN_PROFILE,
    runner.REPLAY_PROFILE,
    runner.NODE_PROFILE,
    runner.NODE_INSTALL_PROFILE,
    runner.PYTHON_PROFILE,
    runner.GO_PROFILE,
    runner.GRADLE_PROFILE,
)


def _other_write(path: Path) -> bool:
    return bool(stat.S_IMODE(os.stat(path).st_mode) & stat.S_IWOTH)


class TestWidenedForTheSandboxUid:
    @POSIX_ONLY
    def test_a_fresh_dir_is_created_world_writable(self, tmp_path: Path) -> None:
        assert runner._ensure_writable_mounts(str(tmp_path), runner.MAVEN_PROFILE) == ""
        target = tmp_path / "target"
        assert target.is_dir()
        assert stat.S_IMODE(os.stat(target).st_mode) == 0o777

    @POSIX_ONLY
    def test_a_runner_owned_dir_is_widened(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        os.chmod(target, 0o755)
        assert not _other_write(target)  # witness: this fixture is the CI shape

        assert runner._ensure_writable_mounts(str(tmp_path), runner.MAVEN_PROFILE) == ""
        assert _other_write(target), (
            f"target stayed {oct(stat.S_IMODE(os.stat(target).st_mode))}; "
            "uid 1000 still cannot write /work/target"
        )

    @POSIX_ONLY
    def test_every_profile_submount_is_widened(self, tmp_path: Path) -> None:
        assert [p.name for p in PROFILES if not p.precreate_dirs] == ["node"]
        for profile in PROFILES:
            for rel in profile.precreate_dirs:
                path = tmp_path / profile.name / rel
                path.mkdir(parents=True, exist_ok=True)
                os.chmod(path, 0o755)
        for profile in PROFILES:
            ws = tmp_path / profile.name
            assert runner._ensure_writable_mounts(str(ws), profile) == "", profile.name
            for rel in profile.precreate_dirs:
                assert _other_write(ws / rel), f"{profile.name}:{rel}"

    def test_the_workload_uid_does_not_follow_the_host_user(self) -> None:
        argv = runner.build_docker_argv(["true"], "/ws", runner.MAVEN_PROFILE)
        assert argv[argv.index("--user") + 1] == runner.SANDBOX_USER == "1000:1000"
