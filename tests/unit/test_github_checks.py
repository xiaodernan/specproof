"""P5 unit tests — GitHub App auth (RS256 JWT) + Check Runs API client."""

import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa

from integrations.github_checks import (
    GitHubApiError,
    GitHubAppClient,
    GitHubAppConfig,
    GitHubAppConfigError,
    build_app_jwt,
    check_summary_text,
    conclusion_for_verdict,
)

APP_ID = 12345
INSTALL_ID = 42


def _deb64(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


@pytest.fixture()
def rsa_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return key, pem


def _config(pem: str) -> GitHubAppConfig:
    return GitHubAppConfig(
        app_id=APP_ID, private_key_pem=pem, installation_id=INSTALL_ID
    )


def _clear_github_env(monkeypatch) -> None:
    for name in (
        "GITHUB_APP_ID",
        "GITHUB_APP_INSTALLATION_ID",
        "GITHUB_APP_PRIVATE_KEY",
        "GITHUB_APP_PRIVATE_KEY_FILE",
    ):
        monkeypatch.delenv(name, raising=False)


# ── JWT builder ────────────────────────────────────────────────


def test_build_app_jwt_roundtrip(rsa_key):
    key, pem = rsa_key
    token = build_app_jwt(APP_ID, pem, now=1_700_000_000)
    head_b64, payload_b64, sig_b64 = token.split(".")
    assert json.loads(_deb64(head_b64)) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(_deb64(payload_b64)) == {
        "iat": 1_700_000_000,
        "exp": 1_700_000_540,
        "iss": str(APP_ID),
    }
    key.public_key().verify(
        _deb64(sig_b64),
        f"{head_b64}.{payload_b64}".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


def test_build_app_jwt_rejects_non_rsa_key():
    key = ed25519.Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    with pytest.raises(GitHubAppConfigError):
        build_app_jwt(APP_ID, pem, now=0)


# ── Configuration ──────────────────────────────────────────────


def test_config_absent_returns_none(monkeypatch):
    _clear_github_env(monkeypatch)
    assert GitHubAppConfig.from_env() is None


def test_config_partial_raises(monkeypatch):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    with pytest.raises(GitHubAppConfigError):
        GitHubAppConfig.from_env()


def test_config_loads_private_key_file(monkeypatch, tmp_path, rsa_key):
    _clear_github_env(monkeypatch)
    key_file = tmp_path / "app-key.pem"
    key_file.write_text(rsa_key[1], encoding="utf-8")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "42")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_FILE", str(key_file))
    config = GitHubAppConfig.from_env()
    assert config is not None
    assert config.app_id == 123
    assert config.installation_id == 42
    assert "PRIVATE KEY" in config.private_key_pem


def test_config_inline_key_preferred(monkeypatch, rsa_key):
    _clear_github_env(monkeypatch)
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "42")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", rsa_key[1])
    config = GitHubAppConfig.from_env()
    assert config is not None
    assert config.private_key_pem == rsa_key[1]


# ── API client ─────────────────────────────────────────────────


def test_get_installation_token_and_cache(rsa_key):
    _, pem = rsa_key
    client = GitHubAppClient(
        _config(pem), transport=httpx.MockTransport(_token_handler)
    )
    assert client.get_installation_token() == "tok-1"
    assert client.get_installation_token() == "tok-1"
    assert _TOKEN_CALLS == 1
    client.close()


_TOKEN_CALLS = 0


def _token_handler(request: httpx.Request) -> httpx.Response:
    global _TOKEN_CALLS
    _TOKEN_CALLS += 1
    assert request.url.path == f"/app/installations/{INSTALL_ID}/access_tokens"
    auth = request.headers.get("Authorization", "")
    assert auth.startswith("Bearer ")
    _, payload_b64, _ = auth[len("Bearer "):].split(".")
    claims = json.loads(_deb64(payload_b64))
    assert claims["iss"] == str(APP_ID)
    return httpx.Response(201, json={"token": "tok-1"})


def test_create_check_run_payload(rsa_key):
    _, pem = rsa_key
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "tok"})
        body = json.loads(request.content)
        return httpx.Response(201, json={"id": 55, **body})

    client = GitHubAppClient(_config(pem), transport=httpx.MockTransport(handler))
    run = client.create_check_run(
        "acme", "repo", "sha-1", "Title", "Summary", details_url="http://dash"
    )
    assert run["id"] == 55
    create_req = seen[-1]
    assert create_req.url.path == "/repos/acme/repo/check-runs"
    assert create_req.headers["Authorization"] == "Bearer tok"
    body = json.loads(create_req.content)
    assert body["name"] == "specproof/verify"
    assert body["head_sha"] == "sha-1"
    assert body["status"] == "in_progress"
    assert body["output"] == {"title": "Title", "summary": "Summary"}
    assert body["details_url"] == "http://dash"
    client.close()


def test_update_check_run_payload(rsa_key):
    _, pem = rsa_key
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "tok"})
        body = json.loads(request.content)
        return httpx.Response(200, json={"id": 55, **body})

    client = GitHubAppClient(_config(pem), transport=httpx.MockTransport(handler))
    run = client.update_check_run(
        55, "acme", "repo", "success", "T2", "S2"
    )
    assert run["conclusion"] == "success"
    update_req = seen[-1]
    assert update_req.method == "PATCH"
    assert update_req.url.path == "/repos/acme/repo/check-runs/55"
    body = json.loads(update_req.content)
    assert body["status"] == "completed"
    assert body["conclusion"] == "success"
    assert body["completed_at"]
    assert "details_url" not in body
    client.close()


def test_api_error_raises(rsa_key):
    _, pem = rsa_key

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    client = GitHubAppClient(_config(pem), transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubApiError) as exc:
        client.get_installation_token()
    assert exc.value.status_code == 401
    client.close()


# ── Conclusion + summary helpers ───────────────────────────────


def test_conclusion_for_verdict_mapping():
    assert conclusion_for_verdict("VERIFIED") == "success"
    assert conclusion_for_verdict("BLOCKED") == "failure"
    assert conclusion_for_verdict("FAILED") == "failure"
    assert conclusion_for_verdict("CANCELLED") == "neutral"
    assert conclusion_for_verdict("NEEDS REVIEW") == "neutral"
    assert conclusion_for_verdict("UNKNOWN-ISH") == "neutral"


def test_check_summary_text_includes_findings():
    text = check_summary_text(
        "BLOCKED",
        {
            "contracts_total": 5,
            "matrix_passed": 3,
            "matrix_failed": 1,
            "matrix_unverified": 1,
            "findings": [
                {
                    "severity": "BLOCKER",
                    "contract_id": "AUTH-01",
                    "description": "auth bypass",
                }
            ],
            "capsules": ["capsule-1.zip"],
        },
    )
    assert "**Verdict:** BLOCKED" in text
    assert "Contracts: 5 total" in text
    assert "[BLOCKER] AUTH-01: auth bypass" in text
    assert "**Capsules:** 1" in text


# ── P5 Inline Findings + Fix PR (spec 6.2) ─────────────────────


def test_publish_inline_findings_payload(rsa_key):
    _, pem = rsa_key
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "tok"})
        return httpx.Response(200, json={"id": 9, "state": "COMMENTED"})

    client = GitHubAppClient(_config(pem), transport=httpx.MockTransport(handler))
    comments = [
        {"path": "src/A.java", "line": 12, "side": "RIGHT", "body": "b1"}
    ]
    review = client.publish_inline_findings(
        "acme", "repo", 42, "head-sha", comments
    )
    assert review["id"] == 9
    req = seen[-1]
    assert req.method == "POST"
    assert req.url.path == "/repos/acme/repo/pulls/42/reviews"
    body = json.loads(req.content)
    assert body["commit_id"] == "head-sha"
    assert body["event"] == "COMMENT"
    assert body["comments"] == comments
    client.close()


def test_publish_inline_findings_empty_is_noop(rsa_key):
    _, pem = rsa_key
    client = GitHubAppClient(_config(pem), transport=httpx.MockTransport(
        lambda request: httpx.Response(500)
    ))
    result = client.publish_inline_findings("a", "b", 1, "sha", [])
    assert result["submitted_empty"] is True
    client.close()


def test_create_fix_pr_payload(rsa_key):
    _, pem = rsa_key
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "tok"})
        return httpx.Response(
            201, json={"number": 77, "html_url": "https://github.com/a/b/pull/77"}
        )

    client = GitHubAppClient(_config(pem), transport=httpx.MockTransport(handler))
    pr = client.create_fix_pr(
        "acme", "repo", "main", "specproof-fix/x", "Fix title", "Fix body"
    )
    assert pr["number"] == 77
    req = seen[-1]
    assert req.url.path == "/repos/acme/repo/pulls"
    body = json.loads(req.content)
    assert body == {
        "title": "Fix title",
        "head": "specproof-fix/x",
        "base": "main",
        "body": "Fix body",
    }
    client.close()
