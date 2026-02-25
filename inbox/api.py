import logging
from html import escape

from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError
from openai import OpenAI
from accounts.models import gravatar_url_for_email

from projects.models import Project

from .models import OwnerMessage

router = Router(tags=["inbox"])
logger = logging.getLogger(__name__)


class OwnerMessageCreateIn(Schema):
    body: str
    project_slug: Optional[str] = None
    sender_name: str = ""
    sender_email: str = ""


class OwnerMessageOut(Schema):
    id: int
    recipient_id: int
    recipient_handle: str
    project_id: Optional[int] = None
    project_slug: Optional[str] = None
    sender_user_id: Optional[int] = None
    sender_handle: Optional[str] = None
    sender_name: str
    sender_email: str
    sender_avatar_url: str
    body: str
    created_at: str


def _clean_non_empty(value: str, field_name: str):
    cleaned = value.strip()
    if not cleaned:
        raise HttpError(400, f"{field_name} cannot be empty.")
    return cleaned


def _require_auth_user(request):
    user = request.user
    if not user.is_authenticated:
        raise HttpError(401, "Authentication required.")
    return user


def _message_to_dict(message: OwnerMessage):
    return {
        "id": message.id,
        "recipient_id": message.recipient_id,
        "recipient_handle": message.recipient.handle,
        "project_id": message.project_id,
        "project_slug": message.project.slug if message.project else None,
        "sender_user_id": message.sender_user_id,
        "sender_handle": message.sender_user.handle if message.sender_user else None,
        "sender_name": message.sender_name,
        "sender_email": message.sender_email,
        "sender_avatar_url": gravatar_url_for_email(message.sender_email),
        "body": message.body,
        "created_at": message.created_at.isoformat(),
    }


def _resolve_project(owner, project_slug: Optional[str]):
    if not project_slug:
        return None

    return get_object_or_404(
        Project.objects.select_related("owner"),
        owner=owner,
        slug=project_slug,
    )


def _moderate_message_submission(body: str):
    api_key = settings.OPENAI_API_KEY.strip()
    if not api_key:
        return

    client = OpenAI(api_key=api_key)
    instructions = (
        "You moderate direct messages sent through a public feature board inbox. "
        "Default to ALLOW for normal human messages. "
        "Allow concise openers and exploratory questions even if broad (example: 'hey, are you looking for funding?'). "
        "Messages do not need to mention the owner by name or include specific project details. "
        "Allow respectful outreach about funding, hiring, partnerships, collaboration, support, or product feedback. "
        "Reject only messages that are clearly spam/scam, abusive/harassing/hateful, threatening, explicit sexual content, or empty/nonsensical gibberish. "
        "If uncertain, choose ALLOW. "
        "Respond with exactly one line. If valid: ALLOW. If invalid: REJECT: <short reason>."
    )

    try:
        response = client.responses.create(
            model="gpt-5-nano",
            reasoning={"effort": "minimal"},
            max_output_tokens=80,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": instructions}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": body}],
                },
            ],
        )
    except Exception:
        logger.exception("Content moderation call failed.")
        raise HttpError(503, "Content moderation is temporarily unavailable.")

    verdict = (getattr(response, "output_text", "") or "").strip()
    if not verdict:
        raise HttpError(503, "Content moderation is temporarily unavailable.")

    if verdict.lower().startswith("allow"):
        return

    reason = "Content is invalid."
    if ":" in verdict:
        parsed_reason = verdict.split(":", 1)[1].strip()
        if parsed_reason:
            reason = parsed_reason

    raise HttpError(400, f"Message rejected by moderation: {reason}")


def _notify_owner_on_new_message(request, message):
    subject = f"New message for @{message.recipient.handle} from {message.sender_name}"
    board_url = request.build_absolute_uri(f"/{message.recipient.handle}/")
    if message.project:
        board_url = request.build_absolute_uri(
            f"/{message.recipient.handle}/{message.project.slug}/"
        )

    plain_text = (
        f"{message.sender_name} ({message.sender_email}) sent you a message:\n\n"
        f"{message.body}\n\n"
        f"Open the board: {board_url}\n"
    )
    html_body = f"""<!DOCTYPE html>
<html>
  <body style="margin: 0; padding: 0; background: #f8fafc;">
    <div style="padding: 24px 16px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px;">
        <tr>
          <td style="padding: 20px 24px 8px 24px; font-family: Arial, sans-serif; color: #111827;">
            <h1 style="margin: 0; font-size: 20px;">New message for your board</h1>
          </td>
        </tr>
        <tr>
          <td style="padding: 0 24px 16px 24px; font-family: Arial, sans-serif; color: #374151; line-height: 1.6;">
            <p style="margin: 0 0 12px 0;">
              {escape(message.sender_name)} sent you a message.
            </p>
            <p style="margin: 0 0 16px 0;"><strong>Message:</strong><br>{escape(message.body)}</p>
            <a href="{escape(board_url)}" style="display: inline-block; background: #4f46e5; color: #ffffff; text-decoration: none; padding: 10px 16px; border-radius: 8px;">Open board</a>
          </td>
        </tr>
      </table>
    </div>
  </body>
</html>"""

    send_mail(
        subject,
        plain_text,
        settings.DEFAULT_FROM_EMAIL,
        [message.recipient.email],
        html_message=html_body,
        fail_silently=True,
    )


@router.post("/owners/{owner_handle}/messages", response={201: OwnerMessageOut})
def create_owner_message(request, owner_handle: str, payload: OwnerMessageCreateIn):
    User = get_user_model()
    owner = get_object_or_404(User, handle=owner_handle.lower())

    body = _clean_non_empty(payload.body, "Message body")

    sender_user = request.user if request.user.is_authenticated else None
    sender_name = payload.sender_name.strip()
    sender_email = payload.sender_email.strip().lower()

    if sender_user:
        if sender_user.id == owner.id:
            raise HttpError(400, "You cannot send a message to yourself.")
        if not sender_name:
            sender_name = sender_user.display_name.strip() or sender_user.handle
        if not sender_email:
            sender_email = sender_user.email
    else:
        sender_name = _clean_non_empty(sender_name, "sender_name")
        sender_email = _clean_non_empty(sender_email, "sender_email")

    _moderate_message_submission(body)
    project = _resolve_project(owner, payload.project_slug)

    message = OwnerMessage.objects.create(
        recipient=owner,
        project=project,
        sender_user=sender_user,
        sender_name=sender_name,
        sender_email=sender_email,
        body=body,
    )
    _notify_owner_on_new_message(request, message)
    message = OwnerMessage.objects.select_related(
        "recipient",
        "project",
        "sender_user",
    ).get(id=message.id)
    return 201, _message_to_dict(message)


@router.get("/me/messages", response=list[OwnerMessageOut])
def list_my_messages(request):
    user = _require_auth_user(request)
    messages = OwnerMessage.objects.select_related(
        "recipient",
        "project",
        "sender_user",
    ).filter(
        Q(recipient=user) | Q(sender_user=user)
    ).order_by("-created_at")
    return [_message_to_dict(message) for message in messages]
