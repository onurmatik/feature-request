"""Canonical OAuth resource validation and comparison."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import SplitResult, urlsplit


class CanonicalResourceError(ValueError):
    """Raised when an RFC 8707 resource is absent or targets another server."""


def _parse(value: str) -> SplitResult:
    if not isinstance(value, str) or not value:
        raise ValueError("URL must be non-empty text.")
    if any(ord(char) <= 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError("URL must not contain ASCII whitespace or controls.")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("URL must be a valid absolute URL.") from exc
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("URL must be absolute.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not contain userinfo.")
    return parsed


def validate_canonical_url(
    value: str,
    *,
    require_https: bool,
    allow_root_path: bool = True,
) -> str:
    parsed = _parse(value)
    scheme = parsed.scheme.lower()
    allowed = {"https"} if require_https else {"http", "https"}
    if scheme not in allowed:
        raise ValueError("URL must use HTTPS." if require_https else "URL must use HTTP or HTTPS.")
    if parsed.query or parsed.fragment:
        raise ValueError("URL must not contain a query or fragment.")
    if value.endswith("/") and not (allow_root_path and parsed.path == "/"):
        raise ValueError("URL must not contain an unexpected trailing slash.")
    if parsed.scheme != scheme or (parsed.hostname and parsed.hostname != parsed.hostname.lower()):
        raise ValueError("Configured URL scheme and host must be lowercase.")
    return value


def _comparison_key(value: str) -> tuple[str, str, str, str, str]:
    parsed = _parse(value)
    # Only scheme and host are case-insensitive. Preserve explicit port, path,
    # percent encoding, query and trailing slash exactly.
    host = parsed.hostname.lower()
    if parsed.netloc.startswith("["):
        closing = parsed.netloc.find("]")
        port_suffix = parsed.netloc[closing + 1 :]
        authority = f"[{host}]{port_suffix}"
    else:
        port_suffix = ""
        if ":" in parsed.netloc:
            _, _, raw_port = parsed.netloc.rpartition(":")
            port_suffix = f":{raw_port}"
        authority = f"{host}{port_suffix}"
    return (
        parsed.scheme.lower(),
        authority,
        parsed.path,
        parsed.query,
        parsed.fragment,
    )


def canonical_resource_equal(left: str, right: str) -> bool:
    try:
        return _comparison_key(left) == _comparison_key(right)
    except (TypeError, ValueError):
        return False


def canonical_resource_from_pairs(
    pairs: Iterable[tuple[str, str]],
    *,
    expected: str,
) -> tuple[list[tuple[str, str]], str]:
    materialized = list(pairs)
    if not all(
        isinstance(pair, (list, tuple))
        and len(pair) == 2
        and isinstance(pair[0], str)
        and isinstance(pair[1], str)
        for pair in materialized
    ):
        raise CanonicalResourceError("Resource parameters must be text pairs.")
    resources = [value for key, value in materialized if key == "resource"]
    if not resources:
        raise CanonicalResourceError("The resource parameter is required.")
    if len(resources) != 1:
        raise CanonicalResourceError("The resource parameter must occur exactly once.")
    if any(not canonical_resource_equal(value, expected) for value in resources):
        raise CanonicalResourceError("The requested resource is not this MCP server.")
    without = [(key, value) for key, value in materialized if key != "resource"]
    return [*without, ("resource", expected)], expected
