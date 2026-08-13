from __future__ import annotations

from datetime import timedelta
from time import monotonic

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from agent_runtime.models import AgentAuditEvent, AgentIdempotencyRecord
from mcp_oauth.models import (
    ClientMetadataCache,
    OAuthAccessToken,
    OAuthApplication,
    OAuthCleanupRun,
    OAuthGrant,
    OAuthRefreshFamily,
    OAuthSecurityEvent,
    PendingAuthorization,
    RateLimitBucket,
)
from mcp_oauth.operations import send_deduplicated_admin_alert


class Command(BaseCommand):
    help = "Delete bounded expired MCP/OAuth and agent-runtime records."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)

    @staticmethod
    def _delete_batch(queryset, batch_size):
        ids = list(queryset.order_by("pk").values_list("pk", flat=True)[:batch_size])
        if not ids:
            return 0
        deleted, _ = queryset.model.objects.filter(pk__in=ids).delete()
        return deleted

    def handle(self, *args, **options):
        batch_size = max(1, min(int(options["batch_size"]), 2000))
        started = monotonic()
        now = timezone.now()
        run = OAuthCleanupRun.objects.create()
        deleted = {}
        try:
            with transaction.atomic():
                refresh_retention = timedelta(
                    seconds=settings.FEATURE_REQUEST_MCP_REFRESH_FAMILY_TTL_SECONDS
                )
                targets = {
                    # Keep consumed code digests for the refresh-family lifetime.
                    # A replay after the 60-second exchange window must still be
                    # able to revoke every credential issued from that code.
                    "expired_unused_grants": OAuthGrant.objects.filter(
                        consumed_at__isnull=True,
                        expires__lt=now,
                    ),
                    "consumed_grant_replay_records": OAuthGrant.objects.filter(
                        consumed_at__isnull=False,
                        consumed_at__lt=now - refresh_retention,
                    ),
                    "access_tokens": OAuthAccessToken.objects.filter(expires__lt=now),
                    "refresh_families": OAuthRefreshFamily.objects.filter(
                        expires_at__lt=now
                    ),
                    "pending_authorizations": PendingAuthorization.objects.filter(
                        expires_at__lt=now
                    ),
                    "client_metadata": ClientMetadataCache.objects.filter(expires_at__lt=now),
                    "idempotency": AgentIdempotencyRecord.objects.filter(expires_at__lt=now),
                    "agent_audit": AgentAuditEvent.objects.filter(
                        created_at__lt=now - timedelta(days=90)
                    ),
                    "oauth_audit": OAuthSecurityEvent.objects.filter(
                        created_at__lt=now - timedelta(days=90)
                    ),
                    "rate_limits": RateLimitBucket.objects.filter(
                        window_start__lt=now - timedelta(days=2)
                    ),
                    "stale_dcr_clients": OAuthApplication.objects.filter(
                        registration_source="dcr",
                        created__lt=now - timedelta(days=30),
                        last_used_at__isnull=True,
                        oauthgrant__isnull=True,
                        oauthaccesstoken__isnull=True,
                    ),
                }
                oldest = []
                eligibility_offsets = {
                    "expired_unused_grants": timedelta(0),
                    "consumed_grant_replay_records": refresh_retention,
                    "access_tokens": timedelta(0),
                    "refresh_families": timedelta(0),
                    "pending_authorizations": timedelta(0),
                    "client_metadata": timedelta(0),
                    "idempotency": timedelta(0),
                    "agent_audit": timedelta(days=90),
                    "oauth_audit": timedelta(days=90),
                    "rate_limits": timedelta(days=2),
                    "stale_dcr_clients": timedelta(days=30),
                }
                for name, queryset in targets.items():
                    timestamp_field = {
                        "expired_unused_grants": "expires",
                        "consumed_grant_replay_records": "consumed_at",
                        "access_tokens": "expires",
                        "refresh_families": "expires_at",
                        "pending_authorizations": "expires_at",
                        "client_metadata": "expires_at",
                        "idempotency": "expires_at",
                        "agent_audit": "created_at",
                        "oauth_audit": "created_at",
                        "rate_limits": "window_start",
                        "stale_dcr_clients": "created",
                    }[name]
                    value = queryset.order_by(timestamp_field).values_list(timestamp_field, flat=True).first()
                    if value is not None:
                        eligible_at = value + eligibility_offsets[name]
                        oldest.append(
                            max(0, int((now - eligible_at).total_seconds()))
                        )
                    deleted[name] = self._delete_batch(queryset, batch_size)
            run.completed_at = timezone.now()
            run.success = True
            run.deleted = deleted
            run.duration_ms = int((monotonic() - started) * 1000)
            run.oldest_eligible_seconds = max(oldest, default=0)
            run.save(
                update_fields=[
                    "completed_at",
                    "success",
                    "deleted",
                    "duration_ms",
                    "oldest_eligible_seconds",
                ]
            )
            self.stdout.write(self.style.SUCCESS(f"MCP/OAuth cleanup complete: {deleted}"))
        except Exception as exc:
            run.completed_at = timezone.now()
            run.errors = 1
            run.error_code = type(exc).__name__[:64]
            run.duration_ms = int((monotonic() - started) * 1000)
            run.save(
                update_fields=["completed_at", "errors", "error_code", "duration_ms"]
            )
            send_deduplicated_admin_alert(
                "cleanup_failed", {"error_type": type(exc).__name__}
            )
            raise
