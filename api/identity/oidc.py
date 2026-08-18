"""OIDC: standard discovery + JWKS RS256 validation (MULTI_TENANT_DESIGN.md §1).

Flow: OIDC_ISSUER → /.well-known/openid-configuration (cached) →
jwks_uri → PyJWKClient (RS256, key cache) → PyJWT decode with strict
issuer/audience/exp checks → role claim mapping (§2 role vocabulary, least
privilege fallback 'viewer'). SAML is explicitly phase 2+.

The validator accepts an injectable httpx transport so tests drive a mock
IdP (signed RS256 tokens, expired tokens, wrong-issuer tokens) without any
network. PyJWKClient is subclassed so its JWKS fetch rides the same
transport.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from api.identity.config import oidc_client_id, oidc_role_claim
from storage.identity import ROLE_SET

logger = logging.getLogger(__name__)

_DISCOVERY_TTL_SECONDS = 600.0


class OidcError(RuntimeError):
    """Any OIDC validation / discovery failure (mapped to 401 upstream)."""


class _TransportPyJWKClient(PyJWKClient):
    """PyJWKClient whose JWKS fetch goes through the validator's transport."""

    def __init__(self, uri: str, client: httpx.Client) -> None:
        super().__init__(uri, cache_jwk_set=False)
        self._http = client

    def fetch_data(self) -> Any:
        try:
            response = self._http.get(self.uri)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise jwt.PyJWKClientConnectionError(
                f'Fail to fetch data from the url, err: "{exc}"'
            ) from exc


def _map_roles(claims: dict[str, Any]) -> frozenset[str]:
    """Role claim mapping: idp roles → SpecProof roles (§1).

    Accepts a string or a list; values may be bare ("admin") or prefixed
    ("specproof:admin"). Unknown values are dropped; when nothing maps the
    principal gets 'viewer' (least privilege) — an unknown IdP role must
    never escalate.
    """
    claim_name = oidc_role_claim()
    raw = claims.get(claim_name, [])
    if isinstance(raw, str):
        raw = [raw]
    roles: set[str] = set()
    for value in raw:
        name = str(value).strip().lower()
        if name.startswith("specproof:"):
            name = name[len("specproof:"):]
        if name in ROLE_SET:
            roles.add(name)
    if not roles:
        return frozenset({"viewer"})
    return frozenset(roles)


class OidcValidator:
    """Discovery + JWKS + RS256 id_token validation for one issuer."""

    def __init__(
        self,
        issuer: str,
        client_id: str,
        transport: httpx.BaseTransport | None = None,
        discovery_ttl: float = _DISCOVERY_TTL_SECONDS,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self._http = httpx.Client(transport=transport, timeout=10.0)
        self._discovery: dict[str, Any] | None = None
        self._discovery_at = 0.0
        self._jwks: _TransportPyJWKClient | None = None
        self._discovery_ttl = discovery_ttl

    def close(self) -> None:
        self._http.close()

    def _fetch_discovery(self) -> dict[str, Any]:
        url = f"{self.issuer}/.well-known/openid-configuration"
        try:
            response = self._http.get(url)
            response.raise_for_status()
            document = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OidcError(
                f"OIDC discovery at {self.issuer} failed: {exc}"
            ) from exc
        if not isinstance(document, dict):
            raise OidcError("OIDC discovery document is not a JSON object")
        if str(document.get("issuer", "")).rstrip("/") != self.issuer:
            raise OidcError(
                f"discovery issuer {document.get('issuer')!r} does not match "
                f"configured issuer {self.issuer!r}"
            )
        return document

    def discovery(self) -> dict[str, Any]:
        if self._discovery is None or time.time() - self._discovery_at > self._discovery_ttl:
            self._discovery = self._fetch_discovery()
            self._discovery_at = time.time()
            self._jwks = None  # jwks_uri may have rotated
        return self._discovery

    def _jwks_client(self) -> _TransportPyJWKClient:
        jwks_uri = self.discovery().get("jwks_uri")
        if not jwks_uri:
            raise OidcError("OIDC discovery document has no jwks_uri")
        if self._jwks is None:
            self._jwks = _TransportPyJWKClient(str(jwks_uri), self._http)
        return self._jwks

    def exchange_code(self, token_endpoint: str, data: dict[str, str]) -> dict[str, Any]:
        """POST the authorization-code exchange and return the JSON payload."""
        try:
            response = self._http.post(token_endpoint, data=data)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OidcError(f"token endpoint exchange failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise OidcError("token endpoint response is not a JSON object")
        return payload

    def validate(self, id_token: str, *, nonce: str | None = None) -> dict[str, Any]:
        """Verify an RS256 id_token; returns the claims or raises OidcError.

        Enforces signature (JWKS), exp, iss and aud — plus the optional
        nonce for the authorization-code flow. iat/exp/nbf come from PyJWT.
        """
        try:
            signing_key = self._jwks_client().get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
                options={"require": ["exp", "iss", "sub", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise OidcError(f"id_token validation failed: {exc}") from exc
        if nonce is not None and claims.get("nonce") != nonce:
            raise OidcError("id_token nonce mismatch")
        return claims

    def map_roles(self, claims: dict[str, Any]) -> frozenset[str]:
        return _map_roles(claims)


#: Cached validator keyed by (issuer, client_id); tests reset it.
_validator: OidcValidator | None = None
_validator_key: tuple[str, str] | None = None


def get_oidc_validator() -> OidcValidator | None:
    """The configured validator, or None when OIDC is not configured."""
    global _validator, _validator_key
    issuer = os.getenv("OIDC_ISSUER", "").strip()
    if not issuer:
        return None
    client_id = oidc_client_id()
    key = (issuer, client_id)
    if _validator is None or _validator_key != key:
        _validator = OidcValidator(issuer, client_id)
        _validator_key = key
    return _validator


def reset_oidc_validator() -> None:
    """Drop the cached validator (tests, reconfiguration)."""
    global _validator, _validator_key
    if _validator is not None:
        _validator.close()
    _validator = None
    _validator_key = None
