r"""#513 — what the craft adapters read out of a killed or chatty child.

`docs/operations/DEEP_OPTIMIZATION_PLAN.md` #499 left this lane two stable red
gates and one claim: "craft/'s 5 locale-decoded captures + 3 `TimeoutExpired`
branches that read `.stdout` directly". Measured here (#513), the claim was half
wrong, and the wrong half is the interesting part:

* The five captures were real. `subprocess.run(..., text=True)` with no
  `encoding=` decodes with `locale.getpreferredencoding()`, which on this host
  is cp936. Measured on three interpreters (3.11 / 3.12 / 3.14) in the same
  tree: a child that writes UTF-8 makes the reader thread die inside
  `subprocess`, and `CompletedProcess.stdout` comes back as **`None`**. The
  adapters then hand `_as_text(None)` → `""` to `ExecutionResult`, so a build
  that failed loudly looks identical to a build that printed nothing. In
  `craft/mutation.py` the same event raised `TypeError` on
  `result.stdout + result.stderr`, which the broad handler booked as
  `MutationStatus.ERROR` — a killed mutant recorded as an infra error. That
  module turned out to have no published caller (it was the dead second
  mutation engine) and #535 deleted it; the captured-in-tree sites pinned
  below are the four adapters.
* The three timeout branches were **not** reading raw bytes. Each one decoded
  correctly, through a private `_as_text` copy (Go and Node byte-identical,
  Gradle differing only by passing `errors` positionally, which is why the
  #499b AST ratchet never listed it as a clone). The census gate could only see
  the absence of the string `timed_out_partial`, so it reported a defect as a
  violation and a passing comment as compliance. `test_timeout_partial_output.py`
  now checks the shape instead of the spelling.

Both halves of the fix are gated here: the pins are proven to *reach* the child
call (a declaration in dead code would not count), and the timeout branch is
proven to keep the killed child's bytes as text.

#520 — the three host-shaped legs ("is the host already UTF-8?") compared the
*spelling* of `locale.getpreferredencoding(False)` against `"utf-8"`. This host
answers `cp936`; CI answers `UTF-8`, so on run 40714443058 all three ran their
assertions instead of skipping and asserted a trap that cannot exist where the
host and the child agree. One of them normalized the host to `"utf8"` and still
compared against the dashed constant, so it was wrong on *every* UTF-8 host.
The decision is now `tests/_host_codec.host_prefers` (`codecs.lookup(...).name`
on both sides); the host-shaped legs still skip where they cannot judge, two
explicit codec-pair legs keep the mechanism witnessed on every plane, and a
child interpreter started with `PYTHONUTF8=1` walks the CI plane itself.

#541 — one of these five captures was never supposed to exist. Gradle's
`_detect_gradle_version` ran `gradlew --version` from `prepare()`, i.e. on the
host, before any sandbox, against a repository the product is grading — and its
answer described the host, not the toolchain that would run the tests. The
probe is gone (see `tests/unit/test_craft_profile_phase_runs_no_children.py`),
which is why this file no longer says "five capture sites" in a header: a header
cannot notice its own deletion, so the roster below is compared against the
adapters' AST and a capture leaving the code has to leave the roster too.
"""

from __future__ import annotations

import ast
import locale
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from craft.adapters.go_adapter import GoAdapter
from craft.adapters.gradle_adapter import GradleAdapter
from craft.adapters.node_adapter import NodeAdapter
from craft.adapters.protocol import RuntimeProfile
from tests._host_codec import host_prefers

REPO = Path(__file__).resolve().parents[2]

#: Text a CJK toolchain would really print. The `✕` is the whole mechanism: it
#: is not representable in cp936, so the child's UTF-8 bytes are not either
#: (measured: "illegal multibyte sequence" at byte 0x95).
PAYLOAD = "编译失败：找不到符号 ✕ leak\n"

#: The cp936-representable half, for the cases where the *child* is the one
#: writing the host codec (`✕` above cannot be encoded into cp936 at all).
HOST_PAYLOAD = "编译失败：找不到符号 leak\n"

#: The codec every pinned capture in this lane must name, and `errors` is not
#: decoration — see `test_strict_utf8_is_the_same_trap_in_the_other_direction`.
PINNED_CODEC = "utf-8"

#: The three adapters whose timeout branch keeps the killed child's output.
ADAPTERS: list[tuple[str, Any, dict[str, str]]] = [
    ("go", GoAdapter, {}),
    ("gradle", GradleAdapter, {"language": "java", "build_tool": "gradle"}),
    ("node", NodeAdapter, {}),
]


class _ChildRun:
    """A `subprocess.run` stand-in that records the call it intercepted.

    Recording the kwargs is the point: a codec written into a call site that
    never runs would satisfy a source-text gate and save nothing, so every case
    below drives the real adapter method and reads back what actually reached
    `subprocess`.
    """

    def __init__(
        self,
        *,
        raises: subprocess.TimeoutExpired | None = None,
        stdout: object = "",
        stderr: object = "",
        returncode: int = 0,
    ) -> None:
        self.raises = raises
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, argv: list[str], *args: object, **kwargs: object) -> object:
        self.calls.append((list(argv), kwargs))
        if self.raises is not None:
            raise self.raises
        done: subprocess.CompletedProcess[object] = subprocess.CompletedProcess(
            list(argv), self.returncode
        )
        done.stdout = self.stdout
        done.stderr = self.stderr
        return done

    @property
    def kwargs(self) -> dict[str, object]:
        assert len(self.calls) == 1, f"expected exactly one child call, got {len(self.calls)}"
        return self.calls[0][1]


def _timeout(stdout: object, stderr: object = b"") -> subprocess.TimeoutExpired:
    """A timeout shaped the way the killed child's OS shapes it."""
    exc = subprocess.TimeoutExpired(cmd=["<toolchain>", "test"], timeout=3)
    exc.stdout = stdout  # type: ignore[attr-defined]
    exc.stderr = stderr  # type: ignore[attr-defined]
    return exc


def _profile(language: str = "go", build_tool: str = "go", **extra: object) -> RuntimeProfile:
    return RuntimeProfile(
        language=language,
        build_tool=build_tool,
        language_version="1.23",
        dependency_cache_path=Path("/cache"),
        extra=dict(extra),
    )


def _assert_codec_is_named(kwargs: dict[str, object], site: str) -> None:
    """The one rule every capture in this lane shares."""
    assert kwargs.get("capture_output") is True, f"{site} must capture, not inherit"
    assert kwargs.get("text") is True, f"{site} is a text capture: text={kwargs.get('text')!r}"
    assert kwargs.get("encoding") == PINNED_CODEC, (
        f"{site} decodes with the host's preferred codec "
        f"({locale.getpreferredencoding(False)} on this machine) — a child that "
        f"emits UTF-8 then reads back as nothing. Got encoding={kwargs.get('encoding')!r}"
    )
    assert kwargs.get("errors") == "replace", (
        f"{site} names the codec but not the error policy: strict UTF-8 kills the "
        f"reader thread just as quietly, in the other direction. Got errors="
        f"{kwargs.get('errors')!r}"
    )


# --- the capture sites, and the roster that keeps them counted ---------------


def test_the_go_test_capture_names_its_codec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _ChildRun()
    monkeypatch.setattr(subprocess, "run", fake)
    GoAdapter.execute(tmp_path, _profile())
    _assert_codec_is_named(fake.kwargs, "craft/adapters/go_adapter.py::execute")


def test_the_gradle_test_capture_names_its_codec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _ChildRun()
    monkeypatch.setattr(subprocess, "run", fake)
    GradleAdapter.execute(tmp_path, _profile(language="java", build_tool="gradle"))
    _assert_codec_is_named(fake.kwargs, "craft/adapters/gradle_adapter.py::execute")


def _gradlew(tmp_path: Path) -> Path:
    """`_collect_dependency_tree` hides behind `gradlew.exists()`, so the probe needs it."""
    wrapper = tmp_path / ("gradlew.bat" if os.name == "nt" else "gradlew")
    wrapper.write_text("@echo off\r\n", encoding="utf-8")
    return wrapper


def test_the_gradle_dependency_probe_names_its_codec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _gradlew(tmp_path)
    fake = _ChildRun(stdout="+--- org.example:lib:1.0\n")
    monkeypatch.setattr(subprocess, "run", fake)
    GradleAdapter._collect_dependency_tree(tmp_path, _profile(language="java"))
    _assert_codec_is_named(
        fake.kwargs, "craft/adapters/gradle_adapter.py::_collect_dependency_tree"
    )


# --- the roster, and the census that keeps it honest -------------------------

#: Every child process this lane launches, as `(module file, function)`.
#:
#: #513 wrote this as a section header ("the five capture sites") and let the
#: legs restate it one by one. #541 deleted one of those five — the profile
#: phase's `gradlew --version` probe — and a header would have kept saying
#: "five" with nobody reading it, while the remaining legs stayed green. The
#: roster below is now compared against the adapters' own AST, so both
#: directions are charged: a new child process must appear here, and a capture
#: that leaves the code must leave this set in the same commit.
CAPTURES: frozenset[tuple[str, str]] = frozenset(
    {
        ("go_adapter.py", "execute"),
        ("gradle_adapter.py", "execute"),
        ("gradle_adapter.py", "_collect_dependency_tree"),
        ("node_adapter.py", "execute"),
    }
)

ADAPTERS_DIR = REPO / "craft" / "adapters"
_SPAWN_FUNCS = {"run", "Popen", "check_output", "check_call", "call"}


def _capture_sites(adapters_dir: Path) -> set[tuple[str, str]]:
    """`(file, function)` for every `subprocess.*` call inside an adapter method."""
    sites: set[tuple[str, str]] = set()
    for path in sorted(adapters_dir.glob("*.py")):
        if path.name in {"protocol.py", "__init__.py"}:
            continue
        module = ast.parse(path.read_text(encoding="utf-8"))
        for func in (n for n in ast.walk(module) if isinstance(n, ast.FunctionDef)):
            for call in ast.walk(func):
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                    continue
                if getattr(call.func.value, "id", "") != "subprocess":
                    continue
                if call.func.attr in _SPAWN_FUNCS:
                    sites.add((path.name, func.name))
    return sites


def test_the_capture_roster_is_the_census_of_the_lane() -> None:
    measured = _capture_sites(ADAPTERS_DIR)
    assert measured == set(CAPTURES), (
        "this file pins codec `encoding=`/`errors=` site by site, so a site that "
        "appeared without a leg is unpinned and a leg whose site is gone is a "
        f"lie. roster={sorted(CAPTURES)} code={sorted(measured)}"
    )


def test_a_capture_that_leaves_the_lane_must_leave_the_roster(tmp_path: Path) -> None:
    """Reverse control, on a copy: a deleted capture does not leave the roster quietly.

    This is the arm for the site #541 deleted. Parity alone would still pass if
    the code shrank and the roster did not — a pinned codec on a call that no
    longer exists reads as compliance and witnesses nothing.
    """
    copy = tmp_path / "adapters"
    shutil.copytree(ADAPTERS_DIR, copy)
    gradle = copy / "gradle_adapter.py"
    source = gradle.read_text(encoding="utf-8")
    argv_line = (
        '                    [str(gradlew), "dependencies", "--configuration", "runtimeClasspath"],'
    )
    # the *call* loses its target, not one of its arguments: a first draft of
    # this arm replaced only the argv list and the census still saw a child,
    # because `subprocess.run([...])` was intact.
    needle = f"result = subprocess.run(\n{argv_line}"
    found = source.count(needle)
    assert found == 1, f"expected one dependency-tree spawn, found {found}"
    replacement = f"result = _arm_no_child(\n{argv_line}"
    gradle.write_text(source.replace(needle, replacement), encoding="utf-8")

    measured = _capture_sites(copy)
    assert measured == set(CAPTURES) - {("gradle_adapter.py", "_collect_dependency_tree")}, (
        "deleting the dependency-tree capture left the roster reading as complete: "
        f"{sorted(measured)}"
    )


def test_a_capture_in_a_function_not_on_the_roster_is_a_finding(tmp_path: Path) -> None:
    """The growth direction, on a synthetic lane.

    The census counts functions, not call sites: a second child inside one
    `execute` stays one roster entry — that shape is caught by
    `_ChildRun.kwargs`, whose recorder insists on exactly one call. A child in a
    *new* function is the shape only this parity leg can see, and it is the one
    an adapter grows by when it learns to probe.
    """
    lane = tmp_path / "adapters"
    lane.mkdir()
    (lane / "extra_adapter.py").write_text(
        "import subprocess\n"
        "class Extra:\n"
        "    @classmethod\n"
        "    def execute(cls, root, profile):\n"
        "        return subprocess.run(['tool', 'test'], check=False)\n"
        "    @classmethod\n"
        "    def _probe(cls, root):\n"
        "        return subprocess.run(['tool', '--version'], check=False)\n",
        encoding="utf-8",
    )
    measured = _capture_sites(lane)
    assert measured == {
        ("extra_adapter.py", "execute"),
        ("extra_adapter.py", "_probe"),
    }, measured
    assert not measured <= set(CAPTURES), (
        "a lane that outgrew the roster read as compliant"
    )


# --- the killed child --------------------------------------------------------


ADAPTER_IDS = [a[0] for a in ADAPTERS]
ADAPTER_CASES = ("name", "adapter", "profile_kwargs")

@pytest.mark.parametrize(ADAPTER_CASES, ADAPTERS, ids=ADAPTER_IDS)
def test_a_kill_that_carries_bytes_keeps_them_as_text(
    name: str,
    adapter: Any,
    profile_kwargs: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The POSIX shape: `TimeoutExpired.stdout` is bytes, not str.

    Windows re-runs `communicate()` and gives `str`; a reader that accepts only
    `str` loses the killed child's whole output on Linux — which is the plane
    the docker sandbox runs on.
    """
    fake = _ChildRun(raises=_timeout(PAYLOAD.encode("utf-8"), b"boom"))
    monkeypatch.setattr(subprocess, "run", fake)
    result = adapter.execute(tmp_path, _profile(**profile_kwargs))
    assert result.exit_code == -1
    assert result.stdout == PAYLOAD, f"{name} lost the partial output: {result.stdout!r}"
    assert result.stderr == "boom"
    assert any("timeout" in e.lower() for e in result.parse_errors)


ADAPTER_IDS = [a[0] for a in ADAPTERS]
ADAPTER_CASES = ("name", "adapter", "profile_kwargs")

@pytest.mark.parametrize(ADAPTER_CASES, ADAPTERS, ids=ADAPTER_IDS)
def test_a_kill_before_any_output_is_empty_text_not_none(
    name: str,
    adapter: Any,
    profile_kwargs: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _ChildRun(raises=_timeout(None, None))
    monkeypatch.setattr(subprocess, "run", fake)
    result = adapter.execute(tmp_path, _profile(**profile_kwargs))
    assert result.stdout == "" and result.stderr == ""
    assert isinstance(result.stdout, str), f"{name}: ExecutionResult.stdout is declared str"


def test_a_bytes_shaped_normal_read_is_decoded_not_forwarded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Node adapter still runs with `text=False`, so its pipes are bytes.

    It must still hand back text: `ExecutionResult.stdout` is declared `str`, and
    a `bytes` in that field reaches the parsers as a `TypeError` that the broad
    handler books as a failure.
    """
    fake = _ChildRun(stdout=PAYLOAD.encode("utf-8"), stderr=b"")
    monkeypatch.setattr(subprocess, "run", fake)
    result = NodeAdapter.execute(tmp_path, _profile())
    assert result.stdout == PAYLOAD
    assert fake.kwargs.get("text") is None, "node's call is the deliberate bytes-mode one"


# --- the mechanism, kept honest ---------------------------------------------


def _spawn_bytes(payload: str, child_codec: str) -> bytes:
    """Capture as bytes only, so this file never adds an unpinned text capture."""
    raw = payload.encode(child_codec)
    child_src = f"import sys\nsys.stdout.buffer.write({raw!r})\n"
    proc = subprocess.run(
        [sys.executable, "-c", child_src],
        capture_output=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[:200]
    return proc.stdout


def _read_the_way_the_adapters_used_to(raw: bytes) -> str | None:
    """What `text=True` with no `encoding=` does: decode, and swallow the death.

    `subprocess` decodes on a reader thread; when the decode raises, the thread
    dies and `CompletedProcess.stdout` arrives as `None`. Reproduced directly
    here because the host's preferred codec cannot be monkeypatched — measured
    in #513: `locale.getpreferredencoding` patched to latin-1 still produced the
    cp936 failure, because `TextIOWrapper` asks the C locale rather than the
    Python attribute.
    """
    try:
        return raw.decode(locale.getpreferredencoding(False))
    except UnicodeDecodeError:
        return None


# --- the mechanism with both codecs named (runs on every plane) --------------


def test_the_childs_utf8_bytes_are_illegal_cp936_wherever_this_runs() -> None:
    """The mechanism with both codecs named, so no host can make it vacuous.

    The host-shaped legs below skip on a UTF-8 machine — correctly, because
    their trap cannot exist where the host and the child agree. This one keeps
    the claim witnessed on every plane: the bytes a CJK toolchain prints are
    not cp936, so a reader that happens to prefer cp936 loses them. Measured:
    byte 33 (0x95).
    """
    raw = PAYLOAD.encode(PINNED_CODEC)
    with pytest.raises(UnicodeDecodeError):
        raw.decode("cp936")
    assert raw.decode(PINNED_CODEC, errors="replace") == PAYLOAD


def test_cp936_bytes_are_illegal_strict_utf8_wherever_this_runs() -> None:
    """The other direction, also with named codecs: `errors=` is not decoration.

    A parent pinned to utf-8 but strict still loses a cp936 child's output —
    the case `PINNED_CODEC` plus `errors="replace"` exists for. Measured: byte
    0 (0xb1), and the replacing read keeps the text with U+FFFD.
    """
    raw = HOST_PAYLOAD.encode("cp936")
    with pytest.raises(UnicodeDecodeError):
        raw.decode(PINNED_CODEC)
    assert "\ufffd" in raw.decode(PINNED_CODEC, errors="replace")


# --- the host-shaped legs -----------------------------------------------------


def test_the_payload_really_is_illegal_in_the_host_codec() -> None:
    """If the host decodes this payload cleanly, the rows below prove nothing."""
    if host_prefers(PINNED_CODEC):
        pytest.skip(
            f"host prefers {locale.getpreferredencoding(False)!r}: no locale can "
            "disagree with the payload here"
        )
    raw = _spawn_bytes(PAYLOAD, PINNED_CODEC)
    assert _read_the_way_the_adapters_used_to(raw) is None, (
        "a payload the host codec accepts cannot detect an unpinned reader"
    )


def test_the_old_shape_loses_the_output_and_the_new_one_does_not() -> None:
    if host_prefers(PINNED_CODEC):
        pytest.skip(
            f"host prefers {locale.getpreferredencoding(False)!r}: the old shape "
            "cannot fail here"
        )
    raw = _spawn_bytes(PAYLOAD, PINNED_CODEC)
    assert _read_the_way_the_adapters_used_to(raw) is None
    assert raw.decode(PINNED_CODEC, errors="replace") == PAYLOAD, (
        "the pinned shape must read the child's own bytes back"
    )


def test_strict_utf8_is_the_same_trap_in_the_other_direction() -> None:
    """`encoding="utf-8"` without `errors="replace"` still yields nothing.

    Measured on this host: a child that emits cp936 read by a strict UTF-8
    parent gives `stdout is None` too. That is why the gate above insists on the
    error policy, not only on the codec name.

    The payload here is the *host*-representable half of #513's matrix —
    `✕` has no cp936 byte at all, so a cp936-emitting child cannot send it.
    """
    if host_prefers(PINNED_CODEC):
        pytest.skip(
            f"host prefers {locale.getpreferredencoding(False)!r}: its bytes are "
            "valid UTF-8, so strictness cannot fail here"
        )
    raw = _spawn_bytes(HOST_PAYLOAD, locale.getpreferredencoding(False))
    with pytest.raises(UnicodeDecodeError):
        raw.decode(PINNED_CODEC)
    decoded = raw.decode(PINNED_CODEC, errors="replace")
    assert "\ufffd" in decoded, (
        f"the host codec's bytes happen to be valid UTF-8 on this machine, so "
        f"`errors=` cannot be shown to matter here: {decoded!r}"
    )


# --- the CI plane, kept from drifting back ------------------------------------


@pytest.mark.parametrize("alias", ["UTF-8", "utf8", "Utf_8"])
def test_the_host_codec_check_reads_aliases_as_the_same_codec(
    alias: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: alias)
    assert host_prefers(PINNED_CODEC) is True, alias


@pytest.mark.parametrize("alias", ["cp936", "GBK", "latin-1"])
def test_a_non_utf8_host_is_not_mistaken_for_utf8(
    alias: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: alias)
    assert host_prefers(PINNED_CODEC) is False, alias


def test_every_host_shaped_leg_skips_under_an_aliased_utf8_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run 40714443058, reproduced: the host says `UTF-8` and all three decline.

    This is the leg that would have caught that run. Each host-shaped leg is
    called under the CI spelling; each must raise pytest's skip, not an
    assertion. `_spawn_bytes` is scripted here because this leg is about the
    skip decision — the real children above already prove the bytes.
    """
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "UTF-8")
    monkeypatch.setitem(
        globals(), "_spawn_bytes", lambda payload, codec: payload.encode(codec)
    )
    for leg in (
        test_the_payload_really_is_illegal_in_the_host_codec,
        test_the_old_shape_loses_the_output_and_the_new_one_does_not,
        test_strict_utf8_is_the_same_trap_in_the_other_direction,
    ):
        with pytest.raises(pytest.skip.Exception) as skipped:
            leg()
        assert "host prefers" in str(skipped.value), (
            f"{leg.__name__} skipped for a different reason: {skipped.value}"
        )


def test_the_real_utf8_plane_is_recognised_by_the_shared_helper() -> None:
    """The CI plane in a real interpreter, not a patched one.

    `PYTHONUTF8=1` is the switch that changes
    `locale.getpreferredencoding` without a system locale (measured: `'utf-8'`
    with it, `'cp936'` without). The child imports the helper, not this gate:
    the gate pulls `craft.adapters` and, through it, elasticsearch and the
    provider stack (26.7s of cumulative import time measured here), and a
    child *pytest* would rebuild the whole session on top of that. What this
    leg adds is the one thing the in-process legs cannot say — that a real
    UTF-8 interpreter's own answer is the answer the helper recognises.
    """
    code = (
        "import locale\n"
        "from tests._host_codec import host_prefers\n"
        "host = locale.getpreferredencoding(False)\n"
        "assert host_prefers('utf-8'), host\n"
        "print('utf8 plane:', host, 'is utf-8')\n"
    )
    env = dict(os.environ)
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        timeout=120,
        check=False,
    )
    output = proc.stdout.decode("utf-8", errors="replace") + proc.stderr.decode(
        "utf-8", errors="replace"
    )
    assert proc.returncode == 0, f"the UTF-8 plane failed:\n{output[-3000:]}"
    assert "utf8 plane: utf-8 is utf-8" in output, output[-3000:]


def test_the_lane_keeps_no_private_decoder_anymore() -> None:
    """#513's dedup, asserted rather than narrated.

    Three `_as_text` copies became one shared decoder. The census in
    `test_timeout_partial_output.py` trusts the registered name, so this is the
    half that keeps a fourth private copy from hiding behind that trust.
    """
    offenders: list[str] = []
    for path in sorted((REPO / "craft").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_as_text":
                offenders.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    assert offenders == [], f"a private decoder is back: {offenders}"
