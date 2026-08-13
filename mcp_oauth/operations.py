from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import mail_admins
from django.utils import timezone

from .models import OAuthSecurityEvent


logger = logging.getLogger(__name__)


def send_deduplicated_admin_alert(event_type: str, details: dict) -> bool:
    """Deliver one bounded redacted alert per type per hour."""

    now = timezone.now()
    if OAuthSecurityEvent.objects.filter(
        event_type=f"alert:{event_type}",
        decision="sent",
        created_at__gte=now - timedelta(hours=1),
    ).exists():
        return False
    safe_details = {
        str(key)[:64]: value
        for key, value in details.items()
        if key not in {"token", "code", "verifier", "secret", "state", "email", "url"}
    }
    message = json.dumps(safe_details, sort_keys=True, default=str)[:2000]
    event = OAuthSecurityEvent.objects.create(
        request_id=f"ops-{now.strftime('%Y%m%d%H%M%S')}",
        event_type=f"alert:{event_type}",
        resource="feature-request-mcp",
        decision="pending",
        details=safe_details,
    )
    logger.error("FeatureRequest MCP alert event=%s details=%s", event_type, message)
    try:
        mail_admins(
            subject=f"FeatureRequest MCP alert: {event_type}",
            message=message,
            fail_silently=False,
        )
    except Exception as exc:
        logger.error(
            "FeatureRequest MCP alert delivery failed event=%s error_type=%s",
            event_type,
            type(exc).__name__,
        )
        event.decision = "delivery_failed"
        event.error_code = "email_delivery_failed"
        event.save(update_fields=["decision", "error_code"])
        return False
    event.decision = "sent"
    event.save(update_fields=["decision"])
    return True
