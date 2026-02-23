from django.conf import settings
from django.db import models


class Project(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="projects",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    tagline = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    visibility = models.CharField(
        max_length=16,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "slug"],
                name="unique_project_slug_per_owner",
            )
        ]

    def __str__(self):
        return f"{self.owner.handle}/{self.slug}"
