"""Model-neutral OAuth primitives."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable


def credential_digest(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Credential must be non-empty text.")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_opaque_credential(*, bytes_of_entropy: int = 32) -> str:
    if bytes_of_entropy < 24:
        raise ValueError("OAuth credentials require at least 192 bits of entropy.")
    return secrets.token_urlsafe(bytes_of_entropy)


def normalize_scopes(
    scopes: Iterable[str] | None,
    *,
    supported_scopes: Iterable[str],
    required_scopes: Iterable[str] = (),
    default_scopes: Iterable[str] = (),
) -> list[str]:
    supported = tuple(supported_scopes)
    supported_set = frozenset(supported)
    required_set = frozenset(required_scopes)
    requested = list(scopes) if scopes is not None else list(default_scopes)
    normalized = list(dict.fromkeys(scope for scope in requested if scope))
    if not normalized:
        normalized = list(default_scopes)
    if not required_set.issubset(normalized):
        raise ValueError("One or more required scopes are missing.")
    if not set(normalized).issubset(supported_set):
        raise ValueError("One or more requested scopes are not supported.")
    return [scope for scope in supported if scope in normalized]
