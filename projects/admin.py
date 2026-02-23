from django.contrib import admin

from .models import Issue, IssueComment, IssueUpvote, Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "owner", "visibility", "created_at")
    list_filter = ("visibility", "created_at")
    search_fields = ("name", "slug", "owner__email", "owner__handle")
    ordering = ("-created_at",)
    autocomplete_fields = ("owner",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "project",
        "issue_type",
        "status",
        "priority",
        "author",
        "created_at",
    )
    list_filter = ("issue_type", "status", "priority", "created_at")
    search_fields = ("title", "description", "project__name", "project__slug")
    ordering = ("-created_at",)
    autocomplete_fields = ("project", "author")


@admin.register(IssueUpvote)
class IssueUpvoteAdmin(admin.ModelAdmin):
    list_display = ("id", "issue", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("issue__title", "user__email", "user__handle")
    ordering = ("-created_at",)
    autocomplete_fields = ("issue", "user")


@admin.register(IssueComment)
class IssueCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "issue", "author", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("body", "issue__title", "author__email", "author__handle")
    ordering = ("-created_at",)
    autocomplete_fields = ("issue", "author")
