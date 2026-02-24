from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from .forms import ProjectForm
from .models import Project


class ProjectListView(LoginRequiredMixin, ListView):
    login_url = "/admin/login/"
    model = Project
    context_object_name = "projects"
    template_name = "projects/backend/project_list.html"

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user).order_by("-created_at")


class ProjectCreateView(LoginRequiredMixin, CreateView):
    login_url = "/admin/login/"
    form_class = ProjectForm
    template_name = "projects/backend/project_form.html"
    success_url = reverse_lazy("projects:backend-project-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "Project created.")
        return response


class ProjectUpdateView(LoginRequiredMixin, UpdateView):
    login_url = "/admin/login/"
    form_class = ProjectForm
    template_name = "projects/backend/project_form.html"
    success_url = reverse_lazy("projects:backend-project-list")

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Project updated.")
        return response


class ProjectDeleteView(LoginRequiredMixin, DeleteView):
    login_url = "/admin/login/"
    model = Project
    template_name = "projects/backend/project_confirm_delete.html"
    success_url = reverse_lazy("projects:backend-project-list")

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Project deleted.")
        return super().form_valid(form)


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
        context["frontend_use_dev_server"] = settings.FRONTEND_USE_DEV_SERVER
        context["frontend_dev_server_url"] = settings.FRONTEND_DEV_SERVER_URL
        return context
