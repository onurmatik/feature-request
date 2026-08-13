from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from mcp_oauth.models import OAuthCleanupRun
from mcp_oauth.operations import send_deduplicated_admin_alert


class Command(BaseCommand):
    help = "Check persistent MCP/OAuth cleanup health and alert through Django ADMINS."

    def handle(self, *args, **options):
        now = timezone.now()
        latest_success = OAuthCleanupRun.objects.filter(success=True).order_by("-completed_at").first()
        latest_two = list(OAuthCleanupRun.objects.order_by("-started_at")[:2])
        stale = latest_success is None or latest_success.completed_at < now - timedelta(hours=36)
        lagged_twice = len(latest_two) == 2 and all(
            run.oldest_eligible_seconds > 48 * 60 * 60 for run in latest_two
        )
        failed = OAuthCleanupRun.objects.filter(
            success=False,
            started_at__gte=now - timedelta(hours=36),
        ).exists()
        problems = []
        if stale:
            problems.append("last_success_older_than_36h")
        if lagged_twice:
            problems.append("oldest_eligible_older_than_48h_twice")
        if failed:
            problems.append("recent_cleanup_failure")
        if problems:
            send_deduplicated_admin_alert("cleanup_health", {"problems": problems})
            raise CommandError("MCP/OAuth cleanup health is degraded: " + ", ".join(problems))
        self.stdout.write(self.style.SUCCESS("MCP/OAuth cleanup health is good."))
