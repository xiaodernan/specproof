"""Unit tests for providers.net (unified client + log redaction)."""

from __future__ import annotations

import httpx

from providers.net import DEFAULT_TIMEOUT, make_async_client, redact_for_log


def test_make_async_client_uses_explicit_timeout() -> None:
    client = make_async_client(timeout=12.5)
    assert client.timeout == httpx.Timeout(12.5)


def test_make_async_client_defaults() -> None:
    client = make_async_client()
    assert client.timeout == httpx.Timeout(DEFAULT_TIMEOUT)


def test_redact_for_log_scrubs_secrets() -> None:
    text = "Authorization: Bearer sk-abcdefghijklmnop1234567890"
    out = redact_for_log(text)
    assert "sk-abcdefghijklmnop" not in out
    # The Bearer span wins (it matches first); either redaction kind proves
    # the secret span is scrubbed.
    assert "[REDACTED:" in out


def test_redact_for_log_truncates_long_text() -> None:
    out = redact_for_log("x" * 2000, max_len=100)
    assert len(out) == 101  # 100 chars + ellipsis
    assert out.endswith("\u2026")


def test_redact_for_log_handles_non_string() -> None:
    assert redact_for_log(None) == "None"
    assert redact_for_log(42) == "42"


class TestProbeRedactionWiring:
    def test_probe_errors_are_redacted(self, monkeypatch) -> None:
        import asyncio

        from providers.capability_probe import CapabilityProbe

        probe = CapabilityProbe(
            base_url="https://example.invalid/v1",
            api_key="sk-test-key-123456789012345678901234567890",
            model="deepseek-v4-pro",
        )

        async def fake_check(self):
            raise RuntimeError("leaked sk-abcdefghijklmnop1234567890 in error")

        # _check_models is called directly (outside the try): make it pass
        # so the dispatched checks actually run.
        async def models_ok(self):
            return True, ["deepseek-v4-pro"], ""

        monkeypatch.setattr(CapabilityProbe, "_check_models", models_ok)
        # Replace the 11 dispatched checks with the failing fake.
        for name in dir(CapabilityProbe):
            if name.startswith("_check_") and name != "_check_models":
                monkeypatch.setattr(CapabilityProbe, name, fake_check)

        result = asyncio.run(probe.run())
        joined = " ".join(result.errors)
        assert "sk-abcdefghijklmnop" not in joined
        assert "[REDACTED:" in joined
