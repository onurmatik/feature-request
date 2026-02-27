from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.db.models import Count

from .models import ApiToken, User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "handle", "display_name")


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User

    list_display = (
        "id",
        "email",
        "handle",
        "display_name",
        "project_count",
        "request_count",
        "is_staff",
        "is_active",
        "date_joined",
        "subscription_tier",
        "subscription_status",
    )
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "handle", "display_name")
    ordering = ("id",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _project_count=Count("projects", distinct=True),
            _request_count=Count("issues", distinct=True),
        )

    @admin.display(ordering="_project_count", description="Projects")
    def project_count(self, obj):
        return obj._project_count

    @admin.display(ordering="_request_count", description="Requests")
    def request_count(self, obj):
        return obj._request_count

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("handle", "display_name")}),
        ("Billing", {"fields": ("subscription_tier", "subscription_status", "stripe_customer_id", "stripe_subscription_id")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "handle",
                    "display_name",
                    "subscription_tier",
                    "subscription_status",
                    "stripe_customer_id",
                    "stripe_subscription_id",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                    "is_active",
                ),
            },
        ),
    )


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "name",
        "can_write",
        "token_prefix",
        "created_at",
        "last_used_at",
        "revoked_at",
    )
    search_fields = (
        "user__email",
        "user__handle",
        "name",
        "token_prefix",
    )
    list_filter = ("can_write", "revoked_at", "created_at")
    readonly_fields = (
        "token_prefix",
        "token_hash",
        "created_at",
        "last_used_at",
        "revoked_at",
    )
