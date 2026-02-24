import json
import re

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

HANDLE_REGEX = re.compile(r"^[a-z0-9_]+$")


def _session_payload(user):
    if user.is_authenticated:
        return {
            "is_authenticated": True,
            "current_user_handle": user.handle,
            "user_id": user.id,
        }
    return {
        "is_authenticated": False,
        "current_user_handle": "",
        "user_id": None,
    }


def _json_payload(request):
    try:
        raw_body = request.body.decode("utf-8") if request.body else "{}"
        return json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


@ensure_csrf_cookie
def me_view(request):
    return JsonResponse(_session_payload(request.user))


@require_POST
def sign_in_view(request):
    payload = _json_payload(request)
    if payload is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    email_or_handle = str(payload.get("email_or_handle", "")).strip()
    if not email_or_handle:
        return JsonResponse({"detail": "email_or_handle is required."}, status=400)

    User = get_user_model()
    if "@" in email_or_handle:
        user = User.objects.filter(email__iexact=email_or_handle).first()
    else:
        user = User.objects.filter(handle=email_or_handle.lower()).first()

    if user is None:
        return JsonResponse({"detail": "Account not found. Please sign up first."}, status=404)

    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    return JsonResponse(_session_payload(user))


@require_POST
def sign_up_view(request):
    payload = _json_payload(request)
    if payload is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    email = str(payload.get("email", "")).strip().lower()
    handle = str(payload.get("handle", "")).strip().lower()
    display_name = str(payload.get("display_name", "")).strip()

    if not email:
        return JsonResponse({"detail": "email is required."}, status=400)
    if not handle:
        return JsonResponse({"detail": "handle is required."}, status=400)
    if not HANDLE_REGEX.fullmatch(handle):
        return JsonResponse(
            {
                "detail": "Handle can only include lowercase letters, numbers, and underscore.",
            },
            status=400,
        )

    User = get_user_model()
    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse({"detail": "This email is already registered."}, status=400)
    if User.objects.filter(handle=handle).exists():
        return JsonResponse({"detail": "This handle is already taken."}, status=400)

    user = User.objects.create_user(
        email=email,
        handle=handle,
        display_name=display_name,
    )
    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    return JsonResponse(_session_payload(user), status=201)


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
    return JsonResponse({"ok": True})
