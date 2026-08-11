from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import quote

import django
import httpx
from asgiref.sync import sync_to_async
from django.conf import settings
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from accounts.models import ApiToken  # noqa: E402


IssueType = Literal["feature", "bug"]
IssuePriority = Literal[1, 2, 3, 4]
IssueStatus = Literal["open", "planned", "in_progress", "done", "closed"]
IssueStatusFilter = Literal[
    "active",
    "open",
    "planned",
    "in_progress",
    "done",
    "closed",
]
DeliveryArtifactKind = Literal[
    "pull_request",
    "commit",
    "deployment",
    "release",
    "other",
]


READ_ONLY_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
WRITE_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
IDEMPOTENT_WRITE_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
DESTRUCTIVE_WRITE_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=False,
)
TRANSITION_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)


class FeatureRequestTokenVerifier:
    """Resolve MCP bearer tokens through the existing FeatureRequest token model."""

    async def verify_token(self, token: str) -> AccessToken | None:
        api_token = await sync_to_async(
            ApiToken.resolve_active,
            thread_sensitive=True,
        )(token)
        if api_token is None:
            return None

        await sync_to_async(api_token.mark_used, thread_sensitive=True)()
        scopes = ["read"]
        if api_token.can_write:
            scopes.append("write")

        return AccessToken(
            token=token,
            client_id=f"feature-request-api-token-{api_token.id}",
            scopes=scopes,
            resource=settings.FEATURE_REQUEST_MCP_SERVER_URL,
            subject=str(api_token.user_id),
            claims={
                "token_id": api_token.id,
                "user_id": api_token.user_id,
                "user_handle": api_token.user.handle,
                "can_write": api_token.can_write,
            },
        )


def _current_raw_token() -> str:
    access_token = get_access_token()
    if access_token is None:
        raise RuntimeError("An authenticated FeatureRequest MCP connection is required.")
    return access_token.token


def _clean_params(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _next_step_for_status(status_code: int) -> str:
    if status_code == 401:
        return "Reconnect with an active FeatureRequest API token."
    if status_code == 403:
        return "Use a write-enabled token or ask a project owner/issue author to perform this action."
    if status_code == 404:
        return "Verify the owner handle, project slug, issue id, or comment id."
    if status_code == 503:
        return "Retry later; moderation or a provider dependency is temporarily unavailable."
    return "Review the request inputs and retry only after correcting the reported error."


async def _api_request(
    *,
    action: str,
    method: str,
    path: str,
    resource: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = _current_raw_token()
    normalized_path = path.lstrip("/")
    base_url = f"{settings.FEATURE_REQUEST_API_BASE_URL.rstrip('/')}/"

    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=settings.FEATURE_REQUEST_MCP_API_TIMEOUT_SECONDS,
        ) as client:
            response = await client.request(
                method,
                normalized_path,
                params=_clean_params(params or {}),
                json=json_body,
            )
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "action": action,
            "request": {
                "method": method,
                "path": f"/api/{normalized_path}",
                "status": None,
            },
            "resource": resource or {},
            "error": {
                "status_code": None,
                "message": f"FeatureRequest API could not be reached: {exc.__class__.__name__}",
            },
            "next_step": "Verify FEATURE_REQUEST_API_BASE_URL and retry when the API is reachable.",
        }

    try:
        payload: Any = response.json() if response.content else None
    except ValueError:
        payload = {"detail": response.text.strip() or "Invalid API response."}

    request_meta = {
        "method": method,
        "path": f"/api/{normalized_path}",
        "status": response.status_code,
    }
    if response.is_success:
        return {
            "ok": True,
            "action": action,
            "request": request_meta,
            "resource": resource or {},
            "data": payload,
            "meta": {
                "items_returned": len(payload) if isinstance(payload, list) else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    message = "FeatureRequest API rejected the request."
    if isinstance(payload, dict):
        message = str(payload.get("detail") or payload.get("message") or message)

    return {
        "ok": False,
        "action": action,
        "request": request_meta,
        "resource": resource or {},
        "error": {
            "status_code": response.status_code,
            "message": message,
        },
        "next_step": _next_step_for_status(response.status_code),
    }


mcp = MCPServer(
    name="feature-request",
    title="FeatureRequest",
    description="Operate FeatureRequest projects and evidence-backed request lifecycles.",
    instructions=(
        "FeatureRequest returns deterministic evidence; the calling agent owns priority, duplicate, "
        "and delivery judgments. Never infer a duplicate or verified delivery from scores or links alone. "
        "Before deleting a project, call get_project and proceed only on explicit user direction. "
        "Use update_request for content or priority and transition_request for status. "
        "Do not use done or closed without explicit user direction and inspected delivery evidence."
    ),
    version="0.2.0",
    token_verifier=FeatureRequestTokenVerifier(),
    auth=AuthSettings(
        issuer_url=settings.FEATURE_REQUEST_MCP_AUTH_ISSUER_URL,
        resource_server_url=settings.FEATURE_REQUEST_MCP_SERVER_URL,
        required_scopes=[],
    ),
)


@mcp.tool(
    title="List projects",
    description="List projects owned by the authenticated FeatureRequest user.",
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def list_projects() -> dict[str, Any]:
    return await _api_request(
        action="list_projects",
        method="GET",
        path="projects",
    )


@mcp.tool(
    title="Get project",
    description="Get one project owned by the authenticated FeatureRequest user by stable project id.",
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def get_project(project_id: int) -> dict[str, Any]:
    return await _api_request(
        action="get_project",
        method="GET",
        path=f"projects/{project_id}",
        resource={"project_id": project_id},
    )


@mcp.tool(
    title="Create project",
    description="Create a FeatureRequest project owned by the authenticated user.",
    annotations=WRITE_ANNOTATIONS,
    structured_output=True,
)
async def create_project(
    name: str,
    tagline: str = "",
    url: str = "",
) -> dict[str, Any]:
    return await _api_request(
        action="create_project",
        method="POST",
        path="projects",
        json_body={"name": name, "tagline": tagline, "url": url},
    )


@mcp.tool(
    title="Update project",
    description=(
        "Update an owned project's name, tagline, or URL. "
        "A name change may also change the project slug returned by the API."
    ),
    annotations=WRITE_ANNOTATIONS,
    structured_output=True,
)
async def update_project(
    project_id: int,
    name: str | None = None,
    tagline: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    payload = _clean_params({"name": name, "tagline": tagline, "url": url})
    if not payload:
        return {
            "ok": False,
            "action": "update_project",
            "request": {
                "method": "PATCH",
                "path": f"/api/projects/{project_id}",
                "status": None,
            },
            "resource": {"project_id": project_id},
            "error": {"status_code": 400, "message": "Provide at least one field to update."},
            "next_step": "Provide name, tagline, or url.",
        }
    return await _api_request(
        action="update_project",
        method="PATCH",
        path=f"projects/{project_id}",
        resource={"project_id": project_id},
        json_body=payload,
    )


@mcp.tool(
    title="Delete project",
    description=(
        "Permanently delete an owned project and its requests. Call get_project first, "
        "use only after explicit user direction, and pass the same id as confirm_project_id."
    ),
    annotations=DESTRUCTIVE_WRITE_ANNOTATIONS,
    structured_output=True,
)
async def delete_project(project_id: int, confirm_project_id: int) -> dict[str, Any]:
    if confirm_project_id != project_id:
        return {
            "ok": False,
            "action": "delete_project",
            "request": {
                "method": "DELETE",
                "path": f"/api/projects/{project_id}",
                "status": None,
            },
            "resource": {"project_id": project_id},
            "error": {"status_code": 400, "message": "Project confirmation id does not match."},
            "next_step": "Call get_project, confirm the explicit user request, then pass the same project id.",
        }
    return await _api_request(
        action="delete_project",
        method="DELETE",
        path=f"projects/{project_id}",
        resource={"project_id": project_id},
    )


@mcp.tool(
    title="List requests",
    description=(
        "List requests for one FeatureRequest owner or one owner/project board. "
        "Use status=active to exclude done and closed requests."
    ),
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def list_requests(
    owner_handle: str,
    project_slug: str | None = None,
    issue_type: IssueType | None = None,
    status: IssueStatusFilter | None = None,
    priority: IssuePriority | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    owner = quote(owner_handle.strip().lower(), safe="")
    resource: dict[str, Any] = {"owner_handle": owner_handle.strip().lower()}
    params = {
        "issue_type": issue_type,
        "status": status,
        "priority": priority,
        "limit": limit,
    }

    if project_slug:
        project = quote(project_slug.strip(), safe="")
        resource["project_slug"] = project_slug.strip()
        path = f"projects/{owner}/{project}/issues"
    else:
        path = f"owners/{owner}/issues"

    return await _api_request(
        action="list_requests",
        method="GET",
        path=path,
        resource=resource,
        params=params,
    )


@mcp.tool(
    title="Get request",
    description="Get one FeatureRequest request by its stable issue id.",
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def get_request(issue_id: int) -> dict[str, Any]:
    return await _api_request(
        action="get_request",
        method="GET",
        path=f"issues/{issue_id}",
        resource={"issue_id": issue_id},
    )


@mcp.tool(
    title="List request comments",
    description="List the comments on one FeatureRequest request.",
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def list_request_comments(issue_id: int) -> dict[str, Any]:
    return await _api_request(
        action="list_request_comments",
        method="GET",
        path=f"issues/{issue_id}/comments",
        resource={"issue_id": issue_id},
    )


@mcp.tool(
    title="Get queue snapshot",
    description=(
        "Return active requests, current user-assigned priorities, statuses, counts, and activity times. "
        "This is deterministic evidence, not a priority recommendation."
    ),
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def get_queue_snapshot(
    project_id: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    return await _api_request(
        action="get_queue_snapshot",
        method="GET",
        path="me/request-queue",
        resource=_clean_params({"project_id": project_id}),
        params={"project_id": project_id, "limit": limit},
    )


@mcp.tool(
    title="Find duplicate candidates",
    description=(
        "Return explainable lexical similarity candidates within one project before or after intake. "
        "Scores and matched terms are evidence only; the calling agent decides whether requests duplicate."
    ),
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def find_duplicate_candidates(
    owner_handle: str,
    project_slug: str,
    title: str,
    description: str = "",
    exclude_issue_id: int | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    clean_owner = owner_handle.strip().lower()
    clean_project = project_slug.strip()
    return await _api_request(
        action="find_duplicate_candidates",
        method="GET",
        path=(
            f"projects/{quote(clean_owner, safe='')}/"
            f"{quote(clean_project, safe='')}/duplicate-candidates"
        ),
        resource={"owner_handle": clean_owner, "project_slug": clean_project},
        params={
            "title": title,
            "description": description,
            "exclude_issue_id": exclude_issue_id,
            "limit": limit,
        },
    )


@mcp.tool(
    title="List request activity",
    description="List the structured activity history for one request the authenticated user can manage.",
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def list_request_activity(issue_id: int, limit: int = 100) -> dict[str, Any]:
    return await _api_request(
        action="list_request_activity",
        method="GET",
        path=f"issues/{issue_id}/activity",
        resource={"issue_id": issue_id},
        params={"limit": limit},
    )


@mcp.tool(
    title="List request changes",
    description=(
        "Read the authenticated owner's cross-project request change feed after a stable event cursor."
    ),
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def list_request_changes(after_id: int = 0, limit: int = 50) -> dict[str, Any]:
    return await _api_request(
        action="list_request_changes",
        method="GET",
        path="me/issue-changes",
        params={"after_id": after_id, "limit": limit},
    )


@mcp.tool(
    title="List delivery artifacts",
    description=(
        "List stored delivery evidence links for one request. Links are not proof that delivery was verified."
    ),
    annotations=READ_ONLY_ANNOTATIONS,
    structured_output=True,
)
async def list_delivery_artifacts(issue_id: int) -> dict[str, Any]:
    return await _api_request(
        action="list_delivery_artifacts",
        method="GET",
        path=f"issues/{issue_id}/delivery-artifacts",
        resource={"issue_id": issue_id},
    )


@mcp.tool(
    title="Create request",
    description="Create a feature request or bug on one FeatureRequest project board.",
    annotations=WRITE_ANNOTATIONS,
    structured_output=True,
)
async def create_request(
    owner_handle: str,
    project_slug: str,
    title: str,
    description: str = "",
    issue_type: IssueType = "feature",
    priority: IssuePriority = 2,
) -> dict[str, Any]:
    clean_owner = owner_handle.strip().lower()
    clean_project = project_slug.strip()
    return await _api_request(
        action="create_request",
        method="POST",
        path=(
            f"projects/{quote(clean_owner, safe='')}/"
            f"{quote(clean_project, safe='')}/issues"
        ),
        resource={
            "owner_handle": clean_owner,
            "project_slug": clean_project,
        },
        json_body={
            "issue_type": issue_type,
            "title": title,
            "description": description,
            "priority": priority,
        },
    )


@mcp.tool(
    title="Link duplicate request",
    description=(
        "Link one request to a root canonical request in the same project. "
        "This does not change priority or status and is reversible."
    ),
    annotations=IDEMPOTENT_WRITE_ANNOTATIONS,
    structured_output=True,
)
async def link_duplicate_request(
    issue_id: int,
    canonical_issue_id: int,
) -> dict[str, Any]:
    return await _api_request(
        action="link_duplicate_request",
        method="PATCH",
        path=f"issues/{issue_id}/duplicate",
        resource={"issue_id": issue_id, "canonical_issue_id": canonical_issue_id},
        json_body={"canonical_issue_id": canonical_issue_id},
    )


@mcp.tool(
    title="Unlink duplicate request",
    description="Remove a request's duplicate link without changing its priority or status.",
    annotations=IDEMPOTENT_WRITE_ANNOTATIONS,
    structured_output=True,
)
async def unlink_duplicate_request(issue_id: int) -> dict[str, Any]:
    return await _api_request(
        action="unlink_duplicate_request",
        method="DELETE",
        path=f"issues/{issue_id}/duplicate",
        resource={"issue_id": issue_id},
    )


@mcp.tool(
    title="Link delivery artifact",
    description=(
        "Store a pull request, commit, deployment, release, or other delivery evidence URL. "
        "The calling agent must inspect the external artifact before claiming delivery is verified."
    ),
    annotations=IDEMPOTENT_WRITE_ANNOTATIONS,
    structured_output=True,
)
async def link_delivery_artifact(
    issue_id: int,
    kind: DeliveryArtifactKind,
    url: str,
    label: str = "",
) -> dict[str, Any]:
    return await _api_request(
        action="link_delivery_artifact",
        method="POST",
        path=f"issues/{issue_id}/delivery-artifacts",
        resource={"issue_id": issue_id},
        json_body={"kind": kind, "url": url, "label": label},
    )


@mcp.tool(
    title="Unlink delivery artifact",
    description="Remove one stored delivery evidence link from a request.",
    annotations=IDEMPOTENT_WRITE_ANNOTATIONS,
    structured_output=True,
)
async def unlink_delivery_artifact(issue_id: int, artifact_id: int) -> dict[str, Any]:
    return await _api_request(
        action="unlink_delivery_artifact",
        method="DELETE",
        path=f"issues/{issue_id}/delivery-artifacts/{artifact_id}",
        resource={"issue_id": issue_id, "artifact_id": artifact_id},
    )


@mcp.tool(
    title="Update request",
    description=(
        "Update a request title, description, or priority. "
        "Use transition_request separately for status changes."
    ),
    annotations=WRITE_ANNOTATIONS,
    structured_output=True,
)
async def update_request(
    issue_id: int,
    title: str | None = None,
    description: str | None = None,
    priority: IssuePriority | None = None,
) -> dict[str, Any]:
    payload = _clean_params(
        {
            "title": title,
            "description": description,
            "priority": priority,
        }
    )
    if not payload:
        return {
            "ok": False,
            "action": "update_request",
            "request": {"method": "PATCH", "path": f"/api/issues/{issue_id}", "status": None},
            "resource": {"issue_id": issue_id},
            "error": {"status_code": 400, "message": "Provide at least one field to update."},
            "next_step": "Provide title, description, or priority.",
        }

    return await _api_request(
        action="update_request",
        method="PATCH",
        path=f"issues/{issue_id}",
        resource={"issue_id": issue_id},
        json_body=payload,
    )


@mcp.tool(
    title="Transition request",
    description=(
        "Change a request status. Only use done or closed with explicit user direction "
        "and merge or release evidence."
    ),
    annotations=TRANSITION_ANNOTATIONS,
    structured_output=True,
)
async def transition_request(issue_id: int, status: IssueStatus) -> dict[str, Any]:
    return await _api_request(
        action="transition_request",
        method="PATCH",
        path=f"issues/{issue_id}",
        resource={"issue_id": issue_id},
        json_body={"status": status},
    )


@mcp.tool(
    title="Add request comment",
    description="Add a comment to one FeatureRequest request.",
    annotations=WRITE_ANNOTATIONS,
    structured_output=True,
)
async def add_request_comment(issue_id: int, body: str) -> dict[str, Any]:
    return await _api_request(
        action="add_request_comment",
        method="POST",
        path=f"issues/{issue_id}/comments",
        resource={"issue_id": issue_id},
        json_body={"body": body},
    )


@mcp.tool(
    title="Update request comment",
    description="Update an existing request comment when the authenticated user is allowed to edit it.",
    annotations=WRITE_ANNOTATIONS,
    structured_output=True,
)
async def update_request_comment(
    issue_id: int,
    comment_id: int,
    body: str,
) -> dict[str, Any]:
    return await _api_request(
        action="update_request_comment",
        method="PATCH",
        path=f"issues/{issue_id}/comments/{comment_id}",
        resource={"issue_id": issue_id, "comment_id": comment_id},
        json_body={"body": body},
    )


def create_application():
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        host=settings.FEATURE_REQUEST_MCP_HOST,
    )
