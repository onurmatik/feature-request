import re
from uuid import uuid4


_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        candidate = str(request.META.get("HTTP_X_REQUEST_ID", ""))
        request.request_id = candidate if _REQUEST_ID.fullmatch(candidate) else uuid4().hex
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response
