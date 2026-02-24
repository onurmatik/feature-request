from django.contrib.auth import logout
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST


@ensure_csrf_cookie
def me_view(request):
    user = request.user
    if user.is_authenticated:
        payload = {
            "is_authenticated": True,
            "current_user_handle": user.handle,
            "user_id": user.id,
        }
    else:
        payload = {
            "is_authenticated": False,
            "current_user_handle": "",
            "user_id": None,
        }
    return JsonResponse(payload)


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
    return JsonResponse({"ok": True})
