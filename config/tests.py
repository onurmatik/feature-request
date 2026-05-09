from django.test import TestCase
from django.templatetags.static import static


class ApiDocsCompatibilityTest(TestCase):
    def test_legacy_swagger_json_redirects_to_openapi_spec(self):
        response = self.client.get("/api-docs/swagger.json")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/api/openapi.json")

    def test_openapi_json_remains_available(self):
        response = self.client.get("/api/openapi.json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_other_api_docs_paths_remain_not_found(self):
        response = self.client.get("/api-docs/unknown")

        self.assertEqual(response.status_code, 404)


class FaviconRoutingTest(TestCase):
    def test_favicon_ico_redirects_to_static_asset(self):
        response = self.client.get("/favicon.ico")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], static("projects/favicon.svg"))

    def test_frontend_declares_static_favicon(self):
        response = self.client.get("/")

        self.assertContains(
            response,
            f'<link rel="icon" type="image/svg+xml" href="{static("projects/favicon.svg")}">',
        )
