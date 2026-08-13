from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.utils import timezone
from django_embedded_mcp import (
    DynamicClientRegistrationError,
    build_authorization_server_metadata,
    build_protected_resource_metadata,
    canonical_resource_from_pairs,
    credential_digest,
    generate_opaque_credential,
    parse_public_client_registration,
)
from oauth2_provider.models import AbstractApplication

from .models import (
    ClientCompatibilityUsageDaily,
    OAuthAccessToken,
    OAuthApplication,
    OAuthConsent,
    OAuthRefreshToken,
)
from .operations import send_deduplicated_admin_alert
from .services import (
    OAuthProtocolError,
    client_id_digest,
    create_authorization_grant,
    create_pending_authorization,
    enforce_rate_limit,
    exchange_authorization_code,
    load_pending_authorization,
    record_security_event,
    resolve_client_application,
    revoke_presented_token,
    rotate_refresh_token,
    validate_authorization_payload,
)


def _public_json(payload, *, status=200, cache="public, max-age=300"):
    response = JsonResponse(payload, status=status)
    response["Access-Control-Allow-Origin"] = "*"
    response["Cache-Control"] = cache
    return response


def _no_store(response):
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


def _oauth_error(exc: OAuthProtocolError | DynamicClientRegistrationError):
    description = getattr(exc, "description", str(exc))
    response = JsonResponse({"error": exc.error, "error_description": description}, status=exc.status)
    if exc.status == 429:
        response["Retry-After"] = "60"
    return _no_store(response)


def _oauth_redirect(redirect_uri: str, payload: dict[str, str]):
    separator = "&" if "?" in redirect_uri else "?"
    return _no_store(redirect(f"{redirect_uri}{separator}{urlencode(payload)}"))


@require_GET
def authorization_server_metadata(request):
    return _public_json(
        build_authorization_server_metadata(
            issuer=settings.OAUTH_ISSUER,
            scopes_supported=settings.FEATURE_REQUEST_MCP_OAUTH_SCOPES,
        )
    )


@require_GET
def protected_resource_metadata(request):
    return _public_json(
        build_protected_resource_metadata(
            resource=settings.MCP_RESOURCE_URL,
            authorization_server=settings.OAUTH_ISSUER,
            scopes_supported=settings.FEATURE_REQUEST_MCP_BOOTSTRAP_SCOPES,
            resource_name="FeatureRequest MCP",
        )
    )


def _one(values, name, *, required=True):
    found = values.getlist(name)
    if not found and not required:
        return ""
    if len(found) != 1 or not found[0]:
        raise OAuthProtocolError("invalid_request", f"{name} must occur exactly once.")
    return found[0]


def _authorization_query(query):
    pairs = [(key, value) for key, values in query.lists() for value in values]
    try:
        _, resource = canonical_resource_from_pairs(pairs, expected=settings.MCP_RESOURCE_URL)
    except ValueError as exc:
        raise OAuthProtocolError("invalid_target", str(exc)) from exc
    return {
        "client_id": _one(query, "client_id"),
        "redirect_uri": _one(query, "redirect_uri"),
        "response_type": _one(query, "response_type"),
        "scope": _one(query, "scope"),
        "state": _one(query, "state"),
        "code_challenge": _one(query, "code_challenge"),
        "code_challenge_method": _one(query, "code_challenge_method"),
        "resource": resource,
    }


def _authorization_error_target(query):
    """Return a redirect target only after exact client/URI validation.

    OAuth errors must never turn an attacker-provided URI into an open redirect.
    This deliberately validates only the client binding first; all remaining
    request errors can then be returned to that trusted callback with ``iss``.
    """

    try:
        client_id = _one(query, "client_id")
        redirect_uri = _one(query, "redirect_uri")
        application = resolve_client_application(client_id)
    except OAuthProtocolError:
        return None
    if not application.redirect_uri_allowed(redirect_uri):
        return None
    states = query.getlist("state")
    state = states[0] if len(states) == 1 else ""
    return redirect_uri, state


def _login_redirect(handle):
    resume_path = f"{reverse('oauth-authorize')}?{urlencode({'resume': handle})}"
    return redirect(f"/sign-in?{urlencode({'next': resume_path})}")


def _verified_client_hostnames(application: OAuthApplication) -> str:
    if application.client_id.startswith("https://"):
        return urlsplit(application.client_id).hostname or "verified client"
    hosts = sorted(
        {
            urlsplit(uri).hostname
            for uri in application.redirect_uris.split()
            if urlsplit(uri).hostname
        }
    )
    return ", ".join(hosts) or "registered public client"


@require_http_methods(["GET", "POST"])
def authorize(request):
    error_target = None
    try:
        if request.method == "GET":
            enforce_rate_limit(request, "authorize")
            resume = request.GET.get("resume", "")
            if resume:
                payload = load_pending_authorization(request, resume)
                application, payload = validate_authorization_payload(payload)
                enforce_rate_limit(
                    request,
                    "authorize",
                    client_id=application.client_id,
                    verified_client_only=True,
                )
                error_target = (payload["redirect_uri"], payload["state"])
                handle = resume
            else:
                error_target = _authorization_error_target(request.GET)
                payload = _authorization_query(request.GET)
                application, payload = validate_authorization_payload(payload)
                enforce_rate_limit(
                    request,
                    "authorize",
                    client_id=application.client_id,
                    verified_client_only=True,
                )
                handle = create_pending_authorization(request, payload)
            if not request.user.is_authenticated:
                return _no_store(_login_redirect(handle))
            response = render(
                request,
                "mcp_oauth/consent.html",
                {
                    "client_name": application.name,
                    "client_hostname": _verified_client_hostnames(application),
                    "resource": settings.MCP_RESOURCE_URL,
                    "scopes": payload["scope"].split(),
                    "resume": handle,
                },
            )
            response["X-Robots-Tag"] = "noindex, nofollow"
            response["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'unsafe-inline'; "
                "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
            )
            response["Referrer-Policy"] = "no-referrer"
            return _no_store(response)

        if not request.user.is_authenticated:
            raise OAuthProtocolError("access_denied", "Authentication is required.", status=401)
        enforce_rate_limit(request, "authorize")
        handle = str(request.POST.get("resume", ""))
        decision = str(request.POST.get("decision", ""))
        with transaction.atomic():
            payload = load_pending_authorization(request, handle, consume=True)
            application, payload = validate_authorization_payload(payload)
            enforce_rate_limit(
                request,
                "authorize",
                client_id=application.client_id,
                verified_client_only=True,
            )
            redirect_uri = payload["redirect_uri"]
            error_target = (redirect_uri, payload["state"])
            if decision not in {"allow", "deny"}:
                record_security_event(
                    request,
                    event_type="consent",
                    decision="rejected",
                    client_id=application.client_id,
                    actor_id=request.user.pk,
                    scopes=payload["scope"].split(),
                    error_code="invalid_request",
                )
                query = {
                    "error": "invalid_request",
                    "error_description": "Consent decision is required.",
                    "state": payload["state"],
                    "iss": settings.OAUTH_ISSUER,
                }
            elif decision == "deny":
                OAuthConsent.objects.create(
                    user=request.user,
                    application=application,
                    resource=settings.MCP_RESOURCE_URL,
                    scopes=payload["scope"].split(),
                    decision=OAuthConsent.Decision.DENIED,
                )
                record_security_event(
                    request,
                    event_type="consent",
                    decision="denied",
                    client_id=application.client_id,
                    actor_id=request.user.pk,
                    scopes=payload["scope"].split(),
                    details={
                        "redirect_uri_digest": credential_digest(
                            payload["redirect_uri"]
                        )
                    },
                )
                query = {
                    "error": "access_denied",
                    "state": payload["state"],
                    "iss": settings.OAUTH_ISSUER,
                }
            else:
                code = create_authorization_grant(request.user, application, payload)
                record_security_event(
                    request,
                    event_type="consent",
                    decision="approved",
                    client_id=application.client_id,
                    actor_id=request.user.pk,
                    scopes=payload["scope"].split(),
                    details={
                        "redirect_uri_digest": credential_digest(
                            payload["redirect_uri"]
                        )
                    },
                )
                query = {
                    "code": code,
                    "state": payload["state"],
                    "iss": settings.OAUTH_ISSUER,
                }
        return _oauth_redirect(redirect_uri, query)
    except OAuthProtocolError as exc:
        record_security_event(
            request,
            event_type="authorize",
            decision="rejected",
            error_code=exc.error,
        )
        if exc.alert_code:
            send_deduplicated_admin_alert(
                exc.alert_code,
                {"request_id": str(getattr(request, "request_id", ""))[:128]},
            )
        if error_target is not None:
            redirect_uri, state = error_target
            query = {
                "error": exc.error,
                "error_description": exc.description,
                "iss": settings.OAUTH_ISSUER,
            }
            if state:
                query["state"] = state
            return _oauth_redirect(redirect_uri, query)
        return _oauth_error(exc)


@csrf_exempt
@require_POST
def register(request):
    try:
        enforce_rate_limit(request, "register")
        if request.content_type != "application/json" and not request.content_type.endswith(
            "+json"
        ):
            raise DynamicClientRegistrationError(
                "invalid_client_metadata",
                "Registration requests must use a JSON content type.",
            )
        registration = parse_public_client_registration(
            request.body,
            supported_scopes=settings.FEATURE_REQUEST_MCP_OAUTH_SCOPES,
            default_scopes=settings.FEATURE_REQUEST_MCP_BOOTSTRAP_SCOPES,
        )
        client_id = f"frc_{generate_opaque_credential(bytes_of_entropy=24)}"
        with transaction.atomic():
            application = OAuthApplication.objects.create(
                client_id=client_id,
                client_type=AbstractApplication.CLIENT_PUBLIC,
                authorization_grant_type=AbstractApplication.GRANT_AUTHORIZATION_CODE,
                client_secret="",
                hash_client_secret=False,
                name=registration.client_name,
                skip_authorization=False,
                redirect_uris=" ".join(registration.redirect_uris),
                application_type=registration.application_type,
                metadata=dict(registration.metadata),
                allowed_scopes=list(registration.scopes),
                callback_profiles=[
                    profile.value for profile in registration.callback_profiles
                ],
                registration_source=AbstractApplication.RegistrationSource.DCR,
            )
            usage, _ = ClientCompatibilityUsageDaily.objects.get_or_create(
                day=timezone.now().date(),
                client_surface_digest=client_id_digest(client_id),
                registration_method="dcr",
            )
            ClientCompatibilityUsageDaily.objects.filter(pk=usage.pk).update(
                registrations=F("registrations") + 1
            )
            record_security_event(
                request,
                event_type="client_registration",
                decision="approved",
                client_id=client_id,
                scopes=registration.scopes,
                details={
                    "method": "dcr",
                    "application_type": registration.application_type,
                    "redirect_count": len(registration.redirect_uris),
                    "redirect_uri_digests": [
                        credential_digest(uri) for uri in registration.redirect_uris
                    ],
                },
            )
        return _no_store(
            JsonResponse(
                {
                    "client_id": application.client_id,
                    "client_id_issued_at": int(application.created.timestamp()),
                    "client_name": application.name,
                    "redirect_uris": registration.redirect_uris,
                    "application_type": application.application_type,
                    "token_endpoint_auth_method": "none",
                    "response_types": ["code"],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "scope": " ".join(registration.scopes),
                },
                status=201,
            )
        )
    except (OAuthProtocolError, DynamicClientRegistrationError) as exc:
        record_security_event(
            request,
            event_type="client_registration",
            decision="rejected",
            error_code=exc.error,
        )
        return _oauth_error(exc)


def _form_pairs(request):
    if request.content_type != "application/x-www-form-urlencoded":
        raise OAuthProtocolError("invalid_request", "OAuth token requests must use form encoding.")
    try:
        return parse_qsl(request.body.decode("utf-8"), keep_blank_values=True, strict_parsing=True)
    except (UnicodeDecodeError, ValueError) as exc:
        raise OAuthProtocolError("invalid_request", "Malformed form body.") from exc


def _form_one(pairs, name, *, required=True):
    values = [value for key, value in pairs if key == name]
    if not values and not required:
        return ""
    if len(values) != 1 or not values[0]:
        raise OAuthProtocolError("invalid_request", f"{name} must occur exactly once.")
    return values[0]


def _form_resource(pairs):
    try:
        _, resource = canonical_resource_from_pairs(pairs, expected=settings.MCP_RESOURCE_URL)
    except ValueError as exc:
        raise OAuthProtocolError("invalid_target", str(exc)) from exc
    return resource


def _reject_confidential_client_auth(request, pairs):
    if request.META.get("HTTP_AUTHORIZATION") or any(
        key
        in {
            "client_secret",
            "client_assertion",
            "client_assertion_type",
        }
        for key, _ in pairs
    ):
        raise OAuthProtocolError(
            "invalid_client",
            "Only public clients using token_endpoint_auth_method=none are supported.",
        )


@csrf_exempt
@require_POST
def token(request):
    client_id = ""
    grant_type = ""
    try:
        pairs = _form_pairs(request)
        client_id = _form_one(pairs, "client_id")
        enforce_rate_limit(request, "token")
        _reject_confidential_client_auth(request, pairs)
        resource = _form_resource(pairs)
        grant_type = _form_one(pairs, "grant_type")
        application = resolve_client_application(client_id)
        enforce_rate_limit(
            request,
            "token",
            client_id=application.client_id,
            verified_client_only=True,
        )

        def audit_issued(result):
            record_security_event(
                request,
                event_type="token",
                decision="issued",
                client_id=client_id,
                actor_id=OAuthAccessToken.objects.only("user_id").get(
                    token_checksum=credential_digest(result["access_token"])
                ).user_id,
                scopes=result["scope"].split(),
                details={
                    "grant_type": grant_type,
                    "family_digest": credential_digest(
                        str(
                            OAuthRefreshToken.objects.only("family_id").get(
                                token_checksum=credential_digest(
                                    result["refresh_token"]
                                )
                            ).family_id
                        )
                    ),
                },
            )

        if grant_type == "authorization_code":
            result = exchange_authorization_code(
                code=_form_one(pairs, "code"),
                client_id=client_id,
                redirect_uri=_form_one(pairs, "redirect_uri"),
                verifier=_form_one(pairs, "code_verifier"),
                resource=resource,
                on_issued=audit_issued,
            )
        elif grant_type == "refresh_token":
            result, _ = rotate_refresh_token(
                refresh_token=_form_one(pairs, "refresh_token"),
                client_id=client_id,
                resource=resource,
                on_issued=audit_issued,
            )
        else:
            raise OAuthProtocolError("unsupported_grant_type", "Unsupported grant_type.")
        return _no_store(JsonResponse(result))
    except OAuthProtocolError as exc:
        record_security_event(
            request,
            event_type="token",
            decision="rejected",
            client_id=client_id,
            error_code=exc.error,
        )
        if exc.alert_code:
            send_deduplicated_admin_alert(
                exc.alert_code,
                {"request_id": str(getattr(request, "request_id", ""))[:128]},
            )
        return _oauth_error(exc)


@csrf_exempt
@require_POST
def revoke(request):
    client_id = ""
    try:
        pairs = _form_pairs(request)
        client_id = _form_one(pairs, "client_id")
        enforce_rate_limit(request, "revoke")
        _reject_confidential_client_auth(request, pairs)
        resource = _form_resource(pairs)
        application = resolve_client_application(client_id)
        enforce_rate_limit(
            request,
            "revoke",
            client_id=application.client_id,
            verified_client_only=True,
        )
        with transaction.atomic():
            outcome = revoke_presented_token(
                token=_form_one(pairs, "token"),
                client_id=client_id,
                resource=resource,
            )
            record_security_event(
                request,
                event_type="revoke",
                decision="completed",
                client_id=client_id,
                actor_id=outcome["actor_id"],
                details={
                    "token_kind": outcome["token_kind"],
                    "family_digest": outcome["family_digest"],
                },
            )
        return _no_store(HttpResponse(status=200))
    except OAuthProtocolError as exc:
        record_security_event(
            request,
            event_type="revoke",
            decision="rejected",
            client_id=client_id,
            error_code=exc.error,
        )
        return _oauth_error(exc)
