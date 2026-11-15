from django.conf import settings


class HSTSMiddleware:
    """Apply Django's HSTS policy to the separate MCP ASGI application."""

    def __init__(self, app):
        self.app = app
        self.header = None
        if settings.SECURE_HSTS_SECONDS:
            value = f"max-age={settings.SECURE_HSTS_SECONDS}"
            if settings.SECURE_HSTS_INCLUDE_SUBDOMAINS:
                value += "; includeSubDomains"
            if settings.SECURE_HSTS_PRELOAD:
                value += "; preload"
            self.header = value.encode("ascii")
        self.trusted_proxy_ips = settings.FEATURE_REQUEST_TRUSTED_PROXY_IPS

    def is_secure(self, scope):
        if scope.get("scheme") == "https":
            return True
        client = scope.get("client")
        if not client or client[0] not in self.trusted_proxy_ips:
            return False
        # Uvicorn deliberately leaves proxy_headers disabled. Only the known
        # proxy may attest to TLS, and duplicate/ambiguous values fail closed.
        forwarded = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"x-forwarded-proto"
        ]
        return forwarded == [b"https"]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.header or not self.is_secure(scope):
            await self.app(scope, receive, send)
            return

        async def send_with_hsts(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(name.lower() == b"strict-transport-security" for name, _ in headers):
                    headers.append((b"strict-transport-security", self.header))
                    message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_hsts)
