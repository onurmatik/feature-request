from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects", "0005_embeddedissuesubmission"),
    ]

    operations = [
        migrations.AddField(
            model_name="issue",
            name="duplicate_of",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="duplicates",
                to="projects.issue",
            ),
        ),
        migrations.CreateModel(
            name="IssueDeliveryArtifact",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("pull_request", "Pull request"),
                            ("commit", "Commit"),
                            ("deployment", "Deployment"),
                            ("release", "Release"),
                            ("other", "Other"),
                        ],
                        max_length=32,
                    ),
                ),
                ("url", models.URLField(max_length=2048)),
                ("label", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "added_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="issue_delivery_artifacts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "issue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delivery_artifacts",
                        to="projects.issue",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="IssueEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("updated", "Updated"),
                            ("comment_added", "Comment added"),
                            ("comment_updated", "Comment updated"),
                            ("upvote_added", "Upvote added"),
                            ("upvote_removed", "Upvote removed"),
                            ("duplicate_linked", "Duplicate linked"),
                            ("duplicate_unlinked", "Duplicate unlinked"),
                            ("delivery_linked", "Delivery linked"),
                            ("delivery_unlinked", "Delivery unlinked"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("data", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="issue_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "issue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="projects.issue",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddConstraint(
            model_name="issuedeliveryartifact",
            constraint=models.UniqueConstraint(
                fields=("issue", "url"),
                name="unique_delivery_artifact_url_per_issue",
            ),
        ),
        migrations.AddIndex(
            model_name="issueevent",
            index=models.Index(
                fields=["issue", "id"],
                name="issue_event_issue_id_idx",
            ),
        ),
    ]
