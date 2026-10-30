"""#534: a restored build cache is only usable if the sandbox uid can overwrite it.

Measured on CI (eval-golden-cases; run 41063377309), after #533 made
/work/target world-writable: every golden case still ended NOT_RUN, now with

  maven-resources-plugin ... filtering /work/src/main/resources/application.yml
  to /work/target/classes/application.yml failed with FileNotFoundException:
  /work/target/classes/application.yml (Permission denied)

The P6 base-build cache (agent/nodes/build_cache.py) writes compiled classes
from the RUNNER's uid (1001) on the host and shutil.copytree()s them into each
case's fresh worktree, preserving the 0644/0755 modes. Maven's resources phase
rewrites target/classes/application.yml on every run — including the
-Dmaven.main.skip=true cache-hit path — and the workload runs as SANDBOX_USER
(1000), so the restored file was unwritable. case-12 builds first, saves the
cache, and poisons every later case (17/21/56); Docker Desktop's host mounts
ignore modes, which is why local runs stayed green.

Reproduced with the real uid split in Docker (named volume, runner 1001,
workload 1000), three legs on the same volume:
  - pre-fix bytes          -> the exact FileNotFoundException above
  - widen the modes only   -> `FileSystemException: ... Operation not
                              permitted`: maven-resources-plugin copies with
                              COPY_ATTRIBUTES and cannot chmod/utime a file
                              owned by the runner
  - widen + drop the restored resource outputs (the plugin then creates them
    as uid 1000) -> BUILD SUCCESS

Arms (predicted before running, POSIX plane):
  K1 drop the widening call           -> restore + seed widening cases red
  K2 widen files to 0o777             -> file-mode assertions red
  K3 widen only classes/              -> seed test-classes case red
  K4 widen before the copy            -> copytree re-applies 0644; restore + seed red
  K5 drop the resource deletion       -> regenerated-resources case red
  K6 delete before the copy           -> the copy re-adds them; resources case red

The mode assertions are POSIX-gated: Windows stat modes are synthetic
(0777), so the same fixture cannot represent a 1001-owned tree there.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from agent.nodes.build_cache import restore_base_build, seed_head_build

POSIX_ONLY = pytest.mark.skipif(
    os.name != "posix",
    reason="Windows stat modes are synthetic; the ownership rule is POSIX-only",
)

CLASS_BYTES = b"\xca\xfe\xba\xbe-restored-class"
YML_BYTES = b"spring:\n  application:\n    name: demo\n"


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _other_write(path: Path) -> bool:
    return bool(_mode(path) & stat.S_IWOTH)


def _write_cache_tree(root: Path) -> None:
    """Build a cache that looks like the CI one: runner-owned, 0644/0755."""
    root.mkdir(parents=True)
    (root / "pkg").mkdir()
    (root / "pkg" / "App.class").write_bytes(CLASS_BYTES)
    (root / "application.yml").write_bytes(YML_BYTES)
    if os.name == "posix":
        os.chmod(root, 0o755)
        os.chmod(root / "pkg", 0o755)
        os.chmod(root / "pkg" / "App.class", 0o644)
        os.chmod(root / "application.yml", 0o644)
        # Witness: this fixture really is the shape the sandbox could not
        # overwrite. If the fixture silently became writable, every effect
        # assertion below would be vacuous.
        assert not _other_write(root / "application.yml")


@pytest.fixture()
def cache(tmp_path: Path) -> Path:
    root = tmp_path / "cache"
    _write_cache_tree(root / "classes")
    _write_cache_tree(root / "test-classes")
    return root


class TestRestoredCacheIsWritableForTheSandboxUid:
    @POSIX_ONLY
    def test_restore_widens_every_restored_dir_and_file(
        self, cache: Path, tmp_path: Path,
    ) -> None:
        work = tmp_path / "work"
        assert restore_base_build(cache, str(work)) is True
        classes = work / "target" / "classes"
        assert _mode(classes) == 0o777
        assert _mode(classes / "pkg") == 0o777
        assert _mode(classes / "pkg" / "App.class") == 0o666, (
            f"App.class stayed {oct(_mode(classes / 'pkg' / 'App.class'))}; "
            "uid 1000 still cannot rewrite the restored class tree"
        )
        assert _mode(classes / "application.yml") == 0o666
        # The widening is for the disposable worktree copy, not the cache.
        assert _mode(cache / "classes" / "application.yml") == 0o644

    @POSIX_ONLY
    def test_seed_head_build_widens_test_classes_too(
        self, cache: Path, tmp_path: Path,
    ) -> None:
        work = tmp_path / "work"
        assert seed_head_build(cache, str(work), []) is True
        for sub in ("classes", "test-classes"):
            tree = work / "target" / sub
            assert _mode(tree) == 0o777, sub
            assert _mode(tree / "application.yml") == 0o666, sub

    def test_restore_carries_the_cached_bytes(self, cache: Path, tmp_path: Path) -> None:
        work = tmp_path / "work"
        assert restore_base_build(cache, str(work)) is True
        for sub in ("classes", "test-classes"):
            restored = work / "target" / sub
            assert (restored / "pkg" / "App.class").read_bytes() == CLASS_BYTES
            assert (restored / "application.yml").read_bytes() == YML_BYTES

    def test_restore_drops_outputs_the_resources_phase_will_regenerate(
        self, tmp_path: Path,
    ) -> None:
        work = tmp_path / "work"
        for rel, data in (
            ("src/main/resources/application.yml", YML_BYTES),
            ("src/main/resources/static/app.js", b"console.log(1)\n"),
            ("src/test/resources/application-test.yml", b"test: true\n"),
        ):
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            (work / rel).write_bytes(data)
        cache = tmp_path / "cache"
        for rel, data in (
            ("classes/application.yml", YML_BYTES),
            ("classes/static/app.js", b"console.log(1)\n"),
            ("classes/pkg/App.class", CLASS_BYTES),
            ("classes/META-INF/spring-configuration-metadata.json", b"{}"),
            ("test-classes/application-test.yml", b"test: true\n"),
            ("test-classes/pkg/AppTest.class", CLASS_BYTES),
        ):
            (cache / rel).parent.mkdir(parents=True, exist_ok=True)
            (cache / rel).write_bytes(data)

        assert restore_base_build(cache, str(work)) is True
        for gone in (
            "classes/application.yml",
            "classes/static/app.js",
            "test-classes/application-test.yml",
        ):
            assert not (work / "target" / gone).exists(), (
                f"{gone} was restored; the resources phase cannot rewrite a "
                "runner-owned file (COPY_ATTRIBUTES -> EPERM)"
            )
        assert (work / "target/classes/pkg/App.class").read_bytes() == CLASS_BYTES
        assert (work / "target/test-classes/pkg/AppTest.class").read_bytes() == CLASS_BYTES
        metadata = work / "target/classes/META-INF/spring-configuration-metadata.json"
        assert metadata.read_bytes() == b"{}"

    def test_a_missing_cache_leaves_no_target_behind(self, tmp_path: Path) -> None:
        work = tmp_path / "work"
        assert restore_base_build(tmp_path / "absent", str(work)) is False
        assert not (work / "target").exists()
