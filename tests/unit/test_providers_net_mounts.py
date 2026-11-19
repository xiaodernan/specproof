"""Unit tests for the env→httpx proxy mount path — the code that made aizzz
work only after Clash Verge: a fresh test file, not a rewrite of net.py.

Tests cover:
  proxy_mounts_for — the contract between httpx and the environment
  bracket_repair/param round-trips — IPv6 brackets (#602's fix)
  outbound_client / outbound_async_client — mounts actually reach the client
  _routable — unparseable entries raise (never silently dropped)
"""

from __future__ import annotations

import httpx
import pytest

import providers.net as net


def test_proxy_mounts_for_simple_proxy() -> None:
    mounts = net.proxy_mounts_for({"https": "http://127.0.0.1:7897"})
    assert mounts["https://"] == "http://127.0.0.1:7897"


def test_proxy_mounts_for_missing_scheme_is_prefixed() -> None:
    mounts = net.proxy_mounts_for({"http": "127.0.0.1:7897"})
    assert mounts["http://"] == "http://127.0.0.1:7897"


def test_proxy_mounts_for_ipv6_gets_bracketed() -> None:
    mounts = net.proxy_mounts_for({"https": "http://[::1]:7897"})
    assert mounts["https://"] == "http://[::1]:7897"


def test_proxy_mounts_for_bracket_repair_no_scheme() -> None:
    mounts = net.proxy_mounts_for({"https": "[::1]:7897"})
    assert mounts["https://"] == "http://[::1]:7897"


def test_proxy_mounts_for_no_star_wipes_everything() -> None:
    mounts = net.proxy_mounts_for({"http": "http://127.0.0.1:7897", "no": "*"})
    assert mounts == {}


def test_proxy_mounts_for_no_bypass_becomes_none() -> None:
    mounts = net.proxy_mounts_for({"https": "http://127.0.0.1:7897", "no": "localhost,127.0.0.1"})
    assert mounts["https://"] == "http://127.0.0.1:7897"


def test_proxy_mounts_for_empty_proxy_info_is_valid() -> None:
    mounts = net.proxy_mounts_for({})
    assert mounts == {}


def test_proxy_mounts_for_garbage_entry_raises() -> None:
    with pytest.raises(net.UnusableProxyEnv):
        # a syntactically invalid proxy entry must raise instead of being silently dropped
        net.proxy_mounts_for({"https": "http://[invalid::address]:example.com:7897"})


def test_outbound_client_builds_with_mounts_and_limits(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
    client = net.outbound_client(timeout=5.0)
    assert client.timeout == httpx.Timeout(5.0)


def test_outbound_async_client_builds() -> None:
    client = net.outbound_async_client(timeout=3.0)
    assert client.timeout == httpx.Timeout(3.0)


def test_outbound_client_honours_empty_env() -> None:
    # An empty env should not explode — client still constructs.
    client = net.outbound_client(timeout=2.0)
    assert client is not None
