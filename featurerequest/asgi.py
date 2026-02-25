"""ASGI entrypoint kept for deployment-template compatibility."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "featurerequest.settings")

application = get_asgi_application()

