from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models
from slugify import slugify


class Project(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="projects",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    tagline = models.CharField(max_length=160, blank=True)
    url = models.URLField(blank=True)
    favicon_url = models.URLField(blank=True)
    revision = models.PositiveBigIntegerField(default=1)
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

    def _build_slug(self):
        slug_field = self._meta.get_field("slug")
        max_length = slug_field.max_length
        base_slug = slugify(self.name or "").strip("-")[:max_length] or "project"

        if not self.owner_id:
            return base_slug

        existing = Project.objects.filter(owner_id=self.owner_id)
        if self.pk:
            existing = existing.exclude(pk=self.pk)

        candidate = base_slug
        counter = 2
        while existing.filter(slug=candidate).exists():
            suffix = f"-{counter}"
            truncated_base = base_slug[: max_length - len(suffix)].rstrip("-")
            candidate = f"{truncated_base}{suffix}" if truncated_base else f"project{suffix}"
            counter += 1

        return candidate

    def save(self, *args, **kwargs):
        self.slug = self._build_slug()
        super().save(*args, **kwargs)


class ProjectSpec(models.Model):
    MAX_CONTENT_LENGTH = 10_000

    project = models.OneToOneField(
        Project,
        related_name="spec",
        on_delete=models.CASCADE,
    )
    content = models.TextField(
        validators=[MaxLengthValidator(MAX_CONTENT_LENGTH)],
    )
    revision = models.PositiveBigIntegerField(default=1)
    auto_decline_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Spec for {self.project} (r{self.revision})"


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
        DECLINED = "declined", "Declined"

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
    duplicate_of = models.ForeignKey(
        "self",
        related_name="duplicates",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    revision = models.PositiveBigIntegerField(default=1)
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


class IssueScopeAssessment(models.Model):
    class State(models.TextChoices):
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class Verdict(models.TextChoices):
        IN_SCOPE = "in_scope", "In scope"
        OUT_OF_SCOPE = "out_of_scope", "Out of scope"
        SPEC_GAP = "spec_gap", "Spec gap"
        NEEDS_REVIEW = "needs_review", "Needs review"

    issue = models.ForeignKey(
        Issue,
        related_name="scope_assessments",
        on_delete=models.CASCADE,
    )
    spec_revision = models.PositiveBigIntegerField()
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.COMPLETED,
        db_index=True,
    )
    verdict = models.CharField(
        max_length=24,
        choices=Verdict.choices,
        blank=True,
        db_index=True,
    )
    public_reason = models.CharField(max_length=500, blank=True)
    out_of_scope_quote = models.CharField(max_length=1000, blank=True)
    spec_gap_summary = models.CharField(max_length=1000, blank=True)
    evaluator_version = models.CharField(max_length=64, default="spec_scope_v1")
    auto_declined = models.BooleanField(default=False)
    error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["issue", "-created_at"],
                name="scope_assess_issue_at_idx",
            )
        ]

    def __str__(self):
        outcome = self.verdict or self.state
        return f"{outcome} for issue #{self.issue_id} at spec r{self.spec_revision}"


class ProjectSpecChangeProposal(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    project = models.ForeignKey(
        Project,
        related_name="spec_change_proposals",
        on_delete=models.CASCADE,
    )
    issue = models.ForeignKey(
        Issue,
        related_name="spec_change_proposals",
        on_delete=models.CASCADE,
    )
    base_spec_revision = models.PositiveBigIntegerField()
    base_content = models.TextField(
        validators=[MaxLengthValidator(ProjectSpec.MAX_CONTENT_LENGTH)],
    )
    proposed_content = models.TextField(
        validators=[MaxLengthValidator(ProjectSpec.MAX_CONTENT_LENGTH)],
    )
    summary = models.CharField(max_length=1000)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_spec_change_proposals",
        on_delete=models.CASCADE,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="reviewed_spec_change_proposals",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Spec proposal #{self.pk} for {self.project}"


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
    revision = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment #{self.pk} on issue #{self.issue_id}"


class IssueDeliveryArtifact(models.Model):
    class Kind(models.TextChoices):
        PULL_REQUEST = "pull_request", "Pull request"
        COMMIT = "commit", "Commit"
        DEPLOYMENT = "deployment", "Deployment"
        RELEASE = "release", "Release"
        OTHER = "other", "Other"

    issue = models.ForeignKey(
        Issue,
        related_name="delivery_artifacts",
        on_delete=models.CASCADE,
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="issue_delivery_artifacts",
        on_delete=models.CASCADE,
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    url = models.URLField(max_length=2048)
    label = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "url"],
                name="unique_delivery_artifact_url_per_issue",
            )
        ]

    def __str__(self):
        return f"{self.kind} for issue #{self.issue_id}"


class IssueEvent(models.Model):
    class Type(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        COMMENT_ADDED = "comment_added", "Comment added"
        COMMENT_UPDATED = "comment_updated", "Comment updated"
        UPVOTE_ADDED = "upvote_added", "Upvote added"
        UPVOTE_REMOVED = "upvote_removed", "Upvote removed"
        DUPLICATE_LINKED = "duplicate_linked", "Duplicate linked"
        DUPLICATE_UNLINKED = "duplicate_unlinked", "Duplicate unlinked"
        DELIVERY_LINKED = "delivery_linked", "Delivery linked"
        DELIVERY_UNLINKED = "delivery_unlinked", "Delivery unlinked"
        SCOPE_ASSESSED = "scope_assessed", "Scope assessed"
        AUTO_DECLINED = "auto_declined", "Automatically declined"
        SPEC_UPDATED = "spec_updated", "Project spec updated"

    issue = models.ForeignKey(
        Issue,
        related_name="events",
        on_delete=models.CASCADE,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="issue_events",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    event_type = models.CharField(max_length=32, choices=Type.choices, db_index=True)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(
                fields=["issue", "id"],
                name="issue_event_issue_id_idx",
            )
        ]

    def __str__(self):
        return f"{self.event_type} on issue #{self.issue_id}"


class EmbeddedIssueSubmission(models.Model):
    project = models.ForeignKey(
        Project,
        related_name="embedded_issue_submissions",
        on_delete=models.CASCADE,
    )
    display_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    submitter_fingerprint = models.CharField(max_length=64, db_index=True)
    client_submission_id = models.UUIDField(null=True, blank=True, unique=True)
    payload_hash = models.CharField(max_length=64, blank=True)
    issue_type = models.CharField(
        max_length=16,
        choices=Issue.Type.choices,
        blank=True,
    )
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    issue = models.OneToOneField(
        Issue,
        related_name="embedded_submission",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["project", "submitter_fingerprint", "created_at"],
                name="embed_proj_actor_created_idx",
            )
        ]

    def __str__(self):
        return f"Embedded submission for {self.project}"
