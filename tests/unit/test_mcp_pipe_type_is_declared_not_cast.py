"""#491 — the MCP transport's pipe type is declared, not cast.

Measured cause: the repository's type check went red **with no change to the
repository**. `python -m mypy .` — CI's `lint-type` job, and the suite leg
`tests/unit/test_the_ci_type_check_is_a_suite_leg.py` runs over the same bytes —
reported:

    mcp/client.py:191: error: Returning Any from function declared to return "str"

The read site took the pipe's type from whatever the stub gives
`Popen.stdout`. That stub does not carry the class's own type argument: the
handle is annotated `subprocess.Popen[str]`, yet the attribute arrives as
`IO[Any] | None`, so `readline()` hands back a bare `Any` and the declaration
`-> str` is no longer checked at all.

The claim this file closes: the pipe's text type is **declared** where the pipe
is used, so the reader's type does not depend on which shape the stub ships.
The three spellings this site has taken, against the two stub shapes it has
met (measured, `.scratch/m491_stub_shape_matrix.py`; the stub shapes are
`Popen.stdout: IO[AnyStr] | None` and `Popen.stdout: IO[Any] | None`):

    spelling         stub carries the arg   stub does not
    no declaration   green                   red
    cast             red                     green
    declaration      green                   green

A cast cannot carry the claim: it is redundant exactly when the stub already
carries the type and needed exactly when the stub does not — which is why this
site has been spelled three ways and the type check was red in one of them each
time. A declaration is the same under either shape.

So the legs below read the *declaration* out of the shipped source — the shape
that holds regardless of the stub — and check the one live thing that depends
on the stub of the day: that the file as shipped still type-checks.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLIENT = REPO / "mcp" / "client.py"

#: The transport whose pipes are read and written. Its `recv()` is the site the
#: red named; `send()` is the same contract on the other end of the pipe, and
#: it was carrying the same untyped read (`proc.stdin.write(...)` accepted an
#: `Any` without a word).
_TRANSPORT = "StdioTransport"

#: One file, one type check. The whole-repository leg lives in
#: `test_the_ci_type_check_is_a_suite_leg.py`; this one says whether *this*
#: file is the reason the type check is red, which is the question a reader of
#: this file has.
_TIMEOUT = 300.0


def _source() -> ast.Module:
    return ast.parse(CLIENT.read_text(encoding="utf-8"))


def _transport(tree: ast.Module) -> ast.ClassDef:
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == _TRANSPORT
    ]
    assert len(found) == 1, (
        f"{CLIENT.relative_to(REPO).as_posix()} carries {len(found)} classes named "
        f"{_TRANSPORT!r}; this file reads one of them, so re-aim it"
    )
    return found[0]


def _methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)
    }


def _io_argument(annotation: ast.expr) -> str | None:
    """The type argument of the ``IO[...]`` in an annotation, if it carries one."""
    for node in ast.walk(annotation):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "IO"
        ):
            return ast.unparse(node.slice)
    return None


def _declared_pipe(cls: ast.ClassDef, method_name: str, name: str) -> str | None:
    """The type argument the method declares for ``name``, if it declares one."""
    methods = _methods(cls)
    assert method_name in methods, (
        f"{_TRANSPORT} has no {method_name!r}; this file reads the pipe sites of "
        "that class, so re-aim it"
    )
    for node in ast.walk(methods[method_name]):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return _io_argument(node.annotation)
    return None


def _handle_argument(cls: ast.ClassDef) -> str | None:
    """The type argument the handle is annotated with, e.g. ``Popen[str]``."""
    methods = _methods(cls)
    for node in ast.walk(methods["__init__"]):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Attribute)
            and node.target.attr == "_proc"
        ):
            annotation = node.annotation
            if isinstance(annotation, ast.Subscript):
                return ast.unparse(annotation.slice)
    return None


def _popen_call(cls: ast.ClassDef) -> ast.Call:
    methods = _methods(cls)
    calls = [
        node
        for node in ast.walk(methods["__init__"])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Popen"
    ]
    assert len(calls) == 1, (
        f"{_TRANSPORT}.__init__ makes {len(calls)} Popen calls; this file reads the "
        "construction that warrants the pipe's type, so re-aim it"
    )
    return calls[0]


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _casts_in(cls: ast.ClassDef) -> list[str]:
    """Every ``cast(...)`` call inside the class, as source text."""
    found: list[str] = []
    for node in ast.walk(cls):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "cast"
        ):
            found.append(ast.unparse(node))
    return found


# ── the declaration is there ──────────────────────────────────────────


def test_the_read_site_declares_the_pipe_type() -> None:
    tree = _source()
    cls = _transport(tree)
    declared = _declared_pipe(cls, "recv", "stdout")
    assert declared is not None, (
        f"{CLIENT.relative_to(REPO).as_posix()} does not declare a type for the "
        "pipe it reads. The type the reader gets must come from the file, not "
        "from whatever the stub says about `Popen.stdout` — the two have shipped "
        "in different shapes and the read site was red in one of them each time."
    )


def test_the_write_site_declares_the_pipe_type_too() -> None:
    tree = _source()
    cls = _transport(tree)
    declared = _declared_pipe(cls, "send", "stdin")
    assert declared is not None, (
        "the pipe the transport writes to carries no declared type either, so "
        "`stdin.write(...)` accepts whatever the stub hands it"
    )


def test_the_read_site_does_not_cast_the_pipe() -> None:
    tree = _source()
    cls = _transport(tree)
    casts = _casts_in(cls)
    assert not casts, (
        f"{_TRANSPORT} casts: {casts}. A cast is redundant exactly when the stub "
        "already carries the type and needed exactly when it does not, so it is "
        "the spelling that breaks whenever the stub moves."
    )


# ── the declaration is the one the construction warrants ──────────────


def test_the_declared_type_agrees_with_the_handles_type_argument() -> None:
    tree = _source()
    cls = _transport(tree)
    handle = _handle_argument(cls)
    assert handle is not None, (
        f"{_TRANSPORT} no longer annotates its handle, so the pipe's declared "
        "type has nothing to agree with"
    )
    for method_name, name in (("recv", "stdout"), ("send", "stdin")):
        declared = _declared_pipe(cls, method_name, name)
        assert declared == handle, (
            f"{method_name} declares the pipe as IO[{declared}] but the handle is "
            f"annotated Popen[{handle}]: the two spellings of the same contract "
            "have drifted apart"
        )


def test_the_construction_warrants_a_text_pipe() -> None:
    # Text mode is what the declared type rests on, and the subprocess contract
    # says the pipe is opened in text mode when `text` is true or when an
    # encoding or errors handler is given — the pipe is text whenever any of
    # those three is set. The leg asks for that, not for one particular
    # spelling of it: dropping `text=True` while keeping `encoding=` leaves a
    # text pipe and must not be a red.
    tree = _source()
    cls = _transport(tree)
    call = _popen_call(cls)
    text = _keyword(call, "text")
    encoding = _keyword(call, "encoding")
    errors = _keyword(call, "errors")
    requests_text = (
        text is not None
        and ast.unparse(text) == "True"
        or encoding is not None
        and ast.unparse(encoding) != "None"
        or errors is not None
        and ast.unparse(errors) != "None"
    )
    assert requests_text, (
        f"{_TRANSPORT} spawns its server with neither `text=True` nor an "
        "encoding nor an errors handler, so the pipe is binary: the declared "
        "text type would be a claim the construction does not keep"
    )


def test_the_declared_pipe_type_is_optional_like_the_stub_says() -> None:
    # The declared type has to keep the pipe's own nullability: the read site
    # refuses a missing pipe, and that refusal is a branch the type must keep.
    tree = _source()
    cls = _transport(tree)
    methods = _methods(cls)
    for method_name, name in (("recv", "stdout"), ("send", "stdin")):
        annotations = [
            node
            for node in ast.walk(methods[method_name])
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ]
        assert annotations, f"{method_name} declares no type for {name}"
        rendered = ast.unparse(annotations[0].annotation)
        assert rendered.endswith("| None"), (
            f"{method_name}'s {name} is declared as {rendered!r}: the pipe can be "
            "absent, and the declaration has to say so"
        )


# ── and the shipped file still type-checks ────────────────────────────


def test_the_shipped_file_type_checks_under_the_shipped_config() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", str(CLIENT)],
        cwd=REPO,
        capture_output=True,
        timeout=_TIMEOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, (
        f"{CLIENT.relative_to(REPO).as_posix()} does not type-check:\n"
        f"{proc.stdout or ''}{proc.stderr or ''}"
    )
