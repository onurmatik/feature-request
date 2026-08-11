from .models import IssueEvent


def record_issue_event(*, issue, event_type, actor=None, data=None):
    """Append a structured, agent-readable event to one request."""

    return IssueEvent.objects.create(
        issue=issue,
        actor=actor,
        event_type=event_type,
        data=data or {},
    )
