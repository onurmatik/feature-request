"""SSRF-aware OAuth Client ID Metadata Document validation and fetching."""

from __future__ import annotations

import json
import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from time import monotonic
from dataclasses import dataclass
from datetime import timedelta
from ipaddress import ip_address
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from .redirects import CallbackProfile, validate_registered_redirect_uri


_DNS_RESOLVER = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="django-embedded-mcp-dns",
)


class ClientMetadataError(ValueError):
    def __init__(self, description: str, *, retryable: bool = False):
        self.description = description
        self.retryable = retryable
        super().__init__(description)


@dataclass(frozen=True)
class ClientMetadataDocument:
    client_id: str
    client_name: str
    redirect_uris: tuple[str, ...]
    callback_profiles: tuple[CallbackProfile, ...]
    scopes: tuple[str, ...]
    application_type: str
    cache_seconds: int
    raw: dict[str, object]


def validate_client_metadata_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ClientMetadataError("client_id must be an HTTPS metadata URL.")
    if "\\" in value or any(
        ord(character) <= 0x20 or ord(character) == 0x7F for character in value
    ):
        raise ClientMetadataError(
            "client_id metadata URL contains a forbidden character."
        )
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise ClientMetadataError("client_id metadata URL is malformed.") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path in {"", "/"}
        or any(
            segment in {".", ".."} or unquote(segment) in {".", ".."}
            for segment in parsed.path.split("/")
        )
    ):
        raise ClientMetadataError(
            "client_id must be HTTPS with a non-root path and no query, fragment, userinfo or dot segment."
        )
    try:
        ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        raise ClientMetadataError("client_id metadata URL must not use an IP literal.")
    return value


def _validated_redirect_target(current: str, location: str) -> str:
    if not isinstance(location, str) or "\\" in location or any(
        ord(character) <= 0x20 or ord(character) == 0x7F
        for character in location
    ):
        raise ClientMetadataError(
            "Client metadata redirect contains a forbidden character."
        )
    try:
        raw = urlsplit(location)
        _ = raw.port
    except ValueError as exc:
        raise ClientMetadataError(
            "Client metadata redirect URL is malformed."
        ) from exc
    if any(
        segment in {".", ".."} or unquote(segment) in {".", ".."}
        for segment in raw.path.split("/")
    ):
        raise ClientMetadataError(
            "Client metadata redirect must not contain a dot segment."
        )
    return validate_client_metadata_url(urljoin(current, location))


def _validate_public_dns(
    hostname: str,
    port: int = 443,
    *,
    timeout: float = 3.0,
) -> tuple[str, ...]:
    future = _DNS_RESOLVER.submit(
        socket.getaddrinfo,
        hostname,
        port,
        0,
        socket.SOCK_STREAM,
    )
    try:
        records = future.result(timeout=max(0.001, timeout))
    except FutureTimeoutError as exc:
        future.cancel()
        raise ClientMetadataError(
            "Client metadata hostname resolution timed out.", retryable=True
        ) from exc
    except OSError as exc:
        raise ClientMetadataError("Client metadata hostname could not be resolved.", retryable=True) from exc
    addresses = tuple(dict.fromkeys(record[4][0] for record in records))
    if not addresses:
        raise ClientMetadataError("Client metadata hostname has no address.", retryable=True)
    for value in addresses:
        address = ip_address(value)
        if not address.is_global:
            raise ClientMetadataError("Client metadata hostname resolves to a non-public address.")
    return addresses


def _cache_seconds(headers: httpx.Headers) -> int:
    cache_control = headers.get("cache-control", "")
    for directive in cache_control.split(","):
        key, separator, value = directive.strip().partition("=")
        if key.lower() == "max-age" and separator:
            try:
                return min(3600, max(60, int(value.strip('"'))))
            except ValueError:
                break
    return 60


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ClientMetadataError(
                "Client metadata JSON object keys must be unique."
            )
        result[key] = value
    return result


def parse_client_metadata_document(
    payload: object,
    *,
    fetched_url: str,
    supported_scopes: tuple[str, ...] = ("read", "write"),
    cache_seconds: int = 60,
) -> ClientMetadataDocument:
    if not isinstance(payload, dict):
        raise ClientMetadataError("Client metadata must be a JSON object.")
    if payload.get("client_id") != fetched_url:
        raise ClientMetadataError("Client metadata client_id must exactly match its URL.")
    client_name = payload.get("client_name")
    if not isinstance(client_name, str) or not client_name.strip() or len(client_name) > 255:
        raise ClientMetadataError("Client metadata requires a client_name up to 255 characters.")
    redirect_uris = payload.get("redirect_uris")
    if (
        not isinstance(redirect_uris, list)
        or not redirect_uris
        or len(redirect_uris) > 10
        or not all(isinstance(uri, str) for uri in redirect_uris)
        or len(set(redirect_uris)) != len(redirect_uris)
    ):
        raise ClientMetadataError("Client metadata requires 1 to 10 unique redirect_uris.")
    method = payload.get("token_endpoint_auth_method")
    methods = payload.get("token_endpoint_auth_methods_supported")
    if method is not None and method != "none":
        raise ClientMetadataError("Only public clients using token_endpoint_auth_method none are supported.")
    if methods is not None and (
        not isinstance(methods, list)
        or not methods
        or not all(isinstance(value, str) for value in methods)
        or len(methods) != len(set(methods))
        or "none" not in methods
    ):
        raise ClientMetadataError(
            "Client metadata token_endpoint_auth_methods_supported must include none."
        )
    if payload.get("response_types", ["code"]) != ["code"]:
        raise ClientMetadataError("Only the code response type is supported.")
    grant_types = payload.get(
        "grant_types", ["authorization_code", "refresh_token"]
    )
    if (
        not isinstance(grant_types, list)
        or len(grant_types) != 2
        or not all(isinstance(value, str) for value in grant_types)
        or set(grant_types) != {"authorization_code", "refresh_token"}
    ):
        raise ClientMetadataError(
            "Client metadata must use authorization_code and refresh_token only."
        )
    application_type = payload.get("application_type", "web")
    if application_type not in {"native", "web"}:
        raise ClientMetadataError("application_type must be native or web.")
    try:
        parsed_redirects = tuple(
            validate_registered_redirect_uri(
                uri,
                application_type=application_type,
            )
            for uri in redirect_uris
        )
    except ValueError as exc:
        raise ClientMetadataError(str(exc)) from exc
    profiles = tuple(item.profile for item in parsed_redirects)
    scope_value = payload.get("scope", "read")
    if not isinstance(scope_value, str):
        raise ClientMetadataError("scope must be a string.")
    scopes = tuple(dict.fromkeys(scope_value.split()))
    if not scopes or not set(scopes).issubset(supported_scopes):
        raise ClientMetadataError("Client metadata requests unsupported scopes.")
    return ClientMetadataDocument(
        client_id=fetched_url,
        client_name=client_name.strip(),
        redirect_uris=tuple(redirect_uris),
        callback_profiles=profiles,
        scopes=scopes,
        application_type=application_type,
        cache_seconds=min(3600, max(60, cache_seconds)),
        raw=dict(payload),
    )


def fetch_client_metadata_document(
    client_id: str,
    *,
    transport: httpx.BaseTransport | None = None,
    max_redirects: int = 2,
    max_bytes: int = 5 * 1024,
) -> ClientMetadataDocument:
    current = validate_client_metadata_url(client_id)
    started = monotonic()
    with httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(5.0, connect=3.0),
        follow_redirects=False,
        trust_env=False,
        headers={"accept": "application/json"},
    ) as client:
        for hop in range(max_redirects + 1):
            parsed = urlsplit(current)
            remaining = 5.0 - (monotonic() - started)
            if remaining <= 0:
                raise ClientMetadataError(
                    "Client metadata fetch exceeded its total timeout.",
                    retryable=True,
                )
            resolved: tuple[str, ...] = ()
            if transport is None:
                resolved = _validate_public_dns(
                    parsed.hostname or "",
                    parsed.port or 443,
                    timeout=min(3.0, remaining),
                )
                remaining = 5.0 - (monotonic() - started)
                if remaining <= 0:
                    raise ClientMetadataError(
                        "Client metadata fetch exceeded its total timeout.",
                        retryable=True,
                    )
            try:
                response_context = client.stream(
                    "GET",
                    current,
                    timeout=httpx.Timeout(remaining, connect=min(3.0, remaining)),
                )
                response = response_context.__enter__()
            except httpx.HTTPError as exc:
                raise ClientMetadataError("Client metadata could not be fetched.", retryable=True) from exc
            try:
                if resolved:
                    stream = response.extensions.get("network_stream")
                    server_addr = (
                        stream.get_extra_info("server_addr")
                        if stream is not None and hasattr(stream, "get_extra_info")
                        else None
                    )
                    if server_addr and str(server_addr[0]) not in resolved:
                        raise ClientMetadataError(
                            "Client metadata connection address did not match validated DNS."
                        )
                if response.is_redirect:
                    if hop >= max_redirects:
                        raise ClientMetadataError("Client metadata redirect limit exceeded.")
                    location = response.headers.get("location")
                    if not location:
                        raise ClientMetadataError("Client metadata redirect is missing Location.")
                    current = _validated_redirect_target(current, location)
                    continue
                if response.status_code != 200:
                    raise ClientMetadataError("Client metadata endpoint did not return 200.", retryable=True)
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json" and not content_type.endswith("+json"):
                    raise ClientMetadataError("Client metadata response must be JSON.")
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > max_bytes:
                            raise ClientMetadataError("Client metadata response exceeds 5 KiB.")
                    except ValueError as exc:
                        raise ClientMetadataError(
                            "Client metadata Content-Length is invalid."
                        ) from exc
                chunks: list[bytes] = []
                length = 0
                for chunk in response.iter_bytes():
                    length += len(chunk)
                    if length > max_bytes:
                        raise ClientMetadataError("Client metadata response exceeds 5 KiB.")
                    if monotonic() - started > 5.0:
                        raise ClientMetadataError(
                            "Client metadata fetch exceeded its total timeout.",
                            retryable=True,
                        )
                    chunks.append(chunk)
                if monotonic() - started > 5.0:
                    raise ClientMetadataError(
                        "Client metadata fetch exceeded its total timeout.",
                        retryable=True,
                    )
                try:
                    payload = json.loads(
                        b"".join(chunks), object_pairs_hook=_unique_json_object
                    )
                except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
                    raise ClientMetadataError("Client metadata response is invalid JSON.") from exc
                # A redirect changes the effective URL. The document must identify
                # the original client_id, not silently authorize another identity.
                return parse_client_metadata_document(
                    payload,
                    fetched_url=client_id,
                    cache_seconds=_cache_seconds(response.headers),
                )
            except httpx.HTTPError as exc:
                raise ClientMetadataError(
                    "Client metadata transfer failed.", retryable=True
                ) from exc
            finally:
                response_context.__exit__(None, None, None)
    raise ClientMetadataError("Client metadata could not be fetched.", retryable=True)
