from django.contrib import admin

from .models import OwnerMessage


@admin.register(OwnerMessage)
class OwnerMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "recipient",
        "project",
        "sender_user",
        "sender_email",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = (
        "recipient__handle",
        "sender_user__handle",
        "sender_email",
        "body",
    )
