from django.contrib import admin
from django.urls import path
from sesame.views import LoginView

from config.api import api
from projects.views import PublicBoardView

urlpatterns = [
    path("admin-qweasd123/", admin.site.urls),
    path("api/", api.urls),
    path("auth/magic-link/", LoginView.as_view(), name="magic-link-login"),
    path(
        "<str:owner_handle>/<slug:project_slug>/",
        PublicBoardView.as_view(),
        name="public-project-board",
    ),
    path(
        "<str:owner_handle>/",
        PublicBoardView.as_view(),
        name="public-owner-board",
    ),
]
