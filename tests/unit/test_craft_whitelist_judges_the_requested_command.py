"""#131 — the whitelist must judge the command that was ASKED for.

Measured on this host by handing ``Executor`` three different interpreters:

- ``C:/venv/python.exe``            -> stem ``python``     -> ran
- ``/usr/bin/python3.12``           -> stem ``python3.12`` -> CommandNotAllowedError
- ``/opt/hostedtoolcache/Python/3.12.4/x64/bin/python3.12``
  -> stem ``python3.12``            -> CommandNotAllowedError

The third is the shape of ``sys.executable`` on a GitHub Actions Ubuntu runner
with ``actions/setup-python`` (that job reports ``platform linux -- Python
3.12.14``), so the same legal request is accepted here and refused there.

Why it happens: ``Executor._resolve_command`` rewrites a bare ``python`` /
``pytest`` request into ``[self.python, ...]`` and ``Executor.run`` then tests
``Path(resolved[0]).stem.lower()`` — so the whitelist judges OUR substitution,
not the model's request. A version-named interpreter therefore turns
``["pytest", "-q"]`` into a command the product refuses to run itself, and
``run_pytest`` (which puts ``self.python`` in argv[0] directly) is refused on
any host whose interpreter is version-named.

The substitution cannot smuggle anything in: the interpreter is the product's
own configuration, and it is the requested command that needs vetting. Checking
the resolved stem also does not protect against a disallowed binary — an
absolute path supplied as the request is still judged by its own stem below.

These cases pin both directions: a version-named interpreter we chose must not
defeat the whitelist, and a request for something outside it must still be
refused even when it merely looks like an interpreter path.
"""

from __future__ import annotations

import pytest

from craft.executor import CommandNotAllowedError, Executor

VERSIONED = "/usr/bin/python3.12"
BARE = "/opt/venv/bin/python"


def _executor(tmp_path, python: str | None = None, **kwargs) -> Executor:
    return Executor(tmp_path, mode="local", python=python, **kwargs)


def test_a_version_named_interpreter_we_substituted_is_not_a_new_command(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The request is 'pytest'; the interpreter name is ours, so it cannot make
    a whitelisted command unwhitelisted."""
    seen: list[list[str]] = []
    monkeypatch.setattr(
        "craft.executor.run_sandboxed",
        lambda **kw: seen.append(list(kw["command"])) or _result(kw),
    )
    executor = _executor(tmp_path, python=VERSIONED)
    result = executor.run(["pytest", "-q"])
    assert seen == [[VERSIONED, "-m", "pytest", "-q"]], seen
    assert result.exit_code == 0


def test_run_pytest_survives_whichever_interpreter_the_host_named(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_pytest puts the configured interpreter in argv[0] itself; the two
    spellings must not be policed differently."""
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "craft.executor.run_sandboxed",
        lambda **kw: calls.append(list(kw["command"])) or _result(kw),
    )
    for python in (VERSIONED, BARE):
        _executor(tmp_path, python=python).run_pytest(["-q"])
    assert [c[1:3] for c in calls] == [["-m", "pytest"], ["-m", "pytest"]], calls


def test_a_requested_binary_outside_the_whitelist_is_still_refused(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tightening the rule to the requested command must not open a hole: an
    absolute path the caller asked for is judged by its own stem."""
    monkeypatch.setattr(
        "craft.executor.run_sandboxed",
        lambda **kw: _result(kw),
    )
    executor = _executor(tmp_path, python=VERSIONED)
    with pytest.raises(CommandNotAllowedError):
        executor.run(["/bin/rm", "-rf", "/"])
    with pytest.raises(CommandNotAllowedError):
        executor.run(["/usr/bin/python2.7", "evil.py"])


def test_the_profile_follows_the_command_that_was_asked_for(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#129 routes a stem to its container image; with a version-named
    interpreter the routed stem must still be the one that was requested, or
    'pytest' would fall out of the table and lose the python image."""
    profiles: list[object] = []
    monkeypatch.setattr(
        "craft.executor.run_sandboxed",
        lambda **kw: profiles.append(kw["profile"]) or _result(kw),
    )
    executor = _executor(tmp_path, python=VERSIONED)
    executor.run(["pytest", "-q"])
    from craft.executor import PROFILE_BY_STEM

    assert profiles == [PROFILE_BY_STEM["pytest"]], profiles


def _result(kwargs: dict) -> object:
    from sandbox.runner import SandboxResult

    return SandboxResult(exit_code=0, stdout="", stderr="", mode=str(kwargs.get("mode")))
