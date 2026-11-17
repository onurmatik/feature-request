"""Shared project lifecycle and parent-resource access rules for REST and MCP."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import (
    Issue,
    IssueComment,
    IssueDeliveryArtifact,
    IssueScopeAssessment,
    Project,
    ProjectSpec,
    ProjectSpecChangeProposal,
)
from .services import DomainRuleError


def project_id_for_resource(kind, resource_id):
    resources = {
        "project": (Project, "pk"),
        "request": (Issue, "project_id"),
        "comment": (IssueComment, "issue__project_id"),
        "delivery_artifact": (IssueDeliveryArtifact, "issue__project_id"),
        "scope_assessment": (IssueScopeAssessment, "issue__project_id"),
        "project_spec": (ProjectSpec, "project_id"),
        "project_spec_proposal": (ProjectSpecChangeProposal, "project_id"),
    }
    if kind not in resources or not resource_id:
        return None
    model, field = resources[kind]
    return model.objects.filter(pk=resource_id).values_list(field, flat=True).first()


def project_id_from_arguments(arguments):
    for field, kind in (
        ("project_id", "project"),
        ("issue_id", "request"),
        ("comment_id", "comment"),
        ("proposal_id", "project_spec_proposal"),
    ):
        if arguments.get(field) is not None:
            return project_id_for_resource(kind, arguments[field])
    if arguments.get("owner_handle") and arguments.get("project_slug"):
        return Project.objects.filter(
            owner__handle=arguments["owner_handle"].lower(),
            slug=arguments["project_slug"],
        ).values_list("pk", flat=True).first()
    return None


def lock_active_project(project_id):
    project = (
        Project.objects.active().select_for_update(of=("self",))
        .select_related("owner").filter(pk=project_id).first()
    )
    if project is None:
        raise DomainRuleError("not_found", "Project not found.")
    return project


def archived_project_to_dict(project):
    return {
        "id": project.pk,
        "name": project.name,
        "slug": project.slug,
        "revision": project.revision,
        "archived_at": project.archived_at.isoformat(),
    }


def project_lifecycle_receipt(project):
    return {
        "project_id": project.pk,
        "revision": project.revision,
        "archived_at": project.archived_at.isoformat() if project.archived_at else None,
    }


@transaction.atomic
def change_project_archive(*, actor, project_id, archived, expected_revision):
    # Use the same lock order as project creation, including across transports.
    # NO KEY UPDATE serializes capacity checks without blocking child FK checks.
    owner = get_user_model().objects.select_for_update(of=("self",), no_key=True).get(pk=actor.pk)
    project = Project.objects.select_for_update(of=("self",)).filter(pk=project_id).first()
    if project is None:
        raise DomainRuleError("not_found", "Project not found.")
    if project.owner_id != owner.pk:
        raise DomainRuleError("permission_denied", "Only the project owner can manage its archive.")
    if project.revision != expected_revision:
        raise DomainRuleError("revision_conflict", "The project changed. Refresh and try again.")
    if bool(project.archived_at) == archived:
        return project
    if not archived and owner.has_project_limit(Project.objects.active().filter(owner=owner).count()):
        raise DomainRuleError(
            "capacity_reached", "Project limit reached. Archive another project to restore this one."
        )
    project.archived_at = timezone.now() if archived else None
    project.revision += 1
    project.updated_at = timezone.now()
    # A lifecycle transition must never regenerate the reserved slug.
    Project.objects.filter(pk=project.pk).update(
        archived_at=project.archived_at, revision=project.revision, updated_at=project.updated_at
    )
    return project
