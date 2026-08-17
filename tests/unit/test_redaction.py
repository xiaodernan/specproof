"""P0-A3 unit tests — secret redaction before model transmission."""

from providers.redaction import redact_text


def test_redacts_llm_key():
    text = "config: sk-abcdefghijklmnopqrstuvwxyz123456789"
    out, count = redact_text(text)
    assert "sk-" not in out
    assert "[REDACTED:llm_api_key]" in out
    assert count == 1


def test_redacts_github_tokens():
    text = "token=ghp_" + "a" * 36 + " pat=github_pat_" + "b" * 22
    out, count = redact_text(text)
    assert "ghp_" not in out
    assert "github_pat_" not in out
    assert count == 2


def test_redacts_private_key_block():
    text = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIabc...\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    out, count = redact_text(text)
    assert "PRIVATE KEY" not in out
    assert count == 1


def test_redacts_jdbc_credentials():
    text = "url=jdbc:mysql://user:secretpass@db.example:3306/db"
    out, count = redact_text(text)
    assert "secretpass" not in out
    assert count == 1


def test_redacts_bearer_token():
    text = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz12345"
    out, count = redact_text(text)
    assert "Bearer abc" not in out
    assert count == 1


def test_clean_text_untouched():
    text = "All API endpoints must require authentication."
    out, count = redact_text(text)
    assert out == text
    assert count == 0


def test_empty_text():
    out, count = redact_text("")
    assert out == ""
    assert count == 0
