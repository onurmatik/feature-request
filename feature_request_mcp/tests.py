from unittest.mock import AsyncMock, patch

import httpx
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from starlette.testclient import TestClient

from accounts.models import ApiToken

from .server import (
    FeatureRequestTokenVerifier,
    _api_request,
    create_application,
    delete_project,
    find_duplicate_candidates,
    link_delivery_artifact,
    list_requests,
    mcp,
    transition_request,
    update_request,
)


@override_settings(
    FEATURE_REQUEST_API_BASE_URL="https://api.featurerequest.test/api",
    FEATURE_REQUEST_MCP_SERVER_URL="https://mcp.featurerequest.test/mcp",
)
class FeatureRequestTokenVerifierTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="mcp-user@example.com",
            handle="mcp_user",
            password="test-pass-123",
        )

    def test_verifier_inherits_existing_token_write_capability(self):
        _api_token, raw_token = ApiToken.issue(
            user=self.user,
            name="MCP token",
            can_write=True,
        )

        access_token = async_to_sync(FeatureRequestTokenVerifier().verify_token)(raw_token)

        self.assertIsNotNone(access_token)
        self.assertEqual(access_token.subject, str(self.user.id))
        self.assertEqual(access_token.scopes, ["read", "write"])
        self.assertTrue(access_token.claims["can_write"])
        self.assertEqual(access_token.claims["user_handle"], self.user.handle)

    def test_verifier_accepts_read_only_token_without_granting_write(self):
        _api_token, raw_token = ApiToken.issue(
            user=self.user,
            name="Read-only MCP token",
            can_write=False,
        )

        access_token = async_to_sync(FeatureRequestTokenVerifier().verify_token)(raw_token)

        self.assertIsNotNone(access_token)
        self.assertEqual(access_token.scopes, ["read"])
        self.assertFalse(access_token.claims["can_write"])

    def test_verifier_rejects_unknown_token(self):
        access_token = async_to_sync(FeatureRequestTokenVerifier().verify_token)(
            "fr_unknown"
        )

        self.assertIsNone(access_token)


class FeatureRequestMCPToolTest(TestCase):
    def test_streamable_http_endpoint_requires_bearer_authentication(self):
        with TestClient(create_application()) as client:
            response = client.post(
                "/mcp",
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1.0"},
                    },
                },
            )

        self.assertEqual(response.status_code, 401)

    def test_p1_tool_catalog_exposes_evidence_and_controlled_mutations(self):
        tools = async_to_sync(mcp.list_tools)()

        self.assertEqual(
            {tool.name for tool in tools},
            {
                "list_projects",
                "get_project",
                "create_project",
                "update_project",
                "delete_project",
                "list_requests",
                "get_request",
                "list_request_comments",
                "get_queue_snapshot",
                "find_duplicate_candidates",
                "list_request_activity",
                "list_request_changes",
                "list_delivery_artifacts",
                "create_request",
                "link_duplicate_request",
                "unlink_duplicate_request",
                "link_delivery_artifact",
                "unlink_delivery_artifact",
                "update_request",
                "transition_request",
                "add_request_comment",
                "update_request_comment",
            },
        )
        self.assertNotIn("get_connection_context", {tool.name for tool in tools})
        delete_tool = next(tool for tool in tools if tool.name == "delete_project")
        delete_annotations = delete_tool.annotations.model_dump(by_alias=True)
        self.assertTrue(delete_annotations["destructiveHint"])
        candidate_tool = next(
            tool for tool in tools if tool.name == "find_duplicate_candidates"
        )
        candidate_annotations = candidate_tool.annotations.model_dump(by_alias=True)
        self.assertTrue(candidate_annotations["readOnlyHint"])

    def test_list_requests_uses_project_route_and_filters(self):
        expected = {"ok": True}
        with patch(
            "feature_request_mcp.server._api_request",
            new=AsyncMock(return_value=expected),
        ) as request_api:
            result = async_to_sync(list_requests)(
                owner_handle="Owner_Name",
                project_slug="roadmap",
                issue_type="bug",
                status="active",
                priority=3,
                limit=25,
            )

        self.assertEqual(result, expected)
        request_api.assert_awaited_once_with(
            action="list_requests",
            method="GET",
            path="projects/owner_name/roadmap/issues",
            resource={
                "owner_handle": "owner_name",
                "project_slug": "roadmap",
            },
            params={
                "issue_type": "bug",
                "status": "active",
                "priority": 3,
                "limit": 25,
            },
        )

    def test_update_request_requires_at_least_one_field(self):
        with patch(
            "feature_request_mcp.server._api_request",
            new=AsyncMock(),
        ) as request_api:
            result = async_to_sync(update_request)(issue_id=42)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["status_code"], 400)
        request_api.assert_not_awaited()

    def test_delete_project_requires_matching_confirmation_id(self):
        with patch(
            "feature_request_mcp.server._api_request",
            new=AsyncMock(),
        ) as request_api:
            rejected = async_to_sync(delete_project)(
                project_id=42,
                confirm_project_id=41,
            )

        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["status_code"], 400)
        request_api.assert_not_awaited()

    def test_duplicate_candidates_use_read_only_get_route(self):
        expected = {"ok": True}
        with patch(
            "feature_request_mcp.server._api_request",
            new=AsyncMock(return_value=expected),
        ) as request_api:
            result = async_to_sync(find_duplicate_candidates)(
                owner_handle="Owner_Name",
                project_slug="agent-board",
                title="Dark mode",
                description="Dark theme",
                exclude_issue_id=9,
                limit=4,
            )

        self.assertEqual(result, expected)
        request_api.assert_awaited_once_with(
            action="find_duplicate_candidates",
            method="GET",
            path="projects/owner_name/agent-board/duplicate-candidates",
            resource={"owner_handle": "owner_name", "project_slug": "agent-board"},
            params={
                "title": "Dark mode",
                "description": "Dark theme",
                "exclude_issue_id": 9,
                "limit": 4,
            },
        )

    def test_link_delivery_artifact_only_records_evidence(self):
        expected = {"ok": True}
        with patch(
            "feature_request_mcp.server._api_request",
            new=AsyncMock(return_value=expected),
        ) as request_api:
            result = async_to_sync(link_delivery_artifact)(
                issue_id=42,
                kind="pull_request",
                url="https://github.com/example/repo/pull/42",
                label="Implementation PR",
            )

        self.assertEqual(result, expected)
        request_api.assert_awaited_once_with(
            action="link_delivery_artifact",
            method="POST",
            path="issues/42/delivery-artifacts",
            resource={"issue_id": 42},
            json_body={
                "kind": "pull_request",
                "url": "https://github.com/example/repo/pull/42",
                "label": "Implementation PR",
            },
        )

    def test_transition_request_only_updates_status(self):
        expected = {"ok": True}
        with patch(
            "feature_request_mcp.server._api_request",
            new=AsyncMock(return_value=expected),
        ) as request_api:
            result = async_to_sync(transition_request)(issue_id=42, status="planned")

        self.assertEqual(result, expected)
        request_api.assert_awaited_once_with(
            action="transition_request",
            method="PATCH",
            path="issues/42",
            resource={"issue_id": 42},
            json_body={"status": "planned"},
        )

    @override_settings(
        FEATURE_REQUEST_API_BASE_URL="https://api.featurerequest.test/api",
        FEATURE_REQUEST_MCP_API_TIMEOUT_SECONDS=5,
    )
    def test_api_request_returns_normalized_structured_result(self):
        response = httpx.Response(
            200,
            json=[{"id": 1, "name": "Roadmap"}],
            request=httpx.Request("GET", "https://api.featurerequest.test/api/projects"),
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = None
        client.request.return_value = response

        with (
            patch("feature_request_mcp.server._current_raw_token", return_value="fr_test"),
            patch("feature_request_mcp.server.httpx.AsyncClient", return_value=client),
        ):
            result = async_to_sync(_api_request)(
                action="list_projects",
                method="GET",
                path="projects",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["request"]["path"], "/api/projects")
        self.assertEqual(result["meta"]["items_returned"], 1)
        self.assertEqual(result["data"][0]["name"], "Roadmap")
