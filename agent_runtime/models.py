from django.conf import settings
from django.db import models


class AgentIdempotencyRecord(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_idempotency_records",
    )
    tool_name = models.CharField(max_length=80)
    key_digest = models.CharField(max_length=64)
    canonical_input_sha256 = models.CharField(max_length=64)
    idempotency_id = models.CharField(max_length=24)
    result = models.JSONField()
    resource_type = models.CharField(max_length=64, blank=True)
    resource_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "tool_name", "key_digest"],
                name="agent_idempotency_actor_tool_key_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["actor", "tool_name", "expires_at"],
                name="agent_idempotency_lookup_idx",
            )
        ]


class AgentAuditEvent(models.Model):
    request_id = models.CharField(max_length=128, db_index=True)
    authenticated_actor_id = models.CharField(max_length=128)
    # A stable public digest identifier; never a raw CIMD URL.
    authenticated_client_id = models.CharField(max_length=48)
    tool_name = models.CharField(max_length=80, db_index=True)
    resource_type = models.CharField(max_length=64, blank=True)
    resource_public_id = models.CharField(max_length=128, blank=True)
    scope_decision = models.JSONField(default=dict)
    capability_decision = models.JSONField(default=dict)
    ownership_decision = models.CharField(max_length=32)
    redacted_input_sha256 = models.CharField(max_length=64)
    result_code = models.CharField(max_length=64)
    idempotency_id = models.CharField(max_length=24, blank=True)
    approval_evidence = models.JSONField(default=dict, blank=True)
    dependency_outcome = models.CharField(max_length=32, blank=True)
    notification_outcome = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at", "tool_name"], name="agent_audit_retention_idx")
        ]
