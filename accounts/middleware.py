from django.http import JsonResponse

from .models import ApiToken


class BearerTokenAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/"):
            blocked_response = self._attach_user_from_bearer_token(request)
            if blocked_response is not None:
                return blocked_response
        return self.get_response(request)

    def _attach_user_from_bearer_token(self, request):
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            return

        authorization = str(request.META.get("HTTP_AUTHORIZATION", "")).strip()
        if not authorization:
            return

        scheme, _, raw_token = authorization.partition(" ")
        if scheme.lower() != "bearer":
            return

        api_token = ApiToken.resolve_active(raw_token)
        if api_token is None:
            return

        request.user = api_token.user
        request.auth = api_token
        request.api_token = api_token
        api_token.mark_used()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not api_token.can_write:
            return JsonResponse(
                {"detail": "This token is read-only and cannot perform write actions."},
                status=403,
            )
