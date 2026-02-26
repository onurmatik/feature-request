import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase


class SessionApiTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="session-user@example.com",
            handle="session_user",
            password="test-pass-123",
        )

    def test_me_returns_anonymous_session_and_sets_csrf_cookie(self):
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["is_authenticated"], False)
        self.assertEqual(payload["current_user_handle"], "")
        self.assertIsNone(payload["user_id"])
        self.assertIn("csrftoken", response.cookies)

    def test_me_returns_authenticated_session(self):
        self.client.force_login(self.user)
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["is_authenticated"], True)
        self.assertEqual(payload["current_user_handle"], self.user.handle)
        self.assertEqual(payload["user_id"], self.user.id)

    def test_me_treats_legacy_pro_account_without_status_as_paid(self):
        self.user.subscription_tier = "pro_30"
        self.user.subscription_status = ""
        self.user.save(update_fields=["subscription_tier", "subscription_status"])

        self.client.force_login(self.user)
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["subscription_tier"], "pro_30")
        self.assertEqual(payload["project_limit"], 30)

    def test_logout_clears_session(self):
        self.client.force_login(self.user)
        logout_response = self.client.post("/auth/logout")
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json()["ok"], True)

        me_response = self.client.get("/auth/me")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["is_authenticated"], False)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        response = self.client.get("/auth/logout")
        self.assertEqual(response.status_code, 405)


class AuthEntryApiTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="existing-user@example.com",
            handle="existing_user",
            password="test-pass-123",
        )

    def test_sign_up_sends_magic_link(self):
        response = self.client.post(
            "/auth/sign-up",
            data=json.dumps(
                {
                    "email": "new-user@example.com",
                    "handle": "new_user",
                    "display_name": "New User",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["detail"], "Sign-up link sent. Check your email.")
        self.assertTrue(
            get_user_model().objects.filter(email__iexact="new-user@example.com").exists()
        )

        me_response = self.client.get("/auth/me")
        self.assertEqual(me_response.status_code, 200)
        self.assertFalse(me_response.json()["is_authenticated"])

    @patch("accounts.views.send_mail")
    def test_sign_up_notifies_admins(self, mock_send_mail):
        with self.settings(ADMINS=[("Admin", "admin@featurerequest.test")]):
            response = self.client.post(
                "/auth/sign-up",
                data=json.dumps(
                    {
                        "email": "admin-notify-user@example.com",
                        "handle": "admin_notify_user",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_send_mail.call_count, 2)
        admin_call = mock_send_mail.call_args_list[1]
        self.assertEqual(admin_call.args[3], ["admin@featurerequest.test"])

    def test_sign_up_rejects_invalid_or_duplicate_data(self):
        duplicate_email = self.client.post(
            "/auth/sign-up",
            data=json.dumps(
                {
                    "email": self.user.email,
                    "handle": "another_handle",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(duplicate_email.status_code, 400)

        invalid_handle = self.client.post(
            "/auth/sign-up",
            data=json.dumps(
                {
                    "email": "fresh@example.com",
                    "handle": "Invalid-Handle",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(invalid_handle.status_code, 400)

    def test_sign_up_rejects_reserved_handles(self):
        reserved_handles = [
            "messages",
            "settings",
            settings.ADMIN_URL.strip("/").split("/", 1)[0],
        ]

        for index, handle in enumerate(reserved_handles):
            response = self.client.post(
                "/auth/sign-up",
                data=json.dumps(
                    {
                        "email": f"reserved-{index}@example.com",
                        "handle": handle,
                    }
                ),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("reserved", response.json().get("detail", "").lower())

    def test_sign_in_accepts_email_or_handle(self):
        by_email = self.client.post(
            "/auth/sign-in",
            data=json.dumps({"email_or_handle": self.user.email}),
            content_type="application/json",
        )
        self.assertEqual(by_email.status_code, 200)
        self.assertEqual(by_email.json()["current_user_handle"], self.user.handle)

        self.client.post("/auth/logout")

        by_handle = self.client.post(
            "/auth/sign-in",
            data=json.dumps({"email_or_handle": self.user.handle}),
            content_type="application/json",
        )
        self.assertEqual(by_handle.status_code, 200)
        self.assertEqual(by_handle.json()["current_user_handle"], self.user.handle)

    def test_sign_in_returns_404_for_unknown_account(self):
        response = self.client.post(
            "/auth/sign-in",
            data=json.dumps({"email_or_handle": "missing_user"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_create_user_rejects_reserved_handle(self):
        with self.assertRaises(ValueError):
            get_user_model().objects.create_user(
                email="reserved-manager@example.com",
                handle="messages",
            )
