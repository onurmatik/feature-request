import json
from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.db import IntegrityError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from .embed import (
    EmbedSubmissionError,
    email_fingerprint,
    token_digest,
    validate_turnstile,
)
from .models import EmbeddedIssueSubmission, Issue, IssueComment, IssueUpvote, Project


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
            "display_name": "Visitor Name",
            "email": "visitor@example.com",
            "issue_type": Issue.Type.FEATURE,
            "title": "Add a compact mode",
            "description": "It would help on smaller screens.",
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
            email_fingerprint=email_fingerprint(email),
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
        self.assertContains(response, "Submit")
        self.assertNotContains(response, "Send verification link")
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

    @patch("projects.embed.send_mail", return_value=1)
    @patch("projects.api.validate_turnstile")
    def test_submission_sends_verification_without_creating_issue(
        self, validate_turnstile, send_mail
    ):
        response = self.post_submission()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"status": "verification_sent"})
        validate_turnstile.assert_called_once()
        send_mail.assert_called_once()
        self.assertEqual(Issue.objects.count(), 0)
        pending = EmbeddedIssueSubmission.objects.get()
        self.assertEqual(pending.email, "visitor@example.com")
        self.assertIn("/embed/submissions/", send_mail.call_args.args[1])
        self.assertIn("/verify/", send_mail.call_args.args[1])

    @patch("projects.api.validate_turnstile")
    def test_invalid_email_is_rejected_before_turnstile(self, validate_turnstile):
        response = self.post_submission(self.payload(email="not-an-email"))

        self.assertEqual(response.status_code, 400)
        validate_turnstile.assert_not_called()
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)

    @patch("projects.api.validate_turnstile")
    def test_empty_description_is_rejected_before_turnstile(self, validate_turnstile):
        response = self.post_submission(self.payload(description="   "))

        self.assertEqual(response.status_code, 400)
        validate_turnstile.assert_not_called()
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)

    @patch("projects.api.validate_turnstile")
    def test_turnstile_failure_is_returned_without_pending_submission(
        self, validate_turnstile
    ):
        validate_turnstile.side_effect = EmbedSubmissionError(
            400, "Human verification failed."
        )

        response = self.post_submission()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)

    @override_settings(OPENAI_API_KEY="test-openai-key")
    @patch("projects.embed.send_mail", return_value=1)
    @patch("projects.api.validate_turnstile")
    def test_moderation_rejection_does_not_send_email(
        self, validate_turnstile, send_mail
    ):
        mocked_client = Mock()
        mocked_client.responses.create.return_value = Mock(output_text="REJECT: spam")

        with patch("projects.api.OpenAI", return_value=mocked_client):
            response = self.post_submission()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Issue rejected by moderation: spam")
        send_mail.assert_not_called()
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)

    @override_settings(OPENAI_API_KEY="test-openai-key")
    @patch("projects.embed.send_mail", return_value=1)
    @patch("projects.api.validate_turnstile")
    def test_moderation_failure_returns_503_without_email(
        self, validate_turnstile, send_mail
    ):
        mocked_client = Mock()
        mocked_client.responses.create.side_effect = RuntimeError("moderation timeout")

        with patch("projects.api.OpenAI", return_value=mocked_client):
            response = self.post_submission()

        self.assertEqual(response.status_code, 503)
        send_mail.assert_not_called()
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)

    @patch("projects.embed.send_mail", side_effect=RuntimeError("mail unavailable"))
    @patch("projects.api.validate_turnstile")
    def test_email_failure_removes_pending_submission(
        self, validate_turnstile, send_mail
    ):
        response = self.post_submission()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 0)

    @patch("projects.embed.send_mail", return_value=1)
    @patch("projects.api.validate_turnstile")
    def test_submission_is_throttled_after_three_emails_per_hour(
        self, validate_turnstile, send_mail
    ):
        responses = [self.post_submission() for _ in range(4)]

        self.assertEqual([response.status_code for response in responses], [202, 202, 202, 429])
        self.assertEqual(EmbeddedIssueSubmission.objects.count(), 3)
        self.assertEqual(send_mail.call_count, 3)

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
