import json
from datetime import timedelta
from threading import Barrier, Event, Lock, Thread
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from accounts.models import ApiToken
from agent_runtime.context import AgentContext
from agent_runtime.errors import ContractApplicationError, MissingScopeError
from agent_runtime.service import service
from inbox.models import OwnerMessage

from .embed import token_digest
from .models import (
    EmbeddedIssueSubmission, Issue, IssueComment, IssueDeliveryArtifact,
    IssueEvent, IssueScopeAssessment, IssueUpvote, Project, ProjectSpec,
    ProjectSpecChangeProposal,
)
from .services import SPEC_TEMPLATE, create_comment_resource


@override_settings(OPENAI_API_KEY="", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ProjectArchiveTest(TestCase):
    def setUp(self):
        users = get_user_model()
        self.owner = users.objects.create_user(email="archive-owner@example.com", handle="archive_owner")
        self.author = users.objects.create_user(email="archive-author@example.com", handle="archive_author")
        self.project = Project.objects.create(owner=self.owner, name="Roadmap")
        self.issue = Issue.objects.create(project=self.project, author=self.author, title="Keep this request")
        self.comment = IssueComment.objects.create(issue=self.issue, author=self.author, body="Keep this comment")
        self.spec = ProjectSpec.objects.create(project=self.project, content=SPEC_TEMPLATE)
        self.assessment = IssueScopeAssessment.objects.create(
            issue=self.issue, spec_revision=1, verdict="in_scope", public_reason="Fits the scope."
        )
        self.proposal = ProjectSpecChangeProposal.objects.create(
            project=self.project, issue=self.issue, base_spec_revision=1,
            base_content=SPEC_TEMPLATE, proposed_content=SPEC_TEMPLATE,
            summary="Keep the scope", created_by=self.owner,
        )
        self.artifact = IssueDeliveryArtifact.objects.create(
            issue=self.issue, added_by=self.owner, kind="commit", url="https://example.com/commit/1"
        )
        IssueEvent.objects.create(issue=self.issue, actor=self.owner, event_type="created")
        IssueUpvote.objects.create(issue=self.issue, user=self.author)
        self.token = "archive-verification-token"
        self.submission = EmbeddedIssueSubmission.objects.create(
            project=self.project, token_hash=token_digest(self.token),
            expires_at=timezone.now() + timedelta(hours=1), email="pending@example.com",
            display_name="Pending", issue_type="feature", title="Pending request",
        )
        self.board = f"/api/projects/{self.owner.handle}/{self.project.slug}"
        self.project_url = f"/api/projects/{self.project.pk}"
        self.issue_url = f"/api/issues/{self.issue.pk}"
        self.client.force_login(self.owner)

    def request(self, method, path, body=None):
        return getattr(self.client, method)(path, data=json.dumps(body or {}), content_type="application/json")

    def transition(self, action, revision):
        return self.request("post", f"{self.project_url}/{action}", {"expected_revision": revision})

    def archive(self):
        response = self.transition("archive", 1)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def agent(self, name, arguments=None, user=None, scopes=("read", "write")):
        return service.call(name, arguments or {}, AgentContext(
            user=user or self.owner, authenticated_client_id="archive-tests",
            scopes=frozenset(scopes), request_id=f"archive-{uuid4().hex}",
        ))

    def agent_error(self, code, name, arguments=None, **kwargs):
        with self.assertRaises(ContractApplicationError) as raised:
            self.agent(name, arguments, **kwargs)
        self.assertEqual(raised.exception.code, code)

    def test_archive_restore_preserves_data_url_and_revisions(self):
        original_slug = self.project.slug
        receipt = self.archive()
        self.assertEqual(set(receipt), {"project_id", "revision", "archived_at"})
        self.assertEqual(receipt["revision"], 2)
        self.assertIsNotNone(receipt["archived_at"])
        archived = self.client.get("/api/projects/archived").json()
        self.assertEqual([p["id"] for p in archived], [self.project.pk])
        self.assertEqual(set(archived[0]), {"id", "name", "slug", "revision", "archived_at"})
        self.assertEqual(self.transition("archive", 2).json(), receipt)
        self.assertEqual(self.transition("restore", 1).status_code, 409)
        restored = self.transition("restore", 2)
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["revision"], 3)
        self.assertIsNone(restored.json()["archived_at"])
        self.assertEqual(self.transition("restore", 3).json(), restored.json())
        self.project.refresh_from_db()
        self.issue.refresh_from_db()
        self.assertEqual(self.project.slug, original_slug)
        self.assertEqual(self.issue.revision, 1)
        self.assertEqual(self.issue.status, "open")
        for obj in (self.comment, self.spec, self.assessment, self.proposal, self.artifact, self.submission):
            self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())
        self.assertEqual(self.issue.upvotes.count(), 1)
        self.assertEqual(self.client.get(self.issue_url).status_code, 200)
        self.assertEqual(self.client.get(f"{self.board}/spec").status_code, 200)
        self.assertEqual(self.client.get("/api/projects/archived").json(), [])

    def test_lists_counts_and_all_child_reads_hide_archived_content(self):
        self.archive()
        for user in (self.owner, self.author):
            self.client.force_login(user)
            for path in (
                self.project_url, f"{self.board}/issues", f"{self.board}/spec",
                f"{self.board}/duplicate-candidates?title=Keep",
                self.issue_url, f"{self.issue_url}/comments", f"{self.issue_url}/activity",
                f"{self.issue_url}/delivery-artifacts", f"{self.issue_url}/scope-assessment",
                f"{self.project_url}/spec-change-proposals",
            ):
                with self.subTest(user=user.handle, path=path):
                    self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_login(self.owner)
        for path in (
            "/api/projects", f"/api/owners/{self.owner.handle}/projects",
            f"/api/owners/{self.owner.handle}/issues",
            f"/api/owners/{self.author.handle}/interacted-projects",
            "/api/public/featured-projects",
        ):
            self.assertEqual(self.client.get(path).json(), [], path)
        queue = self.client.get("/api/me/request-queue").json()
        self.assertEqual(queue["projects_count"], 0)
        self.assertEqual(queue["active_requests_count"], 0)
        self.assertEqual(self.client.get("/api/me/issue-changes").json()["events"], [])
        self.assertEqual(self.client.get(f"/api/me/request-queue?project_id={self.project.pk}").status_code, 404)
        self.client.logout()
        for path in (self.issue_url, f"{self.issue_url}/comments", f"{self.board}/spec", f"{self.board}/issues"):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get("/api/projects/archived").status_code, 401)

    def test_archived_writes_are_blocked_including_legacy_embed_links(self):
        self.archive()
        operations = (
            ("patch", self.project_url, {"name": "Changed"}),
            ("delete", self.project_url, {}),
            ("put", f"{self.project_url}/spec", {"content": SPEC_TEMPLATE, "expected_revision": 1}),
            ("delete", f"{self.project_url}/spec", {"expected_revision": 1, "confirm_project_id": self.project.pk}),
            ("post", f"{self.board}/issues", {"title": "New request"}),
            ("patch", self.issue_url, {"title": "Changed"}),
            ("post", f"{self.issue_url}/comments", {"body": "New comment"}),
            ("patch", f"{self.issue_url}/comments/{self.comment.pk}", {"body": "Changed"}),
            ("post", f"{self.issue_url}/upvote/toggle", {}),
            ("patch", f"{self.issue_url}/duplicate", {"canonical_issue_id": self.issue.pk}),
            ("delete", f"{self.issue_url}/duplicate", {}),
            ("post", f"{self.issue_url}/delivery-artifacts", {"kind": "commit", "url": "https://example.com/new"}),
            ("delete", f"{self.issue_url}/delivery-artifacts/{self.artifact.pk}", {}),
            ("post", f"{self.issue_url}/scope-assessment/retry", {}),
            ("post", f"{self.issue_url}/spec-change-proposals", {}),
            ("patch", f"/api/spec-change-proposals/{self.proposal.pk}", {"decision": "accept", "expected_revision": 1}),
            ("post", f"/api/embed/projects/{self.owner.handle}/{self.project.slug}/submissions", {"feedback": "A useful request with enough detail.", "submission_id": str(uuid4()), "turnstile_token": "unused"}),
            ("post", f"/api/owners/{self.owner.handle}/messages", {"body": "Hello", "project_slug": self.project.slug}),
        )
        for method, path, body in operations:
            with self.subTest(path=path, method=method):
                # Messages cannot be self-addressed; use the request author.
                self.client.force_login(self.author if path.endswith("/messages") else self.owner)
                self.assertEqual(self.request(method, path, body).status_code, 404)
        self.assertEqual(self.client.get(f"/embed/{self.owner.handle}/{self.project.slug}/").status_code, 404)
        for method in ("get", "post"):
            self.assertEqual(getattr(self.client, method)(f"/embed/submissions/{self.token}/verify/").status_code, 404)
        self.assertEqual(Issue.objects.count(), 1)
        self.assertEqual(IssueComment.objects.count(), 1)
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision, 2)

    def test_capacity_and_slug_reservation_are_shared_by_rest_and_mcp(self):
        self.archive()
        self.assertEqual(self.agent("get_account_capabilities")["limits"]["project_count"]["used"], 0)
        created = self.request("post", "/api/projects", {"name": "Roadmap"})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["slug"], "roadmap-2")
        self.assertEqual(self.transition("restore", 2).status_code, 403)
        self.agent_error("capacity_reached", "restore_project", {
            "project_id": self.project.pk, "expected_revision": 2, "idempotency_key": "restore-full-capacity",
        })
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision, 2)
        self.assertIsNotNone(self.project.archived_at)
        self.agent("archive_project", {
            "project_id": created.json()["id"], "expected_revision": 1, "idempotency_key": "archive-replacement",
        })
        self.assertEqual(self.transition("restore", 2).status_code, 200)
        self.assertEqual(self.agent("get_account_capabilities")["limits"]["project_count"]["used"], 1)

    def test_owner_and_write_scope_are_required(self):
        self.client.force_login(self.author)
        self.assertEqual(self.transition("archive", 1).status_code, 403)
        self.client.logout()
        self.assertEqual(self.transition("archive", 1).status_code, 401)
        _token, secret = ApiToken.issue(user=self.owner, name="Archive read only", can_write=False)
        response = self.client.post(f"{self.project_url}/archive", data=json.dumps({"expected_revision": 1}), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {secret}")
        self.assertEqual(response.status_code, 403)
        args = {"project_id": self.project.pk, "expected_revision": 1, "idempotency_key": "archive-auth-tests"}
        self.agent_error("permission_denied", "archive_project", args, user=self.author)
        with self.assertRaises(MissingScopeError):
            self.agent("archive_project", args, scopes=("read",))
        self.agent("archive_project", args)
        self.assertEqual(self.agent("list_archived_projects", user=self.author), {"projects": []})
        self.client.force_login(self.author)
        self.assertEqual(self.client.get("/api/projects/archived").json(), [])
        self.assertEqual(self.transition("restore", 2).status_code, 403)
        self.agent_error("permission_denied", "restore_project", {**args, "expected_revision": 2}, user=self.author)

    def test_inbox_history_retains_message_without_archived_project_link(self):
        message = OwnerMessage.objects.create(recipient=self.owner, sender_user=self.author, project=self.project, body="Existing conversation")
        self.archive()
        response = self.client.get("/api/me/messages").json()
        self.assertEqual(response[0]["id"], message.pk)
        self.assertEqual(response[0]["body"], "Existing conversation")
        self.assertIsNone(response[0]["project_id"])
        self.assertIsNone(response[0]["project_slug"])

    def test_mcp_replays_cannot_reopen_or_reveal_archived_content(self):
        update = {"project_id": self.project.pk, "expected_revision": 1, "tagline": "Private after archive", "idempotency_key": "update-before-archive"}
        self.agent("update_project", update)
        args = {"project_id": self.project.pk, "expected_revision": 2, "idempotency_key": "archive-for-replay"}
        archived = self.agent("archive_project", args)
        self.assertEqual(self.agent("archive_project", args), archived)
        self.agent_error("not_found", "update_project", update)
        self.agent_error("not_found", "get_project", {"project_id": self.project.pk})
        for tool, inputs in (
            ("get_request", {"issue_id": self.issue.pk}),
            ("list_request_comments", {"issue_id": self.issue.pk}),
            ("get_request_scope_assessment", {"issue_id": self.issue.pk}),
            ("get_project_spec", {"owner_handle": self.owner.handle, "project_slug": self.project.slug}),
            ("list_project_spec_proposals", {"project_id": self.project.pk}),
            ("get_queue_snapshot", {"project_id": self.project.pk}),
        ):
            self.agent_error("not_found", tool, inputs)
        self.assertEqual(self.agent("list_projects"), {"projects": []})
        self.assertEqual(self.agent("list_requests", {"owner_handle": self.owner.handle}), {"requests": []})
        self.assertEqual(self.agent("list_request_changes")["events"], [])
        self.assertEqual(self.agent("get_queue_snapshot")["projects_count"], 0)
        restore = {"project_id": self.project.pk, "expected_revision": 3, "idempotency_key": "restore-for-replay"}
        restored = self.agent("restore_project", restore)
        self.assertEqual(self.agent("archive_project", args), archived)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.archived_at)
        self.assertEqual(self.project.revision, 4)
        self.agent("archive_project", {**args, "expected_revision": 4, "idempotency_key": "archive-again-replay"})
        self.assertEqual(self.agent("restore_project", restore), restored)
        self.project.refresh_from_db()
        self.assertIsNotNone(self.project.archived_at)
        self.assertEqual(self.project.revision, 5)

    def test_archive_during_moderation_prevents_late_write(self):
        def archive_while_moderating(*args, **kwargs):
            self.archive()
        with patch("projects.api._moderate_issue_submission", side_effect=archive_while_moderating):
            response = self.request("post", f"{self.board}/issues", {"title": "Late request"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Issue.objects.count(), 1)

    def test_archive_after_request_commit_does_not_fail_its_response(self):
        def archive_while_notifying(*args, **kwargs):
            self.archive()
        with patch("projects.api._notify_owner_on_new_issue", side_effect=archive_while_notifying):
            response = self.request("post", f"{self.board}/issues", {"title": "Committed request"})
        self.assertEqual(response.status_code, 201)
        issue_id = response.json()["id"]
        self.assertTrue(Issue.objects.filter(pk=issue_id, title="Committed request").exists())
        self.assertEqual(self.client.get(f"/api/issues/{issue_id}").status_code, 404)

    def test_cached_deleted_scope_stays_hidden_after_archive(self):
        arguments = {
            "project_id": self.project.pk, "expected_revision": 1,
            "content": SPEC_TEMPLATE, "auto_decline_enabled": False,
            "idempotency_key": "scope-before-delete-and-archive",
        }
        with patch("agent_runtime.service._moderate_project_spec"):
            result = self.agent("update_project_spec", arguments)
        deleted = self.request("delete", f"{self.project_url}/spec", {
            "expected_revision": result["revision"], "confirm_project_id": self.project.pk,
        })
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(ProjectSpec.objects.filter(pk=self.spec.pk).exists())
        self.archive()
        self.agent_error("not_found", "update_project_spec", arguments)


@skipUnless(connection.vendor == "postgresql", "Row-lock concurrency requires PostgreSQL.")
@override_settings(OPENAI_API_KEY="", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ProjectArchiveConcurrencyTest(TransactionTestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(email="archive-race@example.com", handle="archive_race")
        self.project = Project.objects.create(owner=self.owner, name="Archived", archived_at=timezone.now())

    def agent(self, name, arguments):
        try:
            service.call(name, arguments, AgentContext(
                user=get_user_model().objects.get(pk=self.owner.pk),
                authenticated_client_id="archive-concurrency", scopes=frozenset({"read", "write"}),
                request_id=f"race-{uuid4().hex}",
            ))
            return "success"
        except ContractApplicationError as exc:
            return exc.code

    def restore(self, project):
        return self.agent("restore_project", {
            "project_id": project.pk, "expected_revision": 1, "idempotency_key": f"restore-capacity-race-{project.pk}",
        })

    def race(self, callbacks):
        barrier, lock, results = Barrier(len(callbacks)), Lock(), []

        def worker(callback):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                result = callback()
            except Exception as exc:
                result = exc
            finally:
                connections["default"].close()
            with lock:
                results.append(result)

        threads = [Thread(target=worker, args=(callback,)) for callback in callbacks]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        return results

    def test_rest_create_and_mcp_restore_share_capacity(self):
        def create():
            client = Client()
            client.force_login(get_user_model().objects.get(pk=self.owner.pk))
            response = client.post("/api/projects", data=json.dumps({"name": "New project"}), content_type="application/json")
            return "success" if response.status_code == 201 else "capacity_reached" if response.status_code == 403 else response.status_code

        results = self.race([create, lambda: self.restore(self.project)])
        self.assertCountEqual(results, ["success", "capacity_reached"])
        self.assertEqual(Project.objects.active().filter(owner=self.owner).count(), 1)

    def test_two_restores_cannot_overfill_capacity(self):
        second = Project.objects.create(owner=self.owner, name="Second", archived_at=timezone.now())
        results = self.race([lambda: self.restore(self.project), lambda: self.restore(second)])
        self.assertCountEqual(results, ["success", "capacity_reached"])
        self.assertEqual(Project.objects.active().filter(owner=self.owner).count(), 1)

    def test_same_key_archive_race_changes_revision_once(self):
        Project.objects.filter(pk=self.project.pk).update(archived_at=None)
        args = {"project_id": self.project.pk, "expected_revision": 1, "idempotency_key": "same-key-archive-race"}
        self.assertEqual(self.race([lambda: self.agent("archive_project", args)] * 2), ["success", "success"])
        self.project.refresh_from_db()
        self.assertEqual(self.project.revision, 2)
        self.assertIsNotNone(self.project.archived_at)

    def test_archive_wins_against_comment_waiting_on_moderation(self):
        Project.objects.filter(pk=self.project.pk).update(archived_at=None)
        issue = Issue.objects.create(project=self.project, author=self.owner, title="Original")
        moderation_started, archive_done = Event(), Event()

        def moderate(*args, **kwargs):
            moderation_started.set()
            if not archive_done.wait(timeout=10):
                raise AssertionError("Archive did not complete while moderation was pending")

        def archive():
            if not moderation_started.wait(timeout=10):
                raise AssertionError("Moderation did not start")
            try:
                return self.agent("archive_project", {
                    "project_id": self.project.pk, "expected_revision": 1, "idempotency_key": "archive-during-comment",
                })
            finally:
                archive_done.set()

        with patch("agent_runtime.service._moderate_comment_submission", side_effect=moderate):
            results = self.race([
                lambda: self.agent("add_request_comment", {"issue_id": issue.pk, "body": "Late comment", "idempotency_key": "late-comment-race"}),
                archive,
            ])
        self.assertCountEqual(results, ["success", "not_found"])
        self.assertFalse(IssueComment.objects.exists())

    def test_archive_waits_for_committing_child_without_owner_fk_deadlock(self):
        Project.objects.filter(pk=self.project.pk).update(archived_at=None)
        issue = Issue.objects.create(project=self.project, author=self.owner, title="Original")
        child_saved, archive_waiting_for_project = Event(), Event()

        def save_comment(**kwargs):
            comment = create_comment_resource(**kwargs)
            child_saved.set()
            if not archive_waiting_for_project.wait(timeout=10):
                raise AssertionError("Archive did not attempt its project lock")
            return comment

        def observe_archive_lock(execute, sql, params, many, context):
            if '"projects_project"' in sql and "FOR UPDATE" in sql:
                archive_waiting_for_project.set()
            return execute(sql, params, many, context)

        def archive():
            if not child_saved.wait(timeout=10):
                raise AssertionError("Comment was not saved")
            with connection.execute_wrapper(observe_archive_lock):
                return self.agent("archive_project", {
                    "project_id": self.project.pk, "expected_revision": 1,
                    "idempotency_key": "archive-during-child-commit",
                })

        with patch("agent_runtime.service.create_comment_resource", side_effect=save_comment):
            results = self.race([
                lambda: self.agent("add_request_comment", {
                    "issue_id": issue.pk, "body": "Committing comment",
                    "idempotency_key": "comment-before-archive-commit",
                }),
                archive,
            ])
        self.assertEqual(results, ["success", "success"])
        self.assertEqual(IssueComment.objects.count(), 1)
        self.project.refresh_from_db()
        self.assertIsNotNone(self.project.archived_at)
