"""ASGI CORS and header-only Bearer enforcement for one MCP path."""

from __future__ import annotations

import json
import inspect
from collections.abc import Callable, Iterable
from http.cookies import CookieError, SimpleCookie
from typing import Any
from urllib.parse import parse_qsl

from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

from .challenges import build_auth_failure_challenge

NON_HEADER_BEARER_KEYS = frozenset({"access_token", "bearer_token"})


def non_header_bearer_sources(
    *, query_string: bytes | str = b"", cookie_header: bytes | str = b""
) -> frozenset[str]:
    if isinstance(query_string, bytes):
        query_string = query_string.decode("utf-8", "ignore")
    if isinstance(cookie_header, bytes):
        cookie_header = cookie_header.decode("latin-1", "ignore")
    query_keys = {key.lower() for key, _ in parse_qsl(query_string, keep_blank_values=True)}
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except CookieError:
        cookie_keys: set[str] = set()
    else:
        cookie_keys = {key.lower() for key in cookie}
    sources = set()
    if query_keys & NON_HEADER_BEARER_KEYS:
        sources.add("query")
    if cookie_keys & NON_HEADER_BEARER_KEYS:
        sources.add("cookie")
    return frozenset(sources)


async def _json(send, status: int, payload: dict[str, object], headers=()) -> None:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _empty(send, status: int, headers=()) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-length", b"0"), *headers],
        }
    )
    await send({"type": "http.response.body", "body": b""})


class MCPAuthCORSMiddleware:
    """Run explicit CORS and credential-source checks before MCP authentication."""

    def __init__(
        self,
        app: Callable[..., Any],
        *,
        path: str,
        allowed_origins: Iterable[str],
        token_verifier: Any,
        resource_metadata: str,
        bootstrap_scopes: Iterable[str],
        tool_scope_resolver: Callable[[str, str], Iterable[str]],
        protocol_version: str,
        authorization_decision_callback: Callable[..., Any] | None = None,
    ):
        self.app = app
        self.path = path
        self.allowed_origins = frozenset(allowed_origins)
        self.token_verifier = token_verifier
        self.resource_metadata = resource_metadata
        self.bootstrap_scopes = tuple(bootstrap_scopes)
        self.tool_scope_resolver = tool_scope_resolver
        self.protocol_version = protocol_version
        self.authorization_decision_callback = authorization_decision_callback

    @staticmethod
    def _header(scope, name: bytes) -> bytes:
        return next(
            (value for key, value in scope.get("headers", []) if key.lower() == name),
            b"",
        )

    @staticmethod
    def _headers(scope, name: bytes) -> list[bytes]:
        return [
            value
            for key, value in scope.get("headers", [])
            if key.lower() == name
        ]

    def _challenge(
        self, *, status: int, credential_present: bool, scopes: Iterable[str]
    ) -> bytes:
        return build_auth_failure_challenge(
            resource_metadata=self.resource_metadata,
            scopes=scopes,
            status=status,
            credential_present=credential_present,
        ).encode("ascii")

    def _cors(self, origin: str) -> list[tuple[bytes, bytes]]:
        if not origin or origin not in self.allowed_origins:
            return []
        return [
            (b"access-control-allow-origin", origin.encode("ascii")),
            (b"vary", b"Origin"),
            (b"access-control-allow-methods", b"POST, OPTIONS"),
            (
                b"access-control-allow-headers",
                b"Authorization, Content-Type, MCP-Protocol-Version, Mcp-Method, Mcp-Name, Mcp-Session-Id",
            ),
            (
                b"access-control-expose-headers",
                b"WWW-Authenticate, MCP-Protocol-Version, Mcp-Session-Id",
            ),
            (b"access-control-max-age", b"600"),
        ]

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") != self.path:
            await self.app(scope, receive, send)
            return
        origin_values = self._headers(scope, b"origin")
        if len(origin_values) > 1:
            await _json(send, 403, {"error": "cors_origin_denied"})
            return
        try:
            origin = origin_values[0].decode("ascii") if origin_values else ""
        except UnicodeDecodeError:
            await _json(send, 403, {"error": "cors_origin_denied"})
            return
        if origin and origin not in self.allowed_origins:
            await _json(send, 403, {"error": "cors_origin_denied"})
            return
        cors_headers = self._cors(origin)
        if scope.get("method") == "OPTIONS":
            await _empty(send, 204, headers=cors_headers)
            return
        sources = non_header_bearer_sources(
            query_string=scope.get("query_string", b""),
            cookie_header=b"; ".join(self._headers(scope, b"cookie")),
        )
        if sources:
            await _json(
                send,
                401,
                {"error": "invalid_token", "error_description": "Use the Authorization header."},
                headers=[
                    *cors_headers,
                    (
                        b"www-authenticate",
                        self._challenge(
                            status=401,
                            credential_present=True,
                            scopes=self.bootstrap_scopes,
                        ),
                    ),
                    (b"cache-control", b"no-store"),
                ],
            )
            return

        authorization_values = self._headers(scope, b"authorization")
        credential_present = bool(authorization_values)
        token = ""
        if len(authorization_values) == 1:
            try:
                authorization = authorization_values[0].decode("ascii")
            except UnicodeDecodeError:
                authorization = ""
            scheme, separator, candidate = authorization.partition(" ")
            if (
                separator
                and scheme.lower() == "bearer"
                and candidate
                and not any(char.isspace() for char in candidate)
            ):
                token = candidate
        if not token:
            await _json(
                send,
                401,
                {"error": "invalid_token" if credential_present else "authentication_required"},
                headers=[
                    *cors_headers,
                    (
                        b"www-authenticate",
                        self._challenge(
                            status=401,
                            credential_present=credential_present,
                            scopes=self.bootstrap_scopes,
                        ),
                    ),
                    (b"cache-control", b"no-store"),
                ],
            )
            return
        access_token = await self.token_verifier.verify_token(token)
        if access_token is None:
            await _json(
                send,
                401,
                {"error": "invalid_token"},
                headers=[
                    *cors_headers,
                    (
                        b"www-authenticate",
                        self._challenge(
                            status=401,
                            credential_present=True,
                            scopes=self.bootstrap_scopes,
                        ),
                    ),
                    (b"cache-control", b"no-store"),
                ],
            )
            return

        version_values = self._headers(scope, b"mcp-protocol-version")
        method_values = self._headers(scope, b"mcp-method")
        name_values = self._headers(scope, b"mcp-name")
        try:
            version = (
                version_values[0].decode("ascii")
                if len(version_values) == 1
                else ""
            )
            method = (
                method_values[0].decode("ascii")
                if len(method_values) == 1
                else ""
            )
            name = (
                name_values[0].decode("ascii") if len(name_values) == 1 else ""
            )
        except UnicodeDecodeError:
            version = method = name = ""
        invalid_named_call = method == "tools/call" and (
            len(name_values) != 1
            or not name
            or name.strip() != name
            or any(char.isspace() for char in name)
        )
        if (
            version != self.protocol_version
            or not method
            or method.strip() != method
            or any(char.isspace() for char in method)
            or invalid_named_call
        ):
            await _json(
                send,
                400,
                {
                    "error": "invalid_request",
                    "error_description": (
                        "Modern MCP protocol, method, and named-call headers are required."
                    ),
                },
                headers=[*cors_headers, (b"cache-control", b"no-store")],
            )
            return
        required_scopes = tuple(self.tool_scope_resolver(method, name))
        missing = set(required_scopes) - set(access_token.scopes)
        if missing:
            challenge = self._challenge(
                status=403,
                credential_present=True,
                scopes=required_scopes,
            )
            if self.authorization_decision_callback is not None:
                request_id = self._header(scope, b"x-request-id").decode(
                    "utf-8", "ignore"
                )[:128]
                try:
                    callback_result = self.authorization_decision_callback(
                        access_token=access_token,
                        method=method,
                        name=name,
                        required_scopes=required_scopes,
                        missing_scopes=tuple(sorted(missing)),
                        request_id=request_id,
                    )
                    if inspect.isawaitable(callback_result):
                        await callback_result
                except Exception:
                    await _json(
                        send,
                        503,
                        {"error": "temporarily_unavailable"},
                        headers=[*cors_headers, (b"cache-control", b"no-store")],
                    )
                    return
            await _json(
                send,
                403,
                {
                    "error": "insufficient_scope",
                    "required_scopes": sorted(missing),
                    "_meta": {
                        "mcp/www_authenticate": [challenge.decode("ascii")]
                    },
                },
                headers=[
                    *cors_headers,
                    (b"www-authenticate", challenge),
                    (b"cache-control", b"no-store"),
                ],
            )
            return

        async def send_with_cors(message):
            if message.get("type") == "http.response.start" and cors_headers:
                message = {**message, "headers": [*message.get("headers", []), *cors_headers]}
            await send(message)

        context_token = auth_context_var.set(AuthenticatedUser(access_token))
        try:
            await self.app(scope, receive, send_with_cors)
        finally:
            auth_context_var.reset(context_token)
