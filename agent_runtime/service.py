from __future__ import annotations

import logging
from collections.abc import Callable

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, F, Max, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_embedded_mcp import credential_digest
from ninja.errors import HttpError

from projects.models import Issue, IssueComment, IssueDeliveryArtifact, IssueEvent, Project
from projects.services import (
    DomainRuleError,
    annotated_issue_queryset as _get_annotated_issue_queryset,
    apply_issue_changes,
    apply_project_changes,
    comment_to_dict as _comment_to_dict,
    create_comment_resource,
    create_issue_resource,
    create_project_resource,
    delivery_artifact_to_dict as _delivery_artifact_to_dict,
    duplicate_candidate_dict as _duplicate_candidate_dict,
    issue_event_to_dict as _issue_event_to_dict,
    issue_to_dict as _issue_to_dict,
    link_delivery_resource,
    link_duplicate_resource,
    moderate_comment_submission as _moderate_comment_submission,
    moderate_issue_submission as _moderate_issue_submission,
    project_to_dict as _project_to_dict,
    unlink_delivery_resource,
    unlink_duplicate_resource,
    update_comment_resource,
)

from .audit import record_tool_audit
from .context import AgentContext
from .contract import contract, validate_tool_input, validate_tool_output
from .errors import ContractApplicationError, MissingScopeError, app_error
from .idempotency import execute_idempotent, public_idempotency_id, replay_idempotent


logger = logging.getLogger(__name__)


def _resource_hint(arguments):
    for key, kind in (
        ("comment_id", "comment"),
        ("artifact_id", "delivery_artifact"),
        ("issue_id", "request"),
        ("project_id", "project"),
    ):
        if key in arguments:
            return kind, str(arguments[key])
    return "", ""


def _project_queryset():
    return Project.objects.select_related("owner").annotate(
        open_issues_count=Count(
            "issues", filter=Q(issues__status=Issue.Status.OPEN), distinct=True
        )
    )


def _project_output(project):
    return _project_to_dict(project)


def _issue_output(issue_id):
    return _issue_to_dict(_get_annotated_issue_queryset().get(pk=issue_id))


def _comment_output(comment_id):
    return _comment_to_dict(
        IssueComment.objects.select_related("author", "issue__project__owner").get(pk=comment_id)
    )


def _artifact_output(artifact_id):
    return _delivery_artifact_to_dict(
        IssueDeliveryArtifact.objects.select_related("added_by").get(pk=artifact_id)
    )


class FeatureRequestAgentService:
    @staticmethod
    def _capability_set(context) -> frozenset[str]:
        # Free and Pro expose the same semantic capability catalog in 1.0.0;
        # their only difference is the project_count limit.
        return frozenset(
            {
                "project_management",
                "request_management",
                "request_collaboration",
                "duplicate_evidence",
                "delivery_evidence",
                "activity_feed",
            }
        )

    def call(self, name: str, arguments: dict, context: AgentContext):
        tools = contract()["tools"]
        if name not in tools or tools[name]["exposure"] != "public":
            raise KeyError(name)
        definition = tools[name]
        context.audit_extra.clear()
        missing = set(definition["required_scopes"]) - set(context.scopes)
        if missing:
            raise MissingScopeError(sorted(missing))
        fields = validate_tool_input(name, arguments)
        if fields:
            error = app_error("invalid_input", context.request_id, fields=fields)
            record_tool_audit(
                context=context,
                tool_name=name,
                arguments=arguments,
                result_code=error.code,
                resource_type=_resource_hint(arguments)[0],
                resource_id=_resource_hint(arguments)[1],
            )
            raise error
        if "idempotency_key" in arguments:
            context.audit_extra["idempotency_id"] = public_idempotency_id(
                credential_digest(arguments["idempotency_key"])
            )
        try:
            missing_capabilities = set(definition["required_capabilities"]) - set(
                self._capability_set(context)
            )
            if missing_capabilities:
                context.audit_extra["capability_granted"] = False
                raise app_error(
                    "feature_unavailable",
                    context.request_id,
                    capability=sorted(missing_capabilities)[0],
                )
            result = getattr(self, name)(context, **arguments)
            validate_tool_output(name, result)
        except ContractApplicationError as exc:
            resource_type, resource_id = _resource_hint(arguments)
            record_tool_audit(
                context=context,
                tool_name=name,
                arguments=arguments,
                result_code=exc.code,
                resource_type=resource_type,
                resource_id=resource_id,
                idempotency_id=context.audit_extra.get("idempotency_id", ""),
            )
            raise
        except Exception:
            resource_type, resource_id = _resource_hint(arguments)
            record_tool_audit(
                context=context,
                tool_name=name,
                arguments=arguments,
                result_code="internal_error",
                resource_type=resource_type,
                resource_id=resource_id,
                idempotency_id=context.audit_extra.get("idempotency_id", ""),
            )
            raise
        resource_type, resource_id = _resource_hint(arguments)
        record_tool_audit(
            context=context,
            tool_name=name,
            arguments=arguments,
            result_code="success",
            resource_type=resource_type,
            resource_id=resource_id,
            idempotency_id=context.audit_extra.get("idempotency_id", ""),
        )
        return result

    @staticmethod
    def _not_found(context):
        raise app_error("not_found", context.request_id)

    @staticmethod
    def _deny(context):
        context.audit_extra["ownership_decision"] = "denied"
        raise app_error("permission_denied", context.request_id)

    @staticmethod
    def _revision(context, resource, expected):
        if resource.revision != expected:
            raise app_error(
                "revision_conflict",
                context.request_id,
                expected_revision=expected,
                actual_revision=resource.revision,
            )

    @staticmethod
    def _moderate_issue(context, issue_type, title, description):
        try:
            _moderate_issue_submission(issue_type, title, description)
        except (DomainRuleError, HttpError) as exc:
            unavailable = (
                exc.code == "dependency_unavailable"
                if isinstance(exc, DomainRuleError)
                else exc.status_code == 503
            )
            context.audit_extra["dependency_outcome"] = (
                "unavailable" if unavailable else "rejected"
            )
            if unavailable:
                raise app_error(
                    "dependency_unavailable",
                    context.request_id,
                    dependency="content_moderation",
                ) from exc
            raise app_error(
                "moderation_rejected", context.request_id, fields=["title", "description"]
            ) from exc
        context.audit_extra["dependency_outcome"] = "accepted"

    @staticmethod
    def _moderate_comment(context, body, issue):
        try:
            _moderate_comment_submission(body, issue)
        except (DomainRuleError, HttpError) as exc:
            unavailable = (
                exc.code == "dependency_unavailable"
                if isinstance(exc, DomainRuleError)
                else exc.status_code == 503
            )
            context.audit_extra["dependency_outcome"] = (
                "unavailable" if unavailable else "rejected"
            )
            if unavailable:
                raise app_error(
                    "dependency_unavailable",
                    context.request_id,
                    dependency="content_moderation",
                ) from exc
            raise app_error("moderation_rejected", context.request_id, fields=["body"]) from exc
        context.audit_extra["dependency_outcome"] = "accepted"

    @staticmethod
    def _notify_issue(issue_id):
        issue = Issue.objects.select_related("project__owner", "author").get(pk=issue_id)
        if issue.author_id == issue.project.owner_id:
            return
        send_mail(
            f"New request on {issue.project.owner.handle}/{issue.project.slug}: {issue.title}",
            f"A new request was posted. Open {settings.PUBLIC_BASE_URL}/{issue.project.owner.handle}/{issue.project.slug}/",
            settings.DEFAULT_FROM_EMAIL,
            [issue.project.owner.email],
            fail_silently=False,
        )

    @staticmethod
    def _notify_comment(comment_id):
        comment = IssueComment.objects.select_related(
            "issue__project__owner", "author"
        ).get(pk=comment_id)
        if comment.author_id == comment.issue.project.owner_id:
            return
        send_mail(
            f"New comment on request #{comment.issue_id}",
            f"A new comment was posted. Open {settings.PUBLIC_BASE_URL}/{comment.issue.project.owner.handle}/{comment.issue.project.slug}/",
            settings.DEFAULT_FROM_EMAIL,
            [comment.issue.project.owner.email],
            fail_silently=False,
        )

    @staticmethod
    def _best_effort(callback: Callable[[], None]):
        try:
            callback()
            return "delivered_or_not_applicable"
        except Exception as exc:
            logger.error(
                "Best-effort FeatureRequest notification failed error_type=%s",
                type(exc).__name__,
            )
            return "failed_best_effort"

    def _mutate(self, context, tool_name, arguments, operation):
        context.audit_extra["idempotency_id"] = public_idempotency_id(
            credential_digest(arguments["idempotency_key"])
        )

        def validated_operation():
            result, resource_type, resource_id = operation()
            # Validate the receipt before the transaction containing both the
            # domain mutation and idempotency record is allowed to commit.
            validate_tool_output(tool_name, result)
            return result, resource_type, resource_id

        result, replayed, idempotency_id = execute_idempotent(
            context=context,
            tool_name=tool_name,
            arguments=arguments,
            operation=validated_operation,
        )
        context.audit_extra["idempotency_id"] = idempotency_id
        context.audit_extra["idempotent_replay"] = replayed
        return result

    def get_account_capabilities(self, context):
        used = Project.objects.filter(owner=context.user).count()
        return {
            "capabilities": {
                "project_management": True,
                "request_management": True,
                "request_collaboration": True,
                "duplicate_evidence": True,
                "delivery_evidence": True,
                "activity_feed": True,
            },
            "limits": {
                "project_count": {
                    "used": used,
                    "limit": context.user.project_limit,
                    "period": "lifetime",
                    "reset_at": None,
                }
            },
        }

    def list_projects(self, context):
        projects = _project_queryset().filter(owner=context.user).order_by("-created_at", "-id")
        return {"projects": [_project_output(project) for project in projects]}

    def get_project(self, context, project_id):
        project = _project_queryset().filter(pk=project_id).first()
        if project is None:
            self._not_found(context)
        if project.owner_id != context.user.pk:
            self._deny(context)
        return _project_output(project)

    def list_requests(
        self,
        context,
        owner_handle,
        project_slug=None,
        issue_type=None,
        status=None,
        priority=None,
        limit=50,
    ):
        queryset = _get_annotated_issue_queryset().filter(
            project__owner__handle=owner_handle.lower()
        )
        if project_slug:
            queryset = queryset.filter(project__slug=project_slug)
            if not Project.objects.filter(
                owner__handle=owner_handle.lower(), slug=project_slug
            ).exists():
                self._not_found(context)
        if issue_type:
            queryset = queryset.filter(issue_type=issue_type)
        if status == "active":
            queryset = queryset.exclude(status__in=[Issue.Status.DONE, Issue.Status.CLOSED])
        elif status:
            queryset = queryset.filter(status=status)
        if priority is not None:
            queryset = queryset.filter(priority=priority)
        queryset = queryset.order_by("-_last_comment_at", "-created_at", "-id")[:limit]
        return {"requests": [_issue_to_dict(issue) for issue in queryset]}

    def get_request(self, context, issue_id):
        issue = _get_annotated_issue_queryset().filter(pk=issue_id).first()
        if issue is None:
            self._not_found(context)
        return _issue_to_dict(issue)

    def list_request_comments(self, context, issue_id):
        issue = Issue.objects.filter(pk=issue_id).first()
        if issue is None:
            self._not_found(context)
        comments = issue.comments.select_related("author").order_by("created_at", "id")
        return {"comments": [_comment_to_dict(comment) for comment in comments]}

    def get_queue_snapshot(self, context, project_id=None, limit=100):
        projects = Project.objects.filter(owner=context.user)
        if project_id is not None:
            project = Project.objects.filter(pk=project_id).first()
            if project is None:
                self._not_found(context)
            if project.owner_id != context.user.pk:
                self._deny(context)
            projects = projects.filter(pk=project_id)
        queryset = (
            _get_annotated_issue_queryset()
            .filter(project__in=projects)
            .exclude(status__in=[Issue.Status.DONE, Issue.Status.CLOSED])
            .order_by("-priority", "-updated_at", "-id")
        )
        return {
            "generated_at": timezone.now().isoformat(),
            "projects_count": projects.count(),
            "active_requests_count": queryset.count(),
            "status_counts": {
                value: queryset.filter(status=value).count()
                for value in (Issue.Status.OPEN, Issue.Status.PLANNED, Issue.Status.IN_PROGRESS)
            },
            "priority_counts": {
                str(value): queryset.filter(priority=value).count()
                for value in (
                    Issue.Priority.LOW,
                    Issue.Priority.MEDIUM,
                    Issue.Priority.HIGH,
                    Issue.Priority.CRITICAL,
                )
            },
            "requests": [_issue_to_dict(issue) for issue in queryset[:limit]],
        }

    def find_duplicate_candidates(
        self,
        context,
        owner_handle,
        project_slug,
        title,
        description="",
        exclude_issue_id=None,
        limit=5,
    ):
        project = Project.objects.filter(
            owner__handle=owner_handle.lower(), slug=project_slug
        ).first()
        if project is None:
            self._not_found(context)
        queryset = Issue.objects.filter(project=project)
        if exclude_issue_id is not None:
            if not queryset.filter(pk=exclude_issue_id).exists():
                raise app_error("invalid_input", context.request_id, fields=["exclude_issue_id"])
            queryset = queryset.exclude(pk=exclude_issue_id)
        candidates = [
            _duplicate_candidate_dict(issue, title=title.strip(), description=description.strip())
            for issue in queryset
        ]
        candidates = [item for item in candidates if item["similarity_score"] > 0]
        candidates.sort(
            key=lambda item: (
                item["similarity_score"], len(item["matched_terms"]), item["issue_id"]
            ),
            reverse=True,
        )
        return {"candidates": candidates[:limit]}

    def list_request_activity(self, context, issue_id, limit=100):
        issue = Issue.objects.select_related("project").filter(pk=issue_id).first()
        if issue is None:
            self._not_found(context)
        if context.user.pk not in {issue.author_id, issue.project.owner_id}:
            self._deny(context)
        events = list(
            issue.events.select_related("actor", "issue__project").order_by("-id")[:limit]
        )
        events.reverse()
        return {"events": [_issue_event_to_dict(event) for event in events]}

    def list_request_changes(self, context, after_id=0, limit=50):
        queryset = (
            IssueEvent.objects.select_related("actor", "issue__project")
            .filter(issue__project__owner=context.user, id__gt=after_id)
            .order_by("id")
        )
        events = list(queryset[:limit])
        next_cursor = events[-1].id if events else after_id
        return {
            "events": [_issue_event_to_dict(event) for event in events],
            "next_cursor": next_cursor,
            "has_more": queryset.filter(id__gt=next_cursor).exists(),
        }

    def list_delivery_artifacts(self, context, issue_id):
        issue = Issue.objects.select_related("project").filter(pk=issue_id).first()
        if issue is None:
            self._not_found(context)
        if context.user.pk not in {issue.author_id, issue.project.owner_id}:
            self._deny(context)
        artifacts = issue.delivery_artifacts.select_related("added_by").order_by("created_at", "id")
        return {"artifacts": [_delivery_artifact_to_dict(item) for item in artifacts]}

    def create_project(self, context, name, idempotency_key, tagline="", url=""):
        arguments = {
            "name": name,
            "tagline": tagline,
            "url": url,
            "idempotency_key": idempotency_key,
        }

        def operation():
            user = type(context.user).objects.select_for_update().get(pk=context.user.pk)
            used = Project.objects.filter(owner=user).count()
            if used >= user.project_limit:
                raise app_error(
                    "capacity_reached",
                    context.request_id,
                    used=used,
                    limit=user.project_limit,
                    period="lifetime",
                    reset_at=None,
                )
            project = create_project_resource(
                owner=user,
                name=name.strip(),
                tagline=tagline.strip(),
                url=url.strip(),
            )
            result = _project_output(_project_queryset().get(pk=project.pk))
            return result, "project", project.pk

        return self._mutate(context, "create_project", arguments, operation)

    def update_project(
        self,
        context,
        project_id,
        expected_revision,
        idempotency_key,
        name=None,
        tagline=None,
        url=None,
    ):
        arguments = {
            "project_id": project_id,
            "expected_revision": expected_revision,
            "idempotency_key": idempotency_key,
        }
        arguments.update(
            {key: value for key, value in {"name": name, "tagline": tagline, "url": url}.items() if value is not None}
        )

        def operation():
            project = Project.objects.select_for_update().select_related("owner").filter(pk=project_id).first()
            if project is None:
                self._not_found(context)
            if project.owner_id != context.user.pk:
                self._deny(context)
            self._revision(context, project, expected_revision)
            values = {
                field: value.strip()
                for field, value in (
                    ("name", name),
                    ("tagline", tagline),
                    ("url", url),
                )
                if value is not None
            }
            if "url" in values and values["url"] != project.url:
                # MCP stores untrusted URLs but never dereferences them. Clear a
                # favicon derived from the previous URL instead of presenting
                # stale evidence or fetching a replacement.
                values["favicon_url"] = ""
            apply_project_changes(project, **values)
            result = _project_output(_project_queryset().get(pk=project.pk))
            return result, "project", project.pk

        return self._mutate(context, "update_project", arguments, operation)

    def delete_project(
        self,
        context,
        project_id,
        confirm_project_id,
        expected_revision,
        idempotency_key,
    ):
        arguments = {
            "project_id": project_id,
            "confirm_project_id": confirm_project_id,
            "expected_revision": expected_revision,
            "idempotency_key": idempotency_key,
        }
        context.audit_extra["approval_evidence"] = {
            "owner": "agent",
            "confirmation_field": "confirm_project_id",
            "matched": confirm_project_id == project_id,
        }
        if confirm_project_id != project_id:
            raise app_error(
                "confirmation_mismatch",
                context.request_id,
                confirmation_field="confirm_project_id",
            )

        def operation():
            project = Project.objects.select_for_update().filter(pk=project_id).first()
            if project is None:
                self._not_found(context)
            if project.owner_id != context.user.pk:
                self._deny(context)
            self._revision(context, project, expected_revision)
            receipt = {
                "project_id": project.pk,
                "deleted": True,
                "deleted_revision": project.revision,
            }
            project.delete()
            return receipt, "project", project_id

        return self._mutate(context, "delete_project", arguments, operation)

    def create_request(
        self,
        context,
        owner_handle,
        project_slug,
        title,
        idempotency_key,
        description="",
        issue_type="feature",
        priority=2,
    ):
        arguments = {
            "owner_handle": owner_handle,
            "project_slug": project_slug,
            "title": title,
            "description": description,
            "issue_type": issue_type,
            "priority": priority,
            "idempotency_key": idempotency_key,
        }
        replay = replay_idempotent(
            context=context, tool_name="create_request", arguments=arguments
        )
        if replay is not None:
            result, _, idempotency_id = replay
            context.audit_extra.update(
                idempotency_id=idempotency_id,
                dependency_outcome="not_repeated",
                notification_outcome="not_repeated",
            )
            return result
        self._moderate_issue(context, issue_type, title, description)
        context.audit_extra["approval_evidence"] = {"owner": "agent", "current_turn": True}

        def operation():
            project = Project.objects.select_related("owner").filter(
                owner__handle=owner_handle.lower(), slug=project_slug
            ).first()
            if project is None:
                self._not_found(context)
            issue = create_issue_resource(
                project=project,
                author=context.user,
                issue_type=issue_type,
                title=title.strip(),
                description=description.strip(),
                priority=priority,
                source="mcp",
            )
            context.audit_extra["notification_outcome"] = "scheduled_best_effort"

            def notify():
                context.audit_extra["notification_outcome"] = self._best_effort(
                    lambda: self._notify_issue(issue.pk)
                )

            transaction.on_commit(notify)
            return _issue_output(issue.pk), "request", issue.pk

        return self._mutate(context, "create_request", arguments, operation)

    def link_duplicate_request(
        self,
        context,
        issue_id,
        canonical_issue_id,
        expected_revision,
        idempotency_key,
    ):
        arguments = {
            "issue_id": issue_id,
            "canonical_issue_id": canonical_issue_id,
            "expected_revision": expected_revision,
            "idempotency_key": idempotency_key,
        }

        def operation():
            issue = Issue.objects.select_for_update().select_related("project").filter(pk=issue_id).first()
            if issue is None:
                self._not_found(context)
            if context.user.pk not in {issue.author_id, issue.project.owner_id}:
                self._deny(context)
            self._revision(context, issue, expected_revision)
            canonical = Issue.objects.filter(pk=canonical_issue_id).first()
            if canonical is None:
                self._not_found(context)
            try:
                changed = link_duplicate_resource(
                    issue=issue,
                    canonical=canonical,
                    actor=context.user,
                )
            except DomainRuleError as exc:
                raise app_error(
                    "invalid_state", context.request_id, state="invalid_duplicate_relationship"
                ) from exc
            return {"changed": changed, "request": _issue_output(issue.pk)}, "request", issue.pk

        return self._mutate(context, "link_duplicate_request", arguments, operation)

    def unlink_duplicate_request(
        self, context, issue_id, expected_revision, idempotency_key
    ):
        arguments = {
            "issue_id": issue_id,
            "expected_revision": expected_revision,
            "idempotency_key": idempotency_key,
        }

        def operation():
            issue = Issue.objects.select_for_update().select_related("project").filter(pk=issue_id).first()
            if issue is None:
                self._not_found(context)
            if context.user.pk not in {issue.author_id, issue.project.owner_id}:
                self._deny(context)
            self._revision(context, issue, expected_revision)
            changed = unlink_duplicate_resource(issue=issue, actor=context.user)
            return {"changed": changed, "request": _issue_output(issue.pk)}, "request", issue.pk

        return self._mutate(context, "unlink_duplicate_request", arguments, operation)

    def link_delivery_artifact(
        self,
        context,
        issue_id,
        kind,
        url,
        expected_revision,
        idempotency_key,
        label="",
    ):
        arguments = {
            "issue_id": issue_id,
            "kind": kind,
            "url": url,
            "label": label,
            "expected_revision": expected_revision,
            "idempotency_key": idempotency_key,
        }

        def operation():
            issue = Issue.objects.select_for_update().select_related("project").filter(pk=issue_id).first()
            if issue is None:
                self._not_found(context)
            if context.user.pk not in {issue.author_id, issue.project.owner_id}:
                self._deny(context)
            self._revision(context, issue, expected_revision)
            try:
                artifact, created = link_delivery_resource(
                    issue=issue,
                    actor=context.user,
                    kind=kind,
                    url=url,
                    label=label.strip(),
                    conflict_on_metadata_change=True,
                )
            except DomainRuleError as exc:
                raise app_error(
                    "idempotency_conflict",
                    context.request_id,
                    idempotency_key=public_idempotency_id(
                        credential_digest(idempotency_key)
                    ),
                ) from exc
            return {
                "created": created,
                "artifact": _artifact_output(artifact.pk),
                "request_revision": issue.revision,
            }, "request", issue.pk

        return self._mutate(context, "link_delivery_artifact", arguments, operation)

    def unlink_delivery_artifact(
        self,
        context,
        issue_id,
        artifact_id,
        expected_revision,
        idempotency_key,
    ):
        arguments = {
            "issue_id": issue_id,
            "artifact_id": artifact_id,
            "expected_revision": expected_revision,
            "idempotency_key": idempotency_key,
        }

        def operation():
            issue = Issue.objects.select_for_update().select_related("project").filter(pk=issue_id).first()
            if issue is None:
                self._not_found(context)
            if context.user.pk not in {issue.author_id, issue.project.owner_id}:
                self._deny(context)
            self._revision(context, issue, expected_revision)
            artifact = IssueDeliveryArtifact.objects.filter(
                pk=artifact_id, issue=issue
            ).first()
            changed = unlink_delivery_resource(
                issue=issue,
                artifact=artifact,
                actor=context.user,
            )
            return {
                "changed": changed,
                "issue_id": issue.pk,
                "artifact_id": artifact_id,
                "request_revision": issue.revision,
            }, "request", issue.pk

        return self._mutate(context, "unlink_delivery_artifact", arguments, operation)

    def update_request(
        self,
        context,
        issue_id,
        expected_revision,
        idempotency_key,
        title=None,
        description=None,
        priority=None,
    ):
        arguments = {
            "issue_id": issue_id,
            "expected_revision": expected_revision,
            "idempotency_key": idempotency_key,
        }
        arguments.update(
            {
                key: value
                for key, value in {
                    "title": title,
                    "description": description,
                    "priority": priority,
                }.items()
                if value is not None
            }
        )

        def operation():
            issue = Issue.objects.select_for_update().select_related("project").filter(pk=issue_id).first()
            if issue is None:
                self._not_found(context)
            if context.user.pk not in {issue.author_id, issue.project.owner_id}:
                self._deny(context)
            self._revision(context, issue, expected_revision)
            values = {
                field: value
                for field, value in (
                    ("title", title.strip() if title is not None else None),
                    (
                        "description",
                        description.strip() if description is not None else None,
                    ),
                    ("priority", priority),
                )
                if value is not None
            }
            apply_issue_changes(
                issue,
                actor=context.user,
                source="mcp",
                **values,
            )
            return _issue_output(issue.pk), "request", issue.pk

        return self._mutate(context, "update_request", arguments, operation)

    def transition_request(
        self, context, issue_id, status, expected_revision, idempotency_key
    ):
        arguments = {
            "issue_id": issue_id,
            "status": status,
            "expected_revision": expected_revision,
            "idempotency_key": idempotency_key,
        }
        if status in {Issue.Status.DONE, Issue.Status.CLOSED}:
            context.audit_extra["approval_evidence"] = {
                "owner": "agent",
                "target_status": status,
                "delivery_evidence_required": True,
            }

        def operation():
            issue = Issue.objects.select_for_update().select_related("project").filter(pk=issue_id).first()
            if issue is None:
                self._not_found(context)
            if context.user.pk not in {issue.author_id, issue.project.owner_id}:
                self._deny(context)
            self._revision(context, issue, expected_revision)
            if status in {Issue.Status.DONE, Issue.Status.CLOSED} and not issue.delivery_artifacts.exists():
                raise app_error(
                    "approval_required",
                    context.request_id,
                    operation="inspect_delivery_evidence_before_terminal_transition",
                )
            apply_issue_changes(
                issue,
                actor=context.user,
                source="mcp",
                status=status,
            )
            return _issue_output(issue.pk), "request", issue.pk

        return self._mutate(context, "transition_request", arguments, operation)

    def add_request_comment(self, context, issue_id, body, idempotency_key):
        arguments = {
            "issue_id": issue_id,
            "body": body,
            "idempotency_key": idempotency_key,
        }
        replay = replay_idempotent(
            context=context, tool_name="add_request_comment", arguments=arguments
        )
        if replay is not None:
            result, _, idempotency_id = replay
            context.audit_extra.update(
                idempotency_id=idempotency_id,
                dependency_outcome="not_repeated",
                notification_outcome="not_repeated",
            )
            return result
        issue = Issue.objects.select_related("project").filter(pk=issue_id).first()
        if issue is None:
            self._not_found(context)
        self._moderate_comment(context, body, issue)
        context.audit_extra["approval_evidence"] = {"owner": "agent", "current_turn": True}

        def operation():
            locked_issue = Issue.objects.select_for_update().filter(pk=issue_id).first()
            if locked_issue is None:
                self._not_found(context)
            comment = create_comment_resource(
                issue=locked_issue,
                author=context.user,
                body=body.strip(),
                source="mcp",
            )
            context.audit_extra["notification_outcome"] = "scheduled_best_effort"

            def notify():
                context.audit_extra["notification_outcome"] = self._best_effort(
                    lambda: self._notify_comment(comment.pk)
                )

            transaction.on_commit(notify)
            return _comment_output(comment.pk), "comment", comment.pk

        return self._mutate(context, "add_request_comment", arguments, operation)

    def update_request_comment(
        self,
        context,
        issue_id,
        comment_id,
        body,
        expected_revision,
        idempotency_key,
    ):
        arguments = {
            "issue_id": issue_id,
            "comment_id": comment_id,
            "body": body,
            "expected_revision": expected_revision,
            "idempotency_key": idempotency_key,
        }
        replay = replay_idempotent(
            context=context, tool_name="update_request_comment", arguments=arguments
        )
        if replay is not None:
            result, _, idempotency_id = replay
            context.audit_extra.update(
                idempotency_id=idempotency_id,
                dependency_outcome="not_repeated",
                notification_outcome="not_applicable",
            )
            return result
        comment = IssueComment.objects.select_related("issue__project").filter(
            pk=comment_id, issue_id=issue_id
        ).first()
        if comment is None:
            self._not_found(context)
        if context.user.pk not in {comment.author_id, comment.issue.project.owner_id}:
            self._deny(context)
        self._revision(context, comment, expected_revision)
        self._moderate_comment(context, body, comment.issue)
        context.audit_extra.update(
            approval_evidence={"owner": "agent", "current_turn": True},
            notification_outcome="not_applicable",
        )

        def operation():
            locked = (
                IssueComment.objects.select_for_update()
                .select_related("issue__project")
                .filter(pk=comment_id, issue_id=issue_id)
                .first()
            )
            if locked is None:
                self._not_found(context)
            if context.user.pk not in {locked.author_id, locked.issue.project.owner_id}:
                self._deny(context)
            self._revision(context, locked, expected_revision)
            cleaned = body.strip()
            update_comment_resource(
                comment=locked,
                actor=context.user,
                body=cleaned,
                source="mcp",
            )
            return _comment_output(locked.pk), "comment", locked.pk

        return self._mutate(context, "update_request_comment", arguments, operation)


service = FeatureRequestAgentService()
