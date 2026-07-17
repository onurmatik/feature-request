import asyncio
import json
from io import BytesIO
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from config.middleware import (
    SITEHITS_BOT_EVENTS_URL,
    SiteHitsBotMiddleware,
    _post_bot_event,
    _schedule_best_effort,
)


class _CollectorResponse:
    def __init__(self, status, body=b""):
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self.body


@override_settings(
    SITEHITS_BOT_KEY="server-only-test-key",
    SITEHITS_BOT_TIMEOUT_SECONDS=0.25,
)
class SiteHitsBotMiddlewareTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_schedules_document_event_only_after_response_is_known(self):
        order = []

        def get_response(request):
            order.append("response")
            return HttpResponse("page", status=201)

        request = self.factory.get(
            "/roadmap/?view=popular",
            HTTP_USER_AGENT="ExampleCrawler/1.0",
        )
        middleware = SiteHitsBotMiddleware(get_response)

        with patch("config.middleware._schedule_best_effort") as schedule:
            response = middleware(request)
            order.append("returned")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(order, ["response", "returned"])
        schedule.assert_called_once()
        scheduled_request, callback = schedule.call_args.args
        self.assertIs(scheduled_request, request)

        with patch("config.middleware._post_bot_event") as post_event:
            callback()

        post_event.assert_called_once_with(
            event={
                "url": "http://testserver/roadmap/?view=popular",
                "user_agent": "ExampleCrawler/1.0",
                "status_code": 201,
            },
            path="/roadmap/",
            key="server-only-test-key",
        )

    def test_excludes_apis_framework_internals_and_static_assets(self):
        excluded_paths = (
            "/api/health",
            "/api/readme.md",
            "/api-docs/swagger.json",
            "/auth/me",
            "/admin/",
            "/static/projects/app.css",
            "/static/sitemap.xml",
            "/media/avatar.png",
            "/_next/chunk.js",
            "/favicon.ico",
            "/feed.xml",
        )

        with patch("config.middleware._schedule_best_effort") as schedule:
            for path in excluded_paths:
                with self.subTest(path=path):
                    request = self.factory.get(path, HTTP_USER_AGENT="Crawler/1.0")
                    SiteHitsBotMiddleware(lambda request: HttpResponse("page"))(request)

        schedule.assert_not_called()

    def test_excludes_non_document_responses_and_non_read_methods(self):
        with patch("config.middleware._schedule_best_effort") as schedule:
            SiteHitsBotMiddleware(lambda request: JsonResponse({"ok": True}))(
                self.factory.get("/health", HTTP_USER_AGENT="Crawler/1.0")
            )
            SiteHitsBotMiddleware(lambda request: HttpResponse("page"))(
                self.factory.post("/roadmap/", HTTP_USER_AGENT="Crawler/1.0")
            )

        schedule.assert_not_called()

    def test_keeps_crawler_files_and_markdown_trackable(self):
        tracked_paths = (
            "/robots.txt",
            "/llms.txt",
            "/llms-full.txt",
            "/sitemap.xml",
            "/sitemap-news.xml",
            "/docs/guide.md",
            "/docs/guide.markdown",
        )

        with patch("config.middleware._schedule_best_effort") as schedule:
            for path in tracked_paths:
                with self.subTest(path=path):
                    request = self.factory.get(path, HTTP_USER_AGENT="Crawler/1.0")
                    SiteHitsBotMiddleware(
                        lambda request: HttpResponse(
                            "crawler content",
                            content_type="text/plain",
                        )
                    )(request)

        self.assertEqual(schedule.call_count, len(tracked_paths))

    def test_runtime_wait_until_receives_awaitable(self):
        request = self.factory.get("/")
        scheduled_work = []
        request.waitUntil = scheduled_work.append
        callback = Mock()

        with patch("config.middleware.threading.Thread") as thread:
            _schedule_best_effort(request, callback)

        thread.assert_not_called()
        self.assertEqual(len(scheduled_work), 1)
        asyncio.run(scheduled_work[0])
        callback.assert_called_once_with()

    def test_falls_back_to_daemon_thread_without_wait_until(self):
        request = self.factory.get("/")
        callback = Mock()

        with patch("config.middleware.threading.Thread") as thread:
            _schedule_best_effort(request, callback)

        thread.assert_called_once_with(
            target=callback,
            name="sitehits-bot-event",
            daemon=True,
        )
        thread.return_value.start.assert_called_once_with()

    def test_collector_failures_never_escape_middleware(self):
        request = self.factory.get("/", HTTP_USER_AGENT="Crawler/1.0")
        middleware = SiteHitsBotMiddleware(lambda request: HttpResponse("page"))

        with patch(
            "config.middleware._schedule_best_effort",
            side_effect=RuntimeError("scheduler unavailable"),
        ):
            response = middleware(request)

        self.assertEqual(response.status_code, 200)


@override_settings(SITEHITS_BOT_TIMEOUT_SECONDS=0.25)
class SiteHitsBotCollectorTest(SimpleTestCase):
    key = "server-only-test-key"
    url = "https://featurerequest.io/roadmap/?view=popular"
    user_agent = "ExampleCrawler/1.0"
    path = "/roadmap/"

    @property
    def event(self):
        return {
            "url": self.url,
            "user_agent": self.user_agent,
            "status_code": 200,
        }

    def test_posts_required_headers_and_json_body(self):
        response = _CollectorResponse(202, b'{"accepted":false}')

        with (
            patch("config.middleware.urlopen", return_value=response) as open_url,
            patch("config.middleware.logger.warning") as warning,
        ):
            _post_bot_event(event=self.event, path=self.path, key=self.key)

        warning.assert_not_called()
        outbound_request = open_url.call_args.args[0]
        self.assertEqual(outbound_request.full_url, SITEHITS_BOT_EVENTS_URL)
        self.assertEqual(outbound_request.get_method(), "POST")
        self.assertEqual(
            outbound_request.get_header("Authorization"),
            f"Bearer {self.key}",
        )
        self.assertEqual(
            outbound_request.get_header("Content-type"),
            "application/json",
        )
        self.assertEqual(json.loads(outbound_request.data), self.event)
        self.assertEqual(open_url.call_args.kwargs["timeout"], 0.25)

    def test_logs_non_2xx_status_path_and_returned_error_without_secrets(self):
        returned_error = (
            f"collector rejected {self.url} for {self.user_agent} using {self.key}"
        ).encode()
        response = _CollectorResponse(
            503,
            json.dumps({"error": returned_error.decode()}).encode(),
        )

        with (
            patch("config.middleware.urlopen", return_value=response),
            patch("config.middleware.logger.warning") as warning,
        ):
            _post_bot_event(event=self.event, path=self.path, key=self.key)

        warning.assert_called_once()
        template, *values = warning.call_args.args
        log_line = template % tuple(values)
        self.assertIn("status=503", log_line)
        self.assertIn(f"path={self.path}", log_line)
        self.assertIn("collector rejected", log_line)
        self.assertNotIn(self.key, log_line)
        self.assertNotIn(self.url, log_line)
        self.assertNotIn(self.user_agent, log_line)

    def test_logs_http_error_response_message(self):
        error = HTTPError(
            SITEHITS_BOT_EVENTS_URL,
            429,
            "Too Many Requests",
            {},
            BytesIO(b'{"message":"rate limited"}'),
        )

        with (
            patch("config.middleware.urlopen", side_effect=error),
            patch("config.middleware.logger.warning") as warning,
        ):
            _post_bot_event(event=self.event, path=self.path, key=self.key)

        template, *values = warning.call_args.args
        log_line = template % tuple(values)
        self.assertIn("status=429", log_line)
        self.assertIn("error=rate limited", log_line)

    def test_logs_network_failure_without_sensitive_values(self):
        network_error = URLError(
            f"connection failed for {self.url} {self.user_agent} {self.key}"
        )

        with (
            patch("config.middleware.urlopen", side_effect=network_error),
            patch("config.middleware.logger.warning") as warning,
        ):
            _post_bot_event(event=self.event, path=self.path, key=self.key)

        template, *values = warning.call_args.args
        log_line = template % tuple(values)
        self.assertIn("status=network_error", log_line)
        self.assertIn(f"path={self.path}", log_line)
        self.assertIn("connection failed", log_line)
        self.assertNotIn(self.key, log_line)
        self.assertNotIn(self.url, log_line)
        self.assertNotIn(self.user_agent, log_line)
