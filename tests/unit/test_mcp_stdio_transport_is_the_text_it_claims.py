"""#479 — `StdioTransport`'s text-mode contract, witnessed on a real child.

`mcp/client.py::StdioTransport.recv()` declares `-> str` and returns what the pipe
hands it, and the type checker can only be told that is text by a `cast`: typeshed
gives `Popen.stdout` the type `IO[Any]` whatever the class's type parameter is. A
cast nobody can falsify is a claim, not evidence — and until this file
`StdioTransport` had **no** runtime witness at all. `test_mcp_client.py` drives
`MCPClient` over injected fakes, and the shipped transport is constructed only by
`providers/mcp_bridge.py:_default_transport_factory`, which no test reached. So the
one subprocess transport the product actually spawns was covered only from the other
side of the interface.

The legs below spawn a real child. It writes UTF-8 bytes through its own binary
buffer, so the parent can only hand back the promised text if it set
`text=True` with `encoding="utf-8"`; the machine's locale codec (cp936 on this host)
would yield mojibake or a decode error, and binary pipes would yield `bytes`. That
is the fact the `cast` stands for, checked rather than asserted.
"""
from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from mcp.client import StdioTransport

#: The reply is a token the machine's own codec cannot produce by accident.
_TEXT = "验证 骨 ok\n"

_CHILD_WRITES_UTF8 = (
    "import sys\n"
    f"sys.stdout.buffer.write({_TEXT!r}.encode('utf-8'))\n"
    "sys.stdout.buffer.flush()\n"
)
_CHILD_ECHOES_ONE_LINE = (
    "import sys\n"
    "sys.stdout.buffer.write(sys.stdin.buffer.readline())\n"
    "sys.stdout.buffer.flush()\n"
)
_CHILD_EXITS_WITHOUT_PRINTING = "import sys\nsys.exit(3)\n"


@contextmanager
def _transport(script: str) -> Iterator[StdioTransport]:
    transport = StdioTransport([sys.executable, "-c", script])
    try:
        yield transport
    finally:
        transport.close()


def test_a_real_child_line_arrives_as_text() -> None:
    with _transport(_CHILD_WRITES_UTF8) as transport:
        line = transport.recv()
    assert isinstance(line, str), (
        f"recv() handed back {type(line).__name__}: the pipe is not in text mode, "
        "so the cast in recv() is claiming a contract the constructor does not keep"
    )
    assert line == _TEXT, (
        f"the child's UTF-8 bytes did not decode as UTF-8 (got {line!r}) — "
        "the parent is decoding with something else"
    )


def test_a_line_written_by_the_client_reaches_the_child_unchanged() -> None:
    # The write half of the same contract: the child echoes the bytes it was given
    # without decoding them, so what comes back is only this string if the parent
    # encoded its side as UTF-8 too.
    with _transport(_CHILD_ECHOES_ONE_LINE) as transport:
        transport.send(_TEXT)
        try:
            answer = transport.recv()
        except UnicodeDecodeError as exc:
            pytest.fail(
                f"the child echoed our own bytes and the parent could not decode "
                f"them as UTF-8: {exc}\nso the stdin pipe is not UTF-8 either"
            )
    assert answer == _TEXT


def test_a_child_that_exits_is_an_eof_not_an_empty_line() -> None:
    # The `line == ""` sentinel is the one `recv()` reads on a dead server. It is
    # charged here because it only fires while the pipe really is text: read in
    # binary mode the same EOF compares `b"" == ""` and hands the caller an empty
    # string that `json.loads` would then blame on the protocol. The exit code the
    # refusal quotes is deliberately not pinned — the child can close its stdout
    # a moment before the OS reports it exited, and `poll()` may honestly say None.
    with (
        _transport(_CHILD_EXITS_WITHOUT_PRINTING) as transport,
        pytest.raises(EOFError) as refused,
    ):
        transport.recv()
    assert "closed stdout" in str(refused.value), str(refused.value)


def test_an_empty_command_is_refused_before_any_child_is_spawned() -> None:
    for command in ([], [""], ["python", ""]):
        with pytest.raises(ValueError, match="non-empty strings"):
            StdioTransport(command)
