import hashlib
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from .handles import is_reserved_handle


def gravatar_url_for_email(email: str, size: int = 80) -> str:
    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        return ""

    normalized_size = max(1, min(512, int(size or 80)))
    digest = hashlib.md5(normalized_email.encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?s={normalized_size}&d=mp&r=g"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, handle, password, **extra_fields):
        if not email:
            raise ValueError("Email must be set.")
        if not handle:
            raise ValueError("Handle must be set.")
        if is_reserved_handle(handle):
            raise ValueError("Handle is reserved and cannot be used.")

        email = self.normalize_email(email)
        user = self.model(email=email, handle=handle.lower(), **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_user(self, email, handle, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, handle, password, **extra_fields)

    def create_superuser(self, email, handle, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, handle, password, **extra_fields)


handle_validator = RegexValidator(
    regex=r"^[a-z0-9_]+$",
    message="Handle can only include lowercase letters, numbers, and underscore.",
)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    handle = models.CharField(
        max_length=50,
        unique=True,
        validators=[handle_validator],
        help_text="Used in public URL, e.g. featurerequest.io/onurmatik",
    )
    display_name = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    subscription_tier = models.CharField(
        max_length=20,
        choices=[
            ("free", "Free"),
            ("pro_30", "Pro (30 projects)"),
        ],
        default="free",
    )
    subscription_status = models.CharField(max_length=20, blank=True, default="")
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    stripe_subscription_id = models.CharField(max_length=255, blank=True, default="")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["handle"]

    @property
    def has_active_paid_subscription(self):
        if self.subscription_tier != "pro_30":
            return False

        normalized_status = (self.subscription_status or "").strip().lower()
        # Backward compatibility for legacy paid accounts created before
        # subscription_status was introduced.
        if not normalized_status:
            return True

        return normalized_status in {"active", "trialing"}

    @property
    def project_limit(self):
        return 30 if self.has_active_paid_subscription else 1

    def has_project_limit(self, current_count):
        return int(current_count or 0) >= self.project_limit

    class Meta:
        ordering = ["-date_joined"]

    def save(self, *args, **kwargs):
        self.handle = self.handle.lower()
        self.email = self.__class__.objects.normalize_email(self.email)
        super().save(*args, **kwargs)

    @property
    def avatar_url(self) -> str:
        return gravatar_url_for_email(self.email)

    def __str__(self):
        return self.display_name or self.handle
