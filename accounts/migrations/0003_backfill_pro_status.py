from django.db import migrations


def backfill_pro_status(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(subscription_tier="pro_30", subscription_status="").update(
        subscription_status="active"
    )


def revert_backfill_pro_status(apps, schema_editor):
    # Intentionally left as a no-op: we cannot distinguish rows that were
    # originally active from rows this data migration backfilled.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_add_billing_fields"),
    ]

    operations = [
        migrations.RunPython(backfill_pro_status, revert_backfill_pro_status),
    ]
