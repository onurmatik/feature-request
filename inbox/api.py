from typing import Optional

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from projects.models import Project

from .models import OwnerMessage

router = Router(tags=["inbox"])


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

    project = _resolve_project(owner, payload.project_slug)

    message = OwnerMessage.objects.create(
        recipient=owner,
        project=project,
        sender_user=sender_user,
        sender_name=sender_name,
        sender_email=sender_email,
        body=body,
    )
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
    ).filter(recipient=user)
    return [_message_to_dict(message) for message in messages]
