from django.urls import path

from .views import (
    ProjectCreateView,
    ProjectDeleteView,
    ProjectListView,
    ProjectUpdateView,
    PublicBoardView,
)

app_name = "projects"

urlpatterns = [
    path("backend/projects/", ProjectListView.as_view(), name="backend-project-list"),
    path(
        "backend/projects/create/",
        ProjectCreateView.as_view(),
        name="backend-project-create",
    ),
    path(
        "backend/projects/<int:pk>/edit/",
        ProjectUpdateView.as_view(),
        name="backend-project-edit",
    ),
    path(
        "backend/projects/<int:pk>/delete/",
        ProjectDeleteView.as_view(),
        name="backend-project-delete",
    ),
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
