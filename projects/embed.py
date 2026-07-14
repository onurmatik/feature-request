import hashlib
import hmac
import json
import logging
import secrets
import ssl
import uuid
from datetime import timedelta
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from slugify import slugify

from .models import EmbeddedIssueSubmission, Project

logger = logging.getLogger(__name__)

TURNSTILE_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_ACTION = "embed_submission"
SUBMISSION_EXPIRY = timedelta(minutes=30)
SUBMISSION_RATE_WINDOW = timedelta(hours=1)
SUBMISSION_RATE_LIMIT = 3
SUBMISSION_RETENTION = timedelta(days=30)
SITEVERIFY_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class EmbedSubmissionError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def token_digest(raw_token: str) -> str:
    return hashlib.sha256(str(raw_token or "").encode("utf-8")).hexdigest()


def email_fingerprint(email: str) -> str:
    normalized = str(email or "").strip().lower()
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _client_ip(request) -> str:
    return str(request.META.get("REMOTE_ADDR", "")).strip()


def validate_turnstile(request, token: str) -> None:
    secret_key = str(settings.TURNSTILE_SECRETKEY or "").strip()
    response_token = str(token or "").strip()
    if not secret_key:
        logger.error("Turnstile secret is not configured for embed submissions.")
        raise EmbedSubmissionError(503, "Human verification is temporarily unavailable.")
    if not response_token or len(response_token) > 2048:
        raise EmbedSubmissionError(400, "Complete the human verification challenge.")

    payload = {
        "secret": secret_key,
        "response": response_token,
        "idempotency_key": str(uuid.uuid4()),
    }
    remote_ip = _client_ip(request)
    if remote_ip:
        payload["remoteip"] = remote_ip

    siteverify_request = Request(
        TURNSTILE_SITEVERIFY_URL,
        data=urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(
            siteverify_request,
            timeout=5,
            context=SITEVERIFY_SSL_CONTEXT,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        logger.exception("Turnstile Siteverify request failed.")
        raise EmbedSubmissionError(503, "Human verification is temporarily unavailable.")

    if not isinstance(result, dict):
        logger.error("Turnstile Siteverify returned an unexpected response shape.")
        raise EmbedSubmissionError(503, "Human verification is temporarily unavailable.")

    expected_hostname = request.get_host().split(":", 1)[0].strip().lower()
    verified_hostname = str(result.get("hostname", "")).strip().lower()
    verified_action = str(result.get("action", "")).strip()
    if (
        result.get("success") is not True
        or not expected_hostname
        or verified_hostname != expected_hostname
        or verified_action != TURNSTILE_ACTION
    ):
        logger.info(
            "Turnstile rejected embed submission hostname=%s action=%s errors=%s",
            verified_hostname,
            verified_action,
            result.get("error-codes", []),
        )
        raise EmbedSubmissionError(400, "Human verification failed. Please try again.")


def _purge_old_submissions(now) -> None:
    EmbeddedIssueSubmission.objects.filter(
        issue__isnull=True,
        expires_at__lt=now,
    ).delete()
    EmbeddedIssueSubmission.objects.filter(
        created_at__lt=now - SUBMISSION_RETENTION,
    ).delete()


def _verification_email(request, submission: EmbeddedIssueSubmission, raw_token: str):
    verification_url = request.build_absolute_uri(
        reverse("embed-submission-verify", kwargs={"token": raw_token})
    )
    project = submission.project
    subject = f"Verify your request for {project.name}"
    plain_text = (
        f"Hi {submission.display_name},\n\n"
        f"Confirm and publish your request for {project.name}:\n"
        f"{verification_url}\n\n"
        "The link expires in 30 minutes. Publishing signs you in to a lightweight "
        "FeatureRequest account so you can manage your request later.\n\n"
        "If you did not submit this request, ignore this email.\n"
    )
    html_body = f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f3f4f6;">
    <div style="padding:32px 16px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;">
        <tr><td style="padding:28px 32px 8px;font-family:Arial,sans-serif;color:#111827;"><h1 style="margin:0;font-size:22px;">Publish your request</h1></td></tr>
        <tr><td style="padding:0 32px 20px;font-family:Arial,sans-serif;color:#374151;line-height:1.6;">
          <p>Hi {escape(submission.display_name)},</p>
          <p>Confirm your request for <strong>{escape(project.name)}</strong>. The link expires in 30 minutes.</p>
          <p style="margin:0 0 16px;"><strong>{escape(submission.title)}</strong></p>
          <a href="{escape(verification_url)}" style="display:inline-block;background:#06B6D4;color:#ffffff;text-decoration:none;padding:11px 18px;border-radius:6px;font-weight:700;">Review and publish</a>
          <p style="margin:20px 0 0;font-size:12px;color:#6b7280;">Publishing signs you in to a lightweight FeatureRequest account so you can manage your request later. If this was not you, ignore this email.</p>
        </td></tr>
      </table>
    </div>
  </body>
</html>"""
    sent = send_mail(
        subject,
        plain_text,
        settings.DEFAULT_FROM_EMAIL,
        [submission.email],
        html_message=html_body,
        fail_silently=False,
    )
    if sent != 1:
        raise EmbedSubmissionError(502, "The verification email could not be sent.")


def create_pending_submission(
    request,
    project: Project,
    *,
    display_name: str,
    email: str,
    issue_type: str,
    title: str,
    description: str,
) -> EmbeddedIssueSubmission:
    now = timezone.now()
    _purge_old_submissions(now)
    fingerprint = email_fingerprint(email)
    raw_token = secrets.token_urlsafe(32)
    with transaction.atomic():
        Project.objects.select_for_update().only("pk").get(pk=project.pk)
        recent_count = EmbeddedIssueSubmission.objects.filter(
            project=project,
            email_fingerprint=fingerprint,
            created_at__gte=now - SUBMISSION_RATE_WINDOW,
        ).count()
        if recent_count >= SUBMISSION_RATE_LIMIT:
            raise EmbedSubmissionError(
                429,
                "Too many verification emails were requested. Please try again later.",
            )

        submission = EmbeddedIssueSubmission.objects.create(
            project=project,
            display_name=display_name,
            email=email,
            email_fingerprint=fingerprint,
            issue_type=issue_type,
            title=title,
            description=description,
            token_hash=token_digest(raw_token),
            expires_at=now + SUBMISSION_EXPIRY,
        )
    try:
        _verification_email(request, submission, raw_token)
    except Exception:
        submission.delete()
        raise
    return submission


def get_or_create_embed_user(email: str, display_name: str):
    User = get_user_model()
    existing = User.objects.filter(email__iexact=email).first()
    if existing is not None:
        return existing, False

    readable = slugify(display_name or "guest").replace("-", "_") or "guest"
    readable = readable[:32].strip("_") or "guest"
    while True:
        handle = f"guest_{readable}_{secrets.token_hex(3)}"[:50]
        if not User.objects.filter(handle=handle).exists():
            break
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                handle=handle,
                display_name=display_name,
            )
        return user, True
    except IntegrityError:
        existing = User.objects.filter(email__iexact=email).first()
        if existing is None:
            raise
        return existing, False
