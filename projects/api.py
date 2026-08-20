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
from django.db import transaction
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
    IssueScopeAssessment,
    IssueUpvote,
    Project,
    ProjectSpec,
    ProjectSpecChangeProposal,
)
from .services import (
    DomainRuleError,
    ScopeEvaluation,
    annotated_issue_queryset as _shared_annotated_issue_queryset,
    apply_issue_changes,
    apply_project_changes,
    comment_to_dict as _shared_comment_to_dict,
    create_comment_resource,
    create_issue_resource,
    create_project_resource,
    create_spec_change_proposal_resource,
    delete_project_spec_resource,
    delivery_artifact_to_dict as _shared_delivery_artifact_to_dict,
    duplicate_candidate_dict as _shared_duplicate_candidate_dict,
    issue_event_to_dict as _shared_issue_event_to_dict,
    issue_to_dict as _shared_issue_to_dict,
    evaluate_request_scope,
    generate_spec_change_proposal,
    link_delivery_resource,
    link_duplicate_resource,
    moderate_board_content,
    moderate_project_spec,
    project_to_dict as _shared_project_to_dict,
    project_spec_to_dict,
    record_scope_assessment,
    resolve_spec_change_proposal_resource,
    save_project_spec_resource,
    scope_assessment_to_dict,
    spec_change_proposal_to_dict,
    unlink_delivery_resource,
    unlink_duplicate_resource,
    update_comment_resource,
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
    has_spec: bool
    spec_revision: int
    revision: int
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


class ProjectSpecUpsertIn(Schema):
    content: str
    auto_decline_enabled: bool = False
    expected_revision: int


class ProjectSpecDeleteIn(Schema):
    confirm_project_id: int
    expected_revision: int


class ProjectSpecOut(Schema):
    project_id: int
    owner_handle: str
    project_slug: str
    content: str
    revision: int
    auto_decline_enabled: bool
    created_at: str
    updated_at: str


class ProjectSpecDeleteOut(Schema):
    project_id: int
    deleted: bool
    deleted_revision: int


class IssueUpdateIn(Schema):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    public_reason: Optional[str] = None
    scope_assessment_id: Optional[int] = None


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
    revision: int
    created_at: str
    updated_at: str


class ScopeAssessmentOut(Schema):
    id: int
    issue_id: int
    spec_revision: int
    state: str
    verdict: str
    public_reason: str
    out_of_scope_quote: str
    spec_gap_summary: str
    evaluator_version: str
    auto_declined: bool
    error_code: Optional[str] = None
    created_at: str


class SpecChangeProposalOut(Schema):
    id: int
    project_id: int
    issue_id: int
    base_spec_revision: int
    proposed_content: str
    summary: str
    diff: str
    status: str
    created_by_id: int
    reviewed_by_id: Optional[int]
    created_at: str
    updated_at: str


class SpecChangeProposalDecisionIn(Schema):
    decision: str
    expected_revision: int


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
    revision: int
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
            status__in=[Issue.Status.DONE, Issue.Status.CLOSED, Issue.Status.DECLINED]
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


def _raise_domain_http_error(exc: DomainRuleError):
    status = {
        "not_found": 404,
        "revision_conflict": 409,
        "invalid_state": 409,
        "dependency_unavailable": 503,
        "moderation_rejected": 400,
    }.get(exc.code, 400)
    raise HttpError(status, exc.message) from exc


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
    try:
        moderate_board_content(
            label,
            content,
            issue_type=issue_type,
            client_factory=OpenAI,
        )
    except DomainRuleError as exc:
        if exc.code == "dependency_unavailable":
            raise HttpError(503, exc.message) from exc
        raise HttpError(400, exc.message) from exc
    except Exception as exc:
        logger.exception("Unexpected moderation service failure.")
        raise HttpError(503, "Content moderation is temporarily unavailable.")


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
        "revision": issue.revision,
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
        "revision": project.revision,
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
        "revision": comment.revision,
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
        Project.objects.select_related("owner", "spec"),
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


# Adapter-compatible private names now resolve to the shared domain projections.
# Existing API imports remain stable while MCP no longer depends on this module.
_duplicate_candidate_dict = _shared_duplicate_candidate_dict
_issue_to_dict = _shared_issue_to_dict
_project_to_dict = _shared_project_to_dict
_comment_to_dict = _shared_comment_to_dict
_delivery_artifact_to_dict = _shared_delivery_artifact_to_dict
_issue_event_to_dict = _shared_issue_event_to_dict
_get_annotated_issue_queryset = _shared_annotated_issue_queryset


@router.get("/projects", response=list[ProjectOut])
def list_my_projects(request):
    user = _require_auth_user(request)
    projects = _order_projects_by_last_request(
        _annotate_open_issues_count(Project.objects.select_related("owner", "spec").filter(owner=user))
    )
    return [_project_to_dict(project) for project in projects]


@router.post("/projects", response={201: ProjectOut})
def create_project(request, payload: ProjectCreateIn):
    user = _require_auth_user(request)
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

    with transaction.atomic():
        locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
        if locked_user.has_project_limit(
            Project.objects.filter(owner=locked_user).count()
        ):
            raise HttpError(
                403,
                "You have reached your project limit. Upgrade to 30 projects to continue.",
            )
        project = create_project_resource(
            owner=locked_user,
            name=name,
            tagline=payload.tagline.strip(),
            url=url,
            favicon_url=favicon_url,
        )
    project = Project.objects.select_related("owner", "spec").get(id=project.id)
    return 201, _project_to_dict(project)


@router.get("/projects/{project_id}", response=ProjectOut)
def get_my_project(request, project_id: int):
    user = _require_auth_user(request)
    project = get_object_or_404(
        Project.objects.select_related("owner", "spec"),
        id=project_id,
        owner=user,
    )
    return _project_to_dict(project)


@router.patch("/projects/{project_id}", response=ProjectOut)
def update_project(request, project_id: int, payload: ProjectUpdateIn):
    user = _require_auth_user(request)
    with transaction.atomic():
        project = get_object_or_404(
            Project.objects.select_for_update().select_related("owner"),
            id=project_id,
        )
        if not _can_manage_project(user, project):
            raise HttpError(403, "Not allowed to update this project.")

        values = {}
        if payload.name is not None:
            values["name"] = _clean_non_empty(payload.name, "Project name")
        if payload.tagline is not None:
            values["tagline"] = payload.tagline.strip()
        if payload.url is not None:
            values["url"] = _normalize_project_url(payload.url)

        if any(getattr(project, field) != value for field, value in values.items()):
            resulting_url = values.get("url", project.url)
            if resulting_url:
                favicon_url, favicon_debug = _resolve_favicon_url_with_debug(
                    resulting_url
                )
                if not favicon_url:
                    logger.warning(
                        "Could not resolve favicon for project_id=%s url=%s. debug=%s",
                        project.id,
                        resulting_url,
                        " | ".join(favicon_debug),
                    )
            else:
                favicon_url = ""
            values["favicon_url"] = favicon_url
            apply_project_changes(project, **values)

    return _project_to_dict(project)


@router.delete("/projects/{project_id}", response={204: None})
def delete_project(request, project_id: int):
    user = _require_auth_user(request)
    project = get_object_or_404(Project, id=project_id)
    if not _can_manage_project(user, project):
        raise HttpError(403, "Not allowed to delete this project.")
    project.delete()
    return 204, None


@router.get(
    "/projects/{owner_handle}/{project_slug}/spec",
    response=ProjectSpecOut,
)
def get_public_project_spec(request, owner_handle: str, project_slug: str):
    project = _get_project(owner_handle, project_slug)
    spec = get_object_or_404(
        ProjectSpec.objects.select_related("project__owner"),
        project=project,
    )
    return project_spec_to_dict(spec)


@router.put("/projects/{project_id}/spec", response=ProjectSpecOut)
def upsert_project_spec(request, project_id: int, payload: ProjectSpecUpsertIn):
    user = _require_auth_user(request)
    if payload.expected_revision < 0:
        raise HttpError(400, "expected_revision cannot be negative.")
    try:
        moderate_project_spec(payload.content, client_factory=OpenAI)
    except DomainRuleError as exc:
        _raise_domain_http_error(exc)

    with transaction.atomic():
        project = get_object_or_404(
            Project.objects.select_for_update().select_related("owner"),
            id=project_id,
        )
        if not _can_manage_project(user, project):
            raise HttpError(403, "Not allowed to update this project spec.")
        try:
            spec, _ = save_project_spec_resource(
                project=project,
                content=payload.content,
                auto_decline_enabled=payload.auto_decline_enabled,
                expected_revision=payload.expected_revision,
            )
        except DomainRuleError as exc:
            _raise_domain_http_error(exc)
    spec = ProjectSpec.objects.select_related("project__owner").get(pk=spec.pk)
    return project_spec_to_dict(spec)


@router.delete("/projects/{project_id}/spec", response=ProjectSpecDeleteOut)
def delete_project_spec(
    request,
    project_id: int,
    payload: ProjectSpecDeleteIn,
):
    user = _require_auth_user(request)
    if payload.confirm_project_id != project_id:
        raise HttpError(400, "confirm_project_id must match project_id.")
    with transaction.atomic():
        project = get_object_or_404(
            Project.objects.select_for_update(),
            id=project_id,
        )
        if not _can_manage_project(user, project):
            raise HttpError(403, "Not allowed to delete this project spec.")
        try:
            deleted_revision = delete_project_spec_resource(
                project=project,
                expected_revision=payload.expected_revision,
            )
        except DomainRuleError as exc:
            _raise_domain_http_error(exc)
    return {
        "project_id": project_id,
        "deleted": True,
        "deleted_revision": deleted_revision,
    }


@router.get("/owners/{owner_handle}/projects", response=list[ProjectOut])
def list_owner_projects(request, owner_handle: str):
    owner = _get_owner(owner_handle)
    projects = _order_projects_by_last_request(
        _annotate_open_issues_count(Project.objects.select_related("owner", "spec").filter(owner=owner))
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
        Project.objects.select_related("owner", "spec")
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
    spec = ProjectSpec.objects.filter(project=project).first()
    evaluation = (
        evaluate_request_scope(
            spec=spec,
            issue_type=payload.issue_type,
            title=title,
            description=description,
            client_factory=OpenAI,
        )
        if spec is not None
        else None
    )
    with transaction.atomic():
        issue = create_issue_resource(
            project=project,
            author=user,
            issue_type=payload.issue_type,
            title=title,
            description=description,
            priority=payload.priority,
            source="api",
        )
        if spec is not None and evaluation is not None:
            current_spec = ProjectSpec.objects.select_for_update().filter(
                pk=spec.pk,
                revision=spec.revision,
            ).first()
            if current_spec is None:
                evaluation = ScopeEvaluation(
                    state=IssueScopeAssessment.State.FAILED,
                    error_code="spec_revision_changed",
                )
            record_scope_assessment(
                issue=issue,
                spec=spec,
                evaluation=evaluation,
                source="api",
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


@router.get(
    "/issues/{issue_id}/scope-assessment",
    response=ScopeAssessmentOut,
)
def get_issue_scope_assessment(request, issue_id: int):
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    is_owner = request.user.is_authenticated and request.user.id == issue.project.owner_id
    assessments = issue.scope_assessments.all()
    if not is_owner:
        assessments = assessments.filter(state=IssueScopeAssessment.State.COMPLETED)
    assessment = assessments.order_by("-created_at", "-id").first()
    if assessment is None:
        raise HttpError(404, "Scope assessment not found.")
    return scope_assessment_to_dict(assessment, include_private=is_owner)


@router.post(
    "/issues/{issue_id}/scope-assessment/retry",
    response=ScopeAssessmentOut,
)
def retry_issue_scope_assessment(request, issue_id: int):
    user = _require_auth_user(request)
    issue = get_object_or_404(
        Issue.objects.select_related("project"),
        id=issue_id,
    )
    if user.id != issue.project.owner_id:
        raise HttpError(403, "Only the project owner can reassess request scope.")
    spec = get_object_or_404(ProjectSpec, project=issue.project)
    evaluation = evaluate_request_scope(
        spec=spec,
        issue_type=issue.issue_type,
        title=issue.title,
        description=issue.description,
        client_factory=OpenAI,
    )
    with transaction.atomic():
        issue = get_object_or_404(
            Issue.objects.select_for_update().select_related("project"),
            id=issue_id,
        )
        current_spec = ProjectSpec.objects.select_for_update().filter(
            pk=spec.pk,
            revision=spec.revision,
        ).first()
        if current_spec is None:
            evaluation = ScopeEvaluation(
                state=IssueScopeAssessment.State.FAILED,
                error_code="spec_revision_changed",
            )
        assessment = record_scope_assessment(
            issue=issue,
            spec=spec,
            evaluation=evaluation,
            source="api_retry",
        )
    return scope_assessment_to_dict(assessment, include_private=True)


@router.post(
    "/issues/{issue_id}/spec-change-proposals",
    response={201: SpecChangeProposalOut},
)
def create_issue_spec_change_proposal(request, issue_id: int):
    user = _require_auth_user(request)
    issue = get_object_or_404(
        Issue.objects.select_related("project"),
        id=issue_id,
    )
    if user.id != issue.project.owner_id:
        raise HttpError(403, "Only the project owner can propose a spec update.")
    spec = get_object_or_404(ProjectSpec, project=issue.project)
    latest = issue.scope_assessments.order_by("-created_at", "-id").first()
    if latest is None or latest.verdict != IssueScopeAssessment.Verdict.SPEC_GAP:
        raise HttpError(409, "The latest scope assessment is not a spec gap.")
    if latest.spec_revision != spec.revision:
        raise HttpError(409, "The project spec changed after scope assessment.")
    if ProjectSpecChangeProposal.objects.filter(
        issue=issue,
        base_spec_revision=spec.revision,
        status=ProjectSpecChangeProposal.Status.PENDING,
    ).exists():
        raise HttpError(409, "A pending spec proposal already exists for this request.")
    try:
        proposed_content, summary = generate_spec_change_proposal(
            spec=spec,
            issue=issue,
            client_factory=OpenAI,
        )
    except DomainRuleError as exc:
        _raise_domain_http_error(exc)
    with transaction.atomic():
        issue = get_object_or_404(
            Issue.objects.select_for_update().select_related("project"),
            id=issue_id,
        )
        current_spec = get_object_or_404(
            ProjectSpec.objects.select_for_update(),
            project=issue.project,
        )
        if current_spec.revision != spec.revision:
            raise HttpError(409, "The project spec changed while generating the proposal.")
        try:
            proposal = create_spec_change_proposal_resource(
                project=issue.project,
                issue=issue,
                actor=user,
                spec=current_spec,
                proposed_content=proposed_content,
                summary=summary,
            )
        except DomainRuleError as exc:
            _raise_domain_http_error(exc)
    return 201, spec_change_proposal_to_dict(proposal)


@router.get(
    "/projects/{project_id}/spec-change-proposals",
    response=list[SpecChangeProposalOut],
)
def list_project_spec_change_proposals(
    request,
    project_id: int,
    status: str = ProjectSpecChangeProposal.Status.PENDING,
):
    user = _require_auth_user(request)
    project = get_object_or_404(Project, id=project_id)
    if user.id != project.owner_id:
        raise HttpError(403, "Only the project owner can view spec proposals.")
    if status not in ProjectSpecChangeProposal.Status.values:
        raise HttpError(400, "Invalid proposal status.")
    proposals = ProjectSpecChangeProposal.objects.filter(
        project=project,
        status=status,
    ).select_related("created_by", "reviewed_by")
    return [spec_change_proposal_to_dict(proposal) for proposal in proposals]


@router.patch(
    "/spec-change-proposals/{proposal_id}",
    response=SpecChangeProposalOut,
)
def resolve_project_spec_change_proposal(
    request,
    proposal_id: int,
    payload: SpecChangeProposalDecisionIn,
):
    user = _require_auth_user(request)
    decisions = {
        "accept": ProjectSpecChangeProposal.Status.ACCEPTED,
        "accepted": ProjectSpecChangeProposal.Status.ACCEPTED,
        "reject": ProjectSpecChangeProposal.Status.REJECTED,
        "rejected": ProjectSpecChangeProposal.Status.REJECTED,
    }
    decision = decisions.get(payload.decision)
    if decision is None:
        raise HttpError(400, "Decision must be accept or reject.")
    with transaction.atomic():
        proposal = get_object_or_404(
            ProjectSpecChangeProposal.objects.select_for_update().select_related(
                "project", "issue", "created_by", "reviewed_by"
            ),
            id=proposal_id,
        )
        if user.id != proposal.project.owner_id:
            raise HttpError(403, "Only the project owner can resolve spec proposals.")
        spec = get_object_or_404(
            ProjectSpec.objects.select_for_update(),
            project=proposal.project,
        )
        try:
            proposal, _ = resolve_spec_change_proposal_resource(
                proposal=proposal,
                spec=spec,
                actor=user,
                decision=decision,
                expected_spec_revision=payload.expected_revision,
            )
        except DomainRuleError as exc:
            _raise_domain_http_error(exc)
    return spec_change_proposal_to_dict(proposal)


@router.patch("/issues/{issue_id}", response=IssueOut)
def update_issue(request, issue_id: int, payload: IssueUpdateIn):
    user = _require_auth_user(request)
    if payload.status == Issue.Status.DECLINED and payload.public_reason:
        _moderate_board_content(
            "Decline reason",
            payload.public_reason.strip(),
            issue_type=None,
        )
    with transaction.atomic():
        issue = get_object_or_404(
            Issue.objects.select_for_update().select_related("project"), id=issue_id
        )
        if not _can_manage_issue(user, issue):
            raise HttpError(403, "Not allowed to update this issue.")
        if payload.status is not None and (
            payload.status == Issue.Status.DECLINED
            or issue.status == Issue.Status.DECLINED
        ) and user.id != issue.project.owner_id:
            raise HttpError(
                403,
                "Only the project owner can decline or reopen a declined request.",
            )
        values = {}
        if payload.title is not None:
            values["title"] = _clean_non_empty(payload.title, "Issue title")
        if payload.description is not None:
            values["description"] = payload.description.strip()
        if payload.status is not None:
            _validate_status(payload.status)
            if payload.status == Issue.Status.DECLINED:
                assessment = None
                if payload.scope_assessment_id is not None:
                    assessment = IssueScopeAssessment.objects.filter(
                        id=payload.scope_assessment_id,
                        issue=issue,
                        state=IssueScopeAssessment.State.COMPLETED,
                        verdict=IssueScopeAssessment.Verdict.OUT_OF_SCOPE,
                    ).first()
                    if assessment is None:
                        raise HttpError(400, "Invalid scope_assessment_id.")
                reason = (payload.public_reason or "").strip()
                if assessment is None and not reason:
                    raise HttpError(
                        400,
                        "Declining a request requires public_reason or scope_assessment_id.",
                    )
                if assessment is None:
                    spec_revision = (
                        ProjectSpec.objects.filter(project=issue.project)
                        .values_list("revision", flat=True)
                        .first()
                        or 0
                    )
                    assessment = IssueScopeAssessment.objects.create(
                        issue=issue,
                        spec_revision=spec_revision,
                        state=IssueScopeAssessment.State.COMPLETED,
                        verdict=IssueScopeAssessment.Verdict.OUT_OF_SCOPE,
                        public_reason=reason,
                        evaluator_version="owner_manual_v1",
                    )
                    record_issue_event(
                        issue=issue,
                        event_type=IssueEvent.Type.SCOPE_ASSESSED,
                        actor=user,
                        data={
                            "assessment_id": assessment.pk,
                            "spec_revision": assessment.spec_revision,
                            "verdict": assessment.verdict,
                            "public_reason": assessment.public_reason,
                            "source": "owner_manual",
                        },
                    )
            values["status"] = payload.status
        if payload.priority is not None:
            _validate_priority(payload.priority)
            values["priority"] = payload.priority
        if payload.status is not None and (
            payload.status == Issue.Status.DECLINED
            or issue.status == Issue.Status.DECLINED
        ):
            logger.info(
                "scope_owner_override transition=%s",
                "decline" if payload.status == Issue.Status.DECLINED else "reopen",
            )
        apply_issue_changes(issue, actor=user, source=None, **values)

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
        .exclude(
            status__in=[
                Issue.Status.DONE,
                Issue.Status.CLOSED,
                Issue.Status.DECLINED,
            ]
        )
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
    with transaction.atomic():
        issue = get_object_or_404(
            Issue.objects.select_for_update().select_related("project"), id=issue_id
        )
        if not _can_manage_issue(user, issue):
            raise HttpError(403, "Not allowed to classify this issue as a duplicate.")
        canonical = get_object_or_404(
            Issue.objects.select_related("project"),
            id=payload.canonical_issue_id,
        )
        try:
            link_duplicate_resource(issue=issue, canonical=canonical, actor=user)
        except DomainRuleError as exc:
            raise HttpError(400, exc.message) from exc

    issue = _get_annotated_issue_queryset().get(id=issue.id)
    return _issue_to_dict(issue)


@router.delete("/issues/{issue_id}/duplicate", response=IssueOut)
def unlink_issue_duplicate(request, issue_id: int):
    user = _require_auth_user(request)
    with transaction.atomic():
        issue = get_object_or_404(
            Issue.objects.select_for_update().select_related("project"), id=issue_id
        )
        if not _can_manage_issue(user, issue):
            raise HttpError(403, "Not allowed to remove this duplicate link.")
        unlink_duplicate_resource(issue=issue, actor=user)

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
    _validate_delivery_kind(payload.kind)
    url = _clean_non_empty(payload.url, "Artifact URL")
    try:
        URLValidator(schemes=["http", "https"])(url)
    except ValidationError:
        raise HttpError(400, "Artifact URL must be a valid http or https URL.")
    label = payload.label.strip()
    if len(label) > 200:
        raise HttpError(400, "Artifact label must be 200 characters or fewer.")

    with transaction.atomic():
        issue = get_object_or_404(
            Issue.objects.select_for_update().select_related("project"), id=issue_id
        )
        if not _can_manage_issue(user, issue):
            raise HttpError(403, "Not allowed to link delivery evidence to this issue.")
        artifact, created = link_delivery_resource(
            issue=issue,
            actor=user,
            kind=payload.kind,
            url=url,
            label=label,
            conflict_on_metadata_change=False,
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
    with transaction.atomic():
        issue = get_object_or_404(
            Issue.objects.select_for_update().select_related("project"), id=issue_id
        )
        if not _can_manage_issue(user, issue):
            raise HttpError(403, "Not allowed to unlink delivery evidence from this issue.")
        artifact = get_object_or_404(
            IssueDeliveryArtifact,
            id=artifact_id,
            issue=issue,
        )
        unlink_delivery_resource(issue=issue, artifact=artifact, actor=user)
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

    with transaction.atomic():
        comment = create_comment_resource(
            issue=issue,
            author=user,
            body=body,
            source=None,
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

    with transaction.atomic():
        comment = get_object_or_404(
            IssueComment.objects.select_for_update().select_related(
                "author", "issue__project__owner"
            ),
            id=comment_id,
            issue_id=issue_id,
        )
        if user.id not in {comment.author_id, comment.issue.project.owner_id}:
            raise HttpError(403, "Not allowed to update this comment.")
        update_comment_resource(
            comment=comment,
            actor=user,
            body=body,
            source=None,
        )
    comment = IssueComment.objects.select_related("author", "issue__project__owner").get(id=comment.id)
    return _comment_to_dict(comment)
