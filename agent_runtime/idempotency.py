from __future__ import annotations

import hashlib
from datetime import timedelta

import rfc8785
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_embedded_mcp import credential_digest

from .errors import app_error
from .models import AgentIdempotencyRecord


def canonical_input_sha256(arguments: dict) -> str:
    safe = {key: value for key, value in arguments.items() if key != "idempotency_key"}
    return hashlib.sha256(rfc8785.dumps(safe)).hexdigest()


def public_idempotency_id(key_digest: str) -> str:
    return f"idem_{key_digest[:16]}"


def replay_idempotent(*, context, tool_name: str, arguments: dict):
    key_digest = credential_digest(arguments["idempotency_key"])
    record = AgentIdempotencyRecord.objects.filter(
        actor=context.user,
        tool_name=tool_name,
        key_digest=key_digest,
        expires_at__gt=timezone.now(),
    ).first()
    if record is None:
        return None
    if record.canonical_input_sha256 != canonical_input_sha256(arguments):
        raise app_error(
            "idempotency_conflict",
            context.request_id,
            idempotency_key=record.idempotency_id,
        )
    return record.result, True, record.idempotency_id


def execute_idempotent(*, context, tool_name: str, arguments: dict, operation):
    raw_key = arguments["idempotency_key"]
    key_digest = credential_digest(raw_key)
    input_hash = canonical_input_sha256(arguments)
    public_id = public_idempotency_id(key_digest)
    now = timezone.now()
    with transaction.atomic():
        existing = (
            AgentIdempotencyRecord.objects.select_for_update()
            .filter(
                actor=context.user,
                tool_name=tool_name,
                key_digest=key_digest,
            )
            .first()
        )
        if existing is not None and existing.expires_at > now:
            if existing.canonical_input_sha256 != input_hash:
                raise app_error(
                    "idempotency_conflict",
                    context.request_id,
                    idempotency_key=existing.idempotency_id,
                )
            return existing.result, True, existing.idempotency_id
        if existing is not None:
            record = existing
            record.canonical_input_sha256 = input_hash
            record.idempotency_id = public_id
            record.result = {}
            record.resource_type = ""
            record.resource_id = ""
            record.expires_at = now + timedelta(hours=24)
            record.save(
                update_fields=[
                    "canonical_input_sha256",
                    "idempotency_id",
                    "result",
                    "resource_type",
                    "resource_id",
                    "expires_at",
                ]
            )
        else:
            try:
                with transaction.atomic():
                    record = AgentIdempotencyRecord.objects.create(
                        actor=context.user,
                        tool_name=tool_name,
                        key_digest=key_digest,
                        canonical_input_sha256=input_hash,
                        idempotency_id=public_id,
                        result={},
                        expires_at=now + timedelta(hours=24),
                    )
            except IntegrityError:
                record = AgentIdempotencyRecord.objects.select_for_update().get(
                    actor=context.user,
                    tool_name=tool_name,
                    key_digest=key_digest,
                )
                if record.canonical_input_sha256 != input_hash:
                    raise app_error(
                        "idempotency_conflict",
                        context.request_id,
                        idempotency_key=record.idempotency_id,
                    )
                return record.result, True, record.idempotency_id
        result, resource_type, resource_id = operation()
        record.result = result
        record.resource_type = resource_type
        record.resource_id = str(resource_id or "")
        record.save(update_fields=["result", "resource_type", "resource_id"])
        return result, False, public_id
