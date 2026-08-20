from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from urllib.parse import parse_qsl

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django_embedded_mcp import (
    ClientMetadataError,
    canonical_resource_equal,
    credential_digest,
    fetch_client_metadata_document,
    generate_opaque_credential,
    normalize_scopes,
    parse_client_metadata_document,
)
from oauth2_provider.models import AbstractApplication

from .models import (
    ClientCompatibilityUsageDaily,
    ClientMetadataCache,
    OAuthAccessToken,
    OAuthApplication,
    OAuthConsent,
    OAuthGrant,
    OAuthRefreshFamily,
    OAuthRefreshToken,
    OAuthSecurityEvent,
    PendingAuthorization,
    RateLimitBucket,
)


class OAuthProtocolError(ValueError):
    def __init__(
        self,
        error: str,
        description: str,
        *,
        status: int = 400,
        alert_code: str = "",
    ):
        self.error = error
        self.description = description
        self.status = status
        self.alert_code = alert_code
        super().__init__(description)


def request_id(request) -> str:
    return str(getattr(request, "request_id", "") or "oauth-unknown")


def client_id_digest(client_id: str) -> str:
    return hashlib.sha256(client_id.encode()).hexdigest()


def record_security_event(
    request,
    *,
    event_type: str,
    decision: str,
    client_id: str = "",
    actor_id: str = "",
    scopes=(),
    error_code: str = "",
    details: dict | None = None,
):
    safe_details = dict(details or {})
    safe_details.setdefault(
        "trusted_source_digest",
        credential_digest(_source_ip(request) or "unknown-source"),
    )
    OAuthSecurityEvent.objects.create(
        request_id=request_id(request),
        event_type=event_type,
        actor_id_public=str(actor_id or ""),
        client_id_digest=client_id_digest(client_id) if client_id else "",
        resource="feature-request-mcp",
        scopes=list(scopes),
        decision=decision,
        error_code=error_code,
        details=safe_details,
    )


def _source_ip(request) -> str:
    direct = str(request.META.get("REMOTE_ADDR", ""))
    if direct in settings.FEATURE_REQUEST_TRUSTED_PROXY_IPS:
        forwarded = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))
        if forwarded:
            return forwarded.split(",", 1)[0].strip()[:64]
    return direct[:64]


def _minute(now):
    return now.replace(second=0, microsecond=0)


def enforce_rate_limit(
    request,
    action: str,
    *,
    client_id: str = "",
    verified_client_only: bool = False,
) -> None:
    if action not in {"register", "authorize", "token", "revoke"}:
        raise ValueError("Unknown OAuth rate-limit action.")
    if action == "register":
        bucket_class = "register"
        source_limit, global_limit = 30, 300
    else:
        # Authorization, token and revocation share one public OAuth budget.
        # Separate per-endpoint keys would silently triple the approved limits.
        bucket_class = "oauth"
        source_limit, global_limit = 120, 1200
    if verified_client_only:
        if not client_id:
            raise ValueError("A verified client id is required for the client bucket.")
        keys = [(credential_digest(f"{bucket_class}:client:{client_id}"), 600)]
    else:
        keys = [
            (
                credential_digest(
                    f"{bucket_class}:source:{_source_ip(request)}"
                ),
                source_limit,
            ),
            (credential_digest(f"{bucket_class}:global"), global_limit),
        ]
    window = _minute(timezone.now())
    try:
        with transaction.atomic():
            for key, limit in keys:
                try:
                    with transaction.atomic():
                        bucket, _ = (
                            RateLimitBucket.objects.select_for_update(
                                of=("self",)
                            ).get_or_create(
                                bucket_key=key,
                                window_start=window,
                                defaults={"count": 0},
                            )
                        )
                except IntegrityError:
                    bucket = RateLimitBucket.objects.select_for_update(of=("self",)).get(
                        bucket_key=key,
                        window_start=window,
                    )
                if bucket.count >= limit:
                    raise OAuthProtocolError(
                        "rate_limited", "Too many OAuth requests.", status=429
                    )
                bucket.count = F("count") + 1
                bucket.save(update_fields=["count", "updated_at"])
    except DatabaseError as exc:
        # This path is deliberately independent from request audit. A persistent
        # limiter failure is an availability/security event and must page through
        # the configured operations channel without exposing the failing key.
        try:
            from .operations import send_deduplicated_admin_alert

            send_deduplicated_admin_alert(
                "rate_limit_backend_anomaly",
                {
                    "action": action,
                    "bucket_class": (
                        "verified_client" if verified_client_only else "baseline"
                    ),
                },
            )
        except Exception:
            # Alert delivery must not replace the protocol-safe failure below.
            pass
        raise OAuthProtocolError(
            "temporarily_unavailable",
            "OAuth request limiting is temporarily unavailable.",
            status=503,
        ) from exc


def _fernet() -> Fernet:
    digest = hashlib.sha256(
        f"feature-request-oauth-pending-v1:{settings.SECRET_KEY}".encode()
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _session_digest(request) -> str:
    # Django rotates the session key during login. Bind pending authorization
    # to a random digest carried inside session data so the binding survives
    # that rotation without persisting a raw bearer secret.
    session_key = "mcp_oauth_pending_binding_v1"
    binding = request.session.get(session_key)
    if not isinstance(binding, str) or len(binding) != 64:
        binding = credential_digest(generate_opaque_credential())
        request.session[session_key] = binding
        request.session.modified = True
    return binding


def create_pending_authorization(request, payload: dict) -> str:
    handle = generate_opaque_credential(bytes_of_entropy=24)
    encrypted = _fernet().encrypt(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    )
    PendingAuthorization.objects.create(
        handle_digest=credential_digest(handle),
        session_digest=_session_digest(request),
        encrypted_payload=encrypted,
        expires_at=timezone.now()
        + timedelta(seconds=settings.FEATURE_REQUEST_MCP_PENDING_AUTHORIZATION_TTL_SECONDS),
    )
    return handle


def load_pending_authorization(request, handle: str, *, consume: bool = False) -> dict:
    if not isinstance(handle, str) or len(handle) < 24:
        raise OAuthProtocolError("invalid_request", "Invalid authorization resume handle.")
    queryset = PendingAuthorization.objects
    if consume:
        queryset = queryset.select_for_update(of=("self",))
    pending = queryset.filter(handle_digest=credential_digest(handle)).first()
    now = timezone.now()
    if (
        pending is None
        or pending.consumed_at is not None
        or pending.expires_at <= now
        or pending.session_digest != _session_digest(request)
    ):
        raise OAuthProtocolError("invalid_request", "Authorization request expired or is not valid for this session.")
    try:
        payload = json.loads(_fernet().decrypt(bytes(pending.encrypted_payload)))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthProtocolError("invalid_request", "Authorization request could not be restored.") from exc
    if consume:
        pending.consumed_at = now
        pending.save(update_fields=["consumed_at"])
    return payload


def _application_defaults(document, *, source: str) -> dict:
    return {
        "client_type": AbstractApplication.CLIENT_PUBLIC,
        "authorization_grant_type": AbstractApplication.GRANT_AUTHORIZATION_CODE,
        "client_secret": "",
        "hash_client_secret": False,
        "name": document.client_name,
        "skip_authorization": False,
        "redirect_uris": " ".join(document.redirect_uris),
        "application_type": document.application_type,
        "metadata": document.raw,
        "allowed_scopes": list(document.scopes),
        "callback_profiles": [profile.value for profile in document.callback_profiles],
        "registration_source": source,
        "cimd_expires_at": timezone.now() + timedelta(seconds=document.cache_seconds)
        if source == AbstractApplication.RegistrationSource.CIMD
        else None,
        "last_metadata_fetch_at": timezone.now()
        if source == AbstractApplication.RegistrationSource.CIMD
        else None,
    }


def resolve_client_application(client_id: str) -> OAuthApplication:
    if client_id.startswith("https://"):
        now = timezone.now()
        cache = ClientMetadataCache.objects.filter(client_id=client_id).first()
        try:
            if cache is not None and cache.expires_at > now:
                cached_bytes = json.dumps(
                    cache.document,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                if hashlib.sha256(cached_bytes).hexdigest() != cache.document_sha256:
                    raise ClientMetadataError(
                        "Client metadata cache integrity validation failed."
                    )
                document = parse_client_metadata_document(
                    cache.document,
                    fetched_url=client_id,
                    cache_seconds=max(
                        60, int((cache.expires_at - now).total_seconds())
                    ),
                )
            else:
                document = fetch_client_metadata_document(client_id)
                ClientMetadataCache.objects.update_or_create(
                    client_id=client_id,
                    defaults={
                        "document": document.raw,
                        "document_sha256": hashlib.sha256(
                            json.dumps(
                                document.raw,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ).hexdigest(),
                        "expires_at": now
                        + timedelta(seconds=document.cache_seconds),
                    },
                )
        except ClientMetadataError as exc:
            raise OAuthProtocolError(
                "invalid_client",
                "Client metadata could not be validated.",
            ) from exc
        application, _ = OAuthApplication.objects.update_or_create(
            client_id=client_id,
            defaults=_application_defaults(
                document,
                source=AbstractApplication.RegistrationSource.CIMD,
            ),
        )
    else:
        application = OAuthApplication.objects.filter(
            client_id=client_id,
            registration_source=AbstractApplication.RegistrationSource.DCR,
        ).first()
        if application is None:
            raise OAuthProtocolError("invalid_client", "Unknown public OAuth client.")
    if not application.is_active:
        raise OAuthProtocolError("invalid_client", "OAuth client is revoked.")
    return application


def validate_authorization_payload(payload: dict) -> tuple[OAuthApplication, dict]:
    required = (
        "client_id",
        "redirect_uri",
        "response_type",
        "scope",
        "state",
        "code_challenge",
        "code_challenge_method",
        "resource",
    )
    if any(not isinstance(payload.get(key), str) or not payload[key] for key in required):
        raise OAuthProtocolError("invalid_request", "Required authorization parameters are missing.")
    if payload["response_type"] != "code":
        raise OAuthProtocolError("unsupported_response_type", "Only response_type=code is supported.")
    if payload["code_challenge_method"] != "S256":
        raise OAuthProtocolError("invalid_request", "PKCE S256 is required.")
    challenge = payload["code_challenge"]
    if len(challenge) != 43 or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in challenge):
        raise OAuthProtocolError("invalid_request", "Invalid PKCE code_challenge.")
    if not canonical_resource_equal(payload["resource"], settings.MCP_RESOURCE_URL):
        raise OAuthProtocolError("invalid_target", "The requested resource is not this MCP server.")
    application = resolve_client_application(payload["client_id"])
    if not application.redirect_uri_allowed(payload["redirect_uri"]):
        raise OAuthProtocolError("invalid_request", "redirect_uri is not registered for this client.")
    try:
        requested_scopes = payload["scope"].split()
        if not requested_scopes:
            raise ValueError("At least one OAuth scope is required.")
        scopes = normalize_scopes(
            requested_scopes,
            supported_scopes=settings.FEATURE_REQUEST_MCP_OAUTH_SCOPES,
        )
    except ValueError as exc:
        raise OAuthProtocolError("invalid_scope", str(exc)) from exc
    if not set(scopes).issubset(set(application.allowed_scopes)):
        raise OAuthProtocolError("invalid_scope", "Client is not registered for the requested scopes.")
    normalized = dict(payload)
    normalized["scope"] = " ".join(scopes)
    normalized["resource"] = settings.MCP_RESOURCE_URL
    return application, normalized


def verify_pkce(verifier: str, challenge: str) -> bool:
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    if (
        not isinstance(verifier, str)
        or not 43 <= len(verifier) <= 128
        or any(character not in allowed for character in verifier)
    ):
        return False
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return encoded == challenge


def create_authorization_grant(user, application, payload: dict) -> str:
    raw_code = f"mcp_ac_{generate_opaque_credential()}"
    OAuthConsent.objects.create(
        user=user,
        application=application,
        resource=settings.MCP_RESOURCE_URL,
        scopes=payload["scope"].split(),
        decision=OAuthConsent.Decision.APPROVED,
    )
    OAuthGrant.objects.create(
        user=user,
        application=application,
        code="",
        code_digest=credential_digest(raw_code),
        expires=timezone.now()
        + timedelta(seconds=settings.FEATURE_REQUEST_MCP_AUTHORIZATION_CODE_TTL_SECONDS),
        redirect_uri=payload["redirect_uri"],
        scope=payload["scope"],
        code_challenge=payload["code_challenge"],
        code_challenge_method="S256",
        resource=[settings.MCP_RESOURCE_URL],
    )
    return raw_code


def _has_active_consent(*, user, application, scopes: list[str]) -> bool:
    return any(
        set(scopes).issubset(set(consent.scopes))
        for consent in OAuthConsent.objects.filter(
            user=user,
            application=application,
            resource=settings.MCP_RESOURCE_URL,
            decision=OAuthConsent.Decision.APPROVED,
            revoked_at__isnull=True,
        ).only("scopes")
    )


def _issue_tokens(*, user, application, scopes: list[str], family=None, code_digest="") -> dict:
    now = timezone.now()
    access_raw = f"mcp_at_{generate_opaque_credential()}"
    refresh_raw = f"mcp_rt_{generate_opaque_credential()}"
    if family is None:
        family = OAuthRefreshFamily.objects.create(
            user=user,
            application=application,
            resource=settings.MCP_RESOURCE_URL,
            scopes=scopes,
            authorization_code_digest=code_digest,
        )
    access = OAuthAccessToken.objects.create(
        user=user,
        application=application,
        token="",
        token_checksum=credential_digest(access_raw),
        expires=now + timedelta(seconds=settings.FEATURE_REQUEST_MCP_ACCESS_TOKEN_TTL_SECONDS),
        scope=" ".join(scopes),
        resource=[settings.MCP_RESOURCE_URL],
        authorization_code_digest=code_digest,
    )
    OAuthRefreshToken.objects.create(
        user=user,
        application=application,
        access_token=access,
        token="",
        token_checksum=credential_digest(refresh_raw),
        token_family=family.pk,
        family=family,
        resource=[settings.MCP_RESOURCE_URL],
    )
    OAuthApplication.objects.filter(pk=application.pk).update(last_used_at=now)
    return {
        "access_token": access_raw,
        "token_type": "Bearer",
        "expires_in": settings.FEATURE_REQUEST_MCP_ACCESS_TOKEN_TTL_SECONDS,
        "refresh_token": refresh_raw,
        "scope": " ".join(scopes),
        "resource": settings.MCP_RESOURCE_URL,
    }


def exchange_authorization_code(
    *,
    code: str,
    client_id: str,
    redirect_uri: str,
    verifier: str,
    resource: str,
    on_issued: Callable[[dict], None] | None = None,
) -> dict:
    if not canonical_resource_equal(resource, settings.MCP_RESOURCE_URL):
        raise OAuthProtocolError("invalid_target", "The requested resource is invalid.")
    digest = credential_digest(code)
    rejection: OAuthProtocolError | None = None
    result = None
    with transaction.atomic():
        grant = (
            OAuthGrant.objects.select_for_update(of=("self",))
            .select_related("user", "application")
            .filter(code_digest=digest)
            .first()
        )
        if grant is None:
            raise OAuthProtocolError("invalid_grant", "Authorization code is invalid or expired.")
        if grant.consumed_at is not None:
            grant.replayed_at = timezone.now()
            grant.save(update_fields=["replayed_at"])
            for family in OAuthRefreshFamily.objects.select_for_update(
                of=("self",)
            ).filter(
                authorization_code_digest=grant.code_digest,
                revoked_at__isnull=True,
            ):
                _revoke_family(family, replay=True)
            OAuthAccessToken.objects.filter(
                authorization_code_digest=grant.code_digest,
                revoked_at__isnull=True,
            ).update(revoked_at=timezone.now())
            rejection = OAuthProtocolError(
                "invalid_grant",
                "Authorization code replay revoked issued credentials.",
                alert_code="authorization_code_replay",
            )
        elif grant.expires <= timezone.now():
            rejection = OAuthProtocolError(
                "invalid_grant", "Authorization code is invalid or expired."
            )
        elif (
            grant.application.client_id != client_id
            or grant.redirect_uri != redirect_uri
            or grant.resource != [settings.MCP_RESOURCE_URL]
            or not verify_pkce(verifier, grant.code_challenge)
            or not grant.user.is_active
            or not grant.application.is_active
            or not _has_active_consent(
                user=grant.user,
                application=grant.application,
                scopes=grant.scope.split(),
            )
        ):
            rejection = OAuthProtocolError(
                "invalid_grant", "Authorization code binding is invalid."
            )
        else:
            grant.consumed_at = timezone.now()
            grant.save(update_fields=["consumed_at"])
            result = _issue_tokens(
                user=grant.user,
                application=grant.application,
                scopes=grant.scope.split(),
                code_digest=grant.code_digest,
            )
            if on_issued is not None:
                on_issued(result)
    if rejection is not None:
        raise rejection
    assert result is not None
    return result


def _revoke_family(family, *, replay=False):
    now = timezone.now()
    OAuthRefreshFamily.objects.filter(pk=family.pk).update(
        revoked_at=family.revoked_at or now,
        replayed_at=now if replay else family.replayed_at,
    )
    token_ids = list(family.tokens.values_list("access_token_id", flat=True))
    OAuthRefreshToken.objects.filter(family=family).update(revoked=now, access_token=None)
    OAuthAccessToken.objects.filter(pk__in=[value for value in token_ids if value]).update(
        revoked_at=now
    )


def rotate_refresh_token(
    *,
    refresh_token: str,
    client_id: str,
    resource: str,
    on_issued: Callable[[dict], None] | None = None,
) -> tuple[dict, bool]:
    if not canonical_resource_equal(resource, settings.MCP_RESOURCE_URL):
        raise OAuthProtocolError("invalid_target", "The requested resource is invalid.")
    checksum = credential_digest(refresh_token)
    rejection: OAuthProtocolError | None = None
    result = None
    with transaction.atomic():
        member = (
            OAuthRefreshToken.objects.select_related("family", "application", "user")
            .filter(token_checksum=checksum)
            .first()
        )
        if member is None:
            raise OAuthProtocolError("invalid_grant", "Refresh token is invalid.")
        family = OAuthRefreshFamily.objects.select_for_update(of=("self",)).get(
            pk=member.family_id
        )
        member = OAuthRefreshToken.objects.select_for_update(of=("self",)).get(
            pk=member.pk
        )
        if member.consumed_at is not None or member.revoked is not None:
            _revoke_family(family, replay=True)
            rejection = OAuthProtocolError(
                "invalid_grant",
                "Refresh token replay revoked its family.",
                alert_code="refresh_token_replay",
            )
        elif (
            family.revoked_at is not None
            or family.expires_at <= timezone.now()
            or family.application.client_id != client_id
            or not canonical_resource_equal(family.resource, settings.MCP_RESOURCE_URL)
            or not family.user.is_active
            or not family.application.is_active
            or not _has_active_consent(
                user=family.user,
                application=family.application,
                scopes=list(family.scopes),
            )
        ):
            _revoke_family(family)
            rejection = OAuthProtocolError(
                "invalid_grant", "Refresh family is no longer active."
            )
        else:
            now = timezone.now()
            member.consumed_at = now
            member.revoked = now
            old_access_id = member.access_token_id
            member.access_token = None
            member.save(update_fields=["consumed_at", "revoked", "access_token", "updated"])
            if old_access_id:
                OAuthAccessToken.objects.filter(pk=old_access_id).update(revoked_at=now)
            result = _issue_tokens(
                user=family.user,
                application=family.application,
                scopes=list(family.scopes),
                family=family,
            )
            if on_issued is not None:
                on_issued(result)
    if rejection is not None:
        raise rejection
    assert result is not None
    return result, False


def revoke_presented_token(*, token: str, client_id: str, resource: str) -> dict:
    if not canonical_resource_equal(resource, settings.MCP_RESOURCE_URL):
        raise OAuthProtocolError("invalid_target", "The requested resource is invalid.")
    checksum = credential_digest(token)
    with transaction.atomic():
        refresh = (
            OAuthRefreshToken.objects.select_related("family", "application")
            .filter(token_checksum=checksum)
            .first()
        )
        if refresh is not None and refresh.application.client_id == client_id:
            family = OAuthRefreshFamily.objects.select_for_update(of=("self",)).get(
                pk=refresh.family_id
            )
            _revoke_family(family)
            return {
                "actor_id": str(refresh.user_id),
                "token_kind": "refresh",
                "family_digest": credential_digest(str(family.pk)),
            }
        access = (
            OAuthAccessToken.objects.select_for_update(of=("self",))
            .filter(token_checksum=checksum)
            .first()
        )
        if access is not None and access.application.client_id == client_id:
            access.revoke()
            return {
                "actor_id": str(access.user_id),
                "token_kind": "access",
                "family_digest": "",
            }
    return {"actor_id": "", "token_kind": "unknown", "family_digest": ""}


def revoke_consent_credentials(consent: OAuthConsent) -> None:
    """Revoke every credential bound to a withdrawn consent principal."""

    now = timezone.now()
    with transaction.atomic():
        locked = OAuthConsent.objects.select_for_update(of=("self",)).get(pk=consent.pk)
        if locked.revoked_at is None:
            locked.revoked_at = now
            locked.save(update_fields=["revoked_at", "updated_at"])
        OAuthGrant.objects.filter(
            user=locked.user,
            application=locked.application,
            consumed_at__isnull=True,
        ).update(consumed_at=now)
        OAuthAccessToken.objects.filter(
            user=locked.user,
            application=locked.application,
            revoked_at__isnull=True,
        ).update(revoked_at=now)
        families = OAuthRefreshFamily.objects.select_for_update(of=("self",)).filter(
            user=locked.user,
            application=locked.application,
            revoked_at__isnull=True,
        )
        for family in families:
            _revoke_family(family)


def revoke_application_credentials(application: OAuthApplication) -> None:
    """Revoke a public client and all credentials issued to it."""

    now = timezone.now()
    with transaction.atomic():
        locked = OAuthApplication.objects.select_for_update(of=("self",)).get(
            pk=application.pk
        )
        if locked.revoked_at is None:
            locked.revoked_at = now
            locked.save(update_fields=["revoked_at", "updated"])
        OAuthGrant.objects.filter(
            application=locked,
            consumed_at__isnull=True,
        ).update(consumed_at=now)
        OAuthAccessToken.objects.filter(
            application=locked,
            revoked_at__isnull=True,
        ).update(revoked_at=now)
        for family in OAuthRefreshFamily.objects.select_for_update(of=("self",)).filter(
            application=locked,
            revoked_at__isnull=True,
        ):
            _revoke_family(family)


def resolve_access_token(checksum: str):
    return (
        OAuthAccessToken.objects.select_related("user", "application")
        .filter(token_checksum=checksum)
        .first()
    )


def record_access_token_use(token: OAuthAccessToken) -> None:
    """Record only bearer tokens that passed full verifier validation."""

    now = timezone.now()
    OAuthApplication.objects.filter(pk=token.application_id).update(last_used_at=now)
    surface = client_id_digest(token.application.client_id)
    usage, _ = ClientCompatibilityUsageDaily.objects.get_or_create(
        day=now.date(),
        client_surface_digest=surface,
        registration_method=token.application.registration_source,
    )
    ClientCompatibilityUsageDaily.objects.filter(pk=usage.pk).update(token_uses=F("token_uses") + 1)
