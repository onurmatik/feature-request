"""Deterministic OAuth metadata builders."""

from __future__ import annotations

from collections.abc import Iterable

from .resource import validate_canonical_url


def validated_scope_catalog(scopes: Iterable[str]) -> tuple[str, ...]:
    values = tuple(scopes)
    if any(not isinstance(value, str) or not value or any(c.isspace() for c in value) for value in values):
        raise ValueError("OAuth scope names must be non-empty and contain no whitespace.")
    if len(values) != len(set(values)):
        raise ValueError("OAuth scope names must be unique.")
    return values


def build_authorization_server_metadata(
    *, issuer: str, scopes_supported: Iterable[str] = (), service_documentation: str | None = None
) -> dict[str, object]:
    issuer = validate_canonical_url(issuer, require_https=False, allow_root_path=False)
    scopes = validated_scope_catalog(scopes_supported)
    payload: dict[str, object] = {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize/",
        "token_endpoint": f"{issuer}/oauth/token/",
        "registration_endpoint": f"{issuer}/oauth/register/",
        "revocation_endpoint": f"{issuer}/oauth/revoke/",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
        "authorization_response_iss_parameter_supported": True,
        "client_id_metadata_document_supported": True,
    }
    if scopes:
        payload["scopes_supported"] = list(scopes)
    if service_documentation:
        payload["service_documentation"] = service_documentation
    return payload


def build_protected_resource_metadata(
    *,
    resource: str,
    authorization_server: str,
    scopes_supported: Iterable[str] = (),
    resource_name: str | None = None,
    resource_documentation: str | None = None,
) -> dict[str, object]:
    resource = validate_canonical_url(resource, require_https=False, allow_root_path=False)
    authorization_server = validate_canonical_url(
        authorization_server, require_https=False, allow_root_path=False
    )
    payload: dict[str, object] = {
        "resource": resource,
        "authorization_servers": [authorization_server],
        "bearer_methods_supported": ["header"],
    }
    scopes = validated_scope_catalog(scopes_supported)
    if scopes:
        payload["scopes_supported"] = list(scopes)
    if resource_name:
        payload["resource_name"] = resource_name
    if resource_documentation:
        payload["resource_documentation"] = resource_documentation
    return payload
