from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0006_issue_duplicate_of_issueevent_and_delivery_artifact'),
    ]

    operations = [
        migrations.AddField(
            model_name='issue',
            name='revision',
            field=models.PositiveBigIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='issuecomment',
            name='revision',
            field=models.PositiveBigIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='project',
            name='revision',
            field=models.PositiveBigIntegerField(default=1),
        ),
    ]
