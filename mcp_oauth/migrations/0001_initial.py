import django.db.models.deletion
import mcp_oauth.models
import oauth2_provider.generators
import oauth2_provider.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientMetadataCache',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_id', models.URLField(max_length=2048, unique=True)),
                ('document', models.JSONField(default=dict)),
                ('document_sha256', models.CharField(max_length=64)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('fetched_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='OAuthCleanupRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('success', models.BooleanField(db_index=True, default=False)),
                ('deleted', models.JSONField(default=dict)),
                ('errors', models.PositiveIntegerField(default=0)),
                ('duration_ms', models.PositiveIntegerField(default=0)),
                ('oldest_eligible_seconds', models.PositiveIntegerField(default=0)),
                ('scheduler', models.CharField(default='management_command', max_length=64)),
                ('error_code', models.CharField(blank=True, max_length=64)),
            ],
        ),
        migrations.CreateModel(
            name='OAuthSecurityEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_id', models.CharField(db_index=True, max_length=128)),
                ('event_type', models.CharField(db_index=True, max_length=64)),
                ('actor_id_public', models.CharField(blank=True, max_length=128)),
                ('client_id_digest', models.CharField(blank=True, db_index=True, max_length=64)),
                ('resource', models.TextField(blank=True)),
                ('scopes', models.JSONField(default=list)),
                ('decision', models.CharField(max_length=32)),
                ('error_code', models.CharField(blank=True, max_length=64)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name='PendingAuthorization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('handle_digest', models.CharField(max_length=64, unique=True)),
                ('session_digest', models.CharField(db_index=True, max_length=64)),
                ('encrypted_payload', models.BinaryField()),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('consumed_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='OAuthApplication',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('client_id', models.CharField(db_index=True, max_length=2048, unique=True)),
                ('redirect_uris', models.TextField(blank=True, help_text='Allowed URIs list, space separated')),
                ('post_logout_redirect_uris', models.TextField(blank=True, default='', help_text='Allowed Post Logout URIs list, space separated')),
                ('client_type', models.CharField(choices=[('confidential', 'Confidential'), ('public', 'Public')], max_length=32)),
                ('authorization_grant_type', models.CharField(choices=[('authorization-code', 'Authorization code'), ('urn:ietf:params:oauth:grant-type:device_code', 'Device Code'), ('implicit', 'Implicit'), ('password', 'Resource owner password-based'), ('client-credentials', 'Client credentials'), ('openid-hybrid', 'OpenID connect hybrid')], max_length=44)),
                ('client_secret', oauth2_provider.models.ClientSecretField(blank=True, db_index=True, default=oauth2_provider.generators.generate_client_secret, help_text='Client secret for authentication', max_length=255)),
                ('hash_client_secret', models.BooleanField(default=True)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('skip_authorization', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('algorithm', models.CharField(blank=True, choices=[('', 'No OIDC support'), ('RS256', 'RSA with SHA-2 256'), ('HS256', 'HMAC with SHA-2 256')], default='', max_length=5)),
                ('allowed_origins', models.TextField(blank=True, default='', help_text='Allowed origins list to enable CORS, space separated')),
                ('registration_source', models.CharField(choices=[('manual', 'Manual'), ('dcr', 'Dynamic Client Registration'), ('cimd', 'Client ID Metadata Document')], default='manual', help_text='How this application was registered (manual, DCR per RFC 7591, or CIMD)', max_length=32)),
                ('cimd_expires_at', models.DateTimeField(blank=True, default=None, help_text='When the cached Client ID Metadata Document should be re-fetched', null=True)),
                ('application_type', models.CharField(choices=[('native', 'Native'), ('web', 'Web')], max_length=16)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('allowed_scopes', models.JSONField(default=list)),
                ('callback_profiles', models.JSONField(default=list)),
                ('revoked_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('last_used_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('last_metadata_fetch_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'swappable': 'OAUTH2_PROVIDER_APPLICATION_MODEL',
            },
        ),
        migrations.CreateModel(
            name='OAuthGrant',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('expires', models.DateTimeField()),
                ('redirect_uri', models.TextField()),
                ('scope', models.TextField(blank=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('code_challenge', models.CharField(blank=True, default='', max_length=128)),
                ('code_challenge_method', models.CharField(blank=True, choices=[('plain', 'plain'), ('S256', 'S256')], default='', max_length=10)),
                ('nonce', models.CharField(blank=True, default='', max_length=255)),
                ('claims', models.TextField(blank=True)),
                ('resource', oauth2_provider.models.ResourceJSONField(blank=True, default=list)),
                ('code', models.CharField(blank=True, default='', editable=False, max_length=1)),
                ('code_digest', models.CharField(editable=False, max_length=64, unique=True)),
                ('consumed_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('replayed_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.OAUTH2_PROVIDER_APPLICATION_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'swappable': 'OAUTH2_PROVIDER_GRANT_MODEL',
            },
        ),
        migrations.CreateModel(
            name='OAuthIDToken',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('jti', models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name='JWT Token ID')),
                ('expires', models.DateTimeField()),
                ('scope', models.TextField(blank=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('application', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.OAUTH2_PROVIDER_APPLICATION_MODEL)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'swappable': 'OAUTH2_PROVIDER_ID_TOKEN_MODEL',
            },
        ),
        migrations.CreateModel(
            name='OAuthAccessToken',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('token_checksum', oauth2_provider.models.TokenChecksumField(db_index=True, max_length=64, unique=True)),
                ('expires', models.DateTimeField()),
                ('scope', models.TextField(blank=True)),
                ('resource', oauth2_provider.models.ResourceJSONField(blank=True, default=list)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('token', models.TextField(blank=True, default='', editable=False)),
                ('revoked_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('authorization_code_digest', models.CharField(blank=True, db_index=True, max_length=64)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s', to=settings.AUTH_USER_MODEL)),
                ('application', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.OAUTH2_PROVIDER_APPLICATION_MODEL)),
                ('id_token', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='access_token', to=settings.OAUTH2_PROVIDER_ID_TOKEN_MODEL)),
            ],
            options={
                'swappable': 'OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL',
            },
        ),
        migrations.CreateModel(
            name='OAuthRefreshToken',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('token_checksum', oauth2_provider.models.TokenChecksumField(max_length=64)),
                ('token_family', models.UUIDField(blank=True, editable=False, null=True)),
                ('resource', oauth2_provider.models.ResourceJSONField(blank=True, default=list)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('revoked', models.DateTimeField(null=True)),
                ('token', models.TextField(blank=True, default='', editable=False)),
                ('consumed_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('access_token', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='refresh_token', to=settings.OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.OAUTH2_PROVIDER_APPLICATION_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'swappable': 'OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL',
            },
        ),
        migrations.AddField(
            model_name='oauthaccesstoken',
            name='source_refresh_token',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='refreshed_access_token', to=settings.OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL),
        ),
        migrations.CreateModel(
            name='ClientCompatibilityUsageDaily',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField()),
                ('client_surface_digest', models.CharField(max_length=64)),
                ('registration_method', models.CharField(max_length=16)),
                ('registrations', models.PositiveIntegerField(default=0)),
                ('token_uses', models.PositiveIntegerField(default=0)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('day', 'client_surface_digest', 'registration_method'), name='fr_oauth_compat_daily_uniq')],
            },
        ),
        migrations.CreateModel(
            name='OAuthConsent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('resource', models.TextField()),
                ('scopes', models.JSONField(default=list)),
                ('decision', models.CharField(choices=[('approved', 'Approved'), ('denied', 'Denied')], max_length=16)),
                ('revoked_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.OAUTH2_PROVIDER_APPLICATION_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='OAuthRefreshFamily',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('resource', models.TextField()),
                ('scopes', models.JSONField(default=list)),
                ('authorization_code_digest', models.CharField(blank=True, db_index=True, max_length=64)),
                ('expires_at', models.DateTimeField(db_index=True, default=mcp_oauth.models.refresh_family_expiry)),
                ('revoked_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('replayed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='refresh_families', to=settings.OAUTH2_PROVIDER_APPLICATION_MODEL)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mcp_refresh_families', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='oauthrefreshtoken',
            name='family',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tokens', to='mcp_oauth.oauthrefreshfamily'),
        ),
        migrations.CreateModel(
            name='RateLimitBucket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bucket_key', models.CharField(max_length=64)),
                ('window_start', models.DateTimeField()),
                ('count', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'indexes': [models.Index(fields=['window_start'], name='fr_oauth_rate_cleanup_idx')],
                'constraints': [models.UniqueConstraint(fields=('bucket_key', 'window_start'), name='fr_oauth_rate_bucket_uniq')],
            },
        ),
        migrations.AddIndex(
            model_name='oauthapplication',
            index=models.Index(fields=['registration_source', 'last_used_at'], name='fr_oauth_app_cleanup_idx'),
        ),
        migrations.AddConstraint(
            model_name='oauthapplication',
            constraint=models.CheckConstraint(condition=models.Q(('client_type', 'public')), name='fr_oauth_app_public_only'),
        ),
        migrations.AddConstraint(
            model_name='oauthapplication',
            constraint=models.CheckConstraint(condition=models.Q(('authorization_grant_type', 'authorization-code')), name='fr_oauth_app_code_only'),
        ),
        migrations.AddConstraint(
            model_name='oauthapplication',
            constraint=models.CheckConstraint(condition=models.Q(('client_secret', '')), name='fr_oauth_app_no_secret'),
        ),
        migrations.AddConstraint(
            model_name='oauthapplication',
            constraint=models.CheckConstraint(condition=models.Q(('hash_client_secret', False)), name='fr_oauth_app_no_secret_hash'),
        ),
        migrations.AddConstraint(
            model_name='oauthapplication',
            constraint=models.CheckConstraint(condition=models.Q(('skip_authorization', False)), name='fr_oauth_app_consent_required'),
        ),
        migrations.AddConstraint(
            model_name='oauthapplication',
            constraint=models.CheckConstraint(condition=models.Q(('registration_source__in', ['dcr', 'cimd'])), name='fr_oauth_app_registration_ck'),
        ),
        migrations.AddIndex(
            model_name='oauthgrant',
            index=models.Index(fields=['expires', 'consumed_at'], name='fr_oauth_grant_cleanup_idx'),
        ),
        migrations.AddConstraint(
            model_name='oauthgrant',
            constraint=models.CheckConstraint(condition=models.Q(('code', '')), name='fr_oauth_grant_digest_only'),
        ),
        migrations.AddConstraint(
            model_name='oauthgrant',
            constraint=models.CheckConstraint(condition=models.Q(('consumed_at__isnull', True), ('consumed_at__gte', models.F('created')), _connector='OR'), name='fr_oauth_grant_consumed_ck'),
        ),
        migrations.AddIndex(
            model_name='oauthaccesstoken',
            index=models.Index(fields=['expires', 'revoked_at'], name='fr_oauth_access_cleanup_idx'),
        ),
        migrations.AddIndex(
            model_name='oauthaccesstoken',
            index=models.Index(fields=['application', 'user', 'revoked_at'], name='fr_oauth_access_principal_idx'),
        ),
        migrations.AddConstraint(
            model_name='oauthaccesstoken',
            constraint=models.CheckConstraint(condition=models.Q(('token', '')), name='fr_oauth_access_digest_only'),
        ),
        migrations.AddConstraint(
            model_name='oauthaccesstoken',
            constraint=models.CheckConstraint(condition=models.Q(('revoked_at__isnull', True), ('revoked_at__gte', models.F('created')), _connector='OR'), name='fr_oauth_access_revoke_ck'),
        ),
        migrations.AddIndex(
            model_name='oauthconsent',
            index=models.Index(fields=['user', 'application', 'resource', 'revoked_at'], name='fr_oauth_consent_binding_idx'),
        ),
        migrations.AddIndex(
            model_name='oauthrefreshfamily',
            index=models.Index(fields=['expires_at', 'revoked_at'], name='fr_oauth_family_cleanup_idx'),
        ),
        migrations.AddConstraint(
            model_name='oauthrefreshfamily',
            constraint=models.CheckConstraint(condition=models.Q(('expires_at__gt', models.F('created_at'))), name='fr_oauth_family_expiry_ck'),
        ),
        migrations.AddIndex(
            model_name='oauthrefreshtoken',
            index=models.Index(fields=['family', 'consumed_at', 'revoked'], name='fr_oauth_refresh_family_idx'),
        ),
        migrations.AddConstraint(
            model_name='oauthrefreshtoken',
            constraint=models.UniqueConstraint(fields=('token_checksum',), name='fr_oauth_refresh_sum_uniq'),
        ),
        migrations.AddConstraint(
            model_name='oauthrefreshtoken',
            constraint=models.CheckConstraint(condition=models.Q(('token', '')), name='fr_oauth_refresh_digest_only'),
        ),
        migrations.AddConstraint(
            model_name='oauthrefreshtoken',
            constraint=models.CheckConstraint(condition=models.Q(('token_family', models.F('family_id'))), name='fr_oauth_refresh_family_binding_ck'),
        ),
        migrations.AddConstraint(
            model_name='oauthrefreshtoken',
            constraint=models.CheckConstraint(condition=models.Q(('consumed_at__isnull', True), ('consumed_at__gte', models.F('created')), _connector='OR'), name='fr_oauth_refresh_consumed_ck'),
        ),
    ]
