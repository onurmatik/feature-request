from django.apps import AppConfig


class McpOauthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mcp_oauth"

    def ready(self):
        from . import signals  # noqa: F401
