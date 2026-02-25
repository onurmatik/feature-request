from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="stripe_customer_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="user",
            name="stripe_subscription_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="user",
            name="subscription_status",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="user",
            name="subscription_tier",
            field=models.CharField(
                choices=[
                    ("free", "Free"),
                    ("pro_30", "Pro (30 projects)"),
                ],
                default="free",
                max_length=20,
            ),
        ),
    ]
