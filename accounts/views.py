import json
import re

from html import escape

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.core.mail import send_mail
from django.http import JsonResponse
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.urls import reverse

import stripe
from sesame.utils import get_query_string

from .models import User

HANDLE_REGEX = re.compile(r"^[a-z0-9_]+$")


def _magic_link_email(user, magic_link, action):
    recipient_name = (user.display_name or f"@{user.handle}").strip()
    subject = f"Your {action} link for FeatureRequest"
    plain_text = (
        f"Hi {recipient_name},\n\n"
        f"Use the link below to {action} to your FeatureRequest account:\n"
        f"{magic_link}\n\n"
        "If this wasn't you, you can ignore this message.\n"
    )
    html_body = f"""<!DOCTYPE html>
<html>
  <body style="margin: 0; padding: 0; background: linear-gradient(145deg, #f2f5ff, #f9fafb);">
    <div style="padding: 32px 16px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #e5e7eb;">
        <tr>
          <td style="padding: 28px 32px 12px 32px;">
            <h1 style="margin: 0; font-family: Georgia, 'Times New Roman', serif; color: #111827; letter-spacing: 0.2px;">Your magic link is ready</h1>
          </td>
        </tr>
        <tr>
          <td style="padding: 0 32px 8px 32px; font-family: Arial, sans-serif; color: #374151;">
            <p style="margin: 0 0 14px; line-height: 1.6;">
              Hi {escape(recipient_name)},
            </p>
            <p style="margin: 0 0 14px; line-height: 1.6;">
              Click the button below to {action}.
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding: 0 32px 24px 32px;">
            <a href="{escape(magic_link)}" style="display: inline-block; background: #4f46e5; color: #ffffff; text-decoration: none; padding: 12px 22px; border-radius: 10px; font-family: Arial, sans-serif; font-weight: 700;">{action.title()} to FeatureRequest</a>
          </td>
        </tr>
        <tr>
          <td style="padding: 0 32px 24px 32px; font-family: Arial, sans-serif; color: #4b5563; word-break: break-all;">
            <p style="margin: 0 0 8px; line-height: 1.6;">
              If the button does not work, copy and paste this link:
            </p>
            <p style="margin: 0; line-height: 1.6;">
              {escape(magic_link)}
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding: 0 32px 28px 32px; font-family: Arial, sans-serif; color: #6b7280; font-size: 13px; line-height: 1.6;">
            <p style="margin: 0;">
              This link is valid for 30 minutes. If you did not request this email, simply ignore it.
            </p>
          </td>
        </tr>
      </table>
    </div>
  </body>
</html>"""
    return subject, plain_text, html_body


def _send_magic_link_email(user, magic_link, action):
    subject, plain_text, html_body = _magic_link_email(
        user=user,
        magic_link=magic_link,
        action=action,
    )
    send_mail(
        subject,
        plain_text,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_body,
        fail_silently=False,
    )


def _session_payload(user):
    if user.is_authenticated:
        return {
            "is_authenticated": True,
            "current_user_handle": user.handle,
            "user_id": user.id,
            "subscription_tier": user.subscription_tier,
            "subscription_status": user.subscription_status,
            "project_limit": user.project_limit,
        }
    return {
        "is_authenticated": False,
        "current_user_handle": "",
        "user_id": None,
        "subscription_tier": "free",
        "subscription_status": "",
        "project_limit": 1,
    }


def _json_payload(request):
    try:
        raw_body = request.body.decode("utf-8") if request.body else "{}"
        return json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _billing_user_from_event_payload(payload):
    user_id_raw = payload.get("client_reference_id") or payload.get("metadata", {}).get("user_id")
    if user_id_raw:
        try:
            user_id = int(user_id_raw)
        except (TypeError, ValueError):
            user_id = None
        else:
            user = User.objects.filter(id=user_id).first()
            if user:
                return user

    customer_id = payload.get("customer")
    if customer_id:
        return User.objects.filter(stripe_customer_id=str(customer_id)).first()

    return None


def _apply_subscription_state(user, tier, status, subscription_id=""):
    user.subscription_tier = tier
    user.subscription_status = status
    if subscription_id:
        user.stripe_subscription_id = str(subscription_id)
    elif user.subscription_tier != "pro_30":
        user.stripe_subscription_id = ""

    user.save(
        update_fields=[
            "subscription_tier",
            "subscription_status",
            "stripe_subscription_id",
        ]
    )


def _parse_stripe_event(request):
    payload = request.body or b""
    if not settings.STRIPE_WEBHOOK_SECRET:
        return json.loads(payload.decode("utf-8"))

    signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    return stripe.Webhook.construct_event(
        payload,
        signature,
        settings.STRIPE_WEBHOOK_SECRET,
    )


@ensure_csrf_cookie
def me_view(request):
    return JsonResponse(_session_payload(request.user))


@require_POST
def sign_in_view(request):
    payload = _json_payload(request)
    if payload is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    email_or_handle = str(payload.get("email_or_handle", "")).strip()
    if not email_or_handle:
        return JsonResponse({"detail": "email_or_handle is required."}, status=400)

    User = get_user_model()
    if "@" in email_or_handle:
        user = User.objects.filter(email__iexact=email_or_handle).first()
    else:
        user = User.objects.filter(handle=email_or_handle.lower()).first()

    if user is None:
        return JsonResponse({"detail": "Account not found. Please sign up first."}, status=404)

    if "@" in email_or_handle:
        magic_link = request.build_absolute_uri(reverse("magic-link-login")) + get_query_string(user)
        _send_magic_link_email(
            user=user,
            magic_link=magic_link,
            action="sign in",
        )
        return JsonResponse(
            {"detail": "Sign-in link sent. Check your email."},
            status=200,
        )

    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    return JsonResponse(_session_payload(user))


@require_POST
def sign_up_view(request):
    payload = _json_payload(request)
    if payload is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    email = str(payload.get("email", "")).strip().lower()
    handle = str(payload.get("handle", "")).strip().lower()
    display_name = str(payload.get("display_name", "")).strip()

    if not email:
        return JsonResponse({"detail": "email is required."}, status=400)
    if not handle:
        return JsonResponse({"detail": "handle is required."}, status=400)
    if not HANDLE_REGEX.fullmatch(handle):
        return JsonResponse(
            {
                "detail": "Handle can only include lowercase letters, numbers, and underscore.",
            },
            status=400,
        )

    User = get_user_model()
    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse({"detail": "This email is already registered."}, status=400)
    if User.objects.filter(handle=handle).exists():
        return JsonResponse({"detail": "This handle is already taken."}, status=400)

    user = User.objects.create_user(
        email=email,
        handle=handle,
        display_name=display_name,
    )
    magic_link = request.build_absolute_uri(reverse("magic-link-login")) + get_query_string(user)
    _send_magic_link_email(
        user=user,
        magic_link=magic_link,
        action="sign up",
    )
    return JsonResponse({"detail": "Sign-up link sent. Check your email."}, status=200)


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    try:
        event = _parse_stripe_event(request)
    except (json.JSONDecodeError, ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    event_type = str(event.get("type", ""))
    payload = event.get("data", {}).get("object", {}) or {}

    if event_type == "checkout.session.completed":
        if payload.get("mode") != "subscription":
            return HttpResponse("ok")

        user = _billing_user_from_event_payload(payload)
        subscription_id = payload.get("subscription")
        if user and subscription_id:
            _apply_subscription_state(user, "pro_30", "active", subscription_id)
        return HttpResponse("ok")

    if event_type in {"customer.subscription.created", "customer.subscription.updated"}:
        user = _billing_user_from_event_payload(payload)
        if user is None:
            return HttpResponse("ok")

        status = str(payload.get("status", "")).lower()
        subscription_id = payload.get("id")

        if status == "active":
            _apply_subscription_state(user, "pro_30", "active", subscription_id)
            return HttpResponse("ok")

        _apply_subscription_state(user, "free", status, subscription_id)
        return HttpResponse("ok")

    if event_type == "customer.subscription.deleted":
        user = _billing_user_from_event_payload(payload)
        if user is not None:
            _apply_subscription_state(user, "free", "canceled", payload.get("id", ""))

    return HttpResponse("ok")
