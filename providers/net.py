"""Unified outbound HTTP helper for providers (§14 统一网络客户端+日志脱敏).

One construction point for the HTTP clients the shipped packages make, plus a
redacting formatter: request/response/error summaries pass through
providers.redaction before they reach a log line, so URL credentials or
token-like spans can never leak through provider logging.

Proxy environment (#602). httpx reads ``HTTP_PROXY``/``NO_PROXY`` itself while
building a plain client, and a host that spells an IPv6 bypass entry with
brackets — ``NO_PROXY=[::1]``, the form curl and browsers accept — makes that
builder raise ``httpx.InvalidURL: Invalid port: ':1]'`` before a single request
is sent. The shipped client sites died that way on such a host while CI, which
has no proxy environment at all, stayed green. ``outbound_client`` and
``outbound_async_client`` therefore read the proxy environment here, repair
that one spelling, and pass httpx the result as explicit mounts, so a bracketed
literal bypasses instead of crashing the process. Upstream has no release that
fixes the builder (encode/httpx#3221 is still open at 0.28.1), so
``proxy_mounts_for`` restates its rule, and a differential leg in
``tests/unit/test_outbound_proxy_env_survives_a_bracketed_ipv6.py`` holds it
equal to ``httpx._utils.get_environment_proxies`` on every entry form both can
read.
"""
from __future__ import annotations

import ipaddress
import typing
from urllib.request import getproxies

import httpx

from providers.redaction import redact_text

DEFAULT_TIMEOUT = 30.0

#: The proxy knobs httpx reads, in the order it gives them precedence.
PROXY_SCHEMES = ("http", "https", "all")


class UnusableProxyEnv(httpx.InvalidURL):
    """The proxy environment named a target that cannot be routed.

    Derived from ``httpx.InvalidURL`` so a caller that already copes with the
    library's own parse refusal still copes. What it adds is the message: the
    knob is named and the entry it carried is quoted, where httpx reported only
    ``Invalid port: ':1]'`` about a string the operator never wrote that way.
    """


def _is_ipv4(text: str) -> bool:
    try:
        ipaddress.IPv4Address(text.split("/")[0])
    except ValueError:
        return False
    return True


def _is_ipv6(text: str) -> bool:
    try:
        ipaddress.IPv6Address(text.split("/")[0])
    except ValueError:
        return False
    return True


def bracket_repair(entry: str) -> str:
    """``"[::1]"`` -> ``"::1"``; every other spelling is returned unchanged.

    httpx classifies a ``NO_PROXY`` entry as an IPv4, IPv6, localhost or name
    literal before it builds the bypass pattern, and its classifier calls
    ``ipaddress.IPv6Address`` on the entry as written — brackets included. A
    bracketed literal therefore classifies as a name and reaches the pattern
    builder as ``all://*[::1]``, where the ``:1]`` tail parses as a port.
    """
    if entry.startswith("[") and entry.endswith("]"):
        inner = entry[1:-1]
        if _is_ipv6(inner):
            return inner
    return entry


def proxy_pattern_for(entry: str) -> str:
    """The mount key httpx builds for one ``NO_PROXY`` entry.

    Kept as a separate function because the differential leg compares it,
    entry by entry, against what httpx's own builder produces.
    """
    if "://" in entry:
        return entry
    if _is_ipv4(entry):
        return f"all://{entry}"
    if _is_ipv6(entry):
        return f"all://[{entry}]"
    if entry.lower() == "localhost":
        return f"all://{entry}"
    return f"all://*{entry}"


def _routable(text: str, source: str) -> str:
    try:
        httpx.URL(text)
    except httpx.InvalidURL as exc:
        raise UnusableProxyEnv(
            f"{source} is not a URL httpx can route: {text!r} ({exc})"
        ) from exc
    return text


def proxy_mounts_for(proxy_info: typing.Mapping[str, str]) -> dict[str, str | None]:
    """Explicit httpx mounts for one proxy environment, brackets repaired.

    ``proxy_info`` is what ``urllib.request.getproxies()`` returns: ``http``,
    ``https`` and ``all`` carry proxy targets, ``no`` a comma-separated bypass
    list. A mount value of ``None`` means "never proxy this target", which is
    how httpx spells a ``NO_PROXY`` entry; an entry no repair can explain
    raises :class:`UnusableProxyEnv` rather than being dropped, because a
    dropped bypass entry would send loopback traffic through the proxy.
    """
    mounts: dict[str, str | None] = {}
    for scheme in PROXY_SCHEMES:
        value = proxy_info.get(scheme)
        if value:
            target = value if "://" in value else f"http://{value}"
            mounts[f"{scheme}://"] = _routable(target, f"{scheme.upper()}_PROXY")
    for raw in proxy_info.get("no", "").split(","):
        entry = raw.strip()
        if not entry:
            continue
        if entry == "*":
            # httpx's documented fate for "*": no proxy for anything.
            return {}
        pattern = proxy_pattern_for(bracket_repair(entry))
        mounts[_routable(pattern, f"NO_PROXY entry {entry!r}")] = None
    return mounts


def environment_proxy_mounts() -> dict[str, str | None]:
    """``proxy_mounts_for`` over the environment this process was started with."""
    return proxy_mounts_for(getproxies())


def _sync_mounts(
    mounts: dict[str, str | None],
) -> dict[str, httpx.BaseTransport | None]:
    return {
        pattern: None if target is None else httpx.HTTPTransport(proxy=target)
        for pattern, target in mounts.items()
    }


def _async_mounts(
    mounts: dict[str, str | None],
) -> dict[str, httpx.AsyncBaseTransport | None]:
    return {
        pattern: None if target is None else httpx.AsyncHTTPTransport(proxy=target)
        for pattern, target in mounts.items()
    }


def outbound_client(
    *,
    timeout: float | httpx.Timeout | None = None,
    transport: httpx.BaseTransport | None = None,
    base_url: httpx.URL | str = "",
    headers: typing.Mapping[str, str] | None = None,
) -> httpx.Client:
    """One sync httpx client constructor for shipped code.

    A caller-supplied ``transport`` (the tests' mock) is handed through and no
    proxy mounts are read, which is what httpx itself does once a transport is
    explicit. ``trust_env`` stays True on purpose: it also governs
    ``SSL_CERT_FILE``/``SSL_CERT_DIR``, and cutting it to dodge the proxy read
    would cut the CA bundle with it. Passing an explicit default transport is
    what keeps httpx from reading the proxy environment.
    """
    kwargs: dict[str, typing.Any] = {
        "base_url": base_url,
        "headers": headers,
        "trust_env": True,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    if transport is not None:
        kwargs["transport"] = transport
    else:
        kwargs["transport"] = httpx.HTTPTransport()
        kwargs["mounts"] = _sync_mounts(environment_proxy_mounts())
    return httpx.Client(**kwargs)


def outbound_async_client(
    *,
    timeout: float | httpx.Timeout | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    base_url: httpx.URL | str = "",
    headers: typing.Mapping[str, str] | None = None,
) -> httpx.AsyncClient:
    """The async twin of :func:`outbound_client`, with the same proxy repair."""
    kwargs: dict[str, typing.Any] = {
        "base_url": base_url,
        "headers": headers,
        "trust_env": True,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    if transport is not None:
        kwargs["transport"] = transport
    else:
        kwargs["transport"] = httpx.AsyncHTTPTransport()
        kwargs["mounts"] = _async_mounts(environment_proxy_mounts())
    return httpx.AsyncClient(**kwargs)


def make_async_client(
    timeout: float | None = None,
) -> httpx.AsyncClient:
    """One async client constructor for provider code.

    timeout applies to connect/read/write/pool (httpx semantics). The
    default (30.0s) matches the historical per-check probe timeout.
    """
    effective = DEFAULT_TIMEOUT if timeout is None else timeout
    return outbound_async_client(timeout=effective)


def redact_for_log(text: object, max_len: int = 500) -> str:
    """Redacting formatter: secret-like spans scrubbed, then bounded.

    Returns the redacted string; the returned text is safe to embed in
    log lines. Long payloads are truncated with an ellipsis marker.
    """
    redacted, _count = redact_text(str(text))
    if len(redacted) > max_len:
        return redacted[:max_len] + "\u2026"
    return redacted
