from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0003_remove_project_description_remove_project_visibility_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="favicon_url",
            field=models.URLField(blank=True),
        ),
    ]
