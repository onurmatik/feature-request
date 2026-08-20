import json
from datetime import timedelta
from threading import Barrier, Lock, Thread
from unittest import skipUnless
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.db import IntegrityError, close_old_connections, connection, connections
from django.test import (
    Client,
    RequestFactory,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.utils import timezone

from .embed import (
    EmbedSubmissionError,
    email_fingerprint,
    token_digest,
    validate_turnstile,
)
from .models import (
    EmbeddedIssueSubmission,
    Issue,
    IssueComment,
    IssueDeliveryArtifact,
    IssueEvent,
    IssueUpvote,
    Project,
    ProjectSpec,
    IssueScopeAssessment,
    ProjectSpecChangeProposal,
)
from .services import (
    EmbedFeedbackEvaluation,
    ScopeEvaluation,
    evaluate_embed_feedback,
)


class IssueModelsTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="owner@example.com",
            handle="owner_user",
            password="test-pass-123",
        )
        self.other_user = user_model.objects.create_user(
            email="other@example.com",
            handle="other_user",
            password="test-pass-123",
        )
        self.project = Project.objects.create(
            owner=self.owner,
            name="Roadmap",
            slug="roadmap",
        )

    def test_issue_defaults(self):
        issue = Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Dark mode support",
        )

        self.assertEqual(issue.issue_type, Issue.Type.FEATURE)
        self.assertEqual(issue.status, Issue.Status.OPEN)
        self.assertEqual(issue.priority, Issue.Priority.MEDIUM)

    def test_upvote_is_unique_per_issue_and_user(self):
        issue = Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Crash on login",
            issue_type=Issue.Type.BUG,
        )
        IssueUpvote.objects.create(issue=issue, user=self.other_user)

        with self.assertRaises(IntegrityError):
            IssueUpvote.objects.create(issue=issue, user=self.other_user)

    def test_issue_can_have_comments(self):
        issue = Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Keyboard shortcut support",
        )

        IssueComment.objects.create(
            issue=issue,
            author=self.other_user,
            body="This would be super useful for power users.",
        )

        self.assertEqual(issue.comments.count(), 1)


@override_settings(OPENAI_API_KEY="")
class IssueApiTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="owner2@example.com",
            handle="owner_two",
            password="test-pass-123",
        )
        self.other_user = user_model.objects.create_user(
            email="other2@example.com",
            handle="other_two",
            password="test-pass-123",
        )
        self.project = Project.objects.create(
            owner=self.owner,
            name="Public Board",
            slug="public-board",
        )
        self.secondary_project = Project.objects.create(
            owner=self.owner,
            name="Secondary Board",
            slug="secondary-board",
        )
        self.issue = Issue.objects.create(
            project=self.project,
            author=self.owner,
            issue_type=Issue.Type.FEATURE,
            title="Add roadmap voting",
            description="Allow users to vote on roadmap items.",
            priority=Issue.Priority.MEDIUM,
        )
        self.secondary_issue = Issue.objects.create(
            project=self.secondary_project,
            author=self.owner,
            issue_type=Issue.Type.BUG,
            title="Secondary project issue",
            description="Visible issue",
            priority=Issue.Priority.HIGH,
        )

    def test_create_issue_requires_auth(self):
        response = self.client.post(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
            data=json.dumps(
                {
                    "issue_type": "bug",
                    "title": "Mobile crash",
                    "description": "Crashes on iOS 18",
                    "priority": 3,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_create_issue_rejects_blank_title(self):
        self.client.force_login(self.other_user)
        response = self.client.post(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
            data=json.dumps(
                {
                    "issue_type": "feature",
                    "title": "   ",
                    "description": "Details",
                    "priority": 2,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("projects.api.send_mail")
    def test_create_issue_notifies_owner_when_created_by_visitor(self, mock_send_mail):
        self.client.force_login(self.other_user)
        response = self.client.post(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
            data=json.dumps(
                {
                    "issue_type": "feature",
                    "title": "Add two factor auth",
                    "description": "Support optional 2FA for critical actions.",
                    "priority": 2,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        mock_send_mail.assert_called_once()
        self.assertEqual(mock_send_mail.call_args.args[3], [self.owner.email])

    @patch("projects.api.send_mail")
    def test_create_issue_notifies_owner_when_created_by_owner(self, mock_send_mail):
        self.client.force_login(self.owner)
        response = self.client.post(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
            data=json.dumps(
                {
                    "issue_type": "bug",
                    "title": "Internal follow up request",
                    "description": "Owner is posting for triage.",
                    "priority": 1,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        mock_send_mail.assert_not_called()

    def test_create_comment_requires_auth(self):
        response = self.client.post(
            f"/api/issues/{self.issue.id}/comments",
            data=json.dumps({"body": "Please prioritize this for next sprint."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(IssueComment.objects.count(), 0)

    def test_create_and_list_issue(self):
        self.client.force_login(self.other_user)
        create_response = self.client.post(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
            data=json.dumps(
                {
                    "issue_type": "bug",
                    "title": "Search does not work",
                    "description": "No results are returned.",
                    "priority": 3,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(create_response.status_code, 201)
        payload = create_response.json()
        self.assertEqual(payload["issue_type"], "bug")
        self.assertEqual(payload["priority"], 3)

        list_response = self.client.get(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
            {"issue_type": "bug"},
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

    def test_active_status_filter_excludes_done_and_closed_issues(self):
        expected_active_titles = {
            self.issue.title,
            "Planned request",
            "Request in progress",
        }
        Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Planned request",
            status=Issue.Status.PLANNED,
        )
        Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Request in progress",
            status=Issue.Status.IN_PROGRESS,
        )
        Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Completed request",
            status=Issue.Status.DONE,
        )
        Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Closed request",
            status=Issue.Status.CLOSED,
        )

        project_response = self.client.get(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
            {"status": "active"},
        )
        owner_response = self.client.get(
            f"/api/owners/{self.owner.handle}/issues",
            {"project_slug": self.project.slug, "status": "active"},
        )

        self.assertEqual(project_response.status_code, 200)
        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(
            {item["title"] for item in project_response.json()},
            expected_active_titles,
        )
        self.assertEqual(
            {item["title"] for item in owner_response.json()},
            expected_active_titles,
        )

    def test_active_filter_value_cannot_be_saved_as_issue_status(self):
        self.client.force_login(self.owner)

        response = self.client.patch(
            f"/api/issues/{self.issue.id}",
            data=json.dumps({"status": "active"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.issue.refresh_from_db()
        self.assertEqual(self.issue.status, Issue.Status.OPEN)

    def test_issue_lists_support_bounded_limit(self):
        Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Another request for limit testing",
        )

        project_response = self.client.get(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
            {"limit": 1},
        )
        owner_response = self.client.get(
            f"/api/owners/{self.owner.handle}/issues",
            {"project_slug": self.project.slug, "limit": 1},
        )
        invalid_response = self.client.get(
            f"/api/owners/{self.owner.handle}/issues",
            {"limit": 101},
        )

        self.assertEqual(project_response.status_code, 200)
        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(len(project_response.json()), 1)
        self.assertEqual(len(owner_response.json()), 1)
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(
            invalid_response.json()["detail"],
            "limit must be between 1 and 100.",
        )

    @override_settings(OPENAI_API_KEY="test-openai-key")
    def test_create_issue_rejects_irrelevant_content_with_moderation(self):
        self.client.force_login(self.other_user)
        mocked_client = Mock()
        mocked_client.responses.create.return_value = Mock(output_text="REJECT: spam content")

        with patch("projects.api.OpenAI", return_value=mocked_client):
            response = self.client.post(
                f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
                data=json.dumps(
                    {
                        "issue_type": "feature",
                        "title": "Buy followers now",
                        "description": "Click this random link and join my channel",
                        "priority": 2,
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Issue rejected by moderation: spam content")
        self.assertFalse(Issue.objects.filter(title="Buy followers now").exists())

    @override_settings(OPENAI_API_KEY="test-openai-key")
    def test_create_issue_accepts_valid_content_with_moderation(self):
        self.client.force_login(self.other_user)
        mocked_client = Mock()
        mocked_client.responses.create.return_value = Mock(output_text="ALLOW")

        with patch("projects.api.OpenAI", return_value=mocked_client):
            response = self.client.post(
                f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
                data=json.dumps(
                    {
                        "issue_type": "bug",
                        "title": "Signup fails on Safari",
                        "description": "The signup form returns 500 only on Safari 18.",
                        "priority": 3,
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 201)

    def test_all_projects_are_readable(self):
        list_response = self.client.get(
            f"/api/projects/{self.owner.handle}/{self.secondary_project.slug}/issues"
        )
        self.assertEqual(list_response.status_code, 200)

        detail_response = self.client.get(f"/api/issues/{self.secondary_issue.id}")
        self.assertEqual(detail_response.status_code, 200)

    def test_issue_update_permissions_and_priority(self):
        self.client.force_login(self.other_user)
        forbidden_response = self.client.patch(
            f"/api/issues/{self.issue.id}",
            data=json.dumps({"priority": 4}),
            content_type="application/json",
        )
        self.assertEqual(forbidden_response.status_code, 403)

        self.client.force_login(self.owner)
        update_response = self.client.patch(
            f"/api/issues/{self.issue.id}",
            data=json.dumps({"priority": 4, "status": "planned"}),
            content_type="application/json",
        )
        self.assertEqual(update_response.status_code, 200)

        updated_payload = update_response.json()
        self.assertEqual(updated_payload["priority"], 4)
        self.assertEqual(updated_payload["status"], "planned")

    def test_issue_author_and_owner_can_update_title_and_description(self):
        visitor_issue = Issue.objects.create(
            project=self.project,
            author=self.other_user,
            title="Original visitor title",
            description="Original visitor description",
        )

        self.client.force_login(self.other_user)
        author_response = self.client.patch(
            f"/api/issues/{visitor_issue.id}",
            data=json.dumps(
                {
                    "title": " Updated visitor title ",
                    "description": " Updated visitor description ",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(author_response.status_code, 200)
        author_payload = author_response.json()
        self.assertEqual(author_payload["title"], "Updated visitor title")
        self.assertEqual(author_payload["description"], "Updated visitor description")

        blank_response = self.client.patch(
            f"/api/issues/{visitor_issue.id}",
            data=json.dumps({"title": "   "}),
            content_type="application/json",
        )
        self.assertEqual(blank_response.status_code, 400)

        self.client.force_login(self.owner)
        owner_response = self.client.patch(
            f"/api/issues/{visitor_issue.id}",
            data=json.dumps({"description": "Owner clarified the request."}),
            content_type="application/json",
        )
        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(
            owner_response.json()["description"],
            "Owner clarified the request.",
        )

    def test_toggle_upvote(self):
        self.client.force_login(self.other_user)
        first = self.client.post(f"/api/issues/{self.issue.id}/upvote/toggle")
        second = self.client.post(f"/api/issues/{self.issue.id}/upvote/toggle")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.json()["upvoted"])
        self.assertFalse(second.json()["upvoted"])

    def test_create_and_list_comments(self):
        self.client.force_login(self.other_user)
        create_response = self.client.post(
            f"/api/issues/{self.issue.id}/comments",
            data=json.dumps({"body": "Please prioritize this for next sprint."}),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)

        list_response = self.client.get(f"/api/issues/{self.issue.id}/comments")
        self.assertEqual(list_response.status_code, 200)
        comments = list_response.json()
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["author_handle"], self.other_user.handle)

    def test_update_comment_requires_auth_and_permissions(self):
        comment = IssueComment.objects.create(
            issue=self.issue,
            author=self.other_user,
            body="Original visitor comment.",
        )

        unauthenticated_response = self.client.patch(
            f"/api/issues/{self.issue.id}/comments/{comment.id}",
            data=json.dumps({"body": "Unauthenticated edit."}),
            content_type="application/json",
        )
        self.assertEqual(unauthenticated_response.status_code, 401)

        self.client.force_login(self.other_user)
        author_response = self.client.patch(
            f"/api/issues/{self.issue.id}/comments/{comment.id}",
            data=json.dumps({"body": " Updated by the author. "}),
            content_type="application/json",
        )
        self.assertEqual(author_response.status_code, 200)
        self.assertEqual(author_response.json()["body"], "Updated by the author.")

        blank_response = self.client.patch(
            f"/api/issues/{self.issue.id}/comments/{comment.id}",
            data=json.dumps({"body": "   "}),
            content_type="application/json",
        )
        self.assertEqual(blank_response.status_code, 400)

        self.client.force_login(self.owner)
        owner_response = self.client.patch(
            f"/api/issues/{self.issue.id}/comments/{comment.id}",
            data=json.dumps({"body": "Owner clarified this comment."}),
            content_type="application/json",
        )
        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(owner_response.json()["body"], "Owner clarified this comment.")

        owner_comment = IssueComment.objects.create(
            issue=self.issue,
            author=self.owner,
            body="Owner-only note.",
        )
        self.client.force_login(self.other_user)
        forbidden_response = self.client.patch(
            f"/api/issues/{self.issue.id}/comments/{owner_comment.id}",
            data=json.dumps({"body": "Visitor should not edit this."}),
            content_type="application/json",
        )
        self.assertEqual(forbidden_response.status_code, 403)

        secondary_comment = IssueComment.objects.create(
            issue=self.secondary_issue,
            author=self.other_user,
            body="Secondary project comment.",
        )
        mismatch_response = self.client.patch(
            f"/api/issues/{self.issue.id}/comments/{secondary_comment.id}",
            data=json.dumps({"body": "Wrong issue path."}),
            content_type="application/json",
        )
        self.assertEqual(mismatch_response.status_code, 404)

    @override_settings(OPENAI_API_KEY="test-openai-key")
    def test_create_comment_rejects_spam(self):
        self.client.force_login(self.other_user)
        mocked_client = Mock()
        mocked_client.responses.create.return_value = Mock(output_text="REJECT: spam")

        with patch("projects.api.OpenAI", return_value=mocked_client):
            response = self.client.post(
                f"/api/issues/{self.issue.id}/comments",
                data=json.dumps({"body": "Buy followers and unlock premium now."}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Comment rejected by moderation: spam",
        )

    @patch("projects.api.send_mail")
    def test_create_comment_notifies_owner_when_created_by_visitor(self, mock_send_mail):
        self.client.force_login(self.other_user)
        response = self.client.post(
            f"/api/issues/{self.issue.id}/comments",
            data=json.dumps({"body": "Can we also add audit log support for admins?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        mock_send_mail.assert_called_once()
        self.assertEqual(mock_send_mail.call_args.args[3], [self.owner.email])

    @patch("projects.api.send_mail")
    def test_create_comment_notifies_owner_when_created_by_owner(self, mock_send_mail):
        self.client.force_login(self.owner)
        response = self.client.post(
            f"/api/issues/{self.issue.id}/comments",
            data=json.dumps({"body": "I will take this item in next sprint."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        mock_send_mail.assert_not_called()

    @override_settings(OPENAI_API_KEY="test-openai-key")
    def test_create_comment_allows_valid_comment(self):
        self.client.force_login(self.other_user)
        mocked_client = Mock()
        mocked_client.responses.create.return_value = Mock(output_text="ALLOW")

        with patch("projects.api.OpenAI", return_value=mocked_client):
            response = self.client.post(
                f"/api/issues/{self.issue.id}/comments",
                data=json.dumps({"body": "Can we add keyboard shortcut support too?"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 201)

    def test_list_owner_projects_returns_all_projects(self):
        public_response = self.client.get(f"/api/owners/{self.owner.handle}/projects")
        self.assertEqual(public_response.status_code, 200)
        public_payload = public_response.json()
        self.assertEqual(len(public_payload), 2)
        self.assertIn(self.project.slug, [item["slug"] for item in public_payload])
        self.assertIn(self.secondary_project.slug, [item["slug"] for item in public_payload])

        self.client.force_login(self.owner)
        owner_response = self.client.get(f"/api/owners/{self.owner.handle}/projects")
        self.assertEqual(owner_response.status_code, 200)
        owner_payload = owner_response.json()
        self.assertEqual(len(owner_payload), 2)

    def test_project_responses_include_open_issue_count(self):
        Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Second open issue",
        )
        Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Planned issue",
            status=Issue.Status.PLANNED,
        )
        Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Closed issue",
            status=Issue.Status.CLOSED,
        )

        public_response = self.client.get(f"/api/owners/{self.owner.handle}/projects")
        self.assertEqual(public_response.status_code, 200)
        public_project = next(
            item for item in public_response.json() if item["id"] == self.project.id
        )
        self.assertEqual(public_project["open_issues_count"], 2)

        self.client.force_login(self.owner)
        owner_response = self.client.get("/api/projects")
        self.assertEqual(owner_response.status_code, 200)
        owner_project = next(
            item for item in owner_response.json() if item["id"] == self.project.id
        )
        self.assertEqual(owner_project["open_issues_count"], 2)

        detail_response = self.client.get(f"/api/projects/{self.project.id}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["open_issues_count"], 2)

        update_response = self.client.patch(
            f"/api/projects/{self.project.id}",
            data=json.dumps({"tagline": "Updated tagline"}),
            content_type="application/json",
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["open_issues_count"], 2)

    def test_list_owner_interacted_projects_is_public_and_ordered(self):
        user_model = get_user_model()
        external_owner = user_model.objects.create_user(
            email="external-owner@example.com",
            handle="external_owner",
            password="test-pass-123",
        )
        second_external_owner = user_model.objects.create_user(
            email="second-external-owner@example.com",
            handle="second_external",
            password="test-pass-123",
        )
        authored_project = Project.objects.create(
            owner=external_owner,
            name="Authored External",
            slug="authored-external",
        )
        comment_project = Project.objects.create(
            owner=external_owner,
            name="Comment External",
            slug="comment-external",
        )
        upvote_project = Project.objects.create(
            owner=second_external_owner,
            name="Upvote External",
            slug="upvote-external",
        )

        Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Owned project interaction should be excluded",
        )
        authored_issue = Issue.objects.create(
            project=authored_project,
            author=self.owner,
            title="Issue on someone else's project",
        )
        comment_issue = Issue.objects.create(
            project=comment_project,
            author=external_owner,
            title="Comment target",
        )
        closed_comment_issue = Issue.objects.create(
            project=comment_project,
            author=external_owner,
            title="Closed comment target",
            status=Issue.Status.CLOSED,
        )
        comment = IssueComment.objects.create(
            issue=comment_issue,
            author=self.owner,
            body="Recent useful comment.",
        )
        older_comment = IssueComment.objects.create(
            issue=closed_comment_issue,
            author=self.owner,
            body="Older comment on same project.",
        )
        upvote_issue = Issue.objects.create(
            project=upvote_project,
            author=second_external_owner,
            title="Upvote target",
        )
        upvote = IssueUpvote.objects.create(issue=upvote_issue, user=self.owner)

        base_time = timezone.now()
        Issue.objects.filter(pk=authored_issue.pk).update(
            created_at=base_time - timedelta(days=3)
        )
        IssueComment.objects.filter(pk=comment.pk).update(
            created_at=base_time - timedelta(hours=1)
        )
        IssueComment.objects.filter(pk=older_comment.pk).update(
            created_at=base_time - timedelta(days=5)
        )
        IssueUpvote.objects.filter(pk=upvote.pk).update(
            created_at=base_time - timedelta(days=2)
        )

        response = self.client.get(
            f"/api/owners/{self.owner.handle}/interacted-projects"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["slug"] for item in payload],
            [comment_project.slug, upvote_project.slug, authored_project.slug],
        )
        self.assertNotIn(self.project.slug, [item["slug"] for item in payload])
        self.assertEqual(len(payload), 3)

        comment_payload = next(
            item for item in payload if item["slug"] == comment_project.slug
        )
        self.assertEqual(comment_payload["owner_handle"], external_owner.handle)
        self.assertEqual(comment_payload["open_issues_count"], 1)

    def test_featured_projects_lists_all_projects(self):
        second_public = Project.objects.create(
            owner=self.owner,
            name="Popular Roadmap",
            slug="popular-roadmap",
        )
        Issue.objects.create(
            project=second_public,
            author=self.owner,
            title="Top request one",
        )
        Issue.objects.create(
            project=second_public,
            author=self.other_user,
            title="Top request two",
        )

        response = self.client.get("/api/public/featured-projects", {"limit": 3})
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(len(payload), 3)
        self.assertEqual(payload[0]["slug"], second_public.slug)
        self.assertEqual(payload[0]["owner_handle"], self.owner.handle)
        self.assertEqual(payload[0]["issues_count"], 2)
        self.assertIn(self.secondary_project.slug, [item["slug"] for item in payload])

    def test_list_owner_issues_supports_project_filter(self):
        Issue.objects.create(
            project=self.project,
            author=self.other_user,
            title="Another public issue",
        )

        public_all = self.client.get(f"/api/owners/{self.owner.handle}/issues")
        self.assertEqual(public_all.status_code, 200)
        self.assertEqual(len(public_all.json()), 3)

        public_specific = self.client.get(
            f"/api/owners/{self.owner.handle}/issues",
            {"project_slug": self.project.slug},
        )
        self.assertEqual(public_specific.status_code, 200)
        self.assertEqual(len(public_specific.json()), 2)

        public_secondary = self.client.get(
            f"/api/owners/{self.owner.handle}/issues",
            {"project_slug": self.secondary_project.slug},
        )
        self.assertEqual(public_secondary.status_code, 200)
        self.assertEqual(len(public_secondary.json()), 1)

        self.client.force_login(self.owner)
        owner_all = self.client.get(f"/api/owners/{self.owner.handle}/issues")
        self.assertEqual(owner_all.status_code, 200)
        self.assertEqual(len(owner_all.json()), 3)


class FaviconResolutionTest(TestCase):
    def test_resolver_skips_zero_length_favicon_candidate(self):
        from .api import _resolve_favicon_url_with_debug

        def fetch_headers(url, debug=None):
            if url == "https://example.com/favicon.ico":
                return {"Content-Type": "image/x-icon", "Content-Length": "0"}
            if url == "https://example.com/favicon.png":
                return {"Content-Type": "image/png", "Content-Length": "50801"}
            return None

        with (
            patch("projects.api._extract_project_favicon_url") as extract_favicons,
            patch("projects.api._fetch_url_headers", side_effect=fetch_headers) as fetch,
        ):
            extract_favicons.return_value = ["/favicon.ico", "/favicon.png"]

            favicon_url, debug = _resolve_favicon_url_with_debug("https://example.com")

        self.assertEqual(favicon_url, "https://example.com/favicon.png")
        self.assertIn(
            "Rejected empty favicon response for candidate: https://example.com/favicon.ico",
            debug,
        )
        self.assertEqual(fetch.call_count, 2)


class ProjectApiTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="owner-ui@example.com",
            handle="owner_ui",
            password="test-pass-123",
            subscription_tier="pro_30",
            subscription_status="active",
        )
        self.other_user = user_model.objects.create_user(
            email="other-ui@example.com",
            handle="other_ui",
            password="test-pass-123",
        )
        self.project = Project.objects.create(
            owner=self.owner,
            name="Secret Board",
            slug="secret-board",
        )

    def test_list_my_projects_requires_auth(self):
        response = self.client.get("/api/projects")
        self.assertEqual(response.status_code, 401)

    def test_owner_can_create_update_and_delete_project(self):
        self.client.force_login(self.owner)

        with patch("projects.api._resolve_favicon_url_with_debug") as resolve_favicon:
            resolve_favicon.side_effect = [
                ("https://example.com/platform/favicon.ico", ["ok"]),
                ("https://example.com/platform-v2/favicon.ico", ["ok"]),
            ]

            create_response = self.client.post(
                "/api/projects",
                data=json.dumps(
                    {
                        "name": "Platform Revamp",
                        "tagline": "Major overhaul",
                        "url": "https://example.com/platform",
                    }
                ),
                content_type="application/json",
            )
            self.assertEqual(create_response.status_code, 201)
            created = create_response.json()
            self.assertEqual(created["slug"], "platform-revamp")
            self.assertEqual(created["url"], "https://example.com/platform")
            self.assertEqual(created["favicon_url"], "https://example.com/platform/favicon.ico")
            self.assertEqual(resolve_favicon.call_count, 1)
            resolve_favicon.assert_any_call("https://example.com/platform")

            list_response = self.client.get("/api/projects")
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(len(list_response.json()), 2)

            edit_response = self.client.patch(
                f"/api/projects/{created['id']}",
                data=json.dumps(
                    {
                        "name": "Platform Revamp V2",
                        "tagline": "Updated scope",
                        "url": "https://example.com/platform-v2",
                    }
                ),
                content_type="application/json",
            )
            self.assertEqual(edit_response.status_code, 200)
            project = Project.objects.get(id=created["id"])
            project.refresh_from_db()
            self.assertEqual(project.name, "Platform Revamp V2")
            self.assertEqual(project.slug, "platform-revamp-v2")
            self.assertEqual(project.url, "https://example.com/platform-v2")
            self.assertEqual(project.favicon_url, "https://example.com/platform-v2/favicon.ico")
            self.assertEqual(resolve_favicon.call_count, 2)
            resolve_favicon.assert_any_call("https://example.com/platform-v2")

            delete_response = self.client.delete(f"/api/projects/{created['id']}")
            self.assertEqual(delete_response.status_code, 204)
            self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_favicon_is_resolved_when_missing_on_project_update(self):
        self.client.force_login(self.owner)

        with patch("projects.api._resolve_favicon_url_with_debug") as resolve_favicon:
            resolve_favicon.side_effect = [
                ("", ["none"]),
                ("https://example.com/project/favicon.ico", ["ok"]),
            ]

            create_response = self.client.post(
                "/api/projects",
                data=json.dumps(
                    {
                        "name": "No Favicon Board",
                        "tagline": "Initial",
                        "url": "https://example.com/project",
                    }
                ),
                content_type="application/json",
            )
            self.assertEqual(create_response.status_code, 201)
            created = create_response.json()
            self.assertEqual(created["favicon_url"], "")

            edit_response = self.client.patch(
                f"/api/projects/{created['id']}",
                data=json.dumps({"tagline": "Still no explicit URL update"}),
                content_type="application/json",
            )
            self.assertEqual(edit_response.status_code, 200)

            project = Project.objects.get(id=created["id"])
            self.assertEqual(project.favicon_url, "https://example.com/project/favicon.ico")
            self.assertEqual(resolve_favicon.call_count, 2)
            resolve_favicon.assert_any_call("https://example.com/project")

    def test_create_project_normalizes_scheme_less_url(self):
        self.client.force_login(self.owner)

        with patch("projects.api._resolve_favicon_url_with_debug") as resolve_favicon:
            resolve_favicon.return_value = ("https://featurerequest.io/list-todo.svg", ["ok"])

            create_response = self.client.post(
                "/api/projects",
                data=json.dumps(
                    {
                        "name": "FeatureRequest",
                        "url": "featurerequest.io",
                    }
                ),
                content_type="application/json",
            )

            self.assertEqual(create_response.status_code, 201)
            created = create_response.json()
            self.assertEqual(created["url"], "https://featurerequest.io")
            self.assertEqual(created["favicon_url"], "https://featurerequest.io/list-todo.svg")
            resolve_favicon.assert_called_once_with("https://featurerequest.io")

    def test_admin_refresh_updates_stale_favicon_when_new_candidate_exists(self):
        from .admin import refresh_project_favicons

        self.project.url = "https://example.com"
        self.project.favicon_url = "https://example.com/favicon.ico"
        self.project.save(update_fields=["url", "favicon_url"])

        modeladmin = Mock()
        with patch("projects.admin._resolve_favicon_url_with_debug") as resolve_favicon:
            resolve_favicon.return_value = ("https://example.com/favicon.png", ["ok"])

            refresh_project_favicons(modeladmin, Mock(), Project.objects.filter(pk=self.project.pk))

        self.project.refresh_from_db()
        self.assertEqual(self.project.favicon_url, "https://example.com/favicon.png")
        resolve_favicon.assert_called_once_with("https://example.com")

    def test_admin_refresh_clears_stale_favicon_when_no_candidate_exists(self):
        from .admin import refresh_project_favicons

        self.project.url = "example.com"
        self.project.favicon_url = "https://example.com/favicon.ico"
        self.project.save(update_fields=["url", "favicon_url"])

        modeladmin = Mock()
        with patch("projects.admin._resolve_favicon_url_with_debug") as resolve_favicon:
            resolve_favicon.return_value = ("", ["none"])

            refresh_project_favicons(modeladmin, Mock(), Project.objects.filter(pk=self.project.pk))

        self.project.refresh_from_db()
        self.assertEqual(self.project.url, "https://example.com")
        self.assertEqual(self.project.favicon_url, "")
        resolve_favicon.assert_called_once_with("https://example.com")

    def test_auto_slug_is_unique_per_owner(self):
        self.client.force_login(self.owner)

        first = self.client.post(
            "/api/projects",
            data=json.dumps({"name": "Roadmap", "tagline": "One"}),
            content_type="application/json",
        )
        second = self.client.post(
            "/api/projects",
            data=json.dumps({"name": "Roadmap", "tagline": "Two"}),
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["slug"], "roadmap")
        self.assertEqual(second.json()["slug"], "roadmap-2")

    def test_non_owner_cannot_update_or_delete_project(self):
        self.client.force_login(self.other_user)
        edit_response = self.client.patch(
            f"/api/projects/{self.project.pk}",
            data=json.dumps({"name": "Updated"}),
            content_type="application/json",
        )
        delete_response = self.client.delete(f"/api/projects/{self.project.pk}")
        self.assertEqual(edit_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)


@override_settings(
    OPENAI_API_KEY="",
    TURNSTILE_SITEKEY="test-site-key",
    TURNSTILE_SECRETKEY="test-secret-key",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class EmbedWidgetTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="owner@example.com",
            handle="widget_owner",
            display_name="Widget Owner",
            password="test-pass-123",
        )
        self.project = Project.objects.create(
            owner=self.owner,
            name="Widget Project",
            slug="widget-project",
        )

    @property
    def embed_url(self):
        return f"/embed/{self.owner.handle}/{self.project.slug}/"

    @property
    def submission_url(self):
        return (
            f"/api/embed/projects/{self.owner.handle}/{self.project.slug}/submissions"
        )

    def payload(self, **overrides):
        payload = {
            "feedback": "The compact layout is difficult to use on smaller screens.",
            "submission_id": str(uuid4()),
            "turnstile_token": "turnstile-response",
        }
        payload.update(overrides)
        return payload

    def make_pending(self, *, email="visitor@example.com", expires_at=None):
        raw_token = f"verify-token-{EmbeddedIssueSubmission.objects.count() + 1}"
        submission = EmbeddedIssueSubmission.objects.create(
            project=self.project,
            display_name="Visitor Name",
            email=email,
            submitter_fingerprint=email_fingerprint(email),
            issue_type=Issue.Type.BUG,
            title="A verified browser issue",
            description="Steps to reproduce the problem.",
            token_hash=token_digest(raw_token),
            expires_at=expires_at or timezone.now() + timedelta(minutes=30),
        )
        return raw_token, submission

    def post_submission(self, payload=None):
        return self.client.post(
            self.submission_url,
            data=json.dumps(payload or self.payload()),
            content_type="application/json",
        )

    def test_embed_route_is_frameable_and_preview_disables_submission(self):
        response = self.client.get(f"{self.embed_url}?preview=1&accent=%23FF00AA")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("X-Frame-Options", response.headers)
        self.assertIn("frame-ancestors *", response["Content-Security-Policy"])
        self.assertContains(response, "Preview mode")
        self.assertContains(response, "disabled")
        self.assertNotContains(response, "challenges.cloudflare.com/turnstile")
        self.assertContains(response, "View requests")
        self.assertContains(response, "Send feedback")
        self.assertContains(
            response,
            "Anything here feel off, need fixing, or could be better?",
        )
        self.assertContains(response, 'name="feedback"', count=1)
        self.assertNotContains(response, 'name="email"')
        self.assertNotContains(response, 'name="title"')
        self.assertContains(response, "--fr-accent: #FF00AA")

    def test_embed_route_returns_404_for_unknown_project(self):
        response = self.client.get("/embed/nobody/missing/")
        self.assertEqual(response.status_code, 404)

    def test_embed_turnstile_only_appears_when_interaction_is_required(self):
        response = self.client.get(self.embed_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-appearance="interaction-only"')

    def test_embed_form_hidden_state_overrides_grid_layout(self):
        stylesheet_path = finders.find("projects/embed-widget.css")
        with open(stylesheet_path, encoding="utf-8") as stylesheet:
            css = stylesheet.read()

        self.assertIn(".fr-form[hidden] { display: none; }", css)

    def test_embed_metadata_is_safely_escaped(self):
        embed_url = self.embed_url
        self.project.name = '<script>alert("x")</script>'
        self.project.save(update_fields=["name"])

        response = self.client.get(embed_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;")

    def test_submission_returns_404_for_unknown_project(self):
        response = self.client.post(
            "/api/embed/projects/nobody/missing/submissions",
            data=json.dumps(self.payload()),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    @patch("projects.api._notify_owner_on_new_issue")
    @patch("projects.api.validate_turnstile")
    def test_submission_creates_anonymous_issue_and_returns_link(
        self, validate_turnstile, notify_owner
    ):
        payload = self.payload()
        response = self.post_submission(payload)

        self.assertEqual(response.status_code, 201)
        response_payload = response.json()
        issue = Issue.objects.get()
        self.assertEqual(response_payload["status"], "created")
        self.assertEqual(response_payload["issue_id"], issue.id)
        self.assertEqual(
            response_payload["issue_url"],
            f"http://testserver/{self.owner.handle}/{self.project.slug}/issues/{issue.id}/",
        )
        validate_turnstile.assert_called_once()
        self.assertEqual(issue.description, payload["feedback"])
        self.assertEqual(issue.title, payload["feedback"])
        self.assertEqual(issue.issue_type, Issue.Type.FEATURE)
        self.assertEqual(issue.priority, Issue.Priority.MEDIUM)
        self.assertEqual(issue.author.display_name, "Website visitor")
        self.assertTrue(issue.author.handle.startswith("visitor_"))
        self.assertTrue(issue.author.email.endswith("@anonymous.featurerequest.invalid"))
        self.assertFalse(issue.author.has_usable_password())
        self.assertNotIn("_auth_user_id", self.client.session)
        receipt = EmbeddedIssueSubmission.objects.get()
        self.assertEqual(str(receipt.client_submission_id), payload["submission_id"])
        self.assertEqual(receipt.issue, issue)
        self.assertEqual(receipt.email, "")
        self.assertEqual(receipt.title, "")
        self.assertIsNotNone(receipt.verified_at)
        notify_owner.assert_called_once_with(
            response.wsgi_request,
            issue,
            issue.author,
            include_actor_email=False,
        )

    @patch("projects.api.send_mail", return_value=1)
    @patch("projects.api.validate_turnstile")
    def test_owner_notification_hides_anonymous_internal_email(
        self, validate_turnstile, send_mail
    ):
        response = self.post_submission()

        self.assertEqual(response.status_code, 201)
        plain_text = send_mail.call_args.args[1]
        self.assertIn("Website visitor posted a new request", plain_text)
        self.assertNotIn("anonymous.featurerequest.invalid", plain_text)

    @patch("projects.api.validate_turnstile")
    def test_short_feedback_is_rejected_before_turnstile(self, validate_turnstile):
        response = self.post_submission(self.payload(feedback="x" * 19))

        self.assertEqual(response.status_code, 400)
        validate_turnstile.assert_not_called()
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)
        self.assertEqual(Issue.objects.count(), 0)

    @patch("projects.api.validate_turnstile")
    def test_whitespace_feedback_is_rejected_before_turnstile(self, validate_turnstile):
        response = self.post_submission(self.payload(feedback="   "))

        self.assertEqual(response.status_code, 400)
        validate_turnstile.assert_not_called()
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)

    @patch("projects.api.validate_turnstile")
    def test_feedback_over_maximum_is_rejected_before_turnstile(self, validate_turnstile):
        response = self.post_submission(self.payload(feedback="x" * 5001))

        self.assertEqual(response.status_code, 400)
        validate_turnstile.assert_not_called()
        self.assertEqual(Issue.objects.count(), 0)

    @patch("projects.api.validate_turnstile")
    def test_turnstile_failure_is_returned_without_issue(
        self, validate_turnstile
    ):
        validate_turnstile.side_effect = EmbedSubmissionError(
            400, "Human verification failed."
        )

        response = self.post_submission()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)
        self.assertEqual(Issue.objects.count(), 0)

    @override_settings(OPENAI_API_KEY="test-openai-key")
    @patch("projects.api.validate_turnstile")
    def test_moderation_rejection_does_not_create_issue(self, validate_turnstile):
        mocked_client = Mock()
        mocked_client.responses.create.return_value = Mock(output_text="REJECT: spam")

        with patch("projects.api.OpenAI", return_value=mocked_client):
            response = self.post_submission()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Issue rejected by moderation: spam")
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)
        self.assertEqual(Issue.objects.count(), 0)

    @override_settings(OPENAI_API_KEY="test-openai-key")
    @patch("projects.api.validate_turnstile")
    def test_moderation_failure_returns_503_without_issue(self, validate_turnstile):
        mocked_client = Mock()
        mocked_client.responses.create.side_effect = RuntimeError("moderation timeout")

        with patch("projects.api.OpenAI", return_value=mocked_client):
            response = self.post_submission()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)
        self.assertEqual(Issue.objects.count(), 0)

    @patch("projects.api._notify_owner_on_new_issue")
    @patch("projects.api.evaluate_embed_feedback")
    @patch("projects.api.validate_turnstile")
    def test_ai_enrichment_sets_title_and_type_without_rewriting_feedback(
        self, validate_turnstile, evaluate, notify_owner
    ):
        evaluate.return_value = EmbedFeedbackEvaluation(
            title="Compact layout breaks on phones",
            issue_type=Issue.Type.BUG,
        )
        payload = self.payload()

        response = self.post_submission(payload)

        self.assertEqual(response.status_code, 201)
        issue = Issue.objects.get()
        self.assertEqual(issue.title, "Compact layout breaks on phones")
        self.assertEqual(issue.issue_type, Issue.Type.BUG)
        self.assertEqual(issue.description, payload["feedback"])
        evaluate.assert_called_once()
        notify_owner.assert_called_once()

    @override_settings(OPENAI_API_KEY="test-openai-key")
    def test_embed_feedback_evaluator_returns_structured_metadata(self):
        mocked_client = Mock()
        mocked_client.responses.create.return_value = Mock(
            output_text=json.dumps(
                {
                    "title": "Mobile filters do not open",
                    "issue_type": Issue.Type.BUG,
                }
            )
        )

        result = evaluate_embed_feedback(
            feedback="The filters do not open when I tap them on my phone.",
            spec=None,
            client_factory=Mock(return_value=mocked_client),
        )

        self.assertEqual(result.title, "Mobile filters do not open")
        self.assertEqual(result.issue_type, Issue.Type.BUG)
        self.assertIsNone(result.scope_evaluation)

    @override_settings(OPENAI_API_KEY="test-openai-key")
    def test_embed_feedback_evaluator_falls_back_on_invalid_output(self):
        spec = ProjectSpec.objects.create(
            project=self.project,
            content=ProjectSpecApiTest.SPEC,
        )
        mocked_client = Mock()
        mocked_client.responses.create.return_value = Mock(output_text="not-json")
        feedback = "Please add a much more compact mobile layout for this page."

        result = evaluate_embed_feedback(
            feedback=feedback,
            spec=spec,
            client_factory=Mock(return_value=mocked_client),
        )

        self.assertEqual(result.title, feedback)
        self.assertEqual(result.issue_type, Issue.Type.FEATURE)
        self.assertEqual(
            result.scope_evaluation.state,
            IssueScopeAssessment.State.FAILED,
        )
        self.assertEqual(result.scope_evaluation.error_code, "invalid_output")

    @patch("projects.api._notify_owner_on_new_issue")
    @patch("projects.api.validate_turnstile")
    def test_same_submission_id_is_idempotent(self, validate_turnstile, notify_owner):
        payload = self.payload()

        first = self.post_submission(payload)
        second = self.post_submission(payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Issue.objects.count(), 1)
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 1)
        validate_turnstile.assert_called_once()
        notify_owner.assert_called_once()

    @patch("projects.api._notify_owner_on_new_issue")
    @patch("projects.api.validate_turnstile")
    def test_reused_submission_id_with_different_feedback_conflicts(
        self, validate_turnstile, notify_owner
    ):
        payload = self.payload()
        first = self.post_submission(payload)
        changed = self.payload(
            submission_id=payload["submission_id"],
            feedback="A different feedback message that is long enough to submit.",
        )

        second = self.post_submission(changed)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(Issue.objects.count(), 1)
        validate_turnstile.assert_called_once()
        notify_owner.assert_called_once()

    @patch("projects.api._notify_owner_on_new_issue")
    @patch("projects.api.validate_turnstile")
    def test_submission_is_throttled_after_three_issues_per_hour(
        self, validate_turnstile, notify_owner
    ):
        responses = [self.post_submission() for _ in range(4)]

        self.assertEqual(
            [response.status_code for response in responses],
            [201, 201, 201, 429],
        )
        self.assertEqual(Issue.objects.count(), 3)
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 3)
        self.assertEqual(validate_turnstile.call_count, 4)
        self.assertEqual(notify_owner.call_count, 3)

    @patch("projects.api._notify_owner_on_new_issue")
    @patch("projects.api.evaluate_embed_feedback")
    @patch("projects.api.validate_turnstile")
    def test_direct_embed_records_scope_and_guarded_auto_decline(
        self, validate_turnstile, evaluate, notify_owner
    ):
        ProjectSpec.objects.create(
            project=self.project,
            content=ProjectSpecApiTest.SPEC,
            auto_decline_enabled=True,
        )
        evaluate.return_value = EmbedFeedbackEvaluation(
            title="Request private strategy consulting",
            issue_type=Issue.Type.FEATURE,
            scope_evaluation=ScopeEvaluation(
                state=IssueScopeAssessment.State.COMPLETED,
                verdict=IssueScopeAssessment.Verdict.OUT_OF_SCOPE,
                public_reason="This is an explicit non-goal.",
                out_of_scope_quote="Private strategy consulting.",
                contradicts_in_scope=False,
                requires_owner_judgment=False,
            ),
        )

        response = self.post_submission()

        self.assertEqual(response.status_code, 201)
        issue = Issue.objects.get()
        self.assertEqual(issue.status, Issue.Status.DECLINED)
        assessment = issue.scope_assessments.get()
        self.assertTrue(assessment.auto_declined)
        self.assertEqual(assessment.spec_revision, 1)
        notify_owner.assert_called_once()

    def test_verification_get_only_reviews_and_does_not_publish(self):
        raw_token, _submission = self.make_pending()

        response = self.client.get(f"/embed/submissions/{raw_token}/verify/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "strict-origin")
        self.assertContains(response, "Publish request")
        self.assertContains(response, "A verified browser issue")
        self.assertEqual(Issue.objects.count(), 0)

    @patch("projects.api._notify_owner_on_new_issue")
    def test_verification_form_posts_with_enforced_csrf_checks(self, notify_owner):
        raw_token, _submission = self.make_pending()
        verify_url = f"/embed/submissions/{raw_token}/verify/"
        csrf_client = Client(enforce_csrf_checks=True)

        get_response = csrf_client.get(verify_url, secure=True)
        csrf_token = get_response.cookies["csrftoken"].value
        post_response = csrf_client.post(
            verify_url,
            {"csrfmiddlewaretoken": csrf_token},
            secure=True,
            HTTP_ORIGIN="https://testserver",
        )

        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(Issue.objects.count(), 1)
        notify_owner.assert_called_once()

    @patch("projects.api._notify_owner_on_new_issue")
    def test_verification_reuses_existing_user_scrubs_pending_data_and_notifies_owner(
        self, notify_owner
    ):
        existing = get_user_model().objects.create_user(
            email="visitor@example.com",
            handle="known_visitor",
            display_name="Known Visitor",
            password="test-pass-123",
        )
        raw_token, submission = self.make_pending(email=existing.email)

        response = self.client.post(f"/embed/submissions/{raw_token}/verify/")

        issue = Issue.objects.get()
        submission.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"/{self.owner.handle}/{self.project.slug}/issues/{issue.id}/",
        )
        self.assertEqual(issue.author, existing)
        self.assertEqual(issue.status, Issue.Status.OPEN)
        self.assertEqual(issue.priority, Issue.Priority.MEDIUM)
        self.assertEqual(submission.issue, issue)
        self.assertEqual(submission.email, "")
        self.assertEqual(submission.display_name, "")
        self.assertEqual(submission.title, "")
        self.assertIsNotNone(submission.verified_at)
        self.assertEqual(int(self.client.session["_auth_user_id"]), existing.id)
        notify_owner.assert_called_once_with(response.wsgi_request, issue, existing)

    @patch("projects.api._notify_owner_on_new_issue")
    def test_verification_creates_lightweight_account_without_exposing_email_in_handle(
        self, notify_owner
    ):
        raw_token, _submission = self.make_pending(email="new.person@example.com")

        response = self.client.post(f"/embed/submissions/{raw_token}/verify/")

        issue = Issue.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(issue.author.email, "new.person@example.com")
        self.assertEqual(issue.author.display_name, "Visitor Name")
        self.assertTrue(issue.author.handle.startswith("guest_visitor_name_"))
        self.assertNotIn("new", issue.author.handle)
        self.assertFalse(issue.author.has_usable_password())
        notify_owner.assert_called_once()

    @patch("projects.api._notify_owner_on_new_issue")
    def test_double_verification_post_is_idempotent(self, notify_owner):
        raw_token, _submission = self.make_pending()
        verify_url = f"/embed/submissions/{raw_token}/verify/"

        first = self.client.post(verify_url)
        second = self.client.post(verify_url)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(first["Location"], second["Location"])
        self.assertEqual(Issue.objects.count(), 1)
        notify_owner.assert_called_once()

    @patch("projects.api._notify_owner_on_new_issue")
    @patch("projects.views.evaluate_request_scope")
    def test_verified_embed_uses_current_spec_revision_and_guarded_auto_decline(
        self, evaluate, notify_owner
    ):
        ProjectSpec.objects.create(
            project=self.project,
            content=ProjectSpecApiTest.SPEC,
            auto_decline_enabled=True,
        )
        evaluate.return_value = ScopeEvaluation(
            state=IssueScopeAssessment.State.COMPLETED,
            verdict=IssueScopeAssessment.Verdict.OUT_OF_SCOPE,
            public_reason="This is an explicit non-goal.",
            out_of_scope_quote="Private strategy consulting.",
            contradicts_in_scope=False,
            requires_owner_judgment=False,
        )
        raw_token, _submission = self.make_pending()

        response = self.client.post(f"/embed/submissions/{raw_token}/verify/")

        self.assertEqual(response.status_code, 302)
        issue = Issue.objects.get()
        self.assertEqual(issue.status, Issue.Status.DECLINED)
        assessment = issue.scope_assessments.get()
        self.assertEqual(assessment.spec_revision, 1)
        self.assertTrue(assessment.auto_declined)
        notify_owner.assert_called_once()

    def test_expired_and_invalid_verification_tokens_do_not_publish(self):
        raw_token, _submission = self.make_pending(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        expired = self.client.post(f"/embed/submissions/{raw_token}/verify/")
        invalid = self.client.get("/embed/submissions/not-a-token/verify/")

        self.assertEqual(expired.status_code, 410)
        self.assertEqual(invalid.status_code, 404)
        self.assertEqual(Issue.objects.count(), 0)

    def test_issue_response_includes_backward_compatible_author_display_name(self):
        author = get_user_model().objects.create_user(
            email="display@example.com",
            handle="display_handle",
            display_name="Display Name",
            password="test-pass-123",
        )
        issue = Issue.objects.create(
            project=self.project,
            author=author,
            title="Visible author name",
        )

        response = self.client.get(f"/api/issues/{issue.id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["author_id"], author.id)
        self.assertEqual(payload["author_handle"], author.handle)
        self.assertEqual(payload["author_display_name"], "Display Name")

    def test_turnstile_siteverify_accepts_matching_hostname_and_action(self):
        request = RequestFactory().post("/api/embed", HTTP_HOST="testserver")
        upstream = MagicMock()
        upstream.__enter__.return_value.read.return_value = json.dumps(
            {
                "success": True,
                "hostname": "testserver",
                "action": "embed_submission",
            }
        ).encode("utf-8")

        with patch("projects.embed.urlopen", return_value=upstream) as urlopen:
            validate_turnstile(request, "valid-token")

        urlopen.assert_called_once()
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 5)

    def test_turnstile_siteverify_rejects_wrong_action(self):
        request = RequestFactory().post("/api/embed", HTTP_HOST="testserver")
        upstream = MagicMock()
        upstream.__enter__.return_value.read.return_value = json.dumps(
            {
                "success": True,
                "hostname": "testserver",
                "action": "different_action",
            }
        ).encode("utf-8")

        with patch("projects.embed.urlopen", return_value=upstream):
            with self.assertRaises(EmbedSubmissionError) as caught:
                validate_turnstile(request, "valid-token")

        self.assertEqual(caught.exception.status_code, 400)

    def test_turnstile_siteverify_timeout_is_temporary_failure(self):
        request = RequestFactory().post("/api/embed", HTTP_HOST="testserver")

        with patch("projects.embed.urlopen", side_effect=TimeoutError):
            with self.assertRaises(EmbedSubmissionError) as caught:
                validate_turnstile(request, "valid-token")

        self.assertEqual(caught.exception.status_code, 503)


@skipUnless(
    connection.vendor == "postgresql",
    "PostgreSQL row-lock behavior is part of the production database gate.",
)
@override_settings(
    OPENAI_API_KEY="",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class EmbedVerificationPostgreSQLConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        owner = get_user_model().objects.create_user(
            email="pg-embed-owner@example.com",
            handle="pg_embed_owner",
        )
        self.project = Project.objects.create(
            owner=owner,
            name="PostgreSQL Embed Project",
            slug="postgresql-embed-project",
        )
        self.raw_token = "postgresql-concurrent-verify-token"
        self.submission = EmbeddedIssueSubmission.objects.create(
            project=self.project,
            display_name="Concurrent Visitor",
            email="pg-embed-visitor@example.com",
            submitter_fingerprint=email_fingerprint("pg-embed-visitor@example.com"),
            issue_type=Issue.Type.BUG,
            title="Concurrent verification",
            description="Publish this pending request exactly once.",
            token_hash=token_digest(self.raw_token),
            expires_at=timezone.now() + timedelta(minutes=30),
        )

    @patch("projects.api._notify_owner_on_new_issue")
    def test_concurrent_verification_posts_publish_exactly_one_issue(self, notify_owner):
        barrier = Barrier(2)
        outcome_lock = Lock()
        outcomes = []
        url = f"/embed/submissions/{self.raw_token}/verify/"

        def worker():
            close_old_connections()
            try:
                client = Client()
                barrier.wait(timeout=10)
                response = client.post(url)
                value = (response.status_code, response.get("Location", ""))
            except Exception as exc:
                value = exc
            finally:
                connections["default"].close()
            with outcome_lock:
                outcomes.append(value)

        threads = [Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(outcomes), 2)
        self.assertTrue(all(not isinstance(outcome, Exception) for outcome in outcomes))
        self.assertEqual([outcome[0] for outcome in outcomes], [302, 302])
        self.assertEqual(outcomes[0][1], outcomes[1][1])
        self.assertEqual(Issue.objects.filter(project=self.project).count(), 1)
        self.submission.refresh_from_db()
        self.assertIsNotNone(self.submission.issue_id)
        notify_owner.assert_called_once()


@override_settings(OPENAI_API_KEY="")
class RequestOperatingSystemApiTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="p1-owner@example.com",
            handle="p1_owner",
            password="test-pass-123",
            subscription_tier="pro_30",
            subscription_status="active",
        )
        self.visitor = user_model.objects.create_user(
            email="p1-visitor@example.com",
            handle="p1_visitor",
            password="test-pass-123",
        )
        self.other_owner = user_model.objects.create_user(
            email="p1-other@example.com",
            handle="p1_other",
            password="test-pass-123",
        )
        self.project = Project.objects.create(
            owner=self.owner,
            name="Agent Board",
            slug="agent-board",
        )
        self.other_project = Project.objects.create(
            owner=self.other_owner,
            name="Other Board",
            slug="other-board",
        )
        self.canonical = Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Add dark mode support",
            description="Let users switch the dashboard to a dark color theme.",
            priority=Issue.Priority.HIGH,
        )
        self.possible_duplicate = Issue.objects.create(
            project=self.project,
            author=self.visitor,
            title="Dark mode for dashboard",
            description="Please support a dark dashboard theme.",
            priority=Issue.Priority.MEDIUM,
        )
        self.closed_issue = Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Completed request",
            status=Issue.Status.DONE,
            priority=Issue.Priority.CRITICAL,
        )
        self.external_issue = Issue.objects.create(
            project=self.other_project,
            author=self.other_owner,
            title="Dark mode elsewhere",
        )

    def test_duplicate_candidates_are_explainable_evidence_without_mutation(self):
        self.client.force_login(self.owner)
        response = self.client.get(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/duplicate-candidates",
            {
                "title": "Dashboard dark mode support",
                "description": "Users need a dark theme for the dashboard.",
                "exclude_issue_id": self.possible_duplicate.id,
                "limit": 5,
            },
        )

        self.assertEqual(response.status_code, 200)
        candidates = response.json()
        self.assertEqual(candidates[0]["issue_id"], self.canonical.id)
        self.assertEqual(candidates[0]["algorithm"], "weighted_jaccard_v1")
        self.assertGreater(candidates[0]["similarity_score"], 0)
        self.assertIn("dark", candidates[0]["matched_terms"])
        self.assertEqual(candidates[0]["score_components"]["title_weight"], 0.7)
        self.possible_duplicate.refresh_from_db()
        self.assertIsNone(self.possible_duplicate.duplicate_of_id)

    def test_duplicate_link_is_reversible_and_does_not_change_lifecycle_fields(self):
        self.client.force_login(self.owner)
        original_status = self.possible_duplicate.status
        original_priority = self.possible_duplicate.priority

        link_response = self.client.patch(
            f"/api/issues/{self.possible_duplicate.id}/duplicate",
            data=json.dumps({"canonical_issue_id": self.canonical.id}),
            content_type="application/json",
        )
        self.assertEqual(link_response.status_code, 200)
        self.assertEqual(link_response.json()["duplicate_of_id"], self.canonical.id)
        self.possible_duplicate.refresh_from_db()
        self.assertEqual(self.possible_duplicate.status, original_status)
        self.assertEqual(self.possible_duplicate.priority, original_priority)
        self.assertEqual(
            self.possible_duplicate.events.get().event_type,
            IssueEvent.Type.DUPLICATE_LINKED,
        )

        unlink_response = self.client.delete(
            f"/api/issues/{self.possible_duplicate.id}/duplicate"
        )
        self.assertEqual(unlink_response.status_code, 200)
        self.assertIsNone(unlink_response.json()["duplicate_of_id"])
        self.assertEqual(
            list(self.possible_duplicate.events.values_list("event_type", flat=True)),
            [IssueEvent.Type.DUPLICATE_LINKED, IssueEvent.Type.DUPLICATE_UNLINKED],
        )

    def test_duplicate_link_rejects_cross_project_canonical(self):
        self.client.force_login(self.owner)
        response = self.client.patch(
            f"/api/issues/{self.possible_duplicate.id}/duplicate",
            data=json.dumps({"canonical_issue_id": self.external_issue.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(Issue.objects.get(id=self.possible_duplicate.id).duplicate_of_id)

    def test_delivery_artifact_link_is_idempotent_and_does_not_verify_delivery(self):
        self.client.force_login(self.owner)
        payload = {
            "kind": IssueDeliveryArtifact.Kind.PULL_REQUEST,
            "url": "https://github.com/example/repo/pull/42",
            "label": "Implementation PR",
        }
        first = self.client.post(
            f"/api/issues/{self.canonical.id}/delivery-artifacts",
            data=json.dumps(payload),
            content_type="application/json",
        )
        second = self.client.post(
            f"/api/issues/{self.canonical.id}/delivery-artifacts",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["created"])
        self.assertFalse(second.json()["created"])
        self.assertEqual(self.canonical.delivery_artifacts.count(), 1)
        self.canonical.refresh_from_db()
        self.assertEqual(self.canonical.status, Issue.Status.OPEN)
        self.assertEqual(
            list(self.canonical.events.values_list("event_type", flat=True)),
            [IssueEvent.Type.DELIVERY_LINKED],
        )

        artifact_id = first.json()["artifact"]["id"]
        delete_response = self.client.delete(
            f"/api/issues/{self.canonical.id}/delivery-artifacts/{artifact_id}"
        )
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(IssueDeliveryArtifact.objects.filter(id=artifact_id).exists())
        self.assertEqual(
            list(self.canonical.events.values_list("event_type", flat=True)),
            [IssueEvent.Type.DELIVERY_LINKED, IssueEvent.Type.DELIVERY_UNLINKED],
        )

    def test_queue_snapshot_is_owner_scoped_and_keeps_current_priority_as_data(self):
        self.client.force_login(self.owner)
        response = self.client.get("/api/me/request-queue", {"limit": 100})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["projects_count"], 1)
        self.assertEqual(payload["active_requests_count"], 2)
        self.assertEqual(
            [item["id"] for item in payload["requests"]],
            [self.canonical.id, self.possible_duplicate.id],
        )
        self.assertEqual(payload["priority_counts"][str(Issue.Priority.HIGH)], 1)
        self.assertNotIn(self.closed_issue.id, [item["id"] for item in payload["requests"]])
        self.assertNotIn(self.external_issue.id, [item["id"] for item in payload["requests"]])

    def test_activity_and_cursor_change_feed_are_structured_and_owner_scoped(self):
        self.client.force_login(self.owner)
        update_response = self.client.patch(
            f"/api/issues/{self.canonical.id}",
            data=json.dumps({"priority": Issue.Priority.CRITICAL}),
            content_type="application/json",
        )
        self.assertEqual(update_response.status_code, 200)
        event = self.canonical.events.get()

        activity_response = self.client.get(
            f"/api/issues/{self.canonical.id}/activity"
        )
        self.assertEqual(activity_response.status_code, 200)
        self.assertEqual(activity_response.json()[0]["event_type"], IssueEvent.Type.UPDATED)
        self.assertEqual(
            activity_response.json()[0]["data"]["changes"]["priority"],
            {"from": Issue.Priority.HIGH, "to": Issue.Priority.CRITICAL},
        )

        feed_response = self.client.get("/api/me/issue-changes", {"after_id": 0})
        self.assertEqual(feed_response.status_code, 200)
        self.assertEqual(feed_response.json()["next_cursor"], event.id)
        empty_response = self.client.get(
            "/api/me/issue-changes",
            {"after_id": event.id},
        )
        self.assertEqual(empty_response.json()["events"], [])
        self.assertEqual(empty_response.json()["next_cursor"], event.id)

        self.client.force_login(self.other_owner)
        other_feed = self.client.get("/api/me/issue-changes", {"after_id": 0})
        self.assertEqual(other_feed.json()["events"], [])


@override_settings(OPENAI_API_KEY="")
class ProjectSpecApiTest(TestCase):
    SPEC = """# Purpose
Keep public feedback focused.

## Intended users
Product teams.

## In scope
Public feature requests.

## Out of scope
Private strategy consulting.

## Product principles / Constraints
Safe and transparent defaults.
"""

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="spec-owner@example.com",
            handle="spec_owner",
            password="test-pass-123",
        )
        self.author = User.objects.create_user(
            email="spec-author@example.com",
            handle="spec_author",
            password="test-pass-123",
        )
        self.outsider = User.objects.create_user(
            email="spec-outsider@example.com",
            handle="spec_outsider",
            password="test-pass-123",
        )
        self.project = Project.objects.create(
            owner=self.owner,
            name="Spec Board",
            slug="spec-board",
        )

    def put_spec(self, *, content=None, auto_decline=False, expected_revision=0):
        return self.client.put(
            f"/api/projects/{self.project.id}/spec",
            data=json.dumps(
                {
                    "content": content or self.SPEC,
                    "auto_decline_enabled": auto_decline,
                    "expected_revision": expected_revision,
                }
            ),
            content_type="application/json",
        )

    def create_issue(self, title="A new request", description="Please consider this."):
        return self.client.post(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
            data=json.dumps(
                {
                    "issue_type": "feature",
                    "title": title,
                    "description": description,
                    "priority": Issue.Priority.MEDIUM,
                }
            ),
            content_type="application/json",
        )

    def test_spec_create_update_public_read_revision_and_summary(self):
        self.client.force_login(self.owner)
        created = self.put_spec(auto_decline=True)
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["revision"], 1)
        self.assertTrue(created.json()["auto_decline_enabled"])

        public = self.client.get(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/spec"
        )
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.json()["content"], self.SPEC.strip())

        summaries = self.client.get(f"/api/owners/{self.owner.handle}/projects")
        self.assertTrue(summaries.json()[0]["has_spec"])
        self.assertEqual(summaries.json()[0]["spec_revision"], 1)
        self.assertNotIn("content", summaries.json()[0])

        stale = self.put_spec(expected_revision=0)
        self.assertEqual(stale.status_code, 409)
        updated = self.put_spec(
            content=self.SPEC + "\n- Prefer reversible changes.\n",
            auto_decline=True,
            expected_revision=1,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["revision"], 2)

    def test_auto_decline_requires_both_scope_sections_and_content_limit(self):
        self.client.force_login(self.owner)
        missing_out = self.put_spec(
            content="# Purpose\nFocused.\n## In scope\nPublic requests.",
            auto_decline=True,
        )
        self.assertEqual(missing_out.status_code, 400)
        too_long = self.put_spec(content="x" * 10001)
        self.assertEqual(too_long.status_code, 400)

    def test_only_owner_can_write_or_delete_spec_and_delete_invalidates_pending(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.put_spec().status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.put_spec().status_code, 200)
        issue = Issue.objects.create(project=self.project, author=self.author, title="Gap")
        proposal = ProjectSpecChangeProposal.objects.create(
            project=self.project,
            issue=issue,
            base_spec_revision=1,
            base_content=self.SPEC,
            proposed_content=self.SPEC + "\nMore detail.",
            summary="Clarify the boundary.",
            created_by=self.owner,
        )
        self.client.force_login(self.outsider)
        denied = self.client.delete(
            f"/api/projects/{self.project.id}/spec",
            data=json.dumps({"confirm_project_id": self.project.id, "expected_revision": 1}),
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)
        self.client.force_login(self.owner)
        deleted = self.client.delete(
            f"/api/projects/{self.project.id}/spec",
            data=json.dumps({"confirm_project_id": self.project.id, "expected_revision": 1}),
            content_type="application/json",
        )
        self.assertEqual(deleted.status_code, 200)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, ProjectSpecChangeProposal.Status.REJECTED)

    @patch("projects.api.evaluate_request_scope")
    def test_exact_out_of_scope_quote_auto_declines(self, evaluate):
        self.client.force_login(self.owner)
        self.assertEqual(self.put_spec(auto_decline=True).status_code, 200)
        evaluate.return_value = ScopeEvaluation(
            state=IssueScopeAssessment.State.COMPLETED,
            verdict=IssueScopeAssessment.Verdict.OUT_OF_SCOPE,
            public_reason="This request conflicts with an explicit non-goal.",
            out_of_scope_quote="Private strategy consulting.",
            contradicts_in_scope=False,
            requires_owner_judgment=False,
        )
        self.client.force_login(self.author)
        response = self.create_issue("Private strategy", "Please advise our strategy.")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], Issue.Status.DECLINED)
        assessment = IssueScopeAssessment.objects.get(issue_id=response.json()["id"])
        self.assertTrue(assessment.auto_declined)

    @patch("projects.api.evaluate_request_scope")
    def test_ambiguous_or_conflicting_out_of_scope_result_stays_open(self, evaluate):
        self.client.force_login(self.owner)
        self.put_spec(auto_decline=True)
        evaluate.return_value = ScopeEvaluation(
            state=IssueScopeAssessment.State.COMPLETED,
            verdict=IssueScopeAssessment.Verdict.OUT_OF_SCOPE,
            public_reason="Owner review is needed.",
            out_of_scope_quote="Private strategy consulting.",
            contradicts_in_scope=True,
            requires_owner_judgment=False,
        )
        self.client.force_login(self.author)
        response = self.create_issue()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], Issue.Status.OPEN)

    @patch("projects.api.evaluate_request_scope")
    def test_out_of_scope_result_stays_open_when_auto_decline_is_off(self, evaluate):
        ProjectSpec.objects.create(project=self.project, content=self.SPEC)
        evaluate.return_value = ScopeEvaluation(
            state=IssueScopeAssessment.State.COMPLETED,
            verdict=IssueScopeAssessment.Verdict.OUT_OF_SCOPE,
            public_reason="Explicit non-goal.",
            out_of_scope_quote="Private strategy consulting.",
            contradicts_in_scope=False,
            requires_owner_judgment=False,
        )
        self.client.force_login(self.author)
        response = self.create_issue()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], Issue.Status.OPEN)

    def test_provider_failure_fails_open_and_is_owner_only(self):
        self.client.force_login(self.owner)
        self.put_spec()
        self.client.force_login(self.author)
        response = self.create_issue()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], Issue.Status.OPEN)
        issue_id = response.json()["id"]
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(f"/api/issues/{issue_id}/scope-assessment").status_code,
            404,
        )
        self.client.force_login(self.owner)
        private = self.client.get(f"/api/issues/{issue_id}/scope-assessment")
        self.assertEqual(private.status_code, 200)
        self.assertEqual(private.json()["state"], IssueScopeAssessment.State.FAILED)
        self.assertEqual(private.json()["error_code"], "dependency_unavailable")

    @override_settings(OPENAI_API_KEY="test-key")
    @patch("projects.api._moderate_issue_submission")
    @patch("projects.api.OpenAI")
    def test_malformed_scope_output_fails_open_without_raw_output_storage(
        self, openai_client, _moderation
    ):
        ProjectSpec.objects.create(project=self.project, content=self.SPEC)
        openai_client.return_value.responses.create.return_value.output_text = "{malformed model output"
        self.client.force_login(self.author)
        response = self.create_issue()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], Issue.Status.OPEN)
        assessment = IssueScopeAssessment.objects.get(issue_id=response.json()["id"])
        self.assertEqual(assessment.error_code, "invalid_output")
        serialized = json.dumps(
            {
                field.name: getattr(assessment, field.name)
                for field in assessment._meta.fields
                if field.name != "created_at"
            },
            default=str,
        )
        self.assertNotIn("malformed model output", serialized)

    def test_declined_author_can_comment_but_only_owner_can_reopen(self):
        issue = Issue.objects.create(
            project=self.project,
            author=self.author,
            title="Declined request",
            status=Issue.Status.DECLINED,
        )
        self.client.force_login(self.author)
        comment = self.client.post(
            f"/api/issues/{issue.id}/comments",
            data=json.dumps({"body": "Please reconsider this boundary."}),
            content_type="application/json",
        )
        self.assertEqual(comment.status_code, 201)
        denied = self.client.patch(
            f"/api/issues/{issue.id}",
            data=json.dumps({"status": Issue.Status.OPEN}),
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)
        self.client.force_login(self.owner)
        reopened = self.client.patch(
            f"/api/issues/{issue.id}",
            data=json.dumps({"status": Issue.Status.OPEN}),
            content_type="application/json",
        )
        self.assertEqual(reopened.status_code, 200)

    def test_active_filter_excludes_declined(self):
        Issue.objects.create(
            project=self.project,
            author=self.author,
            title="Open request",
            status=Issue.Status.OPEN,
        )
        declined = Issue.objects.create(
            project=self.project,
            author=self.author,
            title="Declined request",
            status=Issue.Status.DECLINED,
        )
        response = self.client.get(
            f"/api/projects/{self.owner.handle}/{self.project.slug}/issues",
            {"status": "active"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(declined.id, [item["id"] for item in response.json()])

    @patch("projects.api.generate_spec_change_proposal")
    def test_private_proposal_accept_and_stale_revision_conflict(self, generate):
        spec = ProjectSpec.objects.create(project=self.project, content=self.SPEC)
        issue = Issue.objects.create(project=self.project, author=self.author, title="Integration gap")
        IssueScopeAssessment.objects.create(
            issue=issue,
            spec_revision=spec.revision,
            state=IssueScopeAssessment.State.COMPLETED,
            verdict=IssueScopeAssessment.Verdict.SPEC_GAP,
            public_reason="The spec does not define integrations.",
            spec_gap_summary="Clarify integrations.",
            evaluator_version="test-v1",
        )
        proposed = self.SPEC.replace("Public feature requests.", "Public feature requests and integrations.")
        generate.return_value = (proposed, "Clarify integration support.")
        self.client.force_login(self.owner)
        created = self.client.post(f"/api/issues/{issue.id}/spec-change-proposals")
        self.assertEqual(created.status_code, 201)
        proposal_id = created.json()["id"]
        self.assertIn("integrations", created.json()["diff"])

        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(f"/api/projects/{self.project.id}/spec-change-proposals").status_code,
            403,
        )
        self.client.force_login(self.owner)
        spec.content += "\nA concurrent edit."
        spec.revision += 1
        spec.save()
        stale = self.client.patch(
            f"/api/spec-change-proposals/{proposal_id}",
            data=json.dumps({"decision": "accept", "expected_revision": 1}),
            content_type="application/json",
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(
            ProjectSpecChangeProposal.objects.get(id=proposal_id).status,
            ProjectSpecChangeProposal.Status.PENDING,
        )

    def test_spec_proposal_generation_failure_creates_no_draft(self):
        spec = ProjectSpec.objects.create(project=self.project, content=self.SPEC)
        issue = Issue.objects.create(project=self.project, author=self.author, title="Unresolved gap")
        IssueScopeAssessment.objects.create(
            issue=issue,
            spec_revision=spec.revision,
            state=IssueScopeAssessment.State.COMPLETED,
            verdict=IssueScopeAssessment.Verdict.SPEC_GAP,
            public_reason="Undefined boundary.",
            spec_gap_summary="Clarify it.",
            evaluator_version="test-v1",
        )
        self.client.force_login(self.owner)
        response = self.client.post(f"/api/issues/{issue.id}/spec-change-proposals")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(ProjectSpecChangeProposal.objects.exists())

    def test_proposal_accept_publishes_spec_event_and_reject_is_private(self):
        spec = ProjectSpec.objects.create(project=self.project, content=self.SPEC)
        accepted_issue = Issue.objects.create(project=self.project, author=self.author, title="Accepted gap")
        accepted = ProjectSpecChangeProposal.objects.create(
            project=self.project,
            issue=accepted_issue,
            base_spec_revision=1,
            base_content=self.SPEC,
            proposed_content=self.SPEC + "\n- Clarified from a request.",
            summary="Clarify one boundary.",
            created_by=self.owner,
        )
        self.client.force_login(self.owner)
        response = self.client.patch(
            f"/api/spec-change-proposals/{accepted.id}",
            data=json.dumps({"decision": "accept", "expected_revision": 1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        spec.refresh_from_db()
        self.assertEqual(spec.revision, 2)
        self.assertEqual(
            accepted_issue.events.get().event_type,
            IssueEvent.Type.SPEC_UPDATED,
        )

        rejected_issue = Issue.objects.create(project=self.project, author=self.author, title="Rejected gap")
        rejected = ProjectSpecChangeProposal.objects.create(
            project=self.project,
            issue=rejected_issue,
            base_spec_revision=2,
            base_content=spec.content,
            proposed_content=spec.content + "\nRejected detail.",
            summary="A rejected change.",
            created_by=self.owner,
        )
        rejected_response = self.client.patch(
            f"/api/spec-change-proposals/{rejected.id}",
            data=json.dumps({"decision": "reject", "expected_revision": 2}),
            content_type="application/json",
        )
        self.assertEqual(rejected_response.status_code, 200)
        self.assertFalse(rejected_issue.events.exists())
