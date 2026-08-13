"""Transport-neutral FeatureRequest domain services shared by API and MCP.

Authorization, OAuth scope checks, Contract envelopes and HTTP responses belong
to their adapters. This module owns resource projection and state transitions so
the two transports cannot silently evolve different business rules.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Count, F, Max
from django.db.models.functions import Coalesce
from openai import OpenAI

from accounts.models import gravatar_url_for_email

from .events import record_issue_event
from .models import Issue, IssueComment, IssueDeliveryArtifact, IssueEvent, Project


logger = logging.getLogger(__name__)
UNSET = object()


@dataclass(frozen=True)
class DomainRuleError(ValueError):
    code: str
    message: str

    def __str__(self):
        return self.message


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


def _duplicate_terms(value: str) -> set[str]:
    return {
        term
        for term in _DUPLICATE_TERM_PATTERN.findall((value or "").casefold())
        if len(term) > 1 and term not in _DUPLICATE_STOP_WORDS
    }


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def duplicate_candidate_dict(issue: Issue, *, title: str, description: str) -> dict:
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


def annotated_issue_queryset():
    return Issue.objects.select_related("project", "author", "duplicate_of").annotate(
        upvotes_count=Count("upvotes", distinct=True),
        comments_count=Count("comments", distinct=True),
        delivery_artifacts_count=Count("delivery_artifacts", distinct=True),
        _last_comment_at=Coalesce(Max("comments__updated_at"), F("created_at")),
        _last_event_at=Max("events__created_at"),
    )


def issue_to_dict(issue: Issue) -> dict:
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


def project_to_dict(project: Project) -> dict:
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


def comment_to_dict(comment: IssueComment) -> dict:
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


def delivery_artifact_to_dict(artifact: IssueDeliveryArtifact) -> dict:
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


def issue_event_to_dict(event: IssueEvent) -> dict:
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


def moderate_board_content(
    label: str,
    content: str,
    *,
    issue_type: str | None = None,
    client_factory=OpenAI,
) -> None:
    api_key = settings.OPENAI_API_KEY.strip()
    if not api_key:
        return
    client = client_factory(api_key=api_key)
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
        f"{policy} Respond with exactly one line. If valid: ALLOW. "
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
    except Exception as exc:
        logger.error(
            "Content moderation call failed error_type=%s", type(exc).__name__
        )
        raise DomainRuleError(
            "dependency_unavailable", "Content moderation is temporarily unavailable."
        ) from exc
    verdict = (getattr(response, "output_text", "") or "").strip()
    if not verdict:
        raise DomainRuleError(
            "dependency_unavailable", "Content moderation is temporarily unavailable."
        )
    if verdict.lower().startswith("allow"):
        return
    reason = "Content is invalid."
    if ":" in verdict:
        parsed_reason = verdict.split(":", 1)[1].strip()
        if parsed_reason:
            reason = parsed_reason
    raise DomainRuleError("moderation_rejected", f"{label} rejected by moderation: {reason}")


def moderate_issue_submission(
    issue_type: str,
    title: str,
    description: str,
    *,
    client_factory=OpenAI,
) -> None:
    content = (
        f"issue_type: {issue_type}\n"
        f"title: {title}\n"
        f"description: {description or '(empty)'}"
    )
    moderate_board_content(
        "Issue", content, issue_type="issue", client_factory=client_factory
    )


def moderate_comment_submission(
    body: str,
    issue: Issue,
    *,
    client_factory=OpenAI,
) -> None:
    recent_comments = issue.comments.order_by("-created_at").values_list("body", flat=True)[:3]
    context_lines = [
        f"issue_title: {issue.title}",
        f"issue_description: {issue.description or '(empty)'}",
    ]
    if recent_comments:
        context_lines.append("recent_comments:")
        for index, comment_body in enumerate(recent_comments, start=1):
            context_lines.append(f"{index}. {comment_body[:360]}")
    context = "\n".join(context_lines)
    content = f"comment:\n{body}\n\nthread_context:\n{context}"
    moderate_board_content("Comment", content, client_factory=client_factory)


def create_project_resource(
    *, owner, name: str, tagline: str, url: str, favicon_url: str = ""
) -> Project:
    return Project.objects.create(
        owner=owner,
        name=name,
        tagline=tagline,
        url=url,
        favicon_url=favicon_url,
    )


def apply_project_changes(
    project: Project,
    *,
    name=UNSET,
    tagline=UNSET,
    url=UNSET,
    favicon_url=UNSET,
) -> bool:
    persisted_slug = project.slug
    changed: list[str] = []
    for field, value in (
        ("name", name),
        ("tagline", tagline),
        ("url", url),
        ("favicon_url", favicon_url),
    ):
        if value is not UNSET and getattr(project, field) != value:
            setattr(project, field, value)
            changed.append(field)
    if not changed:
        return False
    project.revision += 1
    update_fields = [*changed, "revision", "updated_at"]
    if "name" in changed:
        update_fields.append("slug")
    project.save(update_fields=update_fields)
    if "name" not in changed:
        # Project.save() computes a candidate slug on every save, while Django
        # intentionally omits it from this partial update. Keep the in-memory
        # projection aligned with the persisted row returned by the API.
        project.slug = persisted_slug
    return True


def create_issue_resource(
    *,
    project: Project,
    author,
    issue_type: str,
    title: str,
    description: str,
    priority: int,
    source: str,
) -> Issue:
    issue = Issue.objects.create(
        project=project,
        author=author,
        issue_type=issue_type,
        title=title,
        description=description,
        priority=priority,
    )
    record_issue_event(
        issue=issue,
        event_type=IssueEvent.Type.CREATED,
        actor=author,
        data={"source": source},
    )
    return issue


def apply_issue_changes(
    issue: Issue,
    *,
    actor,
    source: str | None,
    title=UNSET,
    description=UNSET,
    status=UNSET,
    priority=UNSET,
) -> dict:
    changes = {}
    for field, value in (
        ("title", title),
        ("description", description),
        ("status", status),
        ("priority", priority),
    ):
        if value is not UNSET and getattr(issue, field) != value:
            changes[field] = {"from": getattr(issue, field), "to": value}
            setattr(issue, field, value)
    if not changes:
        return changes
    issue.revision += 1
    issue.save(update_fields=[*changes, "revision", "updated_at"])
    data = {"changes": changes}
    if source:
        data["source"] = source
    record_issue_event(
        issue=issue,
        event_type=IssueEvent.Type.UPDATED,
        actor=actor,
        data=data,
    )
    return changes


def link_duplicate_resource(*, issue: Issue, canonical: Issue, actor) -> bool:
    if canonical.pk == issue.pk:
        raise DomainRuleError("self_duplicate", "An issue cannot be a duplicate of itself.")
    if canonical.project_id != issue.project_id:
        raise DomainRuleError(
            "cross_project_duplicate", "Duplicate issues must belong to the same project."
        )
    if canonical.duplicate_of_id is not None:
        raise DomainRuleError(
            "nested_duplicate", "Choose the root canonical issue, not another duplicate."
        )
    if issue.duplicates.exists():
        raise DomainRuleError(
            "canonical_has_duplicates",
            "This issue is canonical for other duplicates and cannot be linked.",
        )
    if issue.duplicate_of_id == canonical.pk:
        return False
    previous = issue.duplicate_of_id
    issue.duplicate_of = canonical
    issue.revision += 1
    issue.save(update_fields=["duplicate_of", "revision", "updated_at"])
    record_issue_event(
        issue=issue,
        event_type=IssueEvent.Type.DUPLICATE_LINKED,
        actor=actor,
        data={
            "canonical_issue_id": canonical.pk,
            "previous_canonical_issue_id": previous,
        },
    )
    return True


def unlink_duplicate_resource(*, issue: Issue, actor) -> bool:
    if issue.duplicate_of_id is None:
        return False
    previous = issue.duplicate_of_id
    issue.duplicate_of = None
    issue.revision += 1
    issue.save(update_fields=["duplicate_of", "revision", "updated_at"])
    record_issue_event(
        issue=issue,
        event_type=IssueEvent.Type.DUPLICATE_UNLINKED,
        actor=actor,
        data={"canonical_issue_id": previous},
    )
    return True


def link_delivery_resource(
    *,
    issue: Issue,
    actor,
    kind: str,
    url: str,
    label: str,
    conflict_on_metadata_change: bool,
) -> tuple[IssueDeliveryArtifact, bool]:
    existing = IssueDeliveryArtifact.objects.filter(issue=issue, url=url).first()
    if existing is not None:
        if conflict_on_metadata_change and (
            existing.kind != kind or existing.label != label
        ):
            raise DomainRuleError(
                "delivery_natural_key_conflict",
                "The delivery URL already exists with different metadata.",
            )
        return existing, False
    artifact = IssueDeliveryArtifact.objects.create(
        issue=issue,
        added_by=actor,
        kind=kind,
        url=url,
        label=label,
    )
    issue.revision += 1
    issue.save(update_fields=["revision", "updated_at"])
    record_issue_event(
        issue=issue,
        event_type=IssueEvent.Type.DELIVERY_LINKED,
        actor=actor,
        data={
            "artifact_id": artifact.pk,
            "kind": artifact.kind,
            "url": artifact.url,
            "label": artifact.label,
        },
    )
    return artifact, True


def unlink_delivery_resource(
    *,
    issue: Issue,
    artifact: IssueDeliveryArtifact | None,
    actor,
) -> bool:
    if artifact is None:
        return False
    event_data = {
        "artifact_id": artifact.pk,
        "kind": artifact.kind,
        "url": artifact.url,
        "label": artifact.label,
    }
    artifact.delete()
    issue.revision += 1
    issue.save(update_fields=["revision", "updated_at"])
    record_issue_event(
        issue=issue,
        event_type=IssueEvent.Type.DELIVERY_UNLINKED,
        actor=actor,
        data=event_data,
    )
    return True


def create_comment_resource(
    *, issue: Issue, author, body: str, source: str | None
) -> IssueComment:
    comment = IssueComment.objects.create(issue=issue, author=author, body=body)
    data = {"comment_id": comment.pk}
    if source:
        data["source"] = source
    record_issue_event(
        issue=issue,
        event_type=IssueEvent.Type.COMMENT_ADDED,
        actor=author,
        data=data,
    )
    return comment


def update_comment_resource(
    *, comment: IssueComment, actor, body: str, source: str | None
) -> bool:
    if comment.body == body:
        return False
    comment.body = body
    comment.revision += 1
    comment.save(update_fields=["body", "revision", "updated_at"])
    data = {"comment_id": comment.pk}
    if source:
        data["source"] = source
    record_issue_event(
        issue=comment.issue,
        event_type=IssueEvent.Type.COMMENT_UPDATED,
        actor=actor,
        data=data,
    )
    return True
