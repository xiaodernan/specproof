"""GitHub App authentication + Check Runs API (P5, spec section 13).

A verification job created from a pull_request webhook gets a Check Run
("specproof/verify") that follows the job lifecycle:

    webhook            -> create check run (in_progress, queued summary)
    worker terminal    -> update check run (completed, success/failure)
    CLI RELEASE        -> publish the final certificate state directly

GitHub App authentication is the two-step GitHub flow:
1. Build a short-lived RS256 JWT (iss = app id), signed with the app
   private key from the environment.
2. Exchange it for an installation access token (60 min TTL, cached).

Everything here is fail-closed and best-effort at the call sites: without
GITHUB_APP_ID / GITHUB_APP_PRIVATE_KEY(_FILE) / GITHUB_APP_INSTALLATION_ID
no client is constructed and callers skip GitHub publishing with a warning
— a missing optional integration must never break a verification.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

CHECK_RUN_NAME = "specproof/verify"
_JWT_TTL_SECONDS = 540  # GitHub caps app JWTs at 10 minutes.
_TOKEN_CACHE_SECONDS = 45 * 60  # installation tokens live 60 minutes.


class GitHubAppConfigError(Exception):
    """Raised when GitHub App credentials are missing or invalid."""


class GitHubApiError(Exception):
    """Non-2xx response from the GitHub REST API."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"GitHub API {status_code}: {message}")
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubAppConfig:
    """Immutable snapshot of the GitHub App identity."""

    app_id: int
    private_key_pem: str
    installation_id: int

    @classmethod
    def from_env(cls) -> GitHubAppConfig | None:
        """Load the app identity from the environment.

        Returns None when nothing is configured (callers skip GitHub
        publishing). Raises GitHubAppConfigError on PARTIAL configuration:
        a half-configured app must be loud, never silently half-published.
        """
        app_id_raw = os.getenv("GITHUB_APP_ID", "")
        install_raw = os.getenv("GITHUB_APP_INSTALLATION_ID", "")
        key = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
        key_file = os.getenv("GITHUB_APP_PRIVATE_KEY_FILE", "")
        if not (app_id_raw or install_raw or key or key_file):
            return None
        missing = [
            name
            for name, value in (
                ("GITHUB_APP_ID", app_id_raw),
                ("GITHUB_APP_INSTALLATION_ID", install_raw),
            )
            if not value
        ]
        if not (key or key_file):
            missing.append("GITHUB_APP_PRIVATE_KEY(_FILE)")
        if missing:
            raise GitHubAppConfigError(
                "incomplete GitHub App config, missing: " + ", ".join(missing)
            )
        pem = key
        if not pem and key_file:
            pem = Path(key_file).read_text(encoding="utf-8")
        try:
            return cls(
                app_id=int(app_id_raw),
                private_key_pem=pem,
                installation_id=int(install_raw),
            )
        except (ValueError, OSError) as exc:
            raise GitHubAppConfigError(
                f"invalid GitHub App config: {exc}"
            ) from exc


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def build_app_jwt(
    app_id: int, private_key_pem: str, now: int | None = None
) -> str:
    """Build the short-lived RS256 JWT the GitHub App authenticates with."""
    issued_at = now if now is not None else int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iat": issued_at,
        "exp": issued_at + _JWT_TTL_SECONDS,
        "iss": str(app_id),
    }
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode()
    key = serialization.load_pem_private_key(
        private_key_pem.encode(), password=None
    )
    if not isinstance(key, rsa.RSAPrivateKey):
        raise GitHubAppConfigError(
            "GitHub App private key must be an RSA key (RS256 JWT)"
        )
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return ".".join([*segments, _b64url(signature)])


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def conclusion_for_verdict(verdict: str) -> str:
    """Map a terminal job state to a Check Run conclusion.

    BLOCKED carries findings — from GitHub's merge-protection perspective
    that is a failed check (it should block merge until reviewed).
    """
    return {
        "VERIFIED": "success",
        "BLOCKED": "failure",
        "FAILED": "failure",
        "CANCELLED": "neutral",
        "STALE": "neutral",
        "ERROR": "neutral",
    }.get(verdict, "neutral")


def check_summary_text(verdict: str, summary: dict[str, Any]) -> str:
    """Markdown Check Run output summarizing a finished job."""
    lines = [f"**Verdict:** {verdict}", ""]
    lines.append(
        f"Contracts: {summary.get('contracts_total', 0)} total — "
        f"{summary.get('matrix_passed', 0)} passed, "
        f"{summary.get('matrix_failed', 0)} failed, "
        f"{summary.get('matrix_unverified', 0)} unverified."
    )
    findings = summary.get("findings", [])
    if findings:
        lines.append("")
        lines.append("**Findings:**")
        for finding in findings:
            lines.append(
                f"- [{finding.get('severity', '?')}] "
                f"{finding.get('contract_id', '?')}: "
                f"{(finding.get('description') or '')[:200]}"
            )
    capsules = summary.get("capsules", [])
    if capsules:
        lines.append("")
        lines.append(f"**Capsules:** {len(capsules)}")
    return "\n".join(lines)


class GitHubAppClient:
    """Minimal GitHub App client for the Check Runs API.

    The transport argument accepts an httpx transport (tests inject
    httpx.MockTransport); production uses the default transport with
    timeouts on every call.
    """

    def __init__(
        self,
        config: GitHubAppConfig,
        transport: httpx.BaseTransport | None = None,
        base_url: str = "https://api.github.com",
        timeout: float = 20.0,
    ) -> None:
        self._config = config
        self._http = httpx.Client(
            transport=transport,
            base_url=base_url,
            timeout=timeout,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        self._installation_token: str | None = None
        self._token_fetched_at = 0.0

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> GitHubAppClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            raise GitHubApiError(resp.status_code, resp.text[:300])

    def get_installation_token(self) -> str:
        """Exchange the app JWT for an installation token (cached)."""
        now = time.time()
        if (
            self._installation_token
            and now - self._token_fetched_at < _TOKEN_CACHE_SECONDS
        ):
            return self._installation_token
        jwt = build_app_jwt(
            self._config.app_id, self._config.private_key_pem
        )
        resp = self._http.post(
            f"/app/installations/{self._config.installation_id}/access_tokens",
            headers={"Authorization": "Bearer " + jwt},
        )
        self._raise_for_status(resp)
        self._installation_token = str(resp.json()["token"])
        self._token_fetched_at = now
        return self._installation_token

    def _api_headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + self.get_installation_token()}

    def create_check_run(
        self,
        owner: str,
        repo: str,
        head_sha: str,
        title: str,
        summary: str,
        details_url: str = "",
    ) -> dict[str, Any]:
        """Create the specproof/verify Check Run for a job."""
        body: dict[str, Any] = {
            "name": CHECK_RUN_NAME,
            "head_sha": head_sha,
            "status": "in_progress",
            "started_at": _iso_now(),
            "output": {"title": title, "summary": summary},
        }
        if details_url:
            body["details_url"] = details_url
        resp = self._http.post(
            f"/repos/{owner}/{repo}/check-runs",
            json=body,
            headers=self._api_headers(),
        )
        self._raise_for_status(resp)
        return dict(resp.json())

    def update_check_run(
        self,
        check_run_id: int,
        owner: str,
        repo: str,
        conclusion: str,
        title: str,
        summary: str,
        details_url: str = "",
    ) -> dict[str, Any]:
        """Complete the Check Run with a terminal conclusion."""
        body: dict[str, Any] = {
            "name": CHECK_RUN_NAME,
            "status": "completed",
            "conclusion": conclusion,
            "completed_at": _iso_now(),
            "output": {"title": title, "summary": summary},
        }
        if details_url:
            body["details_url"] = details_url
        resp = self._http.patch(
            f"/repos/{owner}/{repo}/check-runs/{check_run_id}",
            json=body,
            headers=self._api_headers(),
        )
        self._raise_for_status(resp)
        return dict(resp.json())


def github_app_client_from_env() -> GitHubAppClient | None:
    """Construct a client when GitHub App credentials are configured.

    Returns None when absent; raises GitHubAppConfigError on partial
    configuration (callers treat both as "skip publishing" but log the
    misconfiguration loudly).
    """
    config = GitHubAppConfig.from_env()
    return GitHubAppClient(config) if config else None
