from django.contrib import admin, messages
from django.utils.html import format_html_join

from .models import Issue, IssueComment, IssueUpvote, Project
from .api import _resolve_favicon_url_with_debug


@admin.action(description="Refresh selected projects' favicons")
def refresh_project_favicons(modeladmin, request, queryset):
    updated = 0
    skipped = 0
    skipped_details = []
    updated_details = []
    failed_details = []

    for project in queryset:
        if not project.url:
            skipped += 1
            skipped_details.append(f"{project.name} ({project.slug}): no URL")
            continue

        favicon_url, debug = _resolve_favicon_url_with_debug(project.url)
        if not favicon_url:
            failed_details.append(
                f"{project.name} ({project.slug}): no favicon found | {' | '.join(debug or [])}",
            )
            continue

        if project.favicon_url != favicon_url:
            project.favicon_url = favicon_url
            project.save(update_fields=["favicon_url"])
            updated += 1
            updated_details.append(
                f"{project.name} ({project.slug}): {favicon_url} | {' | '.join(debug[-3:])}",
            )

    if updated:
        modeladmin.message_user(
            request,
            f"Updated {updated} project favicon(s).",
            messages.SUCCESS,
        )
    if updated_details:
        modeladmin.message_user(
            request,
            format_html_join(
                "",
                "<div>{}</div>",
                ((item,) for item in updated_details),
            ),
            messages.INFO,
        )

    if failed_details:
        modeladmin.message_user(
            request,
            format_html_join(
                "",
                "<div>{}</div>",
                ((item,) for item in failed_details),
            ),
            messages.ERROR,
        )

    if skipped:
        modeladmin.message_user(
            request,
            f"Skipped {skipped} project(s) because URL was missing.",
            messages.WARNING,
        )
        if skipped_details:
            modeladmin.message_user(
                request,
                format_html_join(
                    "",
                    "<div>{}</div>",
                    ((item,) for item in skipped_details),
                ),
                messages.INFO,
            )


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    actions = [refresh_project_favicons]
    list_display = ("id", "name", "slug", "url", "favicon_url", "owner", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "slug", "url", "owner__email", "owner__handle")
    ordering = ("-created_at",)
    autocomplete_fields = ("owner",)
    readonly_fields = ("slug", "created_at", "updated_at")
    fields = ("owner", "name", "slug", "tagline", "url", "favicon_url", "created_at", "updated_at")


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
