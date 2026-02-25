from django.contrib import admin
from django.urls import path
from sesame.views import LoginView

from accounts.views import (
    logout_view,
    me_view,
    sign_in_view,
    sign_up_view,
    stripe_webhook,
)
from config.api import api

urlpatterns = [
    path("admin-qweasd123/", admin.site.urls),
    path("auth/me", me_view, name="auth-me"),
    path("auth/sign-in", sign_in_view, name="auth-sign-in"),
    path("auth/sign-up", sign_up_view, name="auth-sign-up"),
    path("auth/logout", logout_view, name="auth-logout"),
    path("stripe/webhook", stripe_webhook, name="stripe-webhook"),
    path("api/", api.urls),
    path("auth/magic-link", LoginView.as_view(), name="magic-link-login"),
]
