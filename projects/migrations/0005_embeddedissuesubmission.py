import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0004_project_add_favicon_url"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmbeddedIssueSubmission",
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
                ("display_name", models.CharField(blank=True, max_length=120)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("email_fingerprint", models.CharField(db_index=True, max_length=64)),
                (
                    "issue_type",
                    models.CharField(
                        blank=True,
                        choices=[("feature", "Feature"), ("bug", "Bug")],
                        max_length=16,
                    ),
                ),
                ("title", models.CharField(blank=True, max_length=200)),
                ("description", models.TextField(blank=True)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "issue",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="embedded_submission",
                        to="projects.issue",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="embedded_issue_submissions",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="embeddedissuesubmission",
            index=models.Index(
                fields=["project", "email_fingerprint", "created_at"],
                name="embed_proj_email_created_idx",
            ),
        ),
    ]
