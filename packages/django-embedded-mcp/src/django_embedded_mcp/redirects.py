"""Strict callback profiles for supported public OAuth clients."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import ip_address
from urllib.parse import unquote, urlsplit


class CallbackProfile(StrEnum):
    CHATGPT = "chatgpt_exact_connector_callback"
    CLAUDE = "claude_exact_https_callbacks"
    CODEX = "exact_registered_ip_loopback"
    CLAUDE_CODE = "claude_code_localhost_callback"


@dataclass(frozen=True)
class ParsedRedirect:
    uri: str
    profile: CallbackProfile
    application_type: str


_CHATGPT = re.compile(r"^https://chatgpt\.com/connector/oauth/[A-Za-z0-9._~-]+$")
_CLAUDE = frozenset(
    {
        "https://claude.ai/api/mcp/auth_callback",
        "https://claude.com/api/mcp/auth_callback",
    }
)


def _parsed(uri: str):
    if not isinstance(uri, str) or not uri:
        raise ValueError("Redirect URI must be non-empty text.")
    if any(ord(c) <= 0x20 or ord(c) == 0x7F for c in uri):
        raise ValueError("Redirect URI must not contain whitespace or controls.")
    if "?" in uri or "#" in uri or "*" in uri or "\\" in uri:
        raise ValueError("Redirect URI contains a forbidden component.")
    try:
        parsed = urlsplit(uri)
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("Redirect URI is malformed.") from exc
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("Redirect URI contains a forbidden authority.")
    if any(
        segment in {".", ".."} or unquote(segment) in {".", ".."}
        for segment in parsed.path.split("/")
    ):
        raise ValueError("Redirect URI must not contain a dot segment.")
    try:
        if ip_address(parsed.hostname).is_unspecified:
            raise ValueError("Redirect URI must not use an unspecified address.")
    except ValueError as exc:
        if str(exc) == "Redirect URI must not use an unspecified address.":
            raise
    return parsed


def callback_profile(uri: str) -> CallbackProfile:
    parsed = _parsed(uri)
    if _CHATGPT.fullmatch(uri):
        return CallbackProfile.CHATGPT
    if uri in _CLAUDE:
        return CallbackProfile.CLAUDE
    if (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "::1"}
        and parsed.port is not None
        and bool(parsed.path)
    ):
        return CallbackProfile.CODEX
    if (
        parsed.scheme == "http"
        and parsed.hostname == "localhost"
        and parsed.port is not None
        and parsed.path == "/callback"
        and not parsed.query
    ):
        return CallbackProfile.CLAUDE_CODE
    raise ValueError("Redirect URI does not match a supported public-client profile.")


def validate_registered_redirect_uri(uri: str, *, application_type: str) -> ParsedRedirect:
    if application_type not in {"native", "web"}:
        raise ValueError("application_type must be native or web.")
    profile = callback_profile(uri)
    native = {CallbackProfile.CODEX, CallbackProfile.CLAUDE_CODE}
    if application_type == "native" and profile not in native:
        raise ValueError("Native clients must use an approved loopback callback.")
    if application_type == "web" and profile in native:
        raise ValueError("Web clients must use an exact HTTPS callback.")
    return ParsedRedirect(uri=uri, profile=profile, application_type=application_type)


def redirect_uri_matches(registered_uri: str, requested_uri: str, *, application_type: str) -> bool:
    try:
        validate_registered_redirect_uri(registered_uri, application_type=application_type)
        validate_registered_redirect_uri(requested_uri, application_type=application_type)
    except (TypeError, ValueError):
        return False
    return registered_uri == requested_uri
