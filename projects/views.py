from django.contrib.auth import get_user_model
from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from .models import Project


class PublicBoardView(TemplateView):
    template_name = "projects/public/board.html"

    def dispatch(self, request, *args, **kwargs):
        owner_handle = kwargs["owner_handle"].lower()
        User = get_user_model()
        self.owner = get_object_or_404(User, handle=owner_handle)
        self.project_slug = kwargs.get("project_slug")

        if self.project_slug:
            queryset = Project.objects.filter(owner=self.owner, slug=self.project_slug)
            if request.user.is_authenticated and request.user.id == self.owner.id:
                has_access = queryset.exists()
            else:
                has_access = queryset.filter(
                    visibility=Project.Visibility.PUBLIC
                ).exists()
            if not has_access:
                raise Http404("Project not found.")

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["owner_handle"] = self.owner.handle
        context["initial_project_slug"] = self.project_slug or ""
        context["frontend_dev_server_url"] = settings.FRONTEND_DEV_SERVER_URL
        return context
