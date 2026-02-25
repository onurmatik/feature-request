from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import User


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
        "is_staff",
        "is_active",
        "date_joined",
        "subscription_tier",
        "subscription_status",
    )
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("email", "handle", "display_name")
    ordering = ("id",)

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
