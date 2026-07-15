import json
import logging
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import login
from django.db import transaction
from django.http import HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_http_methods

from .embed import get_or_create_embed_user, token_digest
from .models import EmbeddedIssueSubmission, Issue, Project


logger = logging.getLogger(__name__)

RESERVED_BACKEND_PREFIXES = {"api", "api-docs", "auth", "embed", "stripe"}
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _safe_accent(value):
    candidate = str(value or "").strip()
    return candidate.upper() if HEX_COLOR_RE.fullmatch(candidate) else "#06B6D4"


def _accent_contrast(accent):
    red, green, blue = (int(accent[index : index + 2], 16) for index in (1, 3, 5))
    luminance = (red * 299 + green * 587 + blue * 114) / 1000
    return "#111827" if luminance > 160 else "#FFFFFF"


def _embed_csp_response(response):
    static_url = static("projects/embed-panel.js")
    parsed_static_url = urlsplit(static_url)
    static_source = (
        f" {parsed_static_url.scheme}://{parsed_static_url.netloc}"
        if parsed_static_url.scheme in {"http", "https"} and parsed_static_url.netloc
        else ""
    )
    response["Content-Security-Policy"] = (
        "default-src 'none'; "
        f"script-src 'self'{static_source} https://challenges.cloudflare.com; "
        f"style-src 'self'{static_source} 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' https: data:; "
        "connect-src 'self' https://challenges.cloudflare.com; "
        "frame-src https://challenges.cloudflare.com; "
        "form-action 'self'; base-uri 'none'; frame-ancestors *"
    )
    response["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def _verification_response(request, context, status=200):
    response = render(request, "projects/embed_verify.html", context, status=status)
    response["Cache-Control"] = "no-store"
    # Keep the tokenized path out of referrers without making form Origin null.
    response["Referrer-Policy"] = "strict-origin"
    return response


def _frontend_session_payload(user):
    if user.is_authenticated:
        return {
            "isAuthenticated": True,
            "currentUserHandle": user.handle,
            "currentUserAvatarUrl": user.avatar_url,
            "user_id": user.id,
            "subscription_tier": user.subscription_tier,
            "subscription_status": user.subscription_status,
            "project_limit": user.project_limit,
        }

    return {
        "isAuthenticated": False,
        "currentUserHandle": "",
        "currentUserAvatarUrl": "",
        "user_id": None,
        "subscription_tier": "free",
        "subscription_status": "",
        "project_limit": 1,
    }


@ensure_csrf_cookie
def frontend_app(request, spa_path=""):
    first_segment = str(spa_path or "").strip("/").split("/", 1)[0]
    if first_segment in RESERVED_BACKEND_PREFIXES:
        return HttpResponseNotFound("Not found.")

    bootstrap = _frontend_session_payload(request.user)
    return render(
        request,
        "projects/app.html",
        {
            "admin_url": settings.ADMIN_URL,
            "fr_bootstrap_json": json.dumps(bootstrap),
            "spa_path": spa_path,
        },
    )


@ensure_csrf_cookie
@xframe_options_exempt
def embed_widget(request, owner_handle, project_slug):
    project = get_object_or_404(
        Project.objects.select_related("owner"),
        owner__handle=str(owner_handle or "").strip().lower(),
        slug=project_slug,
    )
    accent = _safe_accent(request.GET.get("accent"))
    preview = request.GET.get("preview") == "1"
    context = {
        "project": project,
        "accent": accent,
        "accent_contrast": _accent_contrast(accent),
        "preview": preview,
        "turnstile_sitekey": settings.TURNSTILE_SITEKEY,
        "board_url": request.build_absolute_uri(
            f"/{project.owner.handle}/{project.slug}/"
        ),
        "submission_api_url": (
            f"/api/embed/projects/{project.owner.handle}/{project.slug}/submissions"
        ),
    }
    response = render(request, "projects/embed_widget.html", context)
    response["Cache-Control"] = "private, no-store"
    return _embed_csp_response(response)


@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def embed_submission_verify(request, token):
    if not token or len(token) > 128:
        return _verification_response(
            request,
            {"state": "invalid", "message": "This verification link is invalid."},
            status=404,
        )

    digest = token_digest(token)
    submission = (
        EmbeddedIssueSubmission.objects.select_related(
            "project__owner",
            "issue__author",
        )
        .filter(token_hash=digest)
        .first()
    )
    if submission is None:
        return _verification_response(
            request,
            {"state": "invalid", "message": "This verification link is invalid."},
            status=404,
        )

    if submission.issue_id:
        login(
            request,
            submission.issue.author,
            backend=settings.AUTHENTICATION_BACKENDS[0],
        )
        return redirect(
            f"/{submission.project.owner.handle}/{submission.project.slug}/issues/{submission.issue_id}/"
        )

    if submission.expires_at <= timezone.now():
        return _verification_response(
            request,
            {
                "state": "expired",
                "message": "This verification link has expired. Submit the request again from the widget.",
                "project": submission.project,
                "board_url": f"/{submission.project.owner.handle}/{submission.project.slug}/",
            },
            status=410,
        )

    if request.method == "GET":
        return _verification_response(
            request,
            {
                "state": "confirm",
                "submission": submission,
                "project": submission.project,
                "board_url": f"/{submission.project.owner.handle}/{submission.project.slug}/",
            },
        )

    created_issue = False
    with transaction.atomic():
        locked = (
            EmbeddedIssueSubmission.objects.select_for_update()
            .select_related("project__owner", "issue__author")
            .get(pk=submission.pk)
        )
        if locked.issue_id:
            issue = locked.issue
            user = issue.author
        elif locked.expires_at <= timezone.now():
            return _verification_response(
                request,
                {
                    "state": "expired",
                    "message": "This verification link has expired. Submit the request again from the widget.",
                    "project": locked.project,
                    "board_url": f"/{locked.project.owner.handle}/{locked.project.slug}/",
                },
                status=410,
            )
        else:
            user, _created = get_or_create_embed_user(
                locked.email,
                locked.display_name,
            )
            issue = Issue.objects.create(
                project=locked.project,
                author=user,
                issue_type=locked.issue_type,
                title=locked.title,
                description=locked.description,
                status=Issue.Status.OPEN,
                priority=Issue.Priority.MEDIUM,
            )
            created_issue = True
            locked.issue = issue
            locked.verified_at = timezone.now()
            locked.display_name = ""
            locked.email = ""
            locked.issue_type = ""
            locked.title = ""
            locked.description = ""
            locked.save(
                update_fields=[
                    "issue",
                    "verified_at",
                    "display_name",
                    "email",
                    "issue_type",
                    "title",
                    "description",
                ]
            )

    login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
    if created_issue:
        try:
            from .api import _notify_owner_on_new_issue

            _notify_owner_on_new_issue(request, issue, user)
        except Exception:
            logger.exception("Owner notification failed for verified embed issue %s.", issue.id)
    return redirect(
        f"/{issue.project.owner.handle}/{issue.project.slug}/issues/{issue.id}/"
    )
