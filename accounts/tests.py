from django.contrib.auth import get_user_model
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
