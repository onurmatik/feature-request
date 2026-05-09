import json

from django.conf import settings
from django.http import HttpResponseNotFound
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie


RESERVED_BACKEND_PREFIXES = {"api", "api-docs", "auth", "stripe"}


def _frontend_session_payload(user):
    if user.is_authenticated:
        return {
            "isAuthenticated": True,
            "currentUserHandle": user.handle,
            "currentUserAvatarUrl": user.avatar_url,
            "user_id": user.id,
            "subscription_tier": user.subscription_tier,
            "subscription_status": user.subscription_status,
            "project_limit": user.project_limit,
        }

    return {
        "isAuthenticated": False,
        "currentUserHandle": "",
        "currentUserAvatarUrl": "",
        "user_id": None,
        "subscription_tier": "free",
        "subscription_status": "",
        "project_limit": 1,
    }


@ensure_csrf_cookie
def frontend_app(request, spa_path=""):
    first_segment = str(spa_path or "").strip("/").split("/", 1)[0]
    if first_segment in RESERVED_BACKEND_PREFIXES:
        return HttpResponseNotFound("Not found.")

    bootstrap = _frontend_session_payload(request.user)
    return render(
        request,
        "projects/app.html",
        {
            "admin_url": settings.ADMIN_URL,
            "fr_bootstrap_json": json.dumps(bootstrap),
            "spa_path": spa_path,
        },
    )
