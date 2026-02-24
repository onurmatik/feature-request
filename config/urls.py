from django.contrib import admin
from django.urls import path
from sesame.views import LoginView

from accounts.views import logout_view, me_view
from config.api import api

urlpatterns = [
    path("admin-qweasd123/", admin.site.urls),
    path("auth/me", me_view, name="auth-me"),
    path("auth/logout", logout_view, name="auth-logout"),
    path("api/", api.urls),
    path("auth/magic-link", LoginView.as_view(), name="magic-link-login"),
]
