import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.conf import settings
import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "feature_request_mcp.asgi:application",
        host=settings.FEATURE_REQUEST_MCP_HOST,
        port=settings.FEATURE_REQUEST_MCP_PORT,
        proxy_headers=False,
        access_log=False,
    )
