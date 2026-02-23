from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

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
