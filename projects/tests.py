import json

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .models import Issue, IssueComment, IssueUpvote, Project


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
        self.private_project = Project.objects.create(
            owner=self.owner,
            name="Private Board",
            slug="private-board",
            visibility=Project.Visibility.PRIVATE,
        )
        self.issue = Issue.objects.create(
            project=self.project,
            author=self.owner,
            issue_type=Issue.Type.FEATURE,
            title="Add roadmap voting",
            description="Allow users to vote on roadmap items.",
            priority=Issue.Priority.MEDIUM,
        )
        self.private_issue = Issue.objects.create(
            project=self.private_project,
            author=self.owner,
            issue_type=Issue.Type.BUG,
            title="Internal incident",
            description="Internal only",
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

    def test_private_project_access_is_restricted(self):
        self.client.force_login(self.other_user)
        forbidden_list = self.client.get(
            f"/api/projects/{self.owner.handle}/{self.private_project.slug}/issues"
        )
        self.assertEqual(forbidden_list.status_code, 404)

        forbidden_detail = self.client.get(f"/api/issues/{self.private_issue.id}")
        self.assertEqual(forbidden_detail.status_code, 404)

        self.client.force_login(self.owner)
        owner_list = self.client.get(
            f"/api/projects/{self.owner.handle}/{self.private_project.slug}/issues"
        )
        self.assertEqual(owner_list.status_code, 200)

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

    def test_list_owner_projects_respects_visibility(self):
        public_response = self.client.get(f"/api/owners/{self.owner.handle}/projects")
        self.assertEqual(public_response.status_code, 200)
        public_payload = public_response.json()
        self.assertEqual(len(public_payload), 1)
        self.assertEqual(public_payload[0]["slug"], self.project.slug)

        self.client.force_login(self.owner)
        owner_response = self.client.get(f"/api/owners/{self.owner.handle}/projects")
        self.assertEqual(owner_response.status_code, 200)
        owner_payload = owner_response.json()
        self.assertEqual(len(owner_payload), 2)

    def test_list_owner_issues_supports_project_filter(self):
        Issue.objects.create(
            project=self.project,
            author=self.other_user,
            title="Another public issue",
        )

        public_all = self.client.get(f"/api/owners/{self.owner.handle}/issues")
        self.assertEqual(public_all.status_code, 200)
        self.assertEqual(len(public_all.json()), 2)

        public_specific = self.client.get(
            f"/api/owners/{self.owner.handle}/issues",
            {"project_slug": self.project.slug},
        )
        self.assertEqual(public_specific.status_code, 200)
        self.assertEqual(len(public_specific.json()), 2)

        public_private = self.client.get(
            f"/api/owners/{self.owner.handle}/issues",
            {"project_slug": self.private_project.slug},
        )
        self.assertEqual(public_private.status_code, 404)

        self.client.force_login(self.owner)
        owner_all = self.client.get(f"/api/owners/{self.owner.handle}/issues")
        self.assertEqual(owner_all.status_code, 200)
        self.assertEqual(len(owner_all.json()), 3)


class ProjectBackendUiTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="owner-ui@example.com",
            handle="owner_ui",
            password="test-pass-123",
        )
        self.other_user = user_model.objects.create_user(
            email="other-ui@example.com",
            handle="other_ui",
            password="test-pass-123",
        )

    def test_list_requires_auth(self):
        response = self.client.get(reverse("projects:backend-project-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.headers["Location"])

    def test_owner_can_create_edit_and_delete_project(self):
        self.client.force_login(self.owner)

        create_response = self.client.post(
            reverse("projects:backend-project-create"),
            data={
                "name": "Platform Revamp",
                "slug": "",
                "tagline": "Major overhaul",
                "description": "New architecture and workflows.",
                "visibility": Project.Visibility.PRIVATE,
            },
        )
        self.assertEqual(create_response.status_code, 302)

        project = Project.objects.get(owner=self.owner)
        self.assertEqual(project.slug, "platform-revamp")

        edit_response = self.client.post(
            reverse("projects:backend-project-edit", args=[project.pk]),
            data={
                "name": "Platform Revamp V2",
                "slug": "platform-v2",
                "tagline": "Updated scope",
                "description": "Updated description.",
                "visibility": Project.Visibility.PUBLIC,
            },
        )
        self.assertEqual(edit_response.status_code, 302)
        project.refresh_from_db()
        self.assertEqual(project.name, "Platform Revamp V2")
        self.assertEqual(project.slug, "platform-v2")
        self.assertEqual(project.visibility, Project.Visibility.PUBLIC)

        delete_response = self.client.post(
            reverse("projects:backend-project-delete", args=[project.pk])
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_non_owner_cannot_access_edit_or_delete(self):
        project = Project.objects.create(
            owner=self.owner,
            name="Secret Board",
            slug="secret-board",
        )

        self.client.force_login(self.other_user)

        edit_response = self.client.get(
            reverse("projects:backend-project-edit", args=[project.pk])
        )
        delete_response = self.client.get(
            reverse("projects:backend-project-delete", args=[project.pk])
        )

        self.assertEqual(edit_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)


class PublicBoardViewTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="owner-public@example.com",
            handle="owner_public",
            password="test-pass-123",
        )
        self.other_user = user_model.objects.create_user(
            email="other-public@example.com",
            handle="other_public",
            password="test-pass-123",
        )
        self.public_project = Project.objects.create(
            owner=self.owner,
            name="Gezgin",
            slug="gezgin",
            visibility=Project.Visibility.PUBLIC,
        )
        self.private_project = Project.objects.create(
            owner=self.owner,
            name="Secret Roadmap",
            slug="secret-roadmap",
            visibility=Project.Visibility.PRIVATE,
        )

    def test_owner_board_is_publicly_accessible(self):
        response = self.client.get(f"/{self.owner.handle}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "All Projects")

    def test_public_project_board_is_publicly_accessible(self):
        response = self.client.get(f"/{self.owner.handle}/{self.public_project.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Contact @{self.owner.handle}")

    def test_private_project_board_is_hidden_from_visitors(self):
        response = self.client.get(f"/{self.owner.handle}/{self.private_project.slug}/")
        self.assertEqual(response.status_code, 404)

    def test_private_project_board_is_visible_to_owner(self):
        self.client.force_login(self.owner)
        response = self.client.get(f"/{self.owner.handle}/{self.private_project.slug}/")
        self.assertEqual(response.status_code, 200)
