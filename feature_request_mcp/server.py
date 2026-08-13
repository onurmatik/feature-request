from __future__ import annotations

import json
import logging
import os
import re
from threading import current_thread, main_thread
from types import SimpleNamespace
from uuid import uuid4

import django
from asgiref.sync import sync_to_async

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.exceptions import ImproperlyConfigured  # noqa: E402
from django.db import close_old_connections, connections  # noqa: E402
from django_embedded_mcp import (  # noqa: E402
    DigestTokenVerifier,
    MCPAuthCORSMiddleware,
    build_auth_failure_challenge,
)
from django_embedded_mcp.mcp import build_transport_security_settings  # noqa: E402
from mcp import MCPError  # noqa: E402
from mcp.server import CacheHint, MCPServer  # noqa: E402
from mcp.server.auth.middleware.auth_context import get_access_token  # noqa: E402
from mcp.types import (  # noqa: E402
    CallToolResult,
    INTERNAL_ERROR,
    METHOD_NOT_FOUND,
    TextContent,
)

from agent_runtime.context import AgentContext  # noqa: E402
from agent_runtime.audit import record_tool_audit  # noqa: E402
from agent_runtime.contract import (  # noqa: E402
    SERVER_VERSION,
    contract,
    public_registry,
    server_instructions,
)
from agent_runtime.errors import ContractApplicationError, MissingScopeError  # noqa: E402
from agent_runtime.service import service  # noqa: E402
from mcp_oauth.services import record_access_token_use, resolve_access_token  # noqa: E402


logger = logging.getLogger(__name__)
_PUBLIC_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def _validated_request_id(candidate) -> str:
    value = str(candidate or "")
    return value if _PUBLIC_REQUEST_ID.fullmatch(value) else uuid4().hex


def _request_id(context) -> str:
    if context is not None:
        try:
            headers = context.headers
            candidate = headers.get("x-request-id") or headers.get("X-Request-ID")
            if candidate:
                return _validated_request_id(candidate)
        except Exception:
            pass
    return _validated_request_id("")


def _database_operation(callback, *args, **kwargs):
    """Bound ORM connection lifetime to an MCP worker operation."""

    owns_worker_connection = current_thread() is not main_thread()
    if owns_worker_connection:
        close_old_connections()
    try:
        return callback(*args, **kwargs)
    finally:
        # AsyncToSync executes thread-sensitive work back on the test runner's
        # main thread, whose transaction Django owns. Production ASGI dispatch
        # uses a worker thread and must not retain its thread-local connection.
        if owns_worker_connection:
            connections.close_all()


async def _database_sync(callback, *args, **kwargs):
    return await sync_to_async(_database_operation, thread_sensitive=True)(
        callback, *args, **kwargs
    )


class FeatureRequestMCPServer(MCPServer[None]):
    async def list_tools(self):
        return list(public_registry())

    async def call_tool(self, name, arguments, context=None):
        names = {tool.name for tool in public_registry()}
        if name not in names:
            raise MCPError(code=METHOD_NOT_FOUND, message="Unknown FeatureRequest tool.")
        access = get_access_token()
        if access is None or not access.subject:
            raise MCPError(code=INTERNAL_ERROR, message="Authenticated actor context is missing.")
        User = get_user_model()
        user = await _database_sync(
            lambda: User.objects.filter(pk=access.subject, is_active=True).first(),
        )
        if user is None:
            raise MCPError(code=INTERNAL_ERROR, message="Authenticated actor is unavailable.")
        agent_context = AgentContext(
            user=user,
            authenticated_client_id=access.client_id,
            scopes=frozenset(access.scopes),
            request_id=_request_id(context),
        )
        try:
            result = await _database_sync(
                service.call,
                name,
                dict(arguments or {}),
                agent_context,
            )
        except MissingScopeError as exc:
            agent_context.audit_extra.update(
                capability_evaluated=False,
                ownership_decision="not_evaluated",
            )
            resource_type = ""
            resource_id = ""
            for key, kind in (
                ("comment_id", "comment"),
                ("artifact_id", "delivery_artifact"),
                ("issue_id", "request"),
                ("project_id", "project"),
            ):
                if key in (arguments or {}):
                    resource_type = kind
                    resource_id = str(arguments[key])
                    break
            await _database_sync(
                record_tool_audit,
                context=agent_context,
                tool_name=name,
                arguments=dict(arguments or {}),
                result_code="insufficient_scope",
                resource_type=resource_type,
                resource_id=resource_id,
                scope_granted=False,
            )
            challenge = build_auth_failure_challenge(
                resource_metadata=settings.MCP_RESOURCE_METADATA_URL,
                scopes=exc.required_scopes,
                status=403,
                credential_present=True,
            )
            return CallToolResult(
                content=[TextContent(text="Additional OAuth scope is required.")],
                isError=True,
                _meta={"mcp/www_authenticate": [challenge]},
            )
        except ContractApplicationError as exc:
            envelope = exc.envelope
            return CallToolResult(
                content=[
                    TextContent(
                        text=json.dumps(envelope, sort_keys=True, separators=(",", ":"))
                    )
                ],
                structuredContent=envelope,
                isError=True,
            )
        except Exception:
            logger.error(
                "FeatureRequest MCP tool failed request_id=%s tool=%s result=internal_error",
                agent_context.request_id,
                name,
            )
            raise MCPError(code=INTERNAL_ERROR, message="Internal server error.") from None
        return CallToolResult(
            content=[
                TextContent(text=json.dumps(result, sort_keys=True, separators=(",", ":")))
            ],
            structuredContent=result,
            isError=False,
        )


token_verifier = DigestTokenVerifier(
    resource=settings.MCP_RESOURCE_URL,
    issuer=settings.OAUTH_ISSUER,
    allowed_scopes=settings.FEATURE_REQUEST_MCP_OAUTH_SCOPES,
    record_resolver=resolve_access_token,
    verified_callback=record_access_token_use,
)

mcp = FeatureRequestMCPServer(
    name="feature-request",
    title="FeatureRequest",
    description="Operate FeatureRequest projects and evidence-backed request lifecycles.",
    instructions=server_instructions(),
    version=SERVER_VERSION,
    cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="public")},
)


def _required_scopes(method: str, name: str):
    if method == "tools/call" and name in contract()["tools"]:
        return tuple(contract()["tools"][name]["required_scopes"])
    return tuple(settings.FEATURE_REQUEST_MCP_BOOTSTRAP_SCOPES)


async def _audit_scope_denial(
    *,
    access_token,
    method: str,
    name: str,
    required_scopes,
    missing_scopes,
    request_id: str,
):
    if method != "tools/call" or name not in contract()["tools"]:
        return
    context = AgentContext(
        user=SimpleNamespace(pk=access_token.subject),
        authenticated_client_id=access_token.client_id,
        scopes=frozenset(access_token.scopes),
        request_id=_validated_request_id(request_id),
    )
    context.audit_extra.update(
        missing_scopes=list(missing_scopes),
        capability_evaluated=False,
        ownership_decision="not_evaluated",
    )
    await _database_sync(
        record_tool_audit,
        context=context,
        tool_name=name,
        arguments={},
        result_code="insufficient_scope",
        scope_granted=False,
    )


def create_application():
    if not settings.DEBUG and not settings.FEATURE_REQUEST_MCP_PRODUCTION_ENABLED:
        raise ImproperlyConfigured(
            "Production MCP process startup requires FEATURE_REQUEST_MCP_PRODUCTION_ENABLED=true."
        )
    transport_security = build_transport_security_settings(
        resource_url=settings.MCP_RESOURCE_URL,
        allowed_origins=settings.FEATURE_REQUEST_MCP_CORS_ORIGINS,
        production=not settings.DEBUG,
        extra_hosts=(
            f"{settings.FEATURE_REQUEST_MCP_HOST}:{settings.FEATURE_REQUEST_MCP_PORT}",
        ),
    )
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=transport_security,
        host=settings.FEATURE_REQUEST_MCP_HOST,
        max_request_body_size=1024 * 1024,
    )
    return MCPAuthCORSMiddleware(
        app,
        path="/mcp",
        allowed_origins=settings.FEATURE_REQUEST_MCP_CORS_ORIGINS,
        token_verifier=token_verifier,
        resource_metadata=settings.MCP_RESOURCE_METADATA_URL,
        bootstrap_scopes=settings.FEATURE_REQUEST_MCP_BOOTSTRAP_SCOPES,
        tool_scope_resolver=_required_scopes,
        protocol_version="2026-07-28",
        authorization_decision_callback=_audit_scope_denial,
    )
