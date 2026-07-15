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


class FeedbackWidgetInstallationTest(TestCase):
    def test_frontend_loads_feedback_widget_once_before_body_closes(self):
        response = self.client.get("/")
        html = response.content.decode()
        widget_script = """    <script
      src="https://featurerequest-assets.s3.amazonaws.com/static/projects/embed-widget.js"
      data-fr-origin="https://featurerequest.io"
      data-fr-owner="onurmatik"
      data-fr-project="feature-request"
      data-fr-position="right"
      data-fr-color="#06B6D4"
      defer
    ></script>"""

        self.assertEqual(html.count(widget_script), 1)
        self.assertIn(f"{widget_script}\n  </body>", html)
