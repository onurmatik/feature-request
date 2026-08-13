"""Stable configuration seam for MCP SDK 2.0."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings


def build_mcp_auth_settings(
    *, issuer_url: str, resource_server_url: str, required_scopes: Iterable[str]
) -> AuthSettings:
    return AuthSettings(
        issuer_url=issuer_url,
        resource_server_url=resource_server_url,
        required_scopes=list(required_scopes),
    )


def build_transport_security_settings(
    *,
    resource_url: str,
    allowed_origins: Iterable[str],
    production: bool,
    extra_hosts: Iterable[str] = (),
) -> TransportSecuritySettings:
    parsed = urlsplit(resource_url)
    origins = list(dict.fromkeys(allowed_origins))
    if not parsed.netloc:
        raise ValueError("MCP resource URL must have an authority.")
    if not origins:
        raise ValueError("MCP allowed origins must not be empty.")
    if production and "*" in origins:
        raise ValueError("Production MCP CORS must use explicit origins.")
    allowed_hosts = list(dict.fromkeys([parsed.netloc, *extra_hosts]))
    if any(not isinstance(host, str) or not host for host in allowed_hosts):
        raise ValueError("MCP allowed hosts must be non-empty strings.")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=origins,
    )
