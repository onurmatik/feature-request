import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Project

from .models import OwnerMessage


class OwnerMessageApiTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(
            email="owner-message@example.com",
            handle="owner_message",
            password="test-pass-123",
        )
        self.visitor = user_model.objects.create_user(
            email="visitor@example.com",
            handle="visitor_user",
            password="test-pass-123",
        )
        self.public_project = Project.objects.create(
            owner=self.owner,
            name="Public board",
            slug="public-board",
        )
        self.secondary_project = Project.objects.create(
            owner=self.owner,
            name="Secondary board",
            slug="secondary-board",
        )

    def test_anonymous_message_requires_sender_fields(self):
        response = self.client.post(
            f"/api/owners/{self.owner.handle}/messages",
            data=json.dumps({"body": "Hello"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_anonymous_message_is_persisted(self):
        response = self.client.post(
            f"/api/owners/{self.owner.handle}/messages",
            data=json.dumps(
                {
                    "project_slug": self.public_project.slug,
                    "sender_name": "Guest User",
                    "sender_email": "guest@example.com",
                    "body": "Can we add dark mode?",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["recipient_handle"], self.owner.handle)
        self.assertEqual(payload["project_slug"], self.public_project.slug)

        saved = OwnerMessage.objects.get(id=payload["id"])
        self.assertEqual(saved.sender_name, "Guest User")
        self.assertEqual(saved.sender_email, "guest@example.com")

    def test_authenticated_message_uses_user_defaults(self):
        self.client.force_login(self.visitor)
        response = self.client.post(
            f"/api/owners/{self.owner.handle}/messages",
            data=json.dumps(
                {
                    "project_slug": self.public_project.slug,
                    "body": "Please prioritize search improvements.",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["sender_user_id"], self.visitor.id)
        self.assertEqual(payload["sender_name"], self.visitor.handle)
        self.assertEqual(payload["sender_email"], self.visitor.email)

    def test_message_can_target_any_owner_project(self):
        response = self.client.post(
            f"/api/owners/{self.owner.handle}/messages",
            data=json.dumps(
                {
                    "project_slug": self.secondary_project.slug,
                    "sender_name": "Guest User",
                    "sender_email": "guest@example.com",
                    "body": "Feedback for another project",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

    def test_list_my_messages(self):
        OwnerMessage.objects.create(
            recipient=self.owner,
            project=self.public_project,
            sender_user=self.visitor,
            sender_name=self.visitor.handle,
            sender_email=self.visitor.email,
            body="Hello owner",
        )

        self.client.force_login(self.owner)
        response = self.client.get("/api/me/messages")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["recipient_handle"], self.owner.handle)

    def test_list_my_messages_requires_auth(self):
        response = self.client.get("/api/me/messages")
        self.assertEqual(response.status_code, 401)
