from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, handle, password, **extra_fields):
        if not email:
            raise ValueError("Email must be set.")
        if not handle:
            raise ValueError("Handle must be set.")

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

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["handle"]

    class Meta:
        ordering = ["-date_joined"]

    def save(self, *args, **kwargs):
        self.handle = self.handle.lower()
        self.email = self.__class__.objects.normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name or self.handle
