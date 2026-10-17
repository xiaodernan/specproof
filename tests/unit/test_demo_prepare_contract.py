"""Fence tests for ``commands/demo.py`` ref probe and demo-repo preparation.

``_ref_exists`` is the idempotency probe; ``prepare_demo_repo`` builds the
``base`` / ``head-v1`` refs the demo verification diffs. Both run real git in a
repo-external temp directory (never the shipped ``demo/spring-backend``).

Speed: preparing a repo runs ~10 git subprocesses, and this machine's global
pre-commit hook costs ~20s per commit, so the module fixture prepares ONE repo
and every assertion reuses it; ``GIT_CONFIG_*`` disables the hook for the temp
repo only (command-line config beats the machine-wide ``core.hooksPath``).
"""

import subprocess
import tempfile
from pathlib import Path

import click
import pytest

from cli.specproof.commands.demo import _ref_exists, prepare_demo_repo

_CONTROLLER = "src/main/java/com/specproof/demo/controller/UserController.java"

_ORIGINAL = (
    "package com.specproof.demo.controller;\n"
    "\n"
    "class UserController {\n"
    '    @PreAuthorize("isAuthenticated()")\n'
    "    void changeEmail() {}\n"
    "}\n"
)

_NO_GUARD = (
    "package com.specproof.demo.controller;\n"
    "\n"
    "class UserController {\n"
    "    void changeEmail() {}\n"
    "}\n"
)


def _make_repo(root: Path, controller_src: str) -> None:
    ctrl = root / _CONTROLLER
    ctrl.parent.mkdir(parents=True, exist_ok=True)
    ctrl.write_text(controller_src, encoding="utf-8")


@pytest.fixture(scope="module", autouse=True)
def _no_commit_hook():
    # Command-line-level config wins over the machine-wide core.hooksPath, so
    # the temp repo's commits skip the ~20s global pre-commit hook.
    mp = pytest.MonkeyPatch()
    mp.setenv("GIT_CONFIG_COUNT", "1")
    mp.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    mp.setenv("GIT_CONFIG_VALUE_0", str(Path(tempfile.gettempdir()) / "specproof-no-hooks"))
    yield
    mp.undo()


@pytest.fixture(scope="module")
def prepared():
    d = tempfile.TemporaryDirectory()
    root = Path(d.name)
    _make_repo(root, _ORIGINAL)
    created = prepare_demo_repo(root)
    yield root, created
    d.cleanup()


# --- _ref_exists ------------------------------------------------------------

def test_ref_exists_false_without_repo():
    with tempfile.TemporaryDirectory() as d:
        assert _ref_exists(Path(d), "base") is False


# --- prepare_demo_repo: error paths ----------------------------------------

def test_prepare_missing_dir_raises():
    with tempfile.TemporaryDirectory() as d, pytest.raises(click.ClickException):
        prepare_demo_repo(Path(d) / "absent")


def test_prepare_missing_guard_raises():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_repo(root, _NO_GUARD)
        with pytest.raises(click.ClickException) as exc:
            prepare_demo_repo(root)
        assert "权限检查注解已不在源文件中" in str(exc.value)


# --- prepare_demo_repo: happy path (shared repo) ---------------------------

def test_prepare_creates_base_and_head_refs(prepared):
    root, created = prepared
    assert created is True
    assert _ref_exists(root, "base") is True
    assert _ref_exists(root, "head-v1") is True


def test_prepare_is_idempotent(prepared):
    root, _ = prepared
    # both refs exist now -> second call is a no-op returning False
    assert prepare_demo_repo(root) is False


def test_prepare_restores_original_working_tree(prepared):
    root, _ = prepared
    restored = (root / _CONTROLLER).read_text(encoding="utf-8")
    assert restored == _ORIGINAL
    assert '@PreAuthorize("isAuthenticated()")' in restored


def test_head_ref_lacks_the_guard(prepared):
    root, _ = prepared
    content = subprocess.run(
        ["git", "-C", str(root), "show", f"head-v1:{_CONTROLLER}"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    assert '@PreAuthorize("isAuthenticated()")' not in content


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
