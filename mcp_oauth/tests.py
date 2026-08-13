from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_embedded_mcp import (
    CallbackProfile,
    ClientMetadataError,
    callback_profile,
    canonical_resource_equal,
    fetch_client_metadata_document,
    parse_client_metadata_document,
    parse_public_client_registration,
    validate_client_metadata_url,
)

from agent_runtime.models import AgentAuditEvent
from .models import (
    ClientMetadataCache,
    OAuthAccessToken,
    OAuthApplication,
    OAuthCleanupRun,
    OAuthConsent,
    OAuthGrant,
    OAuthRefreshFamily,
    OAuthRefreshToken,
    OAuthSecurityEvent,
    RateLimitBucket,
)
from .operations import send_deduplicated_admin_alert
from .services import (
    OAuthProtocolError,
    client_id_digest,
    enforce_rate_limit,
    resolve_client_application,
    revoke_application_credentials,
    revoke_consent_credentials,
    verify_pkce,
)


@override_settings(DEBUG=True)
class MetadataAndRegistrationTest(TestCase):
    def test_discovery_is_public_cors_and_cimd_first(self):
        response = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")
        payload = response.json()
        self.assertTrue(payload["client_id_metadata_document_supported"])
        self.assertEqual(payload["token_endpoint_auth_methods_supported"], ["none"])
        self.assertEqual(
            payload["authorization_endpoint"],
            "http://127.0.0.1:8000/oauth/authorize/",
        )
        self.assertEqual(
            payload["token_endpoint"], "http://127.0.0.1:8000/oauth/token/"
        )
        self.assertEqual(
            payload["registration_endpoint"],
            "http://127.0.0.1:8000/oauth/register/",
        )
        self.assertEqual(
            payload["revocation_endpoint"],
            "http://127.0.0.1:8000/oauth/revoke/",
        )
        resource = self.client.get("/.well-known/oauth-protected-resource/mcp").json()
        self.assertEqual(resource["resource"], "http://127.0.0.1:8001/mcp")
        self.assertEqual(resource["scopes_supported"], ["read"])

    def test_slashless_oauth_aliases_are_not_published(self):
        for path in (
            "/oauth/authorize",
            "/oauth/token",
            "/oauth/revoke",
            "/oauth/register",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    @override_settings(
        DEBUG=False,
        FEATURE_REQUEST_MCP_PRODUCTION_ENABLED=False,
        SECURE_SSL_REDIRECT=False,
    )
    def test_production_oauth_surface_is_hidden_until_release_enablement(self):
        for path in (
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, secure=True).status_code, 404)
        for path in (
            "/oauth/authorize/",
            "/oauth/register/",
            "/oauth/token/",
            "/oauth/revoke/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, secure=True).status_code, 404)

    @override_settings(
        DEBUG=False,
        FEATURE_REQUEST_MCP_PRODUCTION_ENABLED=True,
        SECURE_SSL_REDIRECT=False,
    )
    def test_enabled_production_discovery_surface_remains_available(self):
        response = self.client.get(
            "/.well-known/oauth-authorization-server", secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["authorization_endpoint"],
            "http://127.0.0.1:8000/oauth/authorize/",
        )

    def test_resource_comparison_casefolds_only_scheme_and_host(self):
        self.assertTrue(
            canonical_resource_equal(
                "HTTP://LOCALHOST:8000/mcp", "http://localhost:8000/mcp"
            )
        )
        self.assertFalse(
            canonical_resource_equal(
                "http://localhost:8000/mcp/", "http://localhost:8000/mcp"
            )
        )
        self.assertFalse(
            canonical_resource_equal(
                "http://localhost:8000/%6dcp", "http://localhost:8000/mcp"
            )
        )
        self.assertFalse(
            canonical_resource_equal(
                "http://localhost:080/mcp", "http://localhost:80/mcp"
            )
        )
        self.assertFalse(
            canonical_resource_equal(
                "http://localhost:/mcp", "http://localhost/mcp"
            )
        )

    def test_resource_indicator_must_occur_exactly_once(self):
        from django_embedded_mcp import CanonicalResourceError, canonical_resource_from_pairs

        resource = "http://127.0.0.1:8001/mcp"
        with self.assertRaises(CanonicalResourceError):
            canonical_resource_from_pairs(
                [("resource", resource), ("resource", resource)],
                expected=resource,
            )

    def test_callback_profiles_are_exact(self):
        self.assertEqual(
            callback_profile("https://chatgpt.com/connector/oauth/callback-1"),
            CallbackProfile.CHATGPT,
        )
        self.assertEqual(
            callback_profile("https://claude.ai/api/mcp/auth_callback"),
            CallbackProfile.CLAUDE,
        )
        self.assertEqual(
            callback_profile("http://127.0.0.1:43210/oauth/callback"),
            CallbackProfile.CODEX,
        )
        self.assertEqual(
            callback_profile("http://localhost:43210/callback"),
            CallbackProfile.CLAUDE_CODE,
        )

    def test_dcr_public_profile_and_limits(self):
        registration = parse_public_client_registration(
            json.dumps(
                {
                    "client_name": "Codex",
                    "application_type": "native",
                    "redirect_uris": ["http://127.0.0.1:43210/callback"],
                    "token_endpoint_auth_method": "none",
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "scope": "read write",
                }
            ).encode(),
            supported_scopes=("read", "write"),
            default_scopes=("read",),
        )
        self.assertEqual(registration.application_type, "native")
        response = self.client.post(
            "/oauth/register/",
            data=json.dumps(
                {
                    "client_name": "Codex",
                    "application_type": "native",
                    "redirect_uris": ["http://127.0.0.1:43210/callback"],
                    "token_endpoint_auth_method": "none",
                    "scope": "read write",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("client_secret", response.json())

    def test_cimd_fetch_bounds_json_and_identity(self):
        client_id = "https://client.example/oauth/metadata.json"

        def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "application/json", "cache-control": "max-age=600"},
                json={
                    "client_id": client_id,
                    "client_name": "Example Agent",
                    "application_type": "web",
                    "redirect_uris": [
                        "https://chatgpt.com/connector/oauth/callback-1"
                    ],
                    "scope": "read",
                },
            )

        document = fetch_client_metadata_document(
            client_id, transport=httpx.MockTransport(handler)
        )
        self.assertEqual(document.client_id, client_id)
        self.assertEqual(document.cache_seconds, 600)

    def test_cimd_fetch_rejects_duplicate_json_keys(self):
        client_id = "https://client.example/oauth/metadata.json"
        body = (
            '{"client_id":"https://client.example/oauth/metadata.json",'
            '"client_id":"https://attacker.example/client.json",'
            '"client_name":"Ambiguous",'
            '"application_type":"web",'
            '"redirect_uris":["https://chatgpt.com/connector/oauth/callback-1"],'
            '"scope":"read"}'
        )

        def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=body.encode(),
            )

        with self.assertRaises(ClientMetadataError):
            fetch_client_metadata_document(
                client_id, transport=httpx.MockTransport(handler)
            )

    def test_cimd_rejects_ssrf_url_shapes_and_private_dns(self):
        invalid = (
            "http://client.example/oauth/client.json",
            "https://user@client.example/oauth/client.json",
            "https://127.0.0.1/oauth/client.json",
            "https://client.example/oauth/../client.json",
            "https://client.example/oauth/%2e%2e/client.json",
            "https://client.example/oauth/client.json?tenant=1",
            "https://client.example/oauth/client.json#fragment",
            "https://client.example\\evil/oauth/client.json",
            "https://client.example/oauth/client.json\n",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ClientMetadataError):
                validate_client_metadata_url(value)
        from django_embedded_mcp import cimd

        with patch.object(
            cimd.socket,
            "getaddrinfo",
            return_value=[(2, 1, 6, "", ("127.0.0.1", 443))],
        ), self.assertRaises(ClientMetadataError):
            cimd._validate_public_dns("client.example")

        with patch.object(
            cimd.socket,
            "getaddrinfo",
            side_effect=lambda *args, **kwargs: time.sleep(0.05),
        ), self.assertRaises(ClientMetadataError) as timed_out:
            cimd._validate_public_dns("client.example", timeout=0.001)
        self.assertTrue(timed_out.exception.retryable)

    def test_unproven_https_callback_and_application_type_mismatch_are_rejected(self):
        client_id = "https://client.example/oauth/client.json"
        base = {
            "client_id": client_id,
            "client_name": "Unknown web client",
            "application_type": "web",
            "redirect_uris": ["https://unverified.example/oauth/callback"],
            "token_endpoint_auth_method": "none",
            "scope": "read",
        }
        with self.assertRaises(ClientMetadataError):
            parse_client_metadata_document(base, fetched_url=client_id)
        with self.assertRaises(ClientMetadataError):
            parse_client_metadata_document(
                {
                    **base,
                    "application_type": "native",
                    "redirect_uris": [
                        "https://chatgpt.com/connector/oauth/callback-1"
                    ],
                },
                fetched_url=client_id,
            )
        with self.assertRaises(ClientMetadataError):
            parse_client_metadata_document(
                {
                    **base,
                    "redirect_uris": [
                        "https://chatgpt.com/connector/oauth/callback-1"
                    ],
                    "grant_types": ["client_credentials"],
                },
                fetched_url=client_id,
            )

    def test_callback_profiles_reject_dot_segments(self):
        for redirect_uri in (
            "http://127.0.0.1:43210/../callback",
            "http://127.0.0.1:43210/%2e%2e/callback",
            "http://127.0.0.1:43210/callback?tenant=1",
        ):
            with self.subTest(redirect_uri=redirect_uri), self.assertRaises(
                ClientMetadataError
            ):
                parse_client_metadata_document(
                    {
                        "client_id": "https://client.example/oauth/client.json",
                        "client_name": "Codex",
                        "application_type": "native",
                        "redirect_uris": [redirect_uri],
                        "token_endpoint_auth_method": "none",
                        "scope": "read",
                    },
                    fetched_url="https://client.example/oauth/client.json",
                )

    def test_cimd_redirect_content_type_size_and_cache_bounds(self):
        client_id = "https://client.example/oauth/client.json"

        def redirect_handler(request):
            if request.url.host == "client.example":
                return httpx.Response(
                    302, headers={"location": "https://metadata.example/client.json"}
                )
            return httpx.Response(
                200,
                headers={
                    "content-type": "application/oauth-client+json",
                    "cache-control": "max-age=999999",
                },
                json={
                    "client_id": client_id,
                    "client_name": "Redirected Agent",
                    "application_type": "web",
                    "redirect_uris": [
                        "https://chatgpt.com/connector/oauth/callback-1"
                    ],
                    "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"],
                    "scope": "read",
                },
            )

        document = fetch_client_metadata_document(
            client_id, transport=httpx.MockTransport(redirect_handler)
        )
        self.assertEqual(document.cache_seconds, 3600)

        def dot_segment_redirect(request):
            return httpx.Response(302, headers={"location": "../client.json"})

        with self.assertRaises(ClientMetadataError):
            fetch_client_metadata_document(
                client_id, transport=httpx.MockTransport(dot_segment_redirect)
            )

        def too_large(request):
            return httpx.Response(
                200,
                headers={"content-type": "application/json", "content-length": "6000"},
                content=b"{}",
            )

        with self.assertRaises(ClientMetadataError):
            fetch_client_metadata_document(
                client_id, transport=httpx.MockTransport(too_large)
            )

        def html(request):
            return httpx.Response(200, headers={"content-type": "text/html"}, text="no")

        with self.assertRaises(ClientMetadataError):
            fetch_client_metadata_document(client_id, transport=httpx.MockTransport(html))

    def test_expired_cimd_cache_is_fail_closed(self):
        client_id = "https://client.example/oauth/client.json"
        ClientMetadataCache.objects.create(
            client_id=client_id,
            document={"client_id": client_id},
            document_sha256="a" * 64,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        with patch(
            "mcp_oauth.services.fetch_client_metadata_document",
            side_effect=ClientMetadataError("unavailable", retryable=True),
        ), self.assertRaises(OAuthProtocolError):
            resolve_client_application(client_id)

    def test_invalid_fresh_cimd_cache_is_protocol_native_fail_closed(self):
        client_id = "https://client.example/oauth/client.json"
        document = {
            "client_id": client_id,
            "client_name": "Cached client",
            "application_type": "web",
            "redirect_uris": [
                "https://chatgpt.com/connector/oauth/callback-1"
            ],
            "scope": "read",
        }
        ClientMetadataCache.objects.create(
            client_id=client_id,
            document=document,
            document_sha256="a" * 64,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        with self.assertRaises(OAuthProtocolError) as caught:
            resolve_client_application(client_id)
        self.assertEqual(caught.exception.error, "invalid_client")
        self.assertNotIn(client_id, caught.exception.description)

    def test_dcr_rejects_wrong_content_type_and_oversize_or_excess_callbacks(self):
        wrong_type = self.client.post(
            "/oauth/register/", data="{}", content_type="text/plain"
        )
        self.assertEqual(wrong_type.status_code, 400)
        self.assertEqual(wrong_type.json()["error"], "invalid_client_metadata")
        oversized = self.client.post(
            "/oauth/register/",
            data=b"x" * (16 * 1024 + 1),
            content_type="application/json",
        )
        self.assertEqual(oversized.status_code, 413)
        callbacks = [f"https://agent.example/callback/{index}" for index in range(11)]
        too_many = self.client.post(
            "/oauth/register/",
            data=json.dumps(
                {
                    "client_name": "Too many",
                    "application_type": "web",
                    "redirect_uris": callbacks,
                    "token_endpoint_auth_method": "none",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(too_many.status_code, 400)
        self.assertEqual(too_many.json()["error"], "invalid_redirect_uri")

        malformed = self.client.post(
            "/oauth/register/",
            data=json.dumps(
                {
                    "client_name": "Malformed",
                    "application_type": "native",
                    "redirect_uris": [{}],
                    "token_endpoint_auth_method": "none",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()["error"], "invalid_redirect_uri")

        with self.assertRaises(ClientMetadataError):
            parse_client_metadata_document(
                {
                    "client_id": "https://client.example/oauth/client.json",
                    "client_name": "Malformed",
                    "application_type": "native",
                    "redirect_uris": [{}],
                    "token_endpoint_auth_method": "none",
                    "scope": "read",
                },
                fetched_url="https://client.example/oauth/client.json",
            )

    def test_persistent_registration_rate_limit(self):
        request = RequestFactory().post("/oauth/register/", REMOTE_ADDR="203.0.113.5")
        now = timezone.now().replace(second=0, microsecond=0)
        from django_embedded_mcp import credential_digest

        RateLimitBucket.objects.create(
            bucket_key=credential_digest("register:source:203.0.113.5"),
            window_start=now,
            count=30,
        )
        with patch("mcp_oauth.services.timezone.now", return_value=now), self.assertRaises(
            OAuthProtocolError
        ) as caught:
            enforce_rate_limit(request, "register")
        self.assertEqual(caught.exception.status, 429)

    def test_client_bucket_is_created_only_after_client_verification(self):
        request = RequestFactory().post("/oauth/token/", REMOTE_ADDR="203.0.113.8")
        enforce_rate_limit(request, "token", client_id="unverified-client")
        self.assertEqual(RateLimitBucket.objects.count(), 2)
        enforce_rate_limit(
            request,
            "token",
            client_id="verified-client",
            verified_client_only=True,
        )
        self.assertEqual(RateLimitBucket.objects.count(), 3)

    def test_authorize_token_and_revoke_share_approved_rate_budgets(self):
        from django_embedded_mcp import credential_digest

        now = timezone.now().replace(second=0, microsecond=0)
        source = "203.0.113.9"
        request = RequestFactory().post("/oauth/token/", REMOTE_ADDR=source)
        RateLimitBucket.objects.create(
            bucket_key=credential_digest(f"oauth:source:{source}"),
            window_start=now,
            count=120,
        )
        with patch("mcp_oauth.services.timezone.now", return_value=now):
            for action in ("authorize", "token", "revoke"):
                with self.subTest(action=action), self.assertRaises(
                    OAuthProtocolError
                ) as caught:
                    enforce_rate_limit(request, action)
                self.assertEqual(caught.exception.status, 429)

        client_id = "verified-shared-client"
        RateLimitBucket.objects.create(
            bucket_key=credential_digest(f"oauth:client:{client_id}"),
            window_start=now,
            count=600,
        )
        with patch("mcp_oauth.services.timezone.now", return_value=now):
            for action in ("authorize", "token", "revoke"):
                with self.subTest(client_action=action), self.assertRaises(
                    OAuthProtocolError
                ) as caught:
                    enforce_rate_limit(
                        request,
                        action,
                        client_id=client_id,
                        verified_client_only=True,
                    )
                self.assertEqual(caught.exception.status, 429)

    def test_registration_endpoint_returns_protocol_rate_limit_headers(self):
        now = timezone.now().replace(second=0, microsecond=0)
        from django_embedded_mcp import credential_digest

        RateLimitBucket.objects.create(
            bucket_key=credential_digest("register:source:127.0.0.1"),
            window_start=now,
            count=30,
        )
        with patch("mcp_oauth.services.timezone.now", return_value=now):
            response = self.client.post(
                "/oauth/register/",
                data=json.dumps(
                    {
                        "client_name": "Rate limited client",
                        "application_type": "native",
                        "redirect_uris": ["http://127.0.0.1:43210/callback"],
                        "token_endpoint_auth_method": "none",
                    }
                ),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "60")
        self.assertEqual(response.json()["error"], "rate_limited")
        self.assertEqual(response["Cache-Control"], "no-store")


@override_settings(DEBUG=True)
class OAuthStateMachineTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="oauth@example.com", handle="oauthuser")
        self.client.force_login(self.user)
        body = {
            "client_name": "Codex",
            "application_type": "native",
            "redirect_uris": ["http://127.0.0.1:43210/callback"],
            "token_endpoint_auth_method": "none",
            "scope": "read write",
        }
        response = self.client.post(
            "/oauth/register/", data=json.dumps(body), content_type="application/json"
        )
        self.client_id = response.json()["client_id"]
        self.application = OAuthApplication.objects.get(client_id=self.client_id)
        self.redirect_uri = body["redirect_uris"][0]

    @staticmethod
    def _challenge(verifier):
        return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    def test_pkce_verifier_rejects_non_unreserved_characters_without_normalizing(self):
        invalid = "v" * 42 + "!"
        self.assertFalse(verify_pkce(invalid, self._challenge(invalid)))
        unicode_invalid = "v" * 42 + "é"
        self.assertFalse(
            verify_pkce(unicode_invalid, self._challenge(unicode_invalid))
        )

    def _authorize(self, scope="read write"):
        verifier = "v" * 64
        response = self.client.get(
            "/oauth/authorize/",
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": scope,
                "state": "opaque-client-state",
                "code_challenge": self._challenge(verifier),
                "code_challenge_method": "S256",
                "resource": "http://127.0.0.1:8001/mcp",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertIn("default-src 'none'", response["Content-Security-Policy"])
        self.assertIn("form-action 'self'", response["Content-Security-Policy"])
        self.assertEqual(response.context["client_hostname"], "127.0.0.1")
        self.assertEqual(response.context["resource"], "http://127.0.0.1:8001/mcp")
        self.assertEqual(response.context["scopes"], scope.split())
        resume = response.context["resume"]
        approved = self.client.post(
            "/oauth/authorize/", {"resume": resume, "decision": "allow"}
        )
        query = parse_qs(urlsplit(approved["Location"]).query)
        self.assertEqual(query["state"], ["opaque-client-state"])
        self.assertEqual(query["iss"], ["http://127.0.0.1:8000"])
        return query["code"][0], verifier

    def test_write_only_step_up_scope_can_issue_a_contract_mutation_token(self):
        code, verifier = self._authorize(scope="write")
        response = self.client.post(
            "/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": verifier,
                    "resource": "http://127.0.0.1:8001/mcp",
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["scope"], "write")
        self.assertEqual(OAuthAccessToken.objects.get().scope, "write")

    def test_code_exchange_refresh_rotation_replay_and_revoke(self):
        code, verifier = self._authorize()
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "code_verifier": verifier,
            "resource": "http://127.0.0.1:8001/mcp",
        }
        response = self.client.post(
            "/oauth/token/",
            data=urlencode(payload),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        tokens = response.json()
        self.assertTrue(tokens["access_token"].startswith("mcp_at_"))
        self.assertTrue(tokens["refresh_token"].startswith("mcp_rt_"))
        self.assertTrue(code.startswith("mcp_ac_"))
        grant = OAuthGrant.objects.get()
        self.assertGreaterEqual((grant.expires - grant.created).total_seconds(), 59)
        self.assertLessEqual((grant.expires - grant.created).total_seconds(), 61)
        access = OAuthAccessToken.objects.get()
        self.assertGreaterEqual((access.expires - access.created).total_seconds(), 899)
        self.assertLessEqual((access.expires - access.created).total_seconds(), 901)
        family = OAuthRefreshFamily.objects.get()
        self.assertGreaterEqual(
            (family.expires_at - family.created_at).total_seconds(),
            (30 * 24 * 60 * 60) - 1,
        )
        self.assertLessEqual(
            (family.expires_at - family.created_at).total_seconds(),
            (30 * 24 * 60 * 60) + 1,
        )
        self.assertFalse(OAuthAccessToken.objects.exclude(token="").exists())
        self.assertFalse(OAuthRefreshToken.objects.exclude(token="").exists())
        self.assertFalse(OAuthGrant.objects.exclude(code="").exists())
        rotate = self.client.post(
            "/oauth/token/",
            data=urlencode({
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": self.client_id,
                "resource": "http://127.0.0.1:8001/mcp",
            }),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(rotate.status_code, 200)
        replay = self.client.post(
            "/oauth/token/",
            data=urlencode({
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": self.client_id,
                "resource": "http://127.0.0.1:8001/mcp",
            }),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(replay.status_code, 400)
        self.assertIsNotNone(OAuthRefreshFamily.objects.get().revoked_at)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ADMINS=[("FeatureRequest Admin", "ops@example.com")],
    )
    def test_authorization_code_replay_revokes_issued_family_even_after_code_expiry(self):
        code, verifier = self._authorize()
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "code_verifier": verifier,
            "resource": "http://127.0.0.1:8001/mcp",
        }
        issued = self.client.post(
            "/oauth/token/",
            data=urlencode(payload),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(issued.status_code, 200)
        OAuthGrant.objects.update(expires=timezone.now() - timedelta(seconds=1))
        replay = self.client.post(
            "/oauth/token/",
            data=urlencode(payload),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(replay.json()["error"], "invalid_grant")
        self.assertIsNotNone(OAuthRefreshFamily.objects.get().revoked_at)
        self.assertIsNotNone(OAuthAccessToken.objects.get().revoked_at)
        self.assertEqual([message.to for message in mail.outbox], [["ops@example.com"]])
        serialized = json.dumps(
            list(OAuthSecurityEvent.objects.values("details", "resource", "error_code"))
        )
        self.assertNotIn(code, serialized)

    def test_wrong_resource_is_protocol_native(self):
        response = self.client.post(
            "/oauth/token/",
            data=urlencode({
                "grant_type": "refresh_token",
                "refresh_token": "not-a-token",
                "client_id": self.client_id,
                "resource": "https://other.example/mcp",
            }),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_target")

    def test_confidential_client_auth_is_rejected_on_public_token_endpoint(self):
        response = self.client.post(
            "/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": "not-a-token",
                    "client_id": self.client_id,
                    "client_secret": "must-not-be-accepted",
                    "resource": "http://127.0.0.1:8001/mcp",
                }
            ),
            content_type="application/x-www-form-urlencoded",
            HTTP_AUTHORIZATION="Basic Zm9vOmJhcg==",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_client")
        serialized = json.dumps(
            list(OAuthSecurityEvent.objects.values("details", "error_code"))
        )
        self.assertNotIn("must-not-be-accepted", serialized)

    def test_anonymous_login_continuation_hides_state_at_rest(self):
        self.client.logout()
        verifier = "z" * 64
        response = self.client.get(
            "/oauth/authorize/",
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "read",
                "state": "private-state-value",
                "code_challenge": self._challenge(verifier),
                "code_challenge_method": "S256",
                "resource": "http://127.0.0.1:8001/mcp",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/sign-in?next="))
        from .models import PendingAuthorization

        pending = PendingAuthorization.objects.get()
        self.assertNotIn(b"private-state-value", bytes(pending.encrypted_payload))
        self.assertEqual(len(pending.handle_digest), 64)
        self.assertGreaterEqual(
            (pending.expires_at - pending.created_at).total_seconds(), 599
        )
        self.assertLessEqual(
            (pending.expires_at - pending.created_at).total_seconds(), 601
        )

        resume = parse_qs(urlsplit(response["Location"]).query)["next"][0]
        resume_handle = parse_qs(urlsplit(resume).query)["resume"][0]
        self.client.force_login(self.user)
        continued = self.client.get("/oauth/authorize/", {"resume": resume_handle})
        self.assertEqual(continued.status_code, 200)
        self.assertEqual(continued.context["scopes"], ["read"])
        self.assertEqual(
            continued.context["resource"], "http://127.0.0.1:8001/mcp"
        )

    def test_consent_deny_redirects_with_state_and_issuer(self):
        verifier = "d" * 64
        response = self.client.get(
            "/oauth/authorize/",
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "read",
                "state": "deny-state",
                "code_challenge": self._challenge(verifier),
                "code_challenge_method": "S256",
                "resource": "http://127.0.0.1:8001/mcp",
            },
        )
        denied = self.client.post(
            "/oauth/authorize/",
            {"resume": response.context["resume"], "decision": "deny"},
        )
        query = parse_qs(urlsplit(denied["Location"]).query)
        self.assertEqual(query["error"], ["access_denied"])
        self.assertEqual(query["state"], ["deny-state"])
        self.assertEqual(query["iss"], ["http://127.0.0.1:8000"])

    def test_valid_callback_receives_authorization_error_with_issuer(self):
        verifier = "e" * 64
        response = self.client.get(
            "/oauth/authorize/",
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "admin",
                "state": "error-state",
                "code_challenge": self._challenge(verifier),
                "code_challenge_method": "S256",
                "resource": "http://127.0.0.1:8001/mcp",
            },
        )
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlsplit(response["Location"]).query)
        self.assertEqual(query["error"], ["invalid_scope"])
        self.assertEqual(query["state"], ["error-state"])
        self.assertEqual(query["iss"], ["http://127.0.0.1:8000"])

    def test_unregistered_callback_is_never_used_for_error_redirect(self):
        verifier = "f" * 64
        response = self.client.get(
            "/oauth/authorize/",
            {
                "client_id": self.client_id,
                "redirect_uri": "http://127.0.0.1:49999/callback",
                "response_type": "code",
                "scope": "admin",
                "state": "error-state",
                "code_challenge": self._challenge(verifier),
                "code_challenge_method": "S256",
                "resource": "http://127.0.0.1:8001/mcp",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Location", response)
        self.assertEqual(response.json()["error"], "invalid_request")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ADMINS=[("FeatureRequest Admin", "ops@example.com")],
    )
    def test_refresh_replay_alerts_once_without_storing_raw_token(self):
        code, verifier = self._authorize()
        exchanged = self.client.post(
            "/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": verifier,
                    "resource": "http://127.0.0.1:8001/mcp",
                }
            ),
            content_type="application/x-www-form-urlencoded",
        ).json()
        refresh_payload = {
            "grant_type": "refresh_token",
            "refresh_token": exchanged["refresh_token"],
            "client_id": self.client_id,
            "resource": "http://127.0.0.1:8001/mcp",
        }
        self.client.post(
            "/oauth/token/",
            data=urlencode(refresh_payload),
            content_type="application/x-www-form-urlencoded",
        )
        self.client.post(
            "/oauth/token/",
            data=urlencode(refresh_payload),
            content_type="application/x-www-form-urlencoded",
        )
        self.client.post(
            "/oauth/token/",
            data=urlencode(refresh_payload),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual([message.to for message in mail.outbox], [["ops@example.com"]])
        serialized = json.dumps(
            list(OAuthSecurityEvent.objects.values("details", "resource", "error_code"))
        )
        self.assertNotIn(exchanged["refresh_token"], serialized)
        self.assertNotIn(self.redirect_uri, serialized)

    def test_consent_and_application_revocation_cascade(self):
        code, verifier = self._authorize()
        tokens = self.client.post(
            "/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": verifier,
                    "resource": "http://127.0.0.1:8001/mcp",
                }
            ),
            content_type="application/x-www-form-urlencoded",
        ).json()
        consent = OAuthConsent.objects.filter(decision="approved").latest("id")
        revoke_consent_credentials(consent)
        self.assertFalse(
            OAuthAccessToken.objects.get().is_valid()
        )
        self.assertIsNotNone(OAuthRefreshFamily.objects.get().revoked_at)
        revoke_application_credentials(self.application)
        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.revoked_at)
        self.assertNotIn(
            tokens["access_token"],
            json.dumps(list(OAuthAccessToken.objects.values()), default=str),
        )

    def test_direct_admin_consent_revocation_triggers_immediate_cascade(self):
        code, verifier = self._authorize()
        response = self.client.post(
            "/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": verifier,
                    "resource": "http://127.0.0.1:8001/mcp",
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        consent = OAuthConsent.objects.filter(decision="approved").latest("id")
        consent.revoked_at = timezone.now()
        consent.save(update_fields=["revoked_at", "updated_at"])
        self.assertIsNotNone(OAuthAccessToken.objects.get().revoked_at)
        self.assertIsNotNone(OAuthRefreshFamily.objects.get().revoked_at)

    def test_direct_admin_application_revocation_triggers_immediate_cascade(self):
        code, verifier = self._authorize()
        response = self.client.post(
            "/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": verifier,
                    "resource": "http://127.0.0.1:8001/mcp",
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        self.application.revoked_at = timezone.now()
        self.application.save(update_fields=["revoked_at", "updated"])
        self.assertIsNotNone(OAuthAccessToken.objects.get().revoked_at)
        self.assertIsNotNone(OAuthRefreshFamily.objects.get().revoked_at)

    def test_user_deactivation_revokes_every_refresh_family_member(self):
        code, verifier = self._authorize()
        response = self.client.post(
            "/oauth/token/",
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": verifier,
                    "resource": "http://127.0.0.1:8001/mcp",
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 200)
        self.user.is_active = False
        self.user.save(update_fields=["is_active", "updated_at"])
        self.assertIsNotNone(OAuthAccessToken.objects.get().revoked_at)
        self.assertIsNotNone(OAuthRefreshFamily.objects.get().revoked_at)
        refresh = OAuthRefreshToken.objects.get()
        self.assertIsNotNone(refresh.revoked)
        self.assertIsNone(refresh.access_token_id)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ADMINS=[("FeatureRequest Admin", "ops@example.com")],
)
@override_settings(DEBUG=True)
class OAuthOperationsTest(TestCase):
    def test_rate_limit_backend_failure_alerts_and_fails_closed(self):
        request = RequestFactory().post(
            "/oauth/register/",
            REMOTE_ADDR="203.0.113.7",
        )
        with patch(
            "mcp_oauth.services.RateLimitBucket.objects.select_for_update",
            side_effect=DatabaseError("backend unavailable"),
        ), self.assertRaises(OAuthProtocolError) as caught:
            enforce_rate_limit(request, "register")
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(caught.exception.error, "temporarily_unavailable")
        self.assertEqual([message.to for message in mail.outbox], [["ops@example.com"]])
        event = OAuthSecurityEvent.objects.get(
            event_type="alert:rate_limit_backend_anomaly"
        )
        self.assertEqual(
            event.details,
            {"action": "register", "bucket_class": "baseline"},
        )

    def test_cleanup_is_bounded_records_run_and_removes_stale_dcr(self):
        User = get_user_model()
        user = User.objects.create_user(email="cleanup@example.com", handle="cleanup")
        application = OAuthApplication.objects.create(
            client_id="frc_cleanup",
            client_type="public",
            authorization_grant_type="authorization-code",
            client_secret="",
            hash_client_secret=False,
            name="Cleanup",
            skip_authorization=False,
            redirect_uris="http://127.0.0.1:43111/callback",
            application_type="native",
            allowed_scopes=["read"],
            callback_profiles=["exact_registered_ip_loopback"],
            registration_source="dcr",
            user=user,
        )
        OAuthApplication.objects.filter(pk=application.pk).update(
            created=timezone.now() - timedelta(days=31)
        )
        audit = AgentAuditEvent.objects.create(
            request_id="old",
            authenticated_actor_id=str(user.pk),
            authenticated_client_id="client-" + "a" * 32,
            tool_name="list_projects",
            redacted_input_sha256="b" * 64,
            result_code="success",
        )
        AgentAuditEvent.objects.filter(pk=audit.pk).update(
            created_at=timezone.now() - timedelta(days=91)
        )
        output = StringIO()
        call_command("cleanup_mcp_oauth", batch_size=500, stdout=output)
        self.assertFalse(OAuthApplication.objects.filter(pk=application.pk).exists())
        run = OAuthCleanupRun.objects.get()
        self.assertTrue(run.success)
        self.assertIn("MCP/OAuth cleanup complete", output.getvalue())

    def test_cleanup_retains_consumed_code_for_family_replay_window(self):
        User = get_user_model()
        user = User.objects.create_user(
            email="grant-retention@example.com", handle="grantretention"
        )
        application = OAuthApplication.objects.create(
            client_id="frc_grant_retention",
            client_type="public",
            authorization_grant_type="authorization-code",
            client_secret="",
            hash_client_secret=False,
            name="Grant retention",
            skip_authorization=False,
            redirect_uris="http://127.0.0.1:43112/callback",
            application_type="native",
            allowed_scopes=["read"],
            callback_profiles=["exact_registered_ip_loopback"],
            registration_source="dcr",
        )
        grant = OAuthGrant.objects.create(
            user=user,
            application=application,
            code="",
            code_digest="c" * 64,
            expires=timezone.now() - timedelta(days=1),
            redirect_uri="http://127.0.0.1:43112/callback",
            scope="read",
            code_challenge="x" * 43,
            code_challenge_method="S256",
            resource=["http://127.0.0.1:8001/mcp"],
        )
        OAuthGrant.objects.filter(pk=grant.pk).update(consumed_at=timezone.now())
        call_command("cleanup_mcp_oauth", stdout=StringIO())
        self.assertTrue(OAuthGrant.objects.filter(pk=grant.pk).exists())

    def test_cleanup_lag_measures_time_since_retention_eligibility(self):
        User = get_user_model()
        user = User.objects.create_user(
            email="audit-lag@example.com", handle="auditlag"
        )
        event = AgentAuditEvent.objects.create(
            request_id="audit-lag",
            authenticated_actor_id=str(user.pk),
            authenticated_client_id="client-" + "a" * 32,
            tool_name="list_projects",
            redacted_input_sha256="b" * 64,
            result_code="success",
        )
        AgentAuditEvent.objects.filter(pk=event.pk).update(
            created_at=timezone.now() - timedelta(days=90, hours=1)
        )
        call_command("cleanup_mcp_oauth", batch_size=1, stdout=StringIO())
        run = OAuthCleanupRun.objects.latest("pk")
        self.assertGreaterEqual(run.oldest_eligible_seconds, 59 * 60)
        self.assertLess(run.oldest_eligible_seconds, 2 * 60 * 60)

    def test_health_alerts_stale_cleanup_and_deduplicates(self):
        run = OAuthCleanupRun.objects.create(success=True, completed_at=timezone.now())
        OAuthCleanupRun.objects.filter(pk=run.pk).update(
            started_at=timezone.now() - timedelta(hours=37),
            completed_at=timezone.now() - timedelta(hours=37),
        )
        with self.assertRaises(CommandError):
            call_command("check_mcp_oauth_health", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("check_mcp_oauth_health", stdout=StringIO())
        self.assertEqual([message.to for message in mail.outbox], [["ops@example.com"]])

    def test_alert_redacts_forbidden_fields_and_uses_admins(self):
        sent = send_deduplicated_admin_alert(
            "rate_limit_backend_anomaly",
            {
                "token": "raw-token",
                "email": "person@example.com",
                "url": "https://secret.example/path",
                "bucket": "global",
            },
        )
        self.assertTrue(sent)
        self.assertEqual(mail.outbox[0].to, ["ops@example.com"])
        event = OAuthSecurityEvent.objects.get(event_type="alert:rate_limit_backend_anomaly")
        self.assertEqual(event.details, {"bucket": "global"})
