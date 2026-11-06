"""#602 — a host that writes ``NO_PROXY=[::1]`` must not lose every outbound client.

Measured basis. httpx builds its proxy mounts from the environment while the
client is being constructed, and its classifier calls
``ipaddress.IPv6Address`` on a ``NO_PROXY`` entry *as written*. Brackets are not
part of an IPv6 literal to that call, so the entry classifies as a name and
reaches the mount pattern as ``all://*[::1]``, where ``:1]`` parses as a port:

    httpx.InvalidURL: Invalid port: ':1]'

That is raised by the client constructor, before a request exists, so on such a
host every shipped client dies at construction. The nine legs this file pairs
with that behaviour — seven in ``tests/unit/test_notify_connector.py``, two in
``tests/unit/test_providers_net.py`` — were red on the Windows workstation and
green in CI, because CI's runner carries no proxy environment at all. A gate
that only passes where the environment is empty would prove nothing, so every
leg here pins its own proxy environment instead of trusting the host's.

Why the repair lives here rather than in one of three other places:

* **Rewriting ``os.environ`` around the construction** was measured first and
  rejected: on Windows ``no_proxy`` and ``NO_PROXY`` are one variable, so the
  restore is not faithful (a probe reported ``env restored byte-for-byte:
  False``), and any child process spawned during the window inherits a
  ``NO_PROXY`` the operator never set.
* **``trust_env=False``** suppresses the proxy read, but the same flag also
  governs ``SSL_CERT_FILE``/``SSL_CERT_DIR``. Measured: with a bogus
  ``SSL_CERT_FILE``, this seam still raises ``SSLError`` (the CA knob is live),
  while ``trust_env=False`` constructs silently — it would have traded a crash
  for an unverifiable trust store.
* **Dropping the entry it cannot parse** would have sent loopback traffic
  through the proxy, which is the opposite of what ``NO_PROXY`` means.
* **A version floor** is not available: encode/httpx#3221 is still open and
  0.28.1 is the release the lock resolves.

So ``providers.net`` owns the read, restates httpx's pattern rule with one
bracket repair, and hands httpx the mounts explicitly — while ``trust_env``
stays at its default and an explicit transport keeps httpx from reading the
proxy environment at all. The leg
``test_the_mount_table_matches_httpx_where_httpx_can_read_it``
holds that restatement equal to ``httpx._utils.get_environment_proxies`` (key
for key) and to httpx's own routing (target for target) on every entry form the
library can read, so the only divergence allowed is the one this batch is about.

Boundary, disclosed rather than fixed: httpx's ``URLPattern`` does not
understand CIDR notation, so ``NO_PROXY=10.0.0.0/8`` never bypasses
``10.1.2.3`` — with or without this change. The routing legs below pin that
reading so it is a documented fact instead of a surprise.
"""

from __future__ import annotations

import ast
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from providers.net import (
    UnusableProxyEnv,
    bracket_repair,
    environment_proxy_mounts,
    make_async_client,
    outbound_async_client,
    outbound_client,
    proxy_mounts_for,
    proxy_pattern_for,
)

ROOT = Path(__file__).resolve().parents[2]

#: Every spelling urllib may look for; a leg clears all of them before pinning
#: the one it means, so the host's own environment cannot leak into a reading.
PROXY_SPELLINGS = (
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
)

#: The value this batch was reported with, measured on the workstation that
#: raised the nine reds. It mixes entry shapes on purpose: a bare name, a
#: dotted-suffix name, an IPv4 host, an IPv4 network and BOTH spellings of
#: loopback, bracketed and plain.
HOST_SHAPE_NO_PROXY = "localhost,.localhost,127.0.0.1,127.0.0.0/8,[::1],::1"

PROXY_URL = "http://proxy.invalid:3128"

TARGETS = (
    "http://[::1]:3000/api",
    "http://localhost:9100/metrics",
    "http://127.0.0.1:9100/metrics",
    "http://10.1.2.3:9100/metrics",
    "http://a.internal.example/x",
    "https://example.com/y",
    "https://api.github.com/repos/x/y/check-runs",
)

#: The host-shaped environment once the bracket is repaired. ``[::1]`` and
#: ``::1`` are one mount because the repair folds them onto the same pattern,
#: which is the point. The ``10.1.2.3`` line is httpx's missing CIDR support
#: (module docstring), not a regression this batch introduces or hides.
HOST_SHAPE_MOUNTS = {
    "all://localhost": "bypass",
    "all://*.localhost": "bypass",
    "all://127.0.0.1": "bypass",
    "all://127.0.0.0/8": "bypass",
    "all://[::1]": "bypass",
}

HOST_SHAPE_ROUTING = {
    "http://[::1]:3000/api": "direct",
    "http://localhost:9100/metrics": "direct",
    "http://127.0.0.1:9100/metrics": "direct",
    "http://10.1.2.3:9100/metrics": "proxy",
    "http://a.internal.example/x": "proxy",
    "https://example.com/y": "direct",
    "https://api.github.com/repos/x/y/check-runs": "direct",
}


def _pin_env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    """Clear every proxy spelling, then set only the ones this case names."""
    for name in PROXY_SPELLINGS:
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _routes(client: Any) -> dict[str, str]:
    """Which transport httpx picks per target — ``direct`` means not proxied.

    ``_transport_for_url`` is the library's own routing entry point; reading it
    is the only way to see the mount decision without sending traffic.
    """
    return {
        target: "direct"
        if client._transport_for_url(httpx.URL(target)) is client._transport
        else "proxy"
        for target in TARGETS
    }


def _mount_table(client: Any) -> dict[str, str]:
    return {
        pattern.pattern: "bypass" if transport is None else "proxy"
        for pattern, transport in client._mounts.items()
    }


def test_a_bracketed_loopback_entry_kills_a_plain_client(monkeypatch) -> None:
    """The load-bearing premise: without the seam, construction itself fails.

    When this leg goes red because httpx no longer raises, upstream has fixed
    encode/httpx#3221 and the repair in providers/net.py can be retired — that
    is the alarm this leg exists to ring.
    """
    _pin_env(monkeypatch, NO_PROXY=f"localhost,{HOST_SHAPE_NO_PROXY}")
    with pytest.raises(httpx.InvalidURL, match=r"Invalid port"):
        httpx.Client(timeout=5.0)


def test_the_seam_constructs_and_repairs_the_entry(monkeypatch) -> None:
    _pin_env(monkeypatch, NO_PROXY=HOST_SHAPE_NO_PROXY)
    client = outbound_client(timeout=5.0)
    try:
        assert _mount_table(client) == HOST_SHAPE_MOUNTS
    finally:
        client.close()


def test_a_configured_proxy_still_proxies_what_the_bypass_does_not_name(monkeypatch) -> None:
    """Repairing the crash must not quietly become "nothing is ever proxied"."""
    _pin_env(monkeypatch, HTTP_PROXY=PROXY_URL, NO_PROXY=HOST_SHAPE_NO_PROXY)
    client = outbound_client(timeout=5.0)
    try:
        assert _mount_table(client) == {"http://": "proxy", **HOST_SHAPE_MOUNTS}
        assert _routes(client) == HOST_SHAPE_ROUTING
    finally:
        client.close()


def test_the_async_twin_routes_the_same(monkeypatch) -> None:
    import asyncio

    _pin_env(monkeypatch, HTTP_PROXY=PROXY_URL, NO_PROXY=HOST_SHAPE_NO_PROXY)

    async def _read() -> tuple[dict[str, str], dict[str, str]]:
        client = outbound_async_client(timeout=5.0)
        try:
            return _mount_table(client), _routes(client)
        finally:
            await client.aclose()

    mounts, routes = asyncio.run(_read())
    assert mounts == {"http://": "proxy", **HOST_SHAPE_MOUNTS}
    assert routes == HOST_SHAPE_ROUTING


def test_the_provider_wrapper_survives_the_host_environment(monkeypatch) -> None:
    """``make_async_client`` is the shape two of the nine reds died on."""
    _pin_env(monkeypatch, NO_PROXY=HOST_SHAPE_NO_PROXY)
    client = make_async_client(timeout=12.5)
    assert client.timeout.read == 12.5
    assert _mount_table(client) == HOST_SHAPE_MOUNTS


@pytest.mark.parametrize("build", ["webhook", "oidc", "github_checks"])
def test_shipped_sites_construct_under_the_host_shape(monkeypatch, build: str) -> None:
    """Each converted class, with no transport to hide behind.

    Passing a transport would exempt the site: httpx stops reading the proxy
    environment the moment a transport is explicit, so a leg that injected a
    mock would prove only that the mock works.
    """
    _pin_env(monkeypatch, HTTP_PROXY=PROXY_URL, NO_PROXY=HOST_SHAPE_NO_PROXY)
    if build == "webhook":
        from integrations.notify.webhook import WebhookConnector, WebhookKind

        connector = WebhookConnector("http://127.0.0.1:9/hook", kind=WebhookKind.GENERIC)
        assert _routes(connector._client) == HOST_SHAPE_ROUTING
        connector.close()
    elif build == "oidc":
        from api.identity.oidc import OidcValidator

        validator = OidcValidator("https://issuer.invalid", "client-id")
        assert _mount_table(validator._http) == {"http://": "proxy", **HOST_SHAPE_MOUNTS}
        validator.close()
    else:
        from integrations.github_checks import GitHubAppClient, GitHubAppConfig

        config = GitHubAppConfig(app_id=1, private_key_pem="unused", installation_id=2)
        client = GitHubAppClient(config)
        assert _mount_table(client._http) == {"http://": "proxy", **HOST_SHAPE_MOUNTS}
        client.close()


@pytest.mark.parametrize(
    "no_proxy",
    [
        "localhost,::1,.internal.example,10.0.0.0/8",
        "example.com,sub.example.com,*",
        "http://[::1]:8080,.internal.example",
        "",
    ],
    ids=["plain-ipv6", "names-and-star", "scheme-entry", "empty"],
)
def test_the_mount_table_matches_httpx_where_httpx_can_read_it(
    monkeypatch, no_proxy: str
) -> None:
    """The restated rule is held to the library's own output, entry for entry.

    ``get_environment_proxies`` is private to httpx and imported here for the
    comparison only; if it ever changes shape this leg goes red and the
    restatement in providers/net.py has to be re-read against it.
    """
    from httpx._utils import get_environment_proxies

    _pin_env(monkeypatch, HTTP_PROXY=PROXY_URL, NO_PROXY=no_proxy)
    assert environment_proxy_mounts() == get_environment_proxies()

    seam = outbound_client(timeout=5.0)
    plain = httpx.Client(timeout=5.0)
    try:
        assert _routes(seam) == _routes(plain)
    finally:
        seam.close()
        plain.close()


@pytest.mark.parametrize("spelling", ["NO_PROXY", "no_proxy"])
def test_either_spelling_of_the_knob_reaches_the_repair(monkeypatch, spelling: str) -> None:
    """curl, Docker and Windows scheduled tasks do not agree on the casing."""
    _pin_env(monkeypatch, **{spelling: f"localhost,{HOST_SHAPE_NO_PROXY}"})
    mounts = environment_proxy_mounts()
    assert "all://[::1]" in mounts, f"{spelling} never reached the repair: {sorted(mounts)}"
    assert not any("*[" in pattern for pattern in mounts), f"unrepaired bracket: {sorted(mounts)}"
    outbound_client(timeout=5.0).close()


def test_an_entry_no_repair_explains_names_the_knob_and_the_entry(monkeypatch) -> None:
    """``[::1`` is not a bracketed literal; refusing beats guessing."""
    _pin_env(monkeypatch, NO_PROXY="[::1")
    with pytest.raises(UnusableProxyEnv) as raised:
        outbound_client(timeout=5.0)
    message = str(raised.value)
    assert "NO_PROXY" in message, message
    assert "'[::1'" in message, message
    assert "all://*[::1" in message, message
    # Callers that already coped with the library's own refusal still do.
    assert isinstance(raised.value, httpx.InvalidURL)


def test_an_unusable_proxy_value_names_its_own_knob(monkeypatch) -> None:
    """A proxy target nobody can route is refused, and the refusal says where.

    ``httpx.URL`` percent-encodes most garbage it is handed, so a bad host is
    not refused here — an unbalanced IPv6 literal is, and that is the shape the
    message has to explain. The contrast reading is the point: the library
    reports only the port it choked on, never the knob that carried it.
    """
    _pin_env(monkeypatch, HTTP_PROXY="http://[::1:8080")
    with pytest.raises(UnusableProxyEnv, match="HTTP_PROXY") as raised:
        outbound_client(timeout=5.0)
    message = str(raised.value)
    assert "'http://[::1:8080'" in message, message
    assert isinstance(raised.value, httpx.InvalidURL), message

    with pytest.raises(httpx.InvalidURL) as library:
        httpx.Client(timeout=5.0)
    assert "HTTP_PROXY" not in str(library.value), str(library.value)


def test_the_ssl_trust_knob_still_decides_the_store(monkeypatch, tmp_path: Path) -> None:
    """The reason the seam passes an explicit transport instead of trust_env.

    A file that is not a CA bundle has to change what httpx will trust, which is
    only observable because the seam leaves ``trust_env`` alone. The contrast
    reading shows the rejected design silently ignoring the same knob.
    """
    bogus = tmp_path / "ca-bundle.pem"
    bogus.write_text("this is not a certificate\n", encoding="utf-8")
    _pin_env(monkeypatch, SSL_CERT_FILE=str(bogus))

    with pytest.raises(Exception) as raised:
        outbound_client(timeout=5.0).close()
    assert "CERTIFICATE" in str(raised.value).upper(), str(raised.value)

    httpx.Client(timeout=5.0, trust_env=False).close()  # reaches no error


def test_construction_leaves_the_host_environment_alone(monkeypatch) -> None:
    _pin_env(monkeypatch, HTTP_PROXY=PROXY_URL, NO_PROXY=HOST_SHAPE_NO_PROXY)
    before = {name: os.environ.get(name) for name in PROXY_SPELLINGS}
    for _ in range(3):
        outbound_client(timeout=5.0).close()
    assert {name: os.environ.get(name) for name in PROXY_SPELLINGS} == before


def test_the_repair_rule_itself() -> None:
    """The two pure helpers, read straight, so a leg can fail on one rule."""
    assert bracket_repair("[::1]") == "::1"
    assert bracket_repair("[::1") == "[::1"
    assert bracket_repair("[not-an-address]") == "[not-an-address]"
    assert bracket_repair("example.com") == "example.com"
    assert proxy_pattern_for("::1") == "all://[::1]"
    assert proxy_pattern_for("10.0.0.0/8") == "all://10.0.0.0/8"
    assert proxy_pattern_for("localhost") == "all://localhost"
    assert proxy_pattern_for(".internal.example") == "all://*.internal.example"
    assert proxy_pattern_for("example.com") == "all://*example.com"
    assert proxy_pattern_for("http://[::1]:8080") == "http://[::1]:8080"
    assert proxy_mounts_for({"no": "[::1]"}) == {"all://[::1]": None}


# ── census: no shipped module builds an httpx client on its own ───────────

_CLIENT_NAMES = frozenset({"Client", "AsyncClient"})
_DIRECT_API_NAMES = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "request", "stream"}
)

#: The only function bodies allowed to build a client. Admission is structural:
#: the exempted file is whichever file declares all three of these names, so a
#: second owner module makes the owner clause disagree instead of quietly
#: widening the exemption.
_SEAM_BUILDERS = ("outbound_client", "outbound_async_client")
_SEAM_REQUIRED = ("proxy_mounts_for", "environment_proxy_mounts", *_SEAM_BUILDERS)

#: The files this batch converted. They must be inside the scan's reach: a
#: population that missed them would make the census pass by blindness.
_CONVERSION_SITES = (
    "providers/net.py",
    "retrieval/embeddings.py",
    "integrations/notify/webhook.py",
    "integrations/github_checks.py",
    "api/identity/oidc.py",
    "scripts/seed_demo.py",
)


def _shipped_python_files() -> list[Path]:
    """Tracked Python outside ``tests/``, read from the worktree.

    ``scripts/`` is not a declared package, and it builds a client all the same,
    so the population is the tracked list rather than the package globs.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return [
        ROOT / os.fsdecode(name)
        for name in listing.split(b"\0")
        if name and not os.fsdecode(name).startswith("tests/")
    ]


def _parse(path: Path) -> ast.AST | str:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        return f"{path.relative_to(ROOT)}: unreadable by the census ({exc!r})"


def _call_sites(tree: ast.AST) -> Iterator[tuple[str, int, str]]:
    """Yield ``(enclosing_function, line, described_call)`` per client build."""
    imported: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "httpx":
            for alias in node.names:
                if alias.name in _CLIENT_NAMES | _DIRECT_API_NAMES:
                    imported[alias.asname or alias.name] = alias.name

    def describe(func: ast.expr) -> str | None:
        if isinstance(func, ast.Attribute):
            holder = func.value
            if isinstance(holder, ast.Name) and holder.id == "httpx":
                if func.attr in _CLIENT_NAMES:
                    return f"httpx.{func.attr}(...)"
                if func.attr in _DIRECT_API_NAMES:
                    return f"httpx.{func.attr}(...) top-level API"
            return None
        if isinstance(func, ast.Name) and func.id in imported:
            return f"{func.id}(...) imported from httpx"
        return None

    def walk(node: ast.AST, scope: str) -> Iterator[tuple[str, int, str]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Call):
                found = describe(child.func)
                if found is not None:
                    yield scope, child.lineno, found
            inner = (
                child.name
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                else scope
            )
            yield from walk(child, inner)

    yield from walk(tree, "<module>")


def _declares(tree: ast.AST, name: str) -> bool:
    return any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name
        for node in ast.walk(tree)
    )


def test_no_shipped_module_builds_an_httpx_client_on_its_own() -> None:
    """One owner for the proxy repair, or the repair does not exist.

    A site that constructs a client directly would crash on the same host this
    batch was filed against, and CI — which has no proxy environment — can never
    see it.
    """
    files = _shipped_python_files()
    trees = {path: _parse(path) for path in files}
    parsed = {path: tree for path, tree in trees.items() if not isinstance(tree, str)}
    owners = [
        path
        for path, tree in parsed.items()
        if all(_declares(tree, name) for name in _SEAM_REQUIRED)
    ]
    assert len(owners) == 1, f"the seam must have exactly one owner module, found {owners}"

    reached = {str(path.relative_to(ROOT)).replace("\\", "/") for path in files}
    missing = [site for site in _CONVERSION_SITES if site not in reached]
    assert not missing, f"the population missed converted sites, so the census is blind: {missing}"
    assert len(files) >= len(_CONVERSION_SITES), f"population is only {len(files)} files"

    offenders = [
        f"{path.relative_to(ROOT)}:{line} {call} in {scope}()"
        for path, tree in parsed.items()
        for scope, line, call in _call_sites(tree)
        if not (path == owners[0] and scope in _SEAM_BUILDERS)
    ]
    unreadable = [tree for tree in trees.values() if isinstance(tree, str)]
    assert not (offenders or unreadable), (
        "shipped httpx clients must be built by providers.net; offenders: "
        + "; ".join([*offenders, *unreadable])
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("c = httpx.Client(timeout=5)", "charged"),
        ("c = httpx.AsyncClient()", "charged"),
        ("r = httpx.post(url, json={})", "charged"),
        ("from httpx import AsyncClient\nc = AsyncClient()", "charged"),
        ("def f() -> httpx.Client:\n    return None", "clear"),
        ("def outbound_client():\n    return httpx.Client()", "clear"),
        ("def other():\n    return httpx.Client()", "charged"),
        ("import httpx\nc = httpx.MockTransport(handler)", "clear"),
    ],
    ids=[
        "sync",
        "async",
        "top-level-api",
        "imported-name",
        "annotation-only",
        "seam-scope",
        "other-scope",
        "not-a-client",
    ],
)
def test_the_census_charges_the_shapes_it_names(source: str, expected: str) -> None:
    """The extractor fires on each spelling, and does not over-charge.

    ``def other()`` in the seam's own file is charged on purpose: owning the
    repair does not license building a client anywhere else in the module.
    """
    sites = list(_call_sites(ast.parse(source)))
    charged = [call for scope, _, call in sites if scope not in _SEAM_BUILDERS]
    if expected == "charged":
        assert charged, f"{source!r} was not charged"
    else:
        assert not charged, f"{source!r} was charged as {charged}"
