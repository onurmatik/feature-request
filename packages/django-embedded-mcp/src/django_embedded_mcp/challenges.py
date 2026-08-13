"""Header-injection-safe RFC 6750 Bearer challenges."""

from __future__ import annotations

from collections.abc import Iterable


def _quoted(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Bearer challenge values must be strings.")
    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in value):
        raise ValueError("Bearer challenge values must contain visible ASCII only.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_bearer_challenge(
    *,
    resource_metadata: str,
    scopes: Iterable[str] = (),
    error: str | None = None,
    error_description: str | None = None,
) -> str:
    parameters = [("resource_metadata", resource_metadata)]
    scope_list = tuple(dict.fromkeys(scopes))
    if scope_list:
        parameters.append(("scope", " ".join(scope_list)))
    if error is not None:
        parameters.append(("error", error))
    if error_description is not None:
        parameters.append(("error_description", error_description))
    return "Bearer " + ", ".join(f"{key}={_quoted(value)}" for key, value in parameters)


def build_auth_failure_challenge(
    *, resource_metadata: str, scopes: Iterable[str], status: int, credential_present: bool
) -> str:
    if status == 403:
        return build_bearer_challenge(
            resource_metadata=resource_metadata,
            scopes=scopes,
            error="insufficient_scope",
            error_description="The token lacks the required scope",
        )
    if credential_present:
        return build_bearer_challenge(
            resource_metadata=resource_metadata,
            scopes=scopes,
            error="invalid_token",
            error_description="The bearer token is invalid or expired",
        )
    return build_bearer_challenge(resource_metadata=resource_metadata, scopes=scopes)
