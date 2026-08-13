from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django_embedded_mcp.redirects import redirect_uri_matches
from django_embedded_mcp.resource import canonical_resource_equal
from oauth2_provider.models import (
    AbstractAccessToken,
    AbstractApplication,
    AbstractGrant,
    AbstractIDToken,
    AbstractRefreshToken,
)


def refresh_family_expiry():
    return timezone.now() + timedelta(
        seconds=settings.FEATURE_REQUEST_MCP_REFRESH_FAMILY_TTL_SECONDS
    )


class OAuthApplication(AbstractApplication):
    """Public DCR or CIMD-backed OAuth client."""

    # CIMD clients use an HTTPS URL while DCR clients use an opaque ``frc_``
    # identifier, so URLField would encode the wrong persistence contract.
    client_id = models.CharField(max_length=2048, unique=True, db_index=True)
    application_type = models.CharField(
        max_length=16,
        choices=(("native", "Native"), ("web", "Web")),
    )
    metadata = models.JSONField(default=dict, blank=True)
    allowed_scopes = models.JSONField(default=list)
    callback_profiles = models.JSONField(default=list)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_used_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_metadata_fetch_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        swappable = "OAUTH2_PROVIDER_APPLICATION_MODEL"
        indexes = [
            models.Index(
                fields=["registration_source", "last_used_at"],
                name="fr_oauth_app_cleanup_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(client_type=AbstractApplication.CLIENT_PUBLIC),
                name="fr_oauth_app_public_only",
            ),
            models.CheckConstraint(
                condition=Q(
                    authorization_grant_type=AbstractApplication.GRANT_AUTHORIZATION_CODE
                ),
                name="fr_oauth_app_code_only",
            ),
            models.CheckConstraint(
                condition=Q(client_secret=""),
                name="fr_oauth_app_no_secret",
            ),
            models.CheckConstraint(
                condition=Q(hash_client_secret=False),
                name="fr_oauth_app_no_secret_hash",
            ),
            models.CheckConstraint(
                condition=Q(skip_authorization=False),
                name="fr_oauth_app_consent_required",
            ),
            models.CheckConstraint(
                condition=Q(registration_source__in=["dcr", "cimd"]),
                name="fr_oauth_app_registration_ck",
            ),
        ]

    @property
    def is_active(self):
        return self.revoked_at is None

    def clean(self):
        errors = {}
        if self.client_type != self.CLIENT_PUBLIC:
            errors["client_type"] = "Only public clients are supported."
        if self.authorization_grant_type != self.GRANT_AUTHORIZATION_CODE:
            errors["authorization_grant_type"] = "Only authorization code is supported."
        if self.client_secret or self.hash_client_secret:
            errors["client_secret"] = "Public clients must not store a client secret."
        if self.skip_authorization:
            errors["skip_authorization"] = "Explicit consent is required."
        if self.registration_source not in {
            self.RegistrationSource.DCR,
            self.RegistrationSource.CIMD,
        }:
            errors["registration_source"] = "Only DCR and CIMD registrations are supported."
        if not isinstance(self.allowed_scopes, list) or not self.allowed_scopes:
            errors["allowed_scopes"] = "At least one scope is required."
        if errors:
            raise ValidationError(errors)

    def redirect_uri_allowed(self, uri):
        return any(
            redirect_uri_matches(
                registered,
                uri,
                application_type=self.application_type,
            )
            for registered in self.redirect_uris.split()
        )

    def is_usable(self, request):
        return self.is_active


class OAuthGrant(AbstractGrant):
    """Digest-only, single-use authorization code."""

    code = models.CharField(max_length=1, blank=True, default="", editable=False)
    code_digest = models.CharField(max_length=64, unique=True, editable=False)
    consumed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    replayed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        swappable = "OAUTH2_PROVIDER_GRANT_MODEL"
        indexes = [
            models.Index(fields=["expires", "consumed_at"], name="fr_oauth_grant_cleanup_idx")
        ]
        constraints = [
            models.CheckConstraint(condition=Q(code=""), name="fr_oauth_grant_digest_only"),
            models.CheckConstraint(
                condition=Q(consumed_at__isnull=True) | Q(consumed_at__gte=F("created")),
                name="fr_oauth_grant_consumed_ck",
            ),
        ]


class OAuthIDToken(AbstractIDToken):
    class Meta:
        swappable = "OAUTH2_PROVIDER_ID_TOKEN_MODEL"


class OAuthAccessToken(AbstractAccessToken):
    """Digest-only access token bound to one canonical MCP resource."""

    token = models.TextField(blank=True, default="", editable=False)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    authorization_code_digest = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        swappable = "OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL"
        indexes = [
            models.Index(fields=["expires", "revoked_at"], name="fr_oauth_access_cleanup_idx"),
            models.Index(
                fields=["application", "user", "revoked_at"],
                name="fr_oauth_access_principal_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(token=""), name="fr_oauth_access_digest_only"),
            models.CheckConstraint(
                condition=Q(revoked_at__isnull=True) | Q(revoked_at__gte=F("created")),
                name="fr_oauth_access_revoke_ck",
            ),
        ]

    @property
    def expires_at(self):
        return self.expires

    def is_valid(self, scopes=None):
        active_consent = any(
            set(self.scope.split()).issubset(set(consent.scopes))
            for consent in OAuthConsent.objects.filter(
                user_id=self.user_id,
                application_id=self.application_id,
                resource=settings.MCP_RESOURCE_URL,
                decision=OAuthConsent.Decision.APPROVED,
                revoked_at__isnull=True,
            ).only("scopes")
        )
        return bool(
            self.revoked_at is None
            and self.user_id
            and self.user.is_active
            and self.application_id
            and self.application.is_active
            and len(self.resource) == 1
            and canonical_resource_equal(self.resource[0], settings.MCP_RESOURCE_URL)
            and active_consent
            and super().is_valid(scopes)
        )

    def revoke(self):
        now = timezone.now()
        type(self).objects.filter(pk=self.pk, revoked_at__isnull=True).update(revoked_at=now)
        self.revoked_at = self.revoked_at or now


class OAuthRefreshFamily(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_refresh_families",
    )
    application = models.ForeignKey(
        settings.OAUTH2_PROVIDER_APPLICATION_MODEL,
        on_delete=models.CASCADE,
        related_name="refresh_families",
    )
    resource = models.TextField()
    scopes = models.JSONField(default=list)
    authorization_code_digest = models.CharField(max_length=64, blank=True, db_index=True)
    expires_at = models.DateTimeField(default=refresh_family_expiry, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    replayed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["expires_at", "revoked_at"], name="fr_oauth_family_cleanup_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="fr_oauth_family_expiry_ck",
            )
        ]

    @property
    def active(self):
        return self.revoked_at is None and self.expires_at > timezone.now()


class OAuthRefreshToken(AbstractRefreshToken):
    token = models.TextField(blank=True, default="", editable=False)
    family = models.ForeignKey(
        OAuthRefreshFamily,
        on_delete=models.CASCADE,
        related_name="tokens",
    )
    consumed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        swappable = "OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL"
        indexes = [
            models.Index(
                fields=["family", "consumed_at", "revoked"],
                name="fr_oauth_refresh_family_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(fields=["token_checksum"], name="fr_oauth_refresh_sum_uniq"),
            models.CheckConstraint(condition=Q(token=""), name="fr_oauth_refresh_digest_only"),
            models.CheckConstraint(
                condition=Q(token_family=F("family_id")),
                name="fr_oauth_refresh_family_binding_ck",
            ),
            models.CheckConstraint(
                condition=Q(consumed_at__isnull=True) | Q(consumed_at__gte=F("created")),
                name="fr_oauth_refresh_consumed_ck",
            ),
        ]


class OAuthConsent(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        DENIED = "denied", "Denied"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    application = models.ForeignKey(OAuthApplication, on_delete=models.CASCADE)
    resource = models.TextField()
    scopes = models.JSONField(default=list)
    decision = models.CharField(max_length=16, choices=Decision.choices)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "application", "resource", "revoked_at"],
                name="fr_oauth_consent_binding_idx",
            )
        ]


class PendingAuthorization(models.Model):
    handle_digest = models.CharField(max_length=64, unique=True)
    session_digest = models.CharField(max_length=64, db_index=True)
    encrypted_payload = models.BinaryField()
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ClientMetadataCache(models.Model):
    client_id = models.URLField(max_length=2048, unique=True)
    document = models.JSONField(default=dict)
    document_sha256 = models.CharField(max_length=64)
    expires_at = models.DateTimeField(db_index=True)
    fetched_at = models.DateTimeField(auto_now=True)


class OAuthSecurityEvent(models.Model):
    request_id = models.CharField(max_length=128, db_index=True)
    event_type = models.CharField(max_length=64, db_index=True)
    actor_id_public = models.CharField(max_length=128, blank=True)
    client_id_digest = models.CharField(max_length=64, blank=True, db_index=True)
    resource = models.TextField(blank=True)
    scopes = models.JSONField(default=list)
    decision = models.CharField(max_length=32)
    error_code = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class RateLimitBucket(models.Model):
    bucket_key = models.CharField(max_length=64)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["bucket_key", "window_start"], name="fr_oauth_rate_bucket_uniq"
            )
        ]
        indexes = [
            models.Index(fields=["window_start"], name="fr_oauth_rate_cleanup_idx")
        ]


class OAuthCleanupRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    success = models.BooleanField(default=False, db_index=True)
    deleted = models.JSONField(default=dict)
    errors = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    oldest_eligible_seconds = models.PositiveIntegerField(default=0)
    scheduler = models.CharField(max_length=64, default="management_command")
    error_code = models.CharField(max_length=64, blank=True)


class ClientCompatibilityUsageDaily(models.Model):
    day = models.DateField()
    client_surface_digest = models.CharField(max_length=64)
    registration_method = models.CharField(max_length=16)
    registrations = models.PositiveIntegerField(default=0)
    token_uses = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["day", "client_surface_digest", "registration_method"],
                name="fr_oauth_compat_daily_uniq",
            )
        ]
