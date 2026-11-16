from django.http import HttpResponse, HttpResponseRedirect
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.templatetags.static import static


@override_settings(
    SECURE_SSL_REDIRECT=True,
    SECURE_HSTS_SECONDS=31536000,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    SECURE_HSTS_PRELOAD=True,
)
class TransportSecurityTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = SecurityMiddleware(lambda request: HttpResponse(status=404))

    def test_https_responses_include_preload_hsts_even_for_errors(self):
        for kwargs in ({"secure": True}, {"HTTP_X_FORWARDED_PROTO": "https"}):
            with self.subTest(kwargs=kwargs):
                response = self.middleware(self.factory.get("/missing", **kwargs))
                self.assertEqual(response.status_code, 404)
                self.assertEqual(
                    response["Strict-Transport-Security"],
                    "max-age=31536000; includeSubDomains; preload",
                )

    def test_https_redirect_includes_hsts_before_leaving_the_host(self):
        middleware = SecurityMiddleware(
            lambda request: HttpResponseRedirect("https://assets.example.com/favicon.svg")
        )
        response = middleware(self.factory.get("/favicon.ico", secure=True))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Strict-Transport-Security"],
            "max-age=31536000; includeSubDomains; preload",
        )

    def test_http_redirect_keeps_path_and_query_without_hsts(self):
        response = self.middleware(
            self.factory.get("/settings/?tab=spec", HTTP_HOST="featurerequest.io")
        )
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://featurerequest.io/settings/?tab=spec")
        self.assertNotIn("Strict-Transport-Security", response)

    @override_settings(SECURE_HSTS_SECONDS=0)
    def test_disabled_hsts_does_not_pin_local_development_to_https(self):
        middleware = SecurityMiddleware(lambda request: HttpResponse())
        response = middleware(self.factory.get("/", secure=True))
        self.assertNotIn("Strict-Transport-Security", response)


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


class PreReleaseBackendSurfaceTest(TestCase):
    def test_mcp_path_never_falls_through_to_frontend(self):
        self.assertEqual(self.client.get("/mcp").status_code, 404)

    def test_unsupported_openid_alias_never_falls_through_to_frontend(self):
        self.assertEqual(
            self.client.get("/.well-known/openid-configuration").status_code,
            404,
        )


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
        widget_script = f"""    <script
      src="{static('projects/embed-widget.js')}"
      data-fr-origin="https://featurerequest.io"
      data-fr-owner="onurmatik"
      data-fr-project="feature-request"
      data-fr-position="right"
      data-fr-color="#06B6D4"
      defer
    ></script>"""

        self.assertEqual(html.count(widget_script), 1)
        self.assertIn(f"{widget_script}\n  </body>", html)

    def test_frontend_reloads_asset_references_without_cached_html(self):
        for path in ("/", "/onurmatik/site-hits/settings"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-cache", response["Cache-Control"])
                self.assertIn("no-store", response["Cache-Control"])


class SiteHitsBrowserTrackerTest(TestCase):
    def test_existing_browser_tracker_is_unchanged_and_has_no_bot_key(self):
        response = self.client.get("/")
        html = response.content.decode()
        browser_tracker = (
            '<script defer src="https://sitehits.io/js/script.js" '
            'data-site-key="sh_vLsGeHosB7zxFqHKWnQ6R5q2" '
            'data-api-url="https://sitehits.io/api/events"></script>'
        )

        self.assertEqual(html.count(browser_tracker), 1)
        self.assertNotIn("shb_", html)
