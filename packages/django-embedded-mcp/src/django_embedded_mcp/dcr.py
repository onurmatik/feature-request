"""Pure RFC 7591 policy for the public-client DCR fallback."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .oauth import normalize_scopes
from .redirects import CallbackProfile, validate_registered_redirect_uri


class DynamicClientRegistrationError(ValueError):
    def __init__(self, error: str, description: str, *, status: int = 400):
        self.error = error
        self.description = description
        self.status = status
        super().__init__(description)


@dataclass(frozen=True)
class PublicClientRegistration:
    redirect_uris: tuple[str, ...]
    callback_profiles: tuple[CallbackProfile, ...]
    scopes: tuple[str, ...]
    client_name: str
    application_type: str
    metadata: Mapping[str, Any]


def parse_public_client_registration(
    body: bytes,
    *,
    supported_scopes: Iterable[str],
    default_scopes: Iterable[str],
    max_body_bytes: int = 16 * 1024,
    max_redirect_uris: int = 10,
) -> PublicClientRegistration:
    if not isinstance(body, (bytes, bytearray)) or len(body) > max_body_bytes:
        raise DynamicClientRegistrationError(
            "invalid_client_metadata",
            f"Registration request must be JSON no larger than {max_body_bytes // 1024} KiB.",
            status=413 if isinstance(body, (bytes, bytearray)) else 400,
        )

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise DynamicClientRegistrationError(
                    "invalid_client_metadata", f"{key} must not be repeated."
                )
            result[key] = value
        return result

    try:
        data = json.loads(body, object_pairs_hook=pairs)
    except DynamicClientRegistrationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise DynamicClientRegistrationError(
            "invalid_client_metadata", "Request body must be a JSON object."
        ) from exc
    if not isinstance(data, dict):
        raise DynamicClientRegistrationError(
            "invalid_client_metadata", "Request body must be a JSON object."
        )
    application_type = data.get("application_type")
    if application_type not in {"native", "web"}:
        raise DynamicClientRegistrationError(
            "invalid_client_metadata", "application_type must be native or web."
        )
    redirects = data.get("redirect_uris")
    if (
        not isinstance(redirects, list)
        or not redirects
        or len(redirects) > max_redirect_uris
        or not all(isinstance(uri, str) for uri in redirects)
        or len(set(redirects)) != len(redirects)
    ):
        raise DynamicClientRegistrationError(
            "invalid_redirect_uri",
            f"redirect_uris must contain 1 to {max_redirect_uris} unique strings.",
        )
    try:
        parsed_redirects = [
            validate_registered_redirect_uri(uri, application_type=application_type)
            for uri in redirects
        ]
    except ValueError as exc:
        raise DynamicClientRegistrationError("invalid_redirect_uri", str(exc)) from exc
    if data.get("token_endpoint_auth_method") != "none":
        raise DynamicClientRegistrationError(
            "invalid_client_metadata", "token_endpoint_auth_method must be none."
        )
    if data.get("response_types", ["code"]) != ["code"]:
        raise DynamicClientRegistrationError(
            "invalid_client_metadata", "response_types must contain only code."
        )
    grant_types = data.get("grant_types", ["authorization_code", "refresh_token"])
    if (
        not isinstance(grant_types, list)
        or len(grant_types) != 2
        or not all(isinstance(value, str) for value in grant_types)
        or set(grant_types) != {"authorization_code", "refresh_token"}
    ):
        raise DynamicClientRegistrationError(
            "invalid_client_metadata",
            "grant_types must contain authorization_code and refresh_token only.",
        )
    try:
        scopes = normalize_scopes(
            str(data.get("scope", " ".join(default_scopes))).split(),
            supported_scopes=supported_scopes,
            default_scopes=default_scopes,
        )
    except ValueError as exc:
        raise DynamicClientRegistrationError("invalid_client_metadata", str(exc)) from exc
    client_name = data.get("client_name", "")
    if not isinstance(client_name, str) or not client_name.strip() or len(client_name) > 255:
        raise DynamicClientRegistrationError(
            "invalid_client_metadata", "client_name must be 1 to 255 characters."
        )
    metadata = {
        key: data[key]
        for key in ("client_uri", "contacts", "tos_uri", "policy_uri", "software_id", "software_version")
        if key in data
    }
    return PublicClientRegistration(
        redirect_uris=tuple(redirects),
        callback_profiles=tuple(item.profile for item in parsed_redirects),
        scopes=tuple(scopes),
        client_name=client_name.strip(),
        application_type=application_type,
        metadata=metadata,
    )
