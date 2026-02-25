import os
from pathlib import Path

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
    "accounts",
    "projects",
    "inbox",
]

AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "").strip()
if AWS_STORAGE_BUCKET_NAME:
    INSTALLED_APPS.append("storages")


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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


# Email & Authentication
DEFAULT_FROM_EMAIL = 'hi@featurerequest.io'
SERVER_EMAIL = 'notice@featurerequest.io'
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')

if ADMIN_EMAIL:
    ADMINS = [('Admin', 'onurmatik@gmail.com')]

EMAIL_SUBJECT_PREFIX = '[FeatureRequest] '

if EMAIL_BACKEND:
    AWS_SES_REGION_NAME = AWS_REGION_NAME
    AWS_SES_ACCESS_KEY_ID = AWS_ACCESS_KEY_ID
    AWS_SES_SECRET_ACCESS_KEY = AWS_SECRET_ACCESS_KEY
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'


CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "sesame.backends.ModelBackend",
]

SESAME_MAX_AGE = 60 * 30
SESAME_ONE_TIME = True
