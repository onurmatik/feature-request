import os
from pathlib import Path
from urllib.parse import urlsplit

import dj_database_url
import yaml
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default):
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def env_path(name, default):
    value = os.getenv(name, default)
    segment = value.strip().strip("/")
    if not segment:
        segment = default.strip("/")
    return f"/{segment}/"


def validate_service_url(name, value, *, path):
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a valid absolute URL.") from exc
    allowed_schemes = {"http", "https"} if DEBUG else {"https"}
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        raise ImproperlyConfigured(f"{name} must use an allowed absolute URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ImproperlyConfigured(f"{name} must not contain userinfo.")
    if parsed.query or parsed.fragment or parsed.path != path or value.endswith("/"):
        raise ImproperlyConfigured(f"{name} must use path {path!r} exactly without a trailing slash.")
    if parsed.scheme != parsed.scheme.lower() or parsed.netloc != parsed.netloc.lower():
        raise ImproperlyConfigured(f"{name} scheme and authority must be lowercase.")
    return value


def validate_cors_origins(origins):
    if not origins:
        raise ImproperlyConfigured("FEATURE_REQUEST_MCP_CORS_ORIGINS must not be empty.")
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            _ = parsed.port
        except ValueError as exc:
            raise ImproperlyConfigured("Invalid MCP CORS origin.") from exc
        if (
            parsed.scheme not in ({"http", "https"} if DEBUG else {"https"})
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ImproperlyConfigured("MCP CORS entries must be exact origins.")


# AWS credentials
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
AWS_REGION_NAME = os.getenv('AWS_DEFAULT_REGION')
AWS_S3_REGION_NAME = AWS_REGION_NAME


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-secret-key-change-in-production")
DEBUG = env_bool("DEBUG", env_bool("DJANGO_DEBUG", True))
ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    [
        "127.0.0.1",
        "localhost",
        "featurerequest.io",
        "www.featurerequest.io",
    ],
)
ADMIN_URL = env_path("ADMIN_URL", "/admin/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "sesame",
    "oauth2_provider",
    "mcp_oauth",
    "agent_runtime",
    "accounts",
    "projects",
    "inbox",
]

OAUTH2_PROVIDER_APPLICATION_MODEL = "mcp_oauth.OAuthApplication"
OAUTH2_PROVIDER_GRANT_MODEL = "mcp_oauth.OAuthGrant"
OAUTH2_PROVIDER_ACCESS_TOKEN_MODEL = "mcp_oauth.OAuthAccessToken"
OAUTH2_PROVIDER_REFRESH_TOKEN_MODEL = "mcp_oauth.OAuthRefreshToken"
OAUTH2_PROVIDER_ID_TOKEN_MODEL = "mcp_oauth.OAuthIDToken"

AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "").strip()
if AWS_STORAGE_BUCKET_NAME:
    INSTALLED_APPS.append("storages")


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "mcp_oauth.middleware.CorrelationIdMiddleware",
    "config.middleware.SiteHitsBotMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.BearerTokenAuthMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEST_RUNNER = "config.test_runner.RepositoryDiscoverRunner"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=60,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Istanbul"

USE_I18N = True
USE_TZ = True

STATIC_URL = os.getenv("STATIC_URL", "/static/")
STATIC_ROOT = Path(os.getenv("STATIC_ROOT", str(BASE_DIR / "staticfiles")))


if AWS_STORAGE_BUCKET_NAME:
    # Production / Staging (S3)
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "location": "media",
                "file_overwrite": False,
            },
        },
        "staticfiles": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
            "OPTIONS": {
                "location": "static",
                "file_overwrite": True,
                "querystring_auth": False,
            },
        },
    }


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID_30 = os.getenv("STRIPE_PRICE_ID_30", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
TURNSTILE_SITEKEY = os.getenv("TURNSTILE_SITEKEY", "")
TURNSTILE_SECRETKEY = os.getenv("TURNSTILE_SECRETKEY", "")
SITEHITS_BOT_KEY = os.getenv("SITEHITS_BOT_KEY", "")
SITEHITS_BOT_TIMEOUT_SECONDS = 2.0

FEATURE_REQUEST_MCP_HOST = os.getenv("FEATURE_REQUEST_MCP_HOST", "127.0.0.1")
FEATURE_REQUEST_MCP_PORT = int(os.getenv("FEATURE_REQUEST_MCP_PORT", "8001"))
PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL",
    "http://127.0.0.1:8000" if DEBUG else "https://featurerequest.io",
)
OAUTH_ISSUER = os.getenv("OAUTH_ISSUER", PUBLIC_BASE_URL)
MCP_RESOURCE_URL = os.getenv(
    "MCP_RESOURCE_URL",
    (
        f"http://127.0.0.1:{FEATURE_REQUEST_MCP_PORT}/mcp"
        if DEBUG
        else f"{PUBLIC_BASE_URL}/mcp"
    ),
)
MCP_RESOURCE_METADATA_URL = os.getenv(
    "MCP_RESOURCE_METADATA_URL",
    f"{PUBLIC_BASE_URL}/.well-known/oauth-protected-resource/mcp",
)
FEATURE_REQUEST_MCP_CORS_ORIGINS = env_list(
    "FEATURE_REQUEST_MCP_CORS_ORIGINS",
    [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]
    if DEBUG
    else [
        "https://chatgpt.com",
        "https://claude.ai",
        "https://claude.com",
    ],
)
FEATURE_REQUEST_TRUSTED_PROXY_IPS = tuple(
    env_list("FEATURE_REQUEST_TRUSTED_PROXY_IPS", ["127.0.0.1", "::1"])
)
FEATURE_REQUEST_MCP_PRODUCTION_ENABLED = env_bool(
    "FEATURE_REQUEST_MCP_PRODUCTION_ENABLED", False
)
FEATURE_REQUEST_MCP_ACCESS_TOKEN_TTL_SECONDS = 15 * 60
FEATURE_REQUEST_MCP_REFRESH_FAMILY_TTL_SECONDS = 30 * 24 * 60 * 60
FEATURE_REQUEST_MCP_AUTHORIZATION_CODE_TTL_SECONDS = 60
FEATURE_REQUEST_MCP_PENDING_AUTHORIZATION_TTL_SECONDS = 10 * 60
FEATURE_REQUEST_MCP_CIMD_MAX_BYTES = 5 * 1024

validate_service_url("PUBLIC_BASE_URL", PUBLIC_BASE_URL, path="")
validate_service_url("OAUTH_ISSUER", OAUTH_ISSUER, path="")
validate_service_url("MCP_RESOURCE_URL", MCP_RESOURCE_URL, path="/mcp")
validate_service_url(
    "MCP_RESOURCE_METADATA_URL",
    MCP_RESOURCE_METADATA_URL,
    path="/.well-known/oauth-protected-resource/mcp",
)
if PUBLIC_BASE_URL != OAUTH_ISSUER:
    raise ImproperlyConfigured("PUBLIC_BASE_URL and OAUTH_ISSUER must be identical.")
if not DEBUG and urlsplit(PUBLIC_BASE_URL).netloc != urlsplit(MCP_RESOURCE_URL).netloc:
    raise ImproperlyConfigured("MCP_RESOURCE_URL must share the public origin.")
validate_cors_origins(FEATURE_REQUEST_MCP_CORS_ORIGINS)
if FEATURE_REQUEST_MCP_PRODUCTION_ENABLED and DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    raise ImproperlyConfigured(
        "Production MCP enablement requires the PostgreSQL concurrency gate; SQLite is implementation-only."
    )
if FEATURE_REQUEST_MCP_PRODUCTION_ENABLED and DEBUG:
    raise ImproperlyConfigured("Production MCP enablement requires DEBUG=false.")
if FEATURE_REQUEST_MCP_PRODUCTION_ENABLED and (
    not os.getenv("DJANGO_SECRET_KEY")
    or SECRET_KEY == "dev-only-secret-key-change-in-production"
    or len(SECRET_KEY) < 32
):
    raise ImproperlyConfigured(
        "Production MCP enablement requires an explicit strong DJANGO_SECRET_KEY."
    )

with (BASE_DIR / "agent" / "contract.yaml").open(encoding="utf-8") as contract_file:
    AGENT_CONTRACT = yaml.safe_load(contract_file)
FEATURE_REQUEST_MCP_OAUTH_SCOPES = tuple(AGENT_CONTRACT["scopes"])
FEATURE_REQUEST_MCP_BOOTSTRAP_SCOPES = tuple(
    AGENT_CONTRACT["tools"][AGENT_CONTRACT["bootstrap"]["tool"]]["required_scopes"]
)
OAUTH2_PROVIDER = {
    "SCOPES": {
        name: definition["description"]
        for name, definition in AGENT_CONTRACT["scopes"].items()
    },
    "DEFAULT_SCOPES": [],
    "AUTHORIZATION_CODE_EXPIRE_SECONDS": FEATURE_REQUEST_MCP_AUTHORIZATION_CODE_TTL_SECONDS,
    "ACCESS_TOKEN_EXPIRE_SECONDS": FEATURE_REQUEST_MCP_ACCESS_TOKEN_TTL_SECONDS,
    "REFRESH_TOKEN_EXPIRE_SECONDS": FEATURE_REQUEST_MCP_REFRESH_FAMILY_TTL_SECONDS,
    "REQUEST_APPROVAL_PROMPT": "force",
    "PKCE_REQUIRED": True,
    "ALLOW_URI_WILDCARDS": False,
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "http"],
    "ALLOWED_SCHEMES": ["http", "https"] if DEBUG else ["https"],
    "COMPLIANT_BCP_RFC9700_IMPLICIT_GRANT": True,
    "COMPLIANT_BCP_RFC9700_PASSWORD_GRANT": True,
    "COMPLIANT_BCP_RFC9700_PKCE_METHOD": True,
    "COMPLIANT_BCP_RFC9700_ACCESS_TOKEN_TRANSPORT": True,
    "COMPLIANT_BCP_RFC9700_AUTHZ_RESPONSE_ISS": True,
    "COMPLIANT_BCP_RFC9700_TOKEN_STORAGE": True,
    "COMPLIANT_BCP_RFC9700_REFRESH_TOKEN": True,
    "COMPLIANT_BCP_RFC9700_REDIRECT_URI_MATCHING": True,
    "COMPLIANT_BCP_RFC9700_PKCE_REQUIRED": True,
    "OIDC_ENABLED": False,
    "OIDC_ISS_ENDPOINT": OAUTH_ISSUER,
    "OAUTH2_RESPONSE_TYPES_SUPPORTED": ["code"],
    "OAUTH2_TOKEN_ENDPOINT_AUTH_METHODS_SUPPORTED": ["none"],
    "OAUTH2_GRANT_TYPES_SUPPORTED": ["authorization_code", "refresh_token"],
}


# Email & Authentication
DEFAULT_FROM_EMAIL = 'FeatureRequest <hi@featurerequest.io>'
SERVER_EMAIL = 'notice@featurerequest.io'
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')

if ADMIN_EMAIL:
    ADMINS = [('FeatureRequest Admin', ADMIN_EMAIL)]

EMAIL_SUBJECT_PREFIX = '[FeatureRequest] '

if EMAIL_BACKEND:
    AWS_SES_REGION_NAME = AWS_REGION_NAME
    AWS_SES_ACCESS_KEY_ID = AWS_ACCESS_KEY_ID
    AWS_SES_SECRET_ACCESS_KEY = AWS_SECRET_ACCESS_KEY
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Keep browser sign-ins for a fixed 10-year period.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365 * 10
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = not DEBUG


CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
)

# Production processes bind to loopback and are reached through the checked-in
# reverse-proxy contract, so only that proxy may assert the original HTTPS scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "sesame.backends.ModelBackend",
]

SESAME_MAX_AGE = 60 * 30
SESAME_ONE_TIME = True
