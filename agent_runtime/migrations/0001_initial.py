import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentAuditEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_id', models.CharField(db_index=True, max_length=128)),
                ('authenticated_actor_id', models.CharField(max_length=128)),
                ('authenticated_client_id', models.CharField(max_length=48)),
                ('tool_name', models.CharField(db_index=True, max_length=80)),
                ('resource_type', models.CharField(blank=True, max_length=64)),
                ('resource_public_id', models.CharField(blank=True, max_length=128)),
                ('scope_decision', models.JSONField(default=dict)),
                ('capability_decision', models.JSONField(default=dict)),
                ('ownership_decision', models.CharField(max_length=32)),
                ('redacted_input_sha256', models.CharField(max_length=64)),
                ('result_code', models.CharField(max_length=64)),
                ('idempotency_id', models.CharField(blank=True, max_length=24)),
                ('approval_evidence', models.JSONField(blank=True, default=dict)),
                ('dependency_outcome', models.CharField(blank=True, max_length=32)),
                ('notification_outcome', models.CharField(blank=True, max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'indexes': [models.Index(fields=['created_at', 'tool_name'], name='agent_audit_retention_idx')],
            },
        ),
        migrations.CreateModel(
            name='AgentIdempotencyRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tool_name', models.CharField(max_length=80)),
                ('key_digest', models.CharField(max_length=64)),
                ('canonical_input_sha256', models.CharField(max_length=64)),
                ('idempotency_id', models.CharField(max_length=24)),
                ('result', models.JSONField()),
                ('resource_type', models.CharField(blank=True, max_length=64)),
                ('resource_id', models.CharField(blank=True, max_length=128)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_idempotency_records', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [models.Index(fields=['actor', 'tool_name', 'expires_at'], name='agent_idempotency_lookup_idx')],
                'constraints': [models.UniqueConstraint(fields=('actor', 'tool_name', 'key_digest'), name='agent_idempotency_actor_tool_key_uniq')],
            },
        ),
    ]
