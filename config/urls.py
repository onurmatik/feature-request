from django.contrib import admin
from django.urls import path
from sesame.views import LoginView

from config.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("auth/magic-link/", LoginView.as_view(), name="magic-link-login"),
]
