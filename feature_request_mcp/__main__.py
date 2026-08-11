from django.conf import settings

from .server import mcp


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=settings.FEATURE_REQUEST_MCP_HOST,
        port=settings.FEATURE_REQUEST_MCP_PORT,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )
