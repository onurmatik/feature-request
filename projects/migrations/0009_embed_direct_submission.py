from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0008_project_spec_scope_assessment"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="embeddedissuesubmission",
            name="embed_proj_email_created_idx",
        ),
        migrations.RenameField(
            model_name="embeddedissuesubmission",
            old_name="email_fingerprint",
            new_name="submitter_fingerprint",
        ),
        migrations.AddField(
            model_name="embeddedissuesubmission",
            name="client_submission_id",
            field=models.UUIDField(blank=True, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="embeddedissuesubmission",
            name="payload_hash",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddIndex(
            model_name="embeddedissuesubmission",
            index=models.Index(
                fields=["project", "submitter_fingerprint", "created_at"],
                name="embed_proj_actor_created_idx",
            ),
        ),
    ]
