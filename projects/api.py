import logging
import re
import ssl
from html.parser import HTMLParser
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from html import escape

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import URLValidator, validate_email
from django.db.models import Count, F, Max, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from openai import OpenAI

from accounts.models import gravatar_url_for_email

from .embed import (
    EmbedSubmissionError,
    create_pending_submission,
    validate_turnstile,
)
from .events import record_issue_event
from .models import (
    Issue,
    IssueComment,
    IssueDeliveryArtifact,
    IssueEvent,
    IssueUpvote,
    Project,
)

router = Router(tags=["issues"])
logger = logging.getLogger(__name__)


class IssueCreateIn(Schema):
    issue_type: str = Issue.Type.FEATURE
    title: str
    description: str = ""
    priority: int = Issue.Priority.MEDIUM


class EmbedSubmissionIn(Schema):
    display_name: str
    email: str
    issue_type: str = Issue.Type.FEATURE
    title: str
    description: str = ""
    turnstile_token: str


class EmbedSubmissionOut(Schema):
    status: str


class ProjectOut(Schema):
    id: int
    owner_id: int
    owner_handle: str
    name: str
    slug: str
    tagline: str
    url: str
    favicon_url: str
    open_issues_count: int
    created_at: str
    updated_at: str


class FeaturedProjectOut(Schema):
    id: int
    owner_handle: str
    name: str
    slug: str
    tagline: str
    issues_count: int
    updated_at: str


class ProjectCreateIn(Schema):
    name: str
    tagline: str = ""
    url: str = ""


class ProjectUpdateIn(Schema):
    name: Optional[str] = None
    tagline: Optional[str] = None
    url: Optional[str] = None


class IssueUpdateIn(Schema):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None


class IssueOut(Schema):
    id: int
    project_id: int
    author_id: int
    author_handle: str
    author_display_name: str
    author_avatar_url: str
    issue_type: str
    title: str
    description: str
    status: str
    priority: int
    duplicate_of_id: Optional[int]
    upvotes_count: int
    comments_count: int
    delivery_artifacts_count: int
    last_activity_at: str
    created_at: str
    updated_at: str


class UpvoteToggleOut(Schema):
    issue_id: int
    upvoted: bool
    upvotes_count: int


class CommentCreateIn(Schema):
    body: str


class CommentOut(Schema):
    id: int
    issue_id: int
    author_id: int
    author_handle: str
    author_avatar_url: str
    body: str
    created_at: str
    updated_at: str


class DuplicateCandidateOut(Schema):
    issue_id: int
    title: str
    description: str
    issue_type: str
    status: str
    priority: int
    duplicate_of_id: Optional[int]
    algorithm: str
    similarity_score: float
    matched_terms: list[str]
    score_components: dict[str, float]


class DuplicateLinkIn(Schema):
    canonical_issue_id: int


class DeliveryArtifactIn(Schema):
    kind: str
    url: str
    label: str = ""


class DeliveryArtifactOut(Schema):
    id: int
    issue_id: int
    added_by_id: int
    added_by_handle: str
    kind: str
    url: str
    label: str
    created_at: str


class DeliveryArtifactLinkOut(Schema):
    created: bool
    artifact: DeliveryArtifactOut


class IssueEventOut(Schema):
    id: int
    issue_id: int
    project_id: int
    event_type: str
    actor_id: Optional[int]
    actor_handle: Optional[str]
    data: dict[str, Any]
    created_at: str


class ChangeFeedOut(Schema):
    events: list[IssueEventOut]
    next_cursor: int
    has_more: bool


class QueueSnapshotOut(Schema):
    generated_at: str
    projects_count: int
    active_requests_count: int
    status_counts: dict[str, int]
    priority_counts: dict[str, int]
    requests: list[IssueOut]


def _require_auth_user(request):
    user = request.user
    if not user.is_authenticated:
        raise HttpError(401, "Authentication required.")
    return user


def _validate_issue_type(issue_type: str):
    allowed = {value for value, _ in Issue.Type.choices}
    if issue_type not in allowed:
        raise HttpError(400, "Invalid issue_type.")


def _validate_status(status: str):
    allowed = {value for value, _ in Issue.Status.choices}
    if status not in allowed:
        raise HttpError(400, "Invalid status.")


def _filter_issues_by_status(queryset, status: Optional[str]):
    if not status:
        return queryset
    if status == "active":
        return queryset.exclude(
            status__in=[Issue.Status.DONE, Issue.Status.CLOSED]
        )
    _validate_status(status)
    return queryset.filter(status=status)


def _validate_priority(priority: int):
    allowed = {value for value, _ in Issue.Priority.choices}
    if priority not in allowed:
        raise HttpError(400, "Invalid priority.")


def _validate_delivery_kind(kind: str):
    allowed = {value for value, _ in IssueDeliveryArtifact.Kind.choices}
    if kind not in allowed:
        raise HttpError(400, "Invalid delivery artifact kind.")


def _validate_limit(limit: int, *, maximum: int = 100):
    if limit < 1 or limit > maximum:
        raise HttpError(400, f"limit must be between 1 and {maximum}.")
    return limit


def _limit_issues(queryset, limit: Optional[int]):
    if limit is None:
        return queryset
    _validate_limit(limit)
    return queryset[:limit]


def _can_manage_issue(user, issue: Issue):
    return user.id == issue.project.owner_id or user.id == issue.author_id


def _can_manage_project(user, project: Project):
    return user.id == project.owner_id


def _clean_non_empty(value: str, field_name: str):
    cleaned = value.strip()
    if not cleaned:
        raise HttpError(400, f"{field_name} cannot be empty.")
    return cleaned


_DUPLICATE_TERM_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_DUPLICATE_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "bir",
    "bu",
    "da",
    "de",
    "for",
    "ile",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "ve",
}


def _duplicate_terms(value: str):
    return {
        term
        for term in _DUPLICATE_TERM_PATTERN.findall((value or "").casefold())
        if len(term) > 1 and term not in _DUPLICATE_STOP_WORDS
    }


def _jaccard_similarity(left: set[str], right: set[str]):
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _duplicate_candidate_dict(issue: Issue, *, title: str, description: str):
    query_title_terms = _duplicate_terms(title)
    issue_title_terms = _duplicate_terms(issue.title)
    query_content_terms = query_title_terms | _duplicate_terms(description)
    issue_content_terms = issue_title_terms | _duplicate_terms(issue.description)
    title_score = _jaccard_similarity(query_title_terms, issue_title_terms)
    content_score = _jaccard_similarity(query_content_terms, issue_content_terms)
    similarity_score = (0.7 * title_score) + (0.3 * content_score)

    return {
        "issue_id": issue.id,
        "title": issue.title,
        "description": issue.description,
        "issue_type": issue.issue_type,
        "status": issue.status,
        "priority": issue.priority,
        "duplicate_of_id": issue.duplicate_of_id,
        "algorithm": "weighted_jaccard_v1",
        "similarity_score": round(similarity_score, 4),
        "matched_terms": sorted(query_content_terms & issue_content_terms),
        "score_components": {
            "title_jaccard": round(title_score, 4),
            "content_jaccard": round(content_score, 4),
            "title_weight": 0.7,
            "content_weight": 0.3,
        },
    }


class _FaviconHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link":
            return

        values = {name.lower(): (value or "").strip() for name, value in attrs}
        rel = values.get("rel", "").lower()
        href = values.get("href", "")
        if not href:
            return

        tokens = rel.split()
        if not (
            "icon" in tokens
            or "shortcut" in tokens
            or "apple-touch-icon" in tokens
            or "mask-icon" in tokens
        ):
            return

        self.urls.append(href)


def _append_debug(debug: Optional[list[str]], message: str):
    if debug is None:
        return
    debug.append(message)


def _normalize_favicon_candidate(base_url: str, candidate: str):
    if not candidate:
        return ""
    normalized = urljoin(base_url, candidate)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return normalized


def _normalize_project_url(url: str):
    candidate = (url or "").strip()
    if not candidate:
        return ""

    parsed = urlparse(candidate)
    if parsed.scheme:
        return candidate

    if candidate.startswith("//"):
        return f"https:{candidate}"

    if candidate.startswith("/"):
        return candidate

    if " " in candidate:
        return candidate

    return f"https://{candidate}"


def _open_url(request: Request, timeout: int, debug: Optional[list[str]] = None):
    try:
        return urlopen(request, timeout=timeout)
    except URLError as error:
        reason = getattr(error, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            _append_debug(
                debug,
                "SSL certificate verification failed; retrying without verification",
            )
            return urlopen(
                request,
                timeout=timeout,
                context=ssl._create_unverified_context(),
            )
        raise


def _fetch_url_headers(url: str, method: str = "HEAD", debug: Optional[list[str]] = None):
    _append_debug(debug, f"{method} {url}")

    request = Request(
        url,
        method=method,
        headers={"User-Agent": "FeatureRequest/1.0 (+https://github.com/)"},
    )
    try:
        with _open_url(request, timeout=5, debug=debug) as response:
            status = getattr(response, "status", 0)
            if not (200 <= status < 400):
                _append_debug(debug, f"Rejected with status {status}")
                return None
            content_type = (response.getheader("Content-Type") or "").lower()
            _append_debug(debug, f"Status {status}; content-type: {content_type or '(missing)'}")
            return response.headers
    except HTTPError as error:
        if method == "HEAD" and error.code == 405:
            _append_debug(debug, "HEAD not supported, retrying with GET")
            return _fetch_url_headers(url, method="GET", debug=debug)
        _append_debug(debug, f"HTTP error {error.code}: {getattr(error, 'reason', '')}")
        return None
    except URLError as error:
        _append_debug(debug, f"Network error for {url}: {getattr(error, 'reason', error)}")
        return None
    except Exception as error:
        _append_debug(debug, f"Unexpected error for {url}: {error}")
        return None


def _content_length_is_zero(headers):
    raw_content_length = headers.get("Content-Length")
    if raw_content_length is None:
        return False

    try:
        return int(raw_content_length) == 0
    except (TypeError, ValueError):
        return False


def _extract_project_favicon_url(base_url: str, debug: Optional[list[str]] = None):
    request = Request(
        base_url,
        headers={"User-Agent": "FeatureRequest/1.0 (+https://github.com/)"},
    )
    try:
        with _open_url(request, timeout=5, debug=debug) as response:
            status = getattr(response, "status", 0)
            if not (200 <= status < 400):
                _append_debug(debug, f"Page response status: {status}")
                return []
            content_type = (response.getheader("Content-Type") or "").lower()
            if "text/html" not in content_type:
                _append_debug(
                    debug,
                    f"Project URL is not HTML (content-type: {content_type})",
                )
                return []

            body_chunks = []
            body_size = 0
            max_bytes = 1_048_576
            while body_size < max_bytes:
                chunk = response.read(8192)
                if not chunk:
                    break

                body_chunks.append(chunk)
                body_size += len(chunk)
                merged = b"".join(body_chunks)
                if b"</head>" in merged.lower():
                    break

            body = b"".join(body_chunks).decode("utf-8", errors="ignore")
    except HTTPError:
        _append_debug(debug, f"HTTP error while fetching page HTML for {base_url}")
        return []
    except URLError as error:
        _append_debug(
            debug,
            f"Network error while fetching page HTML for {base_url}: {getattr(error, 'reason', error)}",
        )
        return []
    except Exception as error:
        _append_debug(debug, f"Unexpected error while fetching page HTML for {base_url}: {error}")
        return []

    parser = _FaviconHTMLParser()
    parser.feed(body)
    _append_debug(
        debug,
        f"Parsed {len(parser.urls)} favicon candidates from HTML: {parser.urls[:5]}",
    )
    return parser.urls


def _resolve_favicon_url_internal(project_url: str, collect_debug: bool = False):
    debug: Optional[list[str]] = [] if collect_debug else None
    normalized_project_url = _normalize_project_url(project_url)
    if normalized_project_url != project_url:
        _append_debug(
            debug,
            f"Normalized project URL from {project_url} to {normalized_project_url}",
        )

    parsed = urlparse(normalized_project_url)
    if parsed.scheme not in {"http", "https"}:
        _append_debug(
            debug,
            f"Skipping favicon lookup because scheme is not http/https: {normalized_project_url}",
        )
        return "", debug

    candidates = _extract_project_favicon_url(normalized_project_url, debug=debug)
    candidates.extend([
        "/favicon.ico",
        "/favicon.png",
        "/icon.png",
        "/apple-touch-icon.png",
        "/apple-touch-icon-precomposed.png",
    ])
    candidates = list(dict.fromkeys([value for value in candidates if value]))
    _append_debug(debug, f"Trying {len(candidates)} favicon candidates")

    for candidate in candidates:
        resolved = _normalize_favicon_candidate(normalized_project_url, candidate)
        if not resolved:
            _append_debug(debug, f"Skipping unsupported favicon candidate: {candidate}")
            continue

        headers = _fetch_url_headers(resolved, debug=debug)
        if not headers:
            _append_debug(debug, f"No valid response for favicon candidate: {resolved}")
            continue

        content_type = (headers.get("Content-Type") or "").lower()
        if content_type and "text/html" in content_type:
            _append_debug(debug, f"Rejected HTML response for favicon candidate: {resolved}")
            continue

        if _content_length_is_zero(headers):
            _append_debug(debug, f"Rejected empty favicon response for candidate: {resolved}")
            continue

        _append_debug(debug, f"Selected favicon candidate: {resolved}")
        return resolved, debug

    _append_debug(debug, f"No favicon candidate resolved for {normalized_project_url}")
    return "", debug


def _resolve_favicon_url_with_debug(project_url: str):
    return _resolve_favicon_url_internal(project_url, collect_debug=True)


def _resolve_favicon_url(project_url: str):
    return _resolve_favicon_url_internal(project_url)[0]


def _moderate_issue_submission(issue_type: str, title: str, description: str):
    content = (
        f"issue_type: {issue_type}\n"
        f"title: {title}\n"
        f"description: {description or '(empty)'}"
    )
    _moderate_board_content("Issue", content, issue_type="issue")


def _moderate_comment_submission(body: str, issue: Issue):
    recent_comments = issue.comments.order_by("-created_at").values_list("body", flat=True)[:3]
    context_lines = [
        f"issue_title: {issue.title}",
        f"issue_description: {issue.description or '(empty)'}",
    ]

    if recent_comments:
        context_lines.append("recent_comments:")
        for idx, comment_body in enumerate(recent_comments, start=1):
            context_lines.append(f"{idx}. {comment_body[:360]}")

    context = "\n".join(context_lines)
    content = f"comment:\n{body}\n\nthread_context:\n{context}"
    _moderate_board_content("Comment", content, issue_type=None)


def _moderate_board_content(label: str, content: str, issue_type: str | None = None):
    api_key = settings.OPENAI_API_KEY.strip()
    if not api_key:
        return

    client = OpenAI(api_key=api_key)
    policy = (
        "Allow only meaningful feature requests or bug reports. "
        "Reject empty, nonsensical, spam, abusive, or unrelated posts."
        if issue_type == "issue"
        else (
            "Allow comments that are constructive and related to the issue context, "
            "including concise agreement/disagreement, clarifying questions, suggestions, "
            "and relevant source references. "
            "Reject empty, nonsensical, spam, abusive, promotional, or clearly unrelated posts. "
            "When uncertain, choose ALLOW."
        )
    )

    instructions = (
        "You moderate content for a public product board. "
        f"{policy} "
        "Respond with exactly one line. "
        "If valid: ALLOW. "
        "If invalid: REJECT: <short reason>."
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
                    "content": [{"type": "input_text", "text": content}],
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
    raise HttpError(400, f"{label} rejected by moderation: {reason}")


def _issue_to_dict(issue: Issue):
    upvotes_count = getattr(issue, "upvotes_count", None)
    comments_count = getattr(issue, "comments_count", None)
    delivery_artifacts_count = getattr(issue, "delivery_artifacts_count", None)
    activity_values = [
        issue.created_at,
        issue.updated_at,
        getattr(issue, "_last_comment_at", None),
        getattr(issue, "_last_event_at", None),
    ]
    last_activity_at = max(value for value in activity_values if value is not None)
    return {
        "id": issue.id,
        "project_id": issue.project_id,
        "author_id": issue.author_id,
        "author_handle": issue.author.handle,
        "author_display_name": (issue.author.display_name or issue.author.handle).strip(),
        "author_avatar_url": gravatar_url_for_email(issue.author.email),
        "issue_type": issue.issue_type,
        "title": issue.title,
        "description": issue.description,
        "status": issue.status,
        "priority": issue.priority,
        "duplicate_of_id": issue.duplicate_of_id,
        "upvotes_count": upvotes_count if upvotes_count is not None else issue.upvotes.count(),
        "comments_count": comments_count if comments_count is not None else issue.comments.count(),
        "delivery_artifacts_count": (
            delivery_artifacts_count
            if delivery_artifacts_count is not None
            else issue.delivery_artifacts.count()
        ),
        "last_activity_at": last_activity_at.isoformat(),
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
    }


def _project_to_dict(project: Project):
    open_issues_count = getattr(project, "open_issues_count", None)
    return {
        "id": project.id,
        "owner_id": project.owner_id,
        "owner_handle": project.owner.handle,
        "name": project.name,
        "slug": project.slug,
        "tagline": project.tagline,
        "url": project.url,
        "favicon_url": project.favicon_url,
        "open_issues_count": (
            open_issues_count
            if open_issues_count is not None
            else project.issues.filter(status=Issue.Status.OPEN).count()
        ),
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def _annotate_open_issues_count(queryset):
    return queryset.annotate(
        open_issues_count=Count(
            "issues",
            filter=Q(issues__status=Issue.Status.OPEN),
            distinct=True,
        )
    )


def _order_projects_by_last_request(queryset):
    return queryset.annotate(
        _last_request_at=Coalesce(Max("issues__created_at"), F("created_at"))
    ).order_by("-_last_request_at", "-created_at", "-id")


def _featured_project_to_dict(project: Project):
    return {
        "id": project.id,
        "owner_handle": project.owner.handle,
        "name": project.name,
        "slug": project.slug,
        "tagline": project.tagline,
        "issues_count": getattr(project, "issues_count", 0),
        "updated_at": project.updated_at.isoformat(),
    }


def _comment_to_dict(comment: IssueComment):
    return {
        "id": comment.id,
        "issue_id": comment.issue_id,
        "author_id": comment.author_id,
        "author_handle": comment.author.handle,
        "author_avatar_url": gravatar_url_for_email(comment.author.email),
        "body": comment.body,
        "created_at": comment.created_at.isoformat(),
        "updated_at": comment.updated_at.isoformat(),
    }


def _delivery_artifact_to_dict(artifact: IssueDeliveryArtifact):
    return {
        "id": artifact.id,
        "issue_id": artifact.issue_id,
        "added_by_id": artifact.added_by_id,
        "added_by_handle": artifact.added_by.handle,
        "kind": artifact.kind,
        "url": artifact.url,
        "label": artifact.label,
        "created_at": artifact.created_at.isoformat(),
    }


def _issue_event_to_dict(event: IssueEvent):
    return {
        "id": event.id,
        "issue_id": event.issue_id,
        "project_id": event.issue.project_id,
        "event_type": event.event_type,
        "actor_id": event.actor_id,
        "actor_handle": event.actor.handle if event.actor_id else None,
        "data": event.data,
        "created_at": event.created_at.isoformat(),
    }


def _owner_display_name(user):
    return (user.display_name or user.handle).strip() or user.email


def _issue_board_url(request, issue):
    return request.build_absolute_uri(f"/{issue.project.owner.handle}/{issue.project.slug}/")


def _notify_owner_on_new_issue(request, issue: Issue, actor):
    if actor.id == issue.project.owner_id:
        return

    subject = f"New request on {issue.project.owner.handle}/{issue.project.slug}: {issue.title}"
    board_url = _issue_board_url(request, issue)
    plain_text = (
        f"{_owner_display_name(actor)} ({actor.email}) posted a new request for @{issue.project.owner.handle}.\n\n"
        f"Title: {issue.title}\n"
        f"Type: {issue.get_issue_type_display()}\n"
        f"Priority: {issue.get_priority_display()}\n"
        f"Description:\n{issue.description or '(No description)'}\n\n"
        f"Open the board: {board_url}\n"
    )
    html_body = f"""<!DOCTYPE html>
<html>
  <body style="margin: 0; padding: 0; background: #f8fafc;">
    <div style="padding: 24px 16px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px;">
        <tr>
          <td style="padding: 20px 24px 8px 24px; font-family: Arial, sans-serif; color: #111827;">
            <h1 style="margin: 0; font-size: 20px;">New request for your board</h1>
          </td>
        </tr>
        <tr>
          <td style="padding: 0 24px 16px 24px; font-family: Arial, sans-serif; color: #374151; line-height: 1.6;">
            <p style="margin: 0 0 12px 0;">
              {_owner_display_name(actor)} has posted a new request on {escape(issue.project.owner.handle)}.
            </p>
            <p style="margin: 0 0 12px 0;"><strong>Title:</strong> {escape(issue.title)}</p>
            <p style="margin: 0 0 12px 0;"><strong>Type:</strong> {issue.get_issue_type_display()}</p>
            <p style="margin: 0 0 12px 0;"><strong>Priority:</strong> {issue.get_priority_display()}</p>
            <p style="margin: 0 0 16px 0;"><strong>Description:</strong><br>{escape(issue.description or "(No description)")}</p>
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
        [issue.project.owner.email],
        html_message=html_body,
        fail_silently=True,
    )


def _notify_owner_on_new_comment(request, comment: IssueComment):
    if comment.author_id == comment.issue.project.owner_id:
        return

    owner = comment.issue.project.owner
    subject = f"New comment on request #{comment.issue_id} for @{owner.handle}"
    board_url = _issue_board_url(request, comment.issue)
    plain_text = (
        f"{_owner_display_name(comment.author)} ({comment.author.email}) commented on issue #{comment.issue_id}.\n\n"
        f"Issue title: {comment.issue.title}\n"
        f"Comment:\n{comment.body}\n\n"
        f"Open the board: {board_url}\n"
    )
    html_body = f"""<!DOCTYPE html>
<html>
  <body style="margin: 0; padding: 0; background: #f8fafc;">
    <div style="padding: 24px 16px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px;">
        <tr>
          <td style="padding: 20px 24px 8px 24px; font-family: Arial, sans-serif; color: #111827;">
            <h1 style="margin: 0; font-size: 20px;">New comment on your request</h1>
          </td>
        </tr>
        <tr>
          <td style="padding: 0 24px 16px 24px; font-family: Arial, sans-serif; color: #374151; line-height: 1.6;">
            <p style="margin: 0 0 12px 0;">
              {_owner_display_name(comment.author)} commented on issue #{comment.issue_id}.
            </p>
            <p style="margin: 0 0 12px 0;"><strong>Issue:</strong> {escape(comment.issue.title)}</p>
            <p style="margin: 0 0 16px 0;"><strong>Comment:</strong><br>{escape(comment.body)}</p>
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
        [owner.email],
        html_message=html_body,
        fail_silently=True,
    )


def _get_project(owner_handle: str, project_slug: str):
    return get_object_or_404(
        Project.objects.select_related("owner"),
        owner__handle=owner_handle.lower(),
        slug=project_slug,
    )


def _get_owner(owner_handle: str):
    User = get_user_model()
    return get_object_or_404(User, handle=owner_handle.lower())


def _get_annotated_issue_queryset():
    return Issue.objects.select_related("project", "author", "duplicate_of").annotate(
        upvotes_count=Count("upvotes", distinct=True),
        comments_count=Count("comments", distinct=True),
        delivery_artifacts_count=Count("delivery_artifacts", distinct=True),
        _last_comment_at=Coalesce(Max("comments__updated_at"), F("created_at")),
        _last_event_at=Max("events__created_at"),
    )


@router.get("/projects", response=list[ProjectOut])
def list_my_projects(request):
    user = _require_auth_user(request)
    projects = _order_projects_by_last_request(
        _annotate_open_issues_count(Project.objects.select_related("owner").filter(owner=user))
    )
    return [_project_to_dict(project) for project in projects]


@router.post("/projects", response={201: ProjectOut})
def create_project(request, payload: ProjectCreateIn):
    user = _require_auth_user(request)

    if user.has_project_limit(Project.objects.filter(owner=user).count()):
        raise HttpError(
            403,
            "You have reached your project limit. Upgrade to 30 projects to continue.",
        )

    name = _clean_non_empty(payload.name, "Project name")
    url = _normalize_project_url(payload.url)
    favicon_url = ""
    if url:
        favicon_url, favicon_debug = _resolve_favicon_url_with_debug(url)
        if not favicon_url:
            logger.warning(
                "Could not resolve favicon for new project url=%s. debug=%s",
                url,
                " | ".join(favicon_debug),
            )
    else:
        favicon_debug = []

    project = Project.objects.create(
        owner=user,
        name=name,
        tagline=payload.tagline.strip(),
        url=url,
        favicon_url=favicon_url,
    )
    project = Project.objects.select_related("owner").get(id=project.id)
    return 201, _project_to_dict(project)


@router.get("/projects/{project_id}", response=ProjectOut)
def get_my_project(request, project_id: int):
    user = _require_auth_user(request)
    project = get_object_or_404(
        Project.objects.select_related("owner"),
        id=project_id,
        owner=user,
    )
    return _project_to_dict(project)


@router.patch("/projects/{project_id}", response=ProjectOut)
def update_project(request, project_id: int, payload: ProjectUpdateIn):
    user = _require_auth_user(request)
    project = get_object_or_404(
        Project.objects.select_related("owner"),
        id=project_id,
    )
    if not _can_manage_project(user, project):
        raise HttpError(403, "Not allowed to update this project.")

    updated_fields = []

    if payload.name is not None:
        project.name = _clean_non_empty(payload.name, "Project name")
        updated_fields.append("name")

    if payload.tagline is not None:
        project.tagline = payload.tagline.strip()
        updated_fields.append("tagline")

    if payload.url is not None:
        url = _normalize_project_url(payload.url)
        project.url = url
        updated_fields.append("url")

    if updated_fields:
        if project.url:
            project.favicon_url, favicon_debug = _resolve_favicon_url_with_debug(project.url)
            if not project.favicon_url:
                logger.warning(
                    "Could not resolve favicon for project_id=%s url=%s. debug=%s",
                    project.id,
                    project.url,
                    " | ".join(favicon_debug),
                )
        else:
            project.favicon_url = ""
            favicon_debug = []
        updated_fields.append("favicon_url")

        project.save()

    return _project_to_dict(project)


@router.delete("/projects/{project_id}", response={204: None})
def delete_project(request, project_id: int):
    user = _require_auth_user(request)
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(user, project):
        raise HttpError(403, "Not allowed to delete this project.")
    project.delete()
    return 204, None


@router.get("/owners/{owner_handle}/projects", response=list[ProjectOut])
def list_owner_projects(request, owner_handle: str):
    owner = _get_owner(owner_handle)
    projects = _order_projects_by_last_request(
        _annotate_open_issues_count(Project.objects.select_related("owner").filter(owner=owner))
    )
    return [_project_to_dict(project) for project in projects]


def _project_latest_interaction_at(project):
    values = [
        getattr(project, "_last_authored_issue_at", None),
        getattr(project, "_last_comment_at", None),
        getattr(project, "_last_upvote_at", None),
    ]
    return max((value for value in values if value), default=project.created_at)


@router.get("/owners/{owner_handle}/interacted-projects", response=list[ProjectOut])
def list_owner_interacted_projects(request, owner_handle: str):
    owner = _get_owner(owner_handle)
    projects = _annotate_open_issues_count(
        Project.objects.select_related("owner")
        .exclude(owner=owner)
        .filter(
            Q(issues__author=owner)
            | Q(issues__comments__author=owner)
            | Q(issues__upvotes__user=owner)
        )
        .annotate(
            _last_authored_issue_at=Max(
                "issues__created_at",
                filter=Q(issues__author=owner),
            ),
            _last_comment_at=Max(
                "issues__comments__created_at",
                filter=Q(issues__comments__author=owner),
            ),
            _last_upvote_at=Max(
                "issues__upvotes__created_at",
                filter=Q(issues__upvotes__user=owner),
            ),
        )
    ).distinct()
    ordered_projects = sorted(
        projects,
        key=lambda project: (_project_latest_interaction_at(project), project.created_at, project.id),
        reverse=True,
    )
    return [_project_to_dict(project) for project in ordered_projects]


@router.get("/public/featured-projects", response=list[FeaturedProjectOut], tags=["projects"])
def list_featured_public_projects(request, limit: int = 3):
    safe_limit = max(1, min(limit, 12))
    projects = (
        Project.objects.select_related("owner")
        .annotate(issues_count=Count("issues", distinct=True))
        .order_by("-issues_count", "-updated_at", "-id")[:safe_limit]
    )
    return [_featured_project_to_dict(project) for project in projects]


@router.get("/owners/{owner_handle}/issues", response=list[IssueOut])
def list_owner_issues(
    request,
    owner_handle: str,
    project_slug: Optional[str] = None,
    issue_type: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    limit: Optional[int] = None,
):
    owner = _get_owner(owner_handle)
    visible_projects = Project.objects.filter(owner=owner)
    if project_slug:
        visible_projects = visible_projects.filter(slug=project_slug)
        if not visible_projects.exists():
            raise HttpError(404, "Project not found.")

    queryset = _get_annotated_issue_queryset().filter(project__in=visible_projects)

    if issue_type:
        _validate_issue_type(issue_type)
        queryset = queryset.filter(issue_type=issue_type)
    queryset = _filter_issues_by_status(queryset, status)
    if priority is not None:
        _validate_priority(priority)
        queryset = queryset.filter(priority=priority)

    ordered_query = _limit_issues(
        queryset.order_by("-_last_comment_at", "-created_at", "-id"),
        limit,
    )
    return [_issue_to_dict(issue) for issue in ordered_query]


@router.get(
    "/projects/{owner_handle}/{project_slug}/issues",
    response=list[IssueOut],
)
def list_project_issues(
    request,
    owner_handle: str,
    project_slug: str,
    issue_type: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    limit: Optional[int] = None,
):
    project = _get_project(owner_handle, project_slug)
    queryset = _get_annotated_issue_queryset().filter(project=project)

    if issue_type:
        _validate_issue_type(issue_type)
        queryset = queryset.filter(issue_type=issue_type)
    queryset = _filter_issues_by_status(queryset, status)
    if priority is not None:
        _validate_priority(priority)
        queryset = queryset.filter(priority=priority)

    return [_issue_to_dict(issue) for issue in _limit_issues(queryset, limit)]


@router.get(
    "/projects/{owner_handle}/{project_slug}/duplicate-candidates",
    response=list[DuplicateCandidateOut],
)
def find_duplicate_candidates(
    request,
    owner_handle: str,
    project_slug: str,
    title: str,
    description: str = "",
    exclude_issue_id: Optional[int] = None,
    limit: int = 5,
):
    _require_auth_user(request)
    project = _get_project(owner_handle, project_slug)
    title = _clean_non_empty(title, "Issue title")
    description = description.strip()
    _validate_limit(limit, maximum=20)

    queryset = Issue.objects.filter(project=project)
    if exclude_issue_id is not None:
        if not queryset.filter(id=exclude_issue_id).exists():
            raise HttpError(400, "exclude_issue_id must belong to the target project.")
        queryset = queryset.exclude(id=exclude_issue_id)

    candidates = [
        _duplicate_candidate_dict(
            issue,
            title=title,
            description=description,
        )
        for issue in queryset
    ]
    candidates = [candidate for candidate in candidates if candidate["similarity_score"] > 0]
    candidates.sort(
        key=lambda candidate: (
            candidate["similarity_score"],
            len(candidate["matched_terms"]),
            candidate["issue_id"],
        ),
        reverse=True,
    )
    return candidates[:limit]


@router.post(
    "/projects/{owner_handle}/{project_slug}/issues",
    response={201: IssueOut},
)
def create_issue(request, owner_handle: str, project_slug: str, payload: IssueCreateIn):
    user = _require_auth_user(request)
    _validate_issue_type(payload.issue_type)
    _validate_priority(payload.priority)

    project = _get_project(owner_handle, project_slug)
    title = _clean_non_empty(payload.title, "Issue title")
    description = payload.description.strip()
    _moderate_issue_submission(payload.issue_type, title, description)
    issue = Issue.objects.create(
        project=project,
        author=user,
        issue_type=payload.issue_type,
        title=title,
        description=description,
        priority=payload.priority,
    )
    record_issue_event(
        issue=issue,
        event_type=IssueEvent.Type.CREATED,
        actor=user,
        data={"source": "api"},
    )
    _notify_owner_on_new_issue(request, issue, user)
    issue = _get_annotated_issue_queryset().get(id=issue.id)
    return 201, _issue_to_dict(issue)


@router.post(
    "/embed/projects/{owner_handle}/{project_slug}/submissions",
    response={202: EmbedSubmissionOut},
    tags=["embed"],
)
def create_embed_submission(
    request,
    owner_handle: str,
    project_slug: str,
    payload: EmbedSubmissionIn,
):
    project = _get_project(owner_handle, project_slug)
    display_name = _clean_non_empty(payload.display_name, "Display name")
    email = str(payload.email or "").strip().lower()
    title = _clean_non_empty(payload.title, "Issue title")
    description = _clean_non_empty(payload.description, "Description")

    if len(display_name) > 120:
        raise HttpError(400, "Display name must be 120 characters or fewer.")
    try:
        validate_email(email)
    except ValidationError:
        raise HttpError(400, "Please provide a valid email address.")
    if len(title) > 200:
        raise HttpError(400, "Issue title must be 200 characters or fewer.")
    if len(description) > 5000:
        raise HttpError(400, "Description must be 5000 characters or fewer.")
    _validate_issue_type(payload.issue_type)

    try:
        validate_turnstile(request, payload.turnstile_token)
        _moderate_issue_submission(payload.issue_type, title, description)
        create_pending_submission(
            request,
            project,
            display_name=display_name,
            email=email,
            issue_type=payload.issue_type,
            title=title,
            description=description,
        )
    except EmbedSubmissionError as exc:
        raise HttpError(exc.status_code, exc.message)
    except HttpError:
        raise
    except Exception:
        logger.exception("Embed submission verification email failed.")
        raise HttpError(502, "The verification email could not be sent.")

    return 202, {"status": "verification_sent"}


@router.get("/issues/{issue_id}", response=IssueOut)
def get_issue(request, issue_id: int):
    issue = get_object_or_404(_get_annotated_issue_queryset(), id=issue_id)
    return _issue_to_dict(issue)


@router.patch("/issues/{issue_id}", response=IssueOut)
def update_issue(request, issue_id: int, payload: IssueUpdateIn):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)

    if not _can_manage_issue(user, issue):
        raise HttpError(403, "Not allowed to update this issue.")

    updated_fields = []
    changes = {}

    if payload.title is not None:
        title = _clean_non_empty(payload.title, "Issue title")
        if title != issue.title:
            changes["title"] = {"from": issue.title, "to": title}
            issue.title = title
            updated_fields.append("title")
    if payload.description is not None:
        description = payload.description.strip()
        if description != issue.description:
            changes["description"] = {"from": issue.description, "to": description}
            issue.description = description
            updated_fields.append("description")
    if payload.status is not None:
        _validate_status(payload.status)
        if payload.status != issue.status:
            changes["status"] = {"from": issue.status, "to": payload.status}
            issue.status = payload.status
            updated_fields.append("status")
    if payload.priority is not None:
        _validate_priority(payload.priority)
        if payload.priority != issue.priority:
            changes["priority"] = {"from": issue.priority, "to": payload.priority}
            issue.priority = payload.priority
            updated_fields.append("priority")

    if updated_fields:
        updated_fields.append("updated_at")
        issue.save(update_fields=updated_fields)
        record_issue_event(
            issue=issue,
            event_type=IssueEvent.Type.UPDATED,
            actor=user,
            data={"changes": changes},
        )

    issue = _get_annotated_issue_queryset().get(id=issue.id)

    return _issue_to_dict(issue)


@router.get("/me/request-queue", response=QueueSnapshotOut)
def get_request_queue(request, project_id: Optional[int] = None, limit: int = 100):
    user = _require_auth_user(request)
    _validate_limit(limit)
    projects = Project.objects.filter(owner=user)
    if project_id is not None:
        projects = projects.filter(id=project_id)
        if not projects.exists():
            raise HttpError(404, "Project not found.")

    queryset = (
        _get_annotated_issue_queryset()
        .filter(project__in=projects)
        .exclude(status__in=[Issue.Status.DONE, Issue.Status.CLOSED])
        .order_by("-priority", "-updated_at", "-id")
    )
    active_requests_count = queryset.count()
    requests = list(queryset[:limit])
    status_counts = {
        status: queryset.filter(status=status).count()
        for status in [
            Issue.Status.OPEN,
            Issue.Status.PLANNED,
            Issue.Status.IN_PROGRESS,
        ]
    }
    priority_counts = {
        str(priority): queryset.filter(priority=priority).count()
        for priority in [
            Issue.Priority.LOW,
            Issue.Priority.MEDIUM,
            Issue.Priority.HIGH,
            Issue.Priority.CRITICAL,
        ]
    }
    return {
        "generated_at": timezone.now().isoformat(),
        "projects_count": projects.count(),
        "active_requests_count": active_requests_count,
        "status_counts": status_counts,
        "priority_counts": priority_counts,
        "requests": [_issue_to_dict(issue) for issue in requests],
    }


@router.get("/me/issue-changes", response=ChangeFeedOut)
def list_issue_changes(request, after_id: int = 0, limit: int = 50):
    user = _require_auth_user(request)
    if after_id < 0:
        raise HttpError(400, "after_id cannot be negative.")
    _validate_limit(limit)
    queryset = (
        IssueEvent.objects.select_related("actor", "issue__project")
        .filter(issue__project__owner=user, id__gt=after_id)
        .order_by("id")
    )
    events = list(queryset[:limit])
    next_cursor = events[-1].id if events else after_id
    return {
        "events": [_issue_event_to_dict(event) for event in events],
        "next_cursor": next_cursor,
        "has_more": queryset.filter(id__gt=next_cursor).exists(),
    }


@router.get("/issues/{issue_id}/activity", response=list[IssueEventOut])
def list_issue_activity(request, issue_id: int, limit: int = 100):
    user = _require_auth_user(request)
    _validate_limit(limit)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    if not _can_manage_issue(user, issue):
        raise HttpError(403, "Not allowed to view this issue activity.")
    events = list(
        issue.events.select_related("actor", "issue__project")
        .order_by("-id")[:limit]
    )
    events.reverse()
    return [_issue_event_to_dict(event) for event in events]


@router.patch("/issues/{issue_id}/duplicate", response=IssueOut)
def link_issue_duplicate(request, issue_id: int, payload: DuplicateLinkIn):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    if not _can_manage_issue(user, issue):
        raise HttpError(403, "Not allowed to classify this issue as a duplicate.")
    canonical = get_object_or_404(
        Issue.objects.select_related("project"),
        id=payload.canonical_issue_id,
    )
    if canonical.id == issue.id:
        raise HttpError(400, "An issue cannot be a duplicate of itself.")
    if canonical.project_id != issue.project_id:
        raise HttpError(400, "Duplicate issues must belong to the same project.")
    if canonical.duplicate_of_id is not None:
        raise HttpError(400, "Choose the root canonical issue, not another duplicate.")
    if issue.duplicates.exists():
        raise HttpError(400, "This issue is canonical for other duplicates and cannot be linked.")

    if issue.duplicate_of_id != canonical.id:
        previous_canonical_id = issue.duplicate_of_id
        issue.duplicate_of = canonical
        issue.save(update_fields=["duplicate_of", "updated_at"])
        record_issue_event(
            issue=issue,
            event_type=IssueEvent.Type.DUPLICATE_LINKED,
            actor=user,
            data={
                "canonical_issue_id": canonical.id,
                "previous_canonical_issue_id": previous_canonical_id,
            },
        )

    issue = _get_annotated_issue_queryset().get(id=issue.id)
    return _issue_to_dict(issue)


@router.delete("/issues/{issue_id}/duplicate", response=IssueOut)
def unlink_issue_duplicate(request, issue_id: int):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    if not _can_manage_issue(user, issue):
        raise HttpError(403, "Not allowed to remove this duplicate link.")

    if issue.duplicate_of_id is not None:
        canonical_issue_id = issue.duplicate_of_id
        issue.duplicate_of = None
        issue.save(update_fields=["duplicate_of", "updated_at"])
        record_issue_event(
            issue=issue,
            event_type=IssueEvent.Type.DUPLICATE_UNLINKED,
            actor=user,
            data={"canonical_issue_id": canonical_issue_id},
        )

    issue = _get_annotated_issue_queryset().get(id=issue.id)
    return _issue_to_dict(issue)


@router.get(
    "/issues/{issue_id}/delivery-artifacts",
    response=list[DeliveryArtifactOut],
)
def list_issue_delivery_artifacts(request, issue_id: int):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    if not _can_manage_issue(user, issue):
        raise HttpError(403, "Not allowed to view this issue's delivery artifacts.")
    artifacts = issue.delivery_artifacts.select_related("added_by").all()
    return [_delivery_artifact_to_dict(artifact) for artifact in artifacts]


@router.post(
    "/issues/{issue_id}/delivery-artifacts",
    response=DeliveryArtifactLinkOut,
)
def link_issue_delivery_artifact(
    request,
    issue_id: int,
    payload: DeliveryArtifactIn,
):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    if not _can_manage_issue(user, issue):
        raise HttpError(403, "Not allowed to link delivery evidence to this issue.")
    _validate_delivery_kind(payload.kind)
    url = _clean_non_empty(payload.url, "Artifact URL")
    try:
        URLValidator(schemes=["http", "https"])(url)
    except ValidationError:
        raise HttpError(400, "Artifact URL must be a valid http or https URL.")
    label = payload.label.strip()
    if len(label) > 200:
        raise HttpError(400, "Artifact label must be 200 characters or fewer.")

    artifact, created = IssueDeliveryArtifact.objects.get_or_create(
        issue=issue,
        url=url,
        defaults={
            "added_by": user,
            "kind": payload.kind,
            "label": label,
        },
    )
    if created:
        record_issue_event(
            issue=issue,
            event_type=IssueEvent.Type.DELIVERY_LINKED,
            actor=user,
            data={
                "artifact_id": artifact.id,
                "kind": artifact.kind,
                "url": artifact.url,
                "label": artifact.label,
            },
        )
    artifact = IssueDeliveryArtifact.objects.select_related("added_by").get(id=artifact.id)
    return {
        "created": created,
        "artifact": _delivery_artifact_to_dict(artifact),
    }


@router.delete(
    "/issues/{issue_id}/delivery-artifacts/{artifact_id}",
    response={204: None},
)
def unlink_issue_delivery_artifact(request, issue_id: int, artifact_id: int):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    if not _can_manage_issue(user, issue):
        raise HttpError(403, "Not allowed to unlink delivery evidence from this issue.")
    artifact = get_object_or_404(
        IssueDeliveryArtifact,
        id=artifact_id,
        issue=issue,
    )
    event_data = {
        "artifact_id": artifact.id,
        "kind": artifact.kind,
        "url": artifact.url,
        "label": artifact.label,
    }
    artifact.delete()
    record_issue_event(
        issue=issue,
        event_type=IssueEvent.Type.DELIVERY_UNLINKED,
        actor=user,
        data=event_data,
    )
    return 204, None


@router.post("/issues/{issue_id}/upvote/toggle", response=UpvoteToggleOut)
def toggle_issue_upvote(request, issue_id: int):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)

    existing = IssueUpvote.objects.filter(issue=issue, user=user).first()
    if existing:
        existing.delete()
        upvoted = False
        event_type = IssueEvent.Type.UPVOTE_REMOVED
    else:
        IssueUpvote.objects.create(issue=issue, user=user)
        upvoted = True
        event_type = IssueEvent.Type.UPVOTE_ADDED

    upvotes_count = issue.upvotes.count()
    record_issue_event(
        issue=issue,
        event_type=event_type,
        actor=user,
        data={"upvotes_count": upvotes_count},
    )

    return {
        "issue_id": issue.id,
        "upvoted": upvoted,
        "upvotes_count": upvotes_count,
    }


@router.get("/issues/{issue_id}/comments", response=list[CommentOut])
def list_issue_comments(request, issue_id: int):
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    comments = issue.comments.select_related("author").all()
    return [_comment_to_dict(comment) for comment in comments]


@router.post("/issues/{issue_id}/comments", response={201: CommentOut})
def create_issue_comment(request, issue_id: int, payload: CommentCreateIn):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    body = _clean_non_empty(payload.body, "Comment body")
    _moderate_comment_submission(body, issue)

    comment = IssueComment.objects.create(
        issue=issue,
        author=user,
        body=body,
    )
    record_issue_event(
        issue=issue,
        event_type=IssueEvent.Type.COMMENT_ADDED,
        actor=user,
        data={"comment_id": comment.id},
    )
    comment = IssueComment.objects.select_related("author", "issue__project__owner").get(id=comment.id)
    _notify_owner_on_new_comment(request, comment)
    return 201, _comment_to_dict(comment)


@router.patch("/issues/{issue_id}/comments/{comment_id}", response=CommentOut)
def update_issue_comment(request, issue_id: int, comment_id: int, payload: CommentCreateIn):
    user = _require_auth_user(request)
    comment = get_object_or_404(
        IssueComment.objects.select_related("author", "issue__project__owner"),
        id=comment_id,
        issue_id=issue_id,
    )

    if user.id not in {comment.author_id, comment.issue.project.owner_id}:
        raise HttpError(403, "Not allowed to update this comment.")

    body = _clean_non_empty(payload.body, "Comment body")
    _moderate_comment_submission(body, comment.issue)

    if body != comment.body:
        comment.body = body
        comment.save(update_fields=["body", "updated_at"])
        record_issue_event(
            issue=comment.issue,
            event_type=IssueEvent.Type.COMMENT_UPDATED,
            actor=user,
            data={"comment_id": comment.id},
        )
    comment = IssueComment.objects.select_related("author", "issue__project__owner").get(id=comment.id)
    return _comment_to_dict(comment)
