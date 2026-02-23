from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "owner", "visibility", "created_at")
    list_filter = ("visibility", "created_at")
    search_fields = ("name", "slug", "owner__email", "owner__handle")
    ordering = ("-created_at",)
    autocomplete_fields = ("owner",)
    prepopulated_fields = {"slug": ("name",)}
