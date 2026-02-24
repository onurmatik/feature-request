from typing import Optional

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from ninja import Router, Schema
from ninja.errors import HttpError

from .models import Issue, IssueComment, IssueUpvote, Project

router = Router(tags=["issues"])


class IssueCreateIn(Schema):
    issue_type: str = Issue.Type.FEATURE
    title: str
    description: str = ""
    priority: int = Issue.Priority.MEDIUM


class ProjectOut(Schema):
    id: int
    owner_id: int
    owner_handle: str
    name: str
    slug: str
    tagline: str
    description: str
    visibility: str
    created_at: str
    updated_at: str


class ProjectCreateIn(Schema):
    name: str
    slug: str = ""
    tagline: str = ""
    description: str = ""
    visibility: str = Project.Visibility.PUBLIC


class ProjectUpdateIn(Schema):
    name: Optional[str] = None
    slug: Optional[str] = None
    tagline: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[str] = None


class IssueUpdateIn(Schema):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None


class IssueOut(Schema):
    id: int
    project_id: int
    author_id: int
    issue_type: str
    title: str
    description: str
    status: str
    priority: int
    upvotes_count: int
    comments_count: int
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
    body: str
    created_at: str
    updated_at: str


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


def _validate_priority(priority: int):
    allowed = {value for value, _ in Issue.Priority.choices}
    if priority not in allowed:
        raise HttpError(400, "Invalid priority.")


def _validate_project_visibility(visibility: str):
    allowed = {value for value, _ in Project.Visibility.choices}
    if visibility not in allowed:
        raise HttpError(400, "Invalid visibility.")


def _can_manage_issue(user, issue: Issue):
    return user.id == issue.project.owner_id or user.id == issue.author_id


def _can_manage_project(user, project: Project):
    return user.id == project.owner_id


def _clean_non_empty(value: str, field_name: str):
    cleaned = value.strip()
    if not cleaned:
        raise HttpError(400, f"{field_name} cannot be empty.")
    return cleaned


def _normalize_project_slug(name: str, slug_value: str):
    raw_slug = slug_value.strip()
    candidate = slugify(raw_slug) if raw_slug else slugify(name)
    if not candidate:
        raise HttpError(400, "Project slug cannot be empty.")
    return candidate


def _issue_to_dict(issue: Issue):
    upvotes_count = getattr(issue, "upvotes_count", None)
    comments_count = getattr(issue, "comments_count", None)
    return {
        "id": issue.id,
        "project_id": issue.project_id,
        "author_id": issue.author_id,
        "issue_type": issue.issue_type,
        "title": issue.title,
        "description": issue.description,
        "status": issue.status,
        "priority": issue.priority,
        "upvotes_count": upvotes_count if upvotes_count is not None else issue.upvotes.count(),
        "comments_count": comments_count if comments_count is not None else issue.comments.count(),
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
    }


def _project_to_dict(project: Project):
    return {
        "id": project.id,
        "owner_id": project.owner_id,
        "owner_handle": project.owner.handle,
        "name": project.name,
        "slug": project.slug,
        "tagline": project.tagline,
        "description": project.description,
        "visibility": project.visibility,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


def _comment_to_dict(comment: IssueComment):
    return {
        "id": comment.id,
        "issue_id": comment.issue_id,
        "author_id": comment.author_id,
        "author_handle": comment.author.handle,
        "body": comment.body,
        "created_at": comment.created_at.isoformat(),
        "updated_at": comment.updated_at.isoformat(),
    }


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
    return Issue.objects.select_related("project", "author").annotate(
        upvotes_count=Count("upvotes", distinct=True),
        comments_count=Count("comments", distinct=True),
    )


def _ensure_project_read_access(request, project: Project):
    if project.visibility == Project.Visibility.PUBLIC:
        return
    user = request.user
    if not user.is_authenticated or user.id != project.owner_id:
        raise HttpError(404, "Project not found.")


def _get_visible_projects_for_owner(request, owner_handle: str):
    owner = _get_owner(owner_handle)
    projects = Project.objects.select_related("owner").filter(owner=owner)
    if request.user.is_authenticated and request.user.id == owner.id:
        return owner, projects
    return owner, projects.filter(visibility=Project.Visibility.PUBLIC)


@router.get("/projects", response=list[ProjectOut])
def list_my_projects(request):
    user = _require_auth_user(request)
    projects = Project.objects.select_related("owner").filter(owner=user)
    return [_project_to_dict(project) for project in projects]


@router.post("/projects", response={201: ProjectOut})
def create_project(request, payload: ProjectCreateIn):
    user = _require_auth_user(request)
    name = _clean_non_empty(payload.name, "Project name")
    _validate_project_visibility(payload.visibility)
    slug = _normalize_project_slug(name, payload.slug)

    if Project.objects.filter(owner=user, slug=slug).exists():
        raise HttpError(400, "This slug is already used for this owner.")

    project = Project.objects.create(
        owner=user,
        name=name,
        slug=slug,
        tagline=payload.tagline.strip(),
        description=payload.description.strip(),
        visibility=payload.visibility,
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

    if payload.slug is not None:
        slug_candidate = _normalize_project_slug(project.name, payload.slug)
        duplicate_qs = Project.objects.filter(owner=project.owner, slug=slug_candidate).exclude(
            id=project.id
        )
        if duplicate_qs.exists():
            raise HttpError(400, "This slug is already used for this owner.")
        project.slug = slug_candidate
        updated_fields.append("slug")

    if payload.tagline is not None:
        project.tagline = payload.tagline.strip()
        updated_fields.append("tagline")

    if payload.description is not None:
        project.description = payload.description.strip()
        updated_fields.append("description")

    if payload.visibility is not None:
        _validate_project_visibility(payload.visibility)
        project.visibility = payload.visibility
        updated_fields.append("visibility")

    if updated_fields:
        updated_fields.append("updated_at")
        project.save(update_fields=updated_fields)

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
    _, projects = _get_visible_projects_for_owner(request, owner_handle)
    return [_project_to_dict(project) for project in projects]


@router.get("/owners/{owner_handle}/issues", response=list[IssueOut])
def list_owner_issues(
    request,
    owner_handle: str,
    project_slug: Optional[str] = None,
    issue_type: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
):
    _, visible_projects = _get_visible_projects_for_owner(request, owner_handle)
    if project_slug:
        visible_projects = visible_projects.filter(slug=project_slug)
        if not visible_projects.exists():
            raise HttpError(404, "Project not found.")

    queryset = _get_annotated_issue_queryset().filter(project__in=visible_projects)

    if issue_type:
        _validate_issue_type(issue_type)
        queryset = queryset.filter(issue_type=issue_type)
    if status:
        _validate_status(status)
        queryset = queryset.filter(status=status)
    if priority is not None:
        _validate_priority(priority)
        queryset = queryset.filter(priority=priority)

    return [_issue_to_dict(issue) for issue in queryset]


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
):
    project = _get_project(owner_handle, project_slug)
    _ensure_project_read_access(request, project)
    queryset = _get_annotated_issue_queryset().filter(project=project)

    if issue_type:
        _validate_issue_type(issue_type)
        queryset = queryset.filter(issue_type=issue_type)
    if status:
        _validate_status(status)
        queryset = queryset.filter(status=status)
    if priority is not None:
        _validate_priority(priority)
        queryset = queryset.filter(priority=priority)

    return [_issue_to_dict(issue) for issue in queryset]


@router.post(
    "/projects/{owner_handle}/{project_slug}/issues",
    response={201: IssueOut},
)
def create_issue(request, owner_handle: str, project_slug: str, payload: IssueCreateIn):
    user = _require_auth_user(request)
    _validate_issue_type(payload.issue_type)
    _validate_priority(payload.priority)

    project = _get_project(owner_handle, project_slug)
    _ensure_project_read_access(request, project)
    issue = Issue.objects.create(
        project=project,
        author=user,
        issue_type=payload.issue_type,
        title=_clean_non_empty(payload.title, "Issue title"),
        description=payload.description.strip(),
        priority=payload.priority,
    )
    return 201, _issue_to_dict(issue)


@router.get("/issues/{issue_id}", response=IssueOut)
def get_issue(request, issue_id: int):
    issue = get_object_or_404(_get_annotated_issue_queryset(), id=issue_id)
    _ensure_project_read_access(request, issue.project)
    return _issue_to_dict(issue)


@router.patch("/issues/{issue_id}", response=IssueOut)
def update_issue(request, issue_id: int, payload: IssueUpdateIn):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    _ensure_project_read_access(request, issue.project)

    if not _can_manage_issue(user, issue):
        raise HttpError(403, "Not allowed to update this issue.")

    updated_fields = []

    if payload.title is not None:
        issue.title = _clean_non_empty(payload.title, "Issue title")
        updated_fields.append("title")
    if payload.description is not None:
        issue.description = payload.description.strip()
        updated_fields.append("description")
    if payload.status is not None:
        _validate_status(payload.status)
        issue.status = payload.status
        updated_fields.append("status")
    if payload.priority is not None:
        _validate_priority(payload.priority)
        issue.priority = payload.priority
        updated_fields.append("priority")

    if updated_fields:
        updated_fields.append("updated_at")
        issue.save(update_fields=updated_fields)
        issue = _get_annotated_issue_queryset().get(id=issue.id)

    return _issue_to_dict(issue)


@router.post("/issues/{issue_id}/upvote/toggle", response=UpvoteToggleOut)
def toggle_issue_upvote(request, issue_id: int):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    _ensure_project_read_access(request, issue.project)

    existing = IssueUpvote.objects.filter(issue=issue, user=user).first()
    if existing:
        existing.delete()
        upvoted = False
    else:
        IssueUpvote.objects.create(issue=issue, user=user)
        upvoted = True

    return {
        "issue_id": issue.id,
        "upvoted": upvoted,
        "upvotes_count": issue.upvotes.count(),
    }


@router.get("/issues/{issue_id}/comments", response=list[CommentOut])
def list_issue_comments(request, issue_id: int):
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    _ensure_project_read_access(request, issue.project)
    comments = issue.comments.select_related("author").all()
    return [_comment_to_dict(comment) for comment in comments]


@router.post("/issues/{issue_id}/comments", response={201: CommentOut})
def create_issue_comment(request, issue_id: int, payload: CommentCreateIn):
    user = _require_auth_user(request)
    issue = get_object_or_404(Issue.objects.select_related("project"), id=issue_id)
    _ensure_project_read_access(request, issue.project)
    body = _clean_non_empty(payload.body, "Comment body")

    comment = IssueComment.objects.create(
        issue=issue,
        author=user,
        body=body,
    )
    comment = IssueComment.objects.select_related("author").get(id=comment.id)
    return 201, _comment_to_dict(comment)
