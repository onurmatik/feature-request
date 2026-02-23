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


class Issue(models.Model):
    class Type(models.TextChoices):
        FEATURE = "feature", "Feature"
        BUG = "bug", "Bug"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"
        CLOSED = "closed", "Closed"

    class Priority(models.IntegerChoices):
        LOW = 1, "Low"
        MEDIUM = 2, "Medium"
        HIGH = 3, "High"
        CRITICAL = 4, "Critical"

    project = models.ForeignKey(
        Project,
        related_name="issues",
        on_delete=models.CASCADE,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="issues",
        on_delete=models.CASCADE,
    )
    issue_type = models.CharField(
        max_length=16,
        choices=Type.choices,
        default=Type.FEATURE,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    priority = models.PositiveSmallIntegerField(
        choices=Priority.choices,
        default=Priority.MEDIUM,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["project", "status", "priority"],
                name="issue_proj_stat_prio_idx",
            )
        ]

    def __str__(self):
        return f"{self.project} - {self.title}"


class IssueUpvote(models.Model):
    issue = models.ForeignKey(
        Issue,
        related_name="upvotes",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="issue_upvotes",
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "user"],
                name="unique_issue_upvote_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user} upvoted #{self.issue_id}"


class IssueComment(models.Model):
    issue = models.ForeignKey(
        Issue,
        related_name="comments",
        on_delete=models.CASCADE,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="issue_comments",
        on_delete=models.CASCADE,
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment #{self.pk} on issue #{self.issue_id}"
