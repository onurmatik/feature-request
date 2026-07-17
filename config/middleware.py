from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


logger = logging.getLogger(__name__)

SITEHITS_BOT_EVENTS_URL = "https://sitehits.io/api/bot-events"

_CRAWLER_TEXT_PATHS = {"/robots.txt", "/llms.txt", "/llms-full.txt"}
_DOCUMENT_CONTENT_TYPES = {
    "application/pdf",
    "application/xhtml+xml",
    "text/html",
    "text/markdown",
}
_STATIC_ASSET_SUFFIXES = {
    ".7z",
    ".avi",
    ".avif",
    ".bmp",
    ".br",
    ".bz2",
    ".css",
    ".csv",
    ".eot",
    ".flac",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".map",
    ".mjs",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".ogg",
    ".otf",
    ".png",
    ".rar",
    ".svg",
    ".tar",
    ".tgz",
    ".tif",
    ".tiff",
    ".ts",
    ".ttf",
    ".txt",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xml",
    ".xz",
    ".zip",
}
_INTERNAL_PREFIXES = (
    "/api",
    "/api-docs",
    "/auth",
    "/media",
    "/static",
    "/stripe",
    "/__debug__",
    "/__reload__",
    "/_next",
    "/_nuxt",
)
_HTTP_URL_RE = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_SITEHITS_KEY_RE = re.compile(r"\bshb_[A-Za-z0-9_-]+\b")


def _path_has_prefix(path: str, prefix: str) -> bool:
    normalized = prefix.rstrip("/") or "/"
    return path == normalized or path.startswith(f"{normalized}/")


def _is_crawler_file(path: str) -> bool:
    lowered = path.lower()
    if lowered in _CRAWLER_TEXT_PATHS:
        return True

    name = PurePosixPath(lowered).name
    if name.endswith((".md", ".markdown")):
        return True
    return name.startswith("sitemap") and name.endswith(".xml")


def _is_trackable_request(request, response) -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False

    path = str(request.path or "/")
    configured_prefixes = list(_INTERNAL_PREFIXES)
    configured_prefixes.extend(
        [
            str(getattr(settings, "STATIC_URL", "/static/") or "/static/"),
            str(getattr(settings, "MEDIA_URL", "/media/") or "/media/"),
            str(getattr(settings, "ADMIN_URL", "/admin/") or "/admin/"),
        ]
    )
    if any(_path_has_prefix(path, prefix) for prefix in configured_prefixes):
        return False

    if _is_crawler_file(path):
        return True

    suffix = PurePosixPath(path.lower()).suffix
    if suffix in _STATIC_ASSET_SUFFIXES:
        return False

    fetch_destination = str(request.META.get("HTTP_SEC_FETCH_DEST", "")).lower()
    if fetch_destination == "document":
        return True

    content_type = str(response.get("Content-Type", "")).split(";", 1)[0].lower()
    return content_type in _DOCUMENT_CONTENT_TYPES


def _returned_error_message(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return "no error message returned"

    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return text

    if isinstance(payload, dict):
        for field in ("error", "message", "detail"):
            value = payload.get(field)
            if value:
                return str(value)
    return text


def _safe_error_message(message: Any, *, url: str, user_agent: str, key: str) -> str:
    safe_message = " ".join(str(message or "unknown error").split())
    for sensitive_value in (key, url, user_agent):
        if sensitive_value:
            safe_message = safe_message.replace(sensitive_value, "[redacted]")
    safe_message = _SITEHITS_KEY_RE.sub("[redacted-key]", safe_message)
    safe_message = _HTTP_URL_RE.sub("[redacted-url]", safe_message)
    return safe_message[:500]


def _log_collector_failure(
    *,
    status: int | str,
    path: str,
    message: Any,
    url: str,
    user_agent: str,
    key: str,
) -> None:
    logger.warning(
        "SiteHits bot event failed: status=%s path=%s error=%s",
        status,
        path,
        _safe_error_message(message, url=url, user_agent=user_agent, key=key),
    )


def _post_bot_event(*, event: dict[str, Any], path: str, key: str) -> None:
    url = str(event["url"])
    user_agent = str(event["user_agent"])

    try:
        request = Request(
            SITEHITS_BOT_EVENTS_URL,
            data=json.dumps(event, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(
            request,
            timeout=float(getattr(settings, "SITEHITS_BOT_TIMEOUT_SECONDS", 2.0)),
        ) as collector_response:
            status = int(collector_response.getcode())
            if 200 <= status < 300:
                # A 202 response is healthy even when its JSON says accepted=false.
                return
            message = _returned_error_message(collector_response.read())
    except HTTPError as exc:
        _log_collector_failure(
            status=exc.code,
            path=path,
            message=_returned_error_message(exc.read()),
            url=url,
            user_agent=user_agent,
            key=key,
        )
        return
    except URLError as exc:
        _log_collector_failure(
            status="network_error",
            path=path,
            message=exc.reason,
            url=url,
            user_agent=user_agent,
            key=key,
        )
        return
    except Exception as exc:  # Collector work must never escape its background task.
        _log_collector_failure(
            status="network_error",
            path=path,
            message=exc,
            url=url,
            user_agent=user_agent,
            key=key,
        )
        return

    _log_collector_failure(
        status=status,
        path=path,
        message=message,
        url=url,
        user_agent=user_agent,
        key=key,
    )


async def _run_callback_async(callback: Callable[[], None]) -> None:
    await asyncio.to_thread(callback)


def _runtime_wait_until(request) -> Callable[[Awaitable[None]], None] | None:
    for name in ("waitUntil", "wait_until"):
        hook = getattr(request, name, None)
        if callable(hook):
            return hook

    scope = getattr(request, "scope", None)
    if isinstance(scope, dict):
        for name in ("waitUntil", "wait_until"):
            hook = scope.get(name)
            if callable(hook):
                return hook
    return None


def _schedule_best_effort(request, callback: Callable[[], None]) -> None:
    wait_until = _runtime_wait_until(request)
    if wait_until is not None:
        awaitable = _run_callback_async(callback)
        try:
            wait_until(awaitable)
            return
        except Exception:
            awaitable.close()

    try:
        threading.Thread(
            target=callback,
            name="sitehits-bot-event",
            daemon=True,
        ).start()
    except Exception:
        # Scheduling is best effort too; it must not affect the page response.
        return


class SiteHitsBotMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        try:
            key = str(getattr(settings, "SITEHITS_BOT_KEY", "") or "").strip()
            if not key or not _is_trackable_request(request, response):
                return response

            path = str(request.path or "/")
            event = {
                "url": request.build_absolute_uri(),
                "user_agent": str(request.META.get("HTTP_USER_AGENT", "")),
                "status_code": int(response.status_code),
            }
            _schedule_best_effort(
                request,
                lambda: _post_bot_event(event=event, path=path, key=key),
            )
        except Exception:
            # URL construction and runtime scheduling are non-critical.
            pass

        return response
