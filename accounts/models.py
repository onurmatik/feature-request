import hashlib
import secrets
from datetime import timedelta

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
        self.handle = (self.handle or "").lower()
        self.email = self.__class__.objects.normalize_email(self.email)
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def avatar_url(self) -> str:
        return gravatar_url_for_email(self.email)

    def __str__(self):
        return self.display_name or self.handle


class ApiToken(models.Model):
    AGENT_TOKEN_NAME = "Agent token"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="api_tokens",
    )
    name = models.CharField(max_length=120, default="Agent token")
    can_write = models.BooleanField(default=True)
    is_agent = models.BooleanField(default=False, db_index=True)
    token_prefix = models.CharField(max_length=16, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        normalized = str(raw_token or "").strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_raw_token() -> str:
        return f"fr_{secrets.token_urlsafe(32)}"

    @classmethod
    def issue(
        cls,
        user,
        name: str = "",
        can_write: bool = True,
        is_agent: bool = False,
    ):
        raw_token = cls._generate_raw_token()
        clean_name = (name or "").strip() or "Agent token"
        token = cls.objects.create(
            user=user,
            name=clean_name,
            can_write=bool(can_write),
            is_agent=bool(is_agent),
            token_prefix=raw_token[:12],
            token_hash=cls._hash_token(raw_token),
        )
        return token, raw_token

    @classmethod
    def resolve_active_agent(cls, user):
        tokens = list(
            cls.objects.filter(
                user=user,
                is_agent=True,
                revoked_at__isnull=True,
            ).order_by("-created_at", "-id")
        )
        if not tokens:
            return None

        primary = tokens[0]
        extras = tokens[1:]
        if extras:
            cls.objects.filter(id__in=[token.id for token in extras]).update(
                revoked_at=timezone.now()
            )
        return primary

    @classmethod
    def ensure_agent_token(cls, user):
        token = cls.resolve_active_agent(user)
        if token is None:
            token, raw_token = cls.issue(
                user=user,
                name=cls.AGENT_TOKEN_NAME,
                can_write=True,
                is_agent=True,
            )
            return token, raw_token, True

        updated_fields = []
        if token.name != cls.AGENT_TOKEN_NAME:
            token.name = cls.AGENT_TOKEN_NAME
            updated_fields.append("name")
        if not token.can_write:
            token.can_write = True
            updated_fields.append("can_write")
        if not token.is_agent:
            token.is_agent = True
            updated_fields.append("is_agent")
        if updated_fields:
            token.save(update_fields=updated_fields)

        return token, None, False

    def rotate_secret(self):
        raw_token = self._generate_raw_token()
        self.token_prefix = raw_token[:12]
        self.token_hash = self._hash_token(raw_token)
        self.can_write = True
        self.save(update_fields=["token_prefix", "token_hash", "can_write"])
        return raw_token

    @classmethod
    def resolve_active(cls, raw_token: str):
        normalized = str(raw_token or "").strip()
        if not normalized:
            return None

        return (
            cls.objects.select_related("user")
            .filter(
                token_hash=cls._hash_token(normalized),
                revoked_at__isnull=True,
                user__is_active=True,
            )
            .first()
        )

    def mark_used(self):
        now = timezone.now()
        if self.last_used_at and now - self.last_used_at < timedelta(minutes=5):
            return
        type(self).objects.filter(id=self.id).update(last_used_at=now)

    def revoke(self):
        type(self).objects.filter(id=self.id, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
