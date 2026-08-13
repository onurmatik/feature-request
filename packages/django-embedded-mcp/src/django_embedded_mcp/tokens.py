"""Digest-only bearer verifier adapter for MCP SDK 2.0."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from asgiref.sync import sync_to_async
from mcp.server.auth.provider import AccessToken, TokenVerifier

from .oauth import credential_digest
from .resource import canonical_resource_equal


class DigestTokenVerifier(TokenVerifier):
    def __init__(
        self,
        *,
        resource: str,
        issuer: str,
        allowed_scopes: Iterable[str],
        record_resolver: Callable[[str], Any | None],
        verified_callback: Callable[[Any], None] | None = None,
        minimum_token_length: int = 32,
    ):
        self.resource = resource
        self.issuer = issuer
        self.allowed_scopes = frozenset(allowed_scopes)
        self.record_resolver = record_resolver
        self.verified_callback = verified_callback
        self.minimum_token_length = minimum_token_length

    async def verify_token(self, token: str) -> AccessToken | None:
        return await sync_to_async(self.verify_token_sync, thread_sensitive=True)(token)

    def verify_token_sync(self, token: str) -> AccessToken | None:
        if not isinstance(token, str) or len(token) < self.minimum_token_length or token.startswith("fr_"):
            return None
        record = self.record_resolver(credential_digest(token))
        if record is None or not record.is_valid():
            return None
        resource = getattr(record, "resource", "")
        if isinstance(resource, list):
            if len(resource) != 1:
                return None
            resource = resource[0]
        if not canonical_resource_equal(resource, self.resource):
            return None
        scopes = str(getattr(record, "scope", "")).split()
        if not scopes or len(scopes) != len(set(scopes)) or not set(scopes).issubset(self.allowed_scopes):
            return None
        application = getattr(record, "application", None)
        user = getattr(record, "user", None)
        if application is None or user is None or not user.is_active or not application.is_active:
            return None
        if self.verified_callback is not None:
            self.verified_callback(record)
        return AccessToken(
            token=token,
            client_id=str(application.client_id),
            scopes=scopes,
            expires_at=int(record.expires_at.timestamp()),
            resource=self.resource,
            subject=str(user.pk),
            claims={"iss": self.issuer, "aud": self.resource},
        )
