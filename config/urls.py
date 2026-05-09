from django.conf import settings
from django.contrib import admin
from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from sesame.views import LoginView

from accounts.views import (
    logout_view,
    feature_request_skill_catalog,
    me_view,
    sign_in_view,
    sign_up_view,
    stripe_webhook,
)
from config.api import api
from projects.views import frontend_app


urlpatterns = [
    path(settings.ADMIN_URL.lstrip("/"), admin.site.urls),
    path("auth/me", me_view, name="auth-me"),
    path("auth/sign-in", sign_in_view, name="auth-sign-in"),
    path("auth/sign-up", sign_up_view, name="auth-sign-up"),
    path("auth/logout", logout_view, name="auth-logout"),
    path(
        "favicon.ico",
        RedirectView.as_view(url=static("projects/favicon.svg"), permanent=True),
        name="favicon",
    ),
    path("stripe/webhook", stripe_webhook, name="stripe-webhook"),
    path(
        "api-docs/swagger.json",
        RedirectView.as_view(url="/api/openapi.json", permanent=False),
        name="legacy-swagger-json",
    ),
    path("api/", api.urls),
    path("auth/magic-link", LoginView.as_view(), name="magic-link-login"),
    path("SKILL.md", feature_request_skill_catalog, name="feature-request-skill-catalog-legacy"),
    path(
        ".agents/skills/feature-request/SKILL.md",
        feature_request_skill_catalog,
        name="feature-request-skill-catalog",
    ),
    path("", frontend_app, name="frontend-app"),
    path("<path:spa_path>", frontend_app, name="frontend-app-catchall"),
]
