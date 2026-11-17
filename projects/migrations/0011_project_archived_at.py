from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("projects", "0010_product_scope_labels")]

    operations = [
        migrations.AddField(
            model_name="project",
            name="archived_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
