from __future__ import annotations

import hashlib

import rfc8785

from .models import AgentAuditEvent


def redacted_input_hash(arguments: dict) -> str:
    redacted = {}
    for key, value in arguments.items():
        if key in {
            "idempotency_key",
            "name",
            "tagline",
            "title",
            "description",
            "body",
            "url",
            "label",
        }:
            redacted[key] = {"present": value is not None, "length": len(str(value or ""))}
        else:
            redacted[key] = value
    return hashlib.sha256(rfc8785.dumps(redacted)).hexdigest()


def public_client_identifier(client_id: str) -> str:
    """Return a stable audit identifier without persisting a CIMD URL."""

    digest = hashlib.sha256(str(client_id).encode()).hexdigest()
    return f"client-{digest[:32]}"


def record_tool_audit(
    *,
    context,
    tool_name: str,
    arguments: dict,
    result_code: str,
    resource_type: str = "",
    resource_id: str = "",
    idempotency_id: str = "",
    scope_granted: bool = True,
):
    definition = __import__("django.conf", fromlist=["settings"]).settings.AGENT_CONTRACT["tools"][tool_name]
    required_scopes = list(definition["required_scopes"])
    AgentAuditEvent.objects.create(
        request_id=context.request_id,
        authenticated_actor_id=context.authenticated_actor_id,
        authenticated_client_id=public_client_identifier(
            context.authenticated_client_id
        ),
        tool_name=tool_name,
        resource_type=resource_type,
        resource_public_id=str(resource_id or ""),
        scope_decision={"required": required_scopes, "granted": scope_granted},
        capability_decision={
            "required": list(definition["required_capabilities"]),
            "evaluated": context.audit_extra.get("capability_evaluated", True),
            "granted": (
                context.audit_extra.get("capability_granted", True)
                if context.audit_extra.get("capability_evaluated", True)
                else None
            ),
        },
        ownership_decision=context.audit_extra.get("ownership_decision", "granted"),
        redacted_input_sha256=redacted_input_hash(arguments),
        result_code=result_code,
        idempotency_id=idempotency_id,
        approval_evidence=context.audit_extra.get("approval_evidence", {}),
        dependency_outcome=context.audit_extra.get("dependency_outcome", ""),
        notification_outcome=context.audit_extra.get("notification_outcome", ""),
    )
