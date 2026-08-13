import json
import runpy
from copy import deepcopy
from threading import Barrier, Lock, Thread
from unittest import skipUnless
from unittest.mock import patch

import yaml
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.management.color import no_style
from django.db import close_old_connections, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from jsonschema import Draft202012Validator
from mcp import MCPError
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from oauth2_provider.models import AbstractApplication
from ninja.errors import HttpError
from starlette.testclient import TestClient

from agent_runtime.contract import public_registry, registry_digest
from agent_runtime.models import AgentAuditEvent, AgentIdempotencyRecord
from feature_request_mcp.server import (
    FeatureRequestMCPServer,
    _request_id,
    create_application,
    mcp,
    token_verifier,
)
from mcp_oauth.models import OAuthApplication, OAuthConsent
from mcp_oauth.services import _issue_tokens
from projects.models import (
    Issue,
    IssueComment,
    IssueDeliveryArtifact,
    IssueEvent,
    Project,
)


class FeatureRequestMCPRegistryTest(TestCase):
    def test_explicit_mcpserver_registry_matches_contract(self):
        self.assertIsInstance(mcp, FeatureRequestMCPServer)
        contract = yaml.safe_load(open("agent/contract.yaml"))
        tools = async_to_sync(mcp.list_tools)()
        self.assertEqual([tool.name for tool in tools], list(contract["tools"]))
        self.assertEqual(len(tools), 23)
        self.assertEqual(registry_digest(), registry_digest())
        for tool in tools:
            definition = contract["tools"][tool.name]
            self.assertEqual(tool.annotations.read_only_hint, definition["side_effect"] == "read_only")
            self.assertEqual(tool.annotations.destructive_hint, definition["destructive"])
            self.assertEqual(tool.annotations.open_world_hint, definition["open_world"])
            self.assertEqual(tool.meta["securitySchemes"][0]["scopes"], definition["required_scopes"])
            semantic_meta = tool.meta["io.featurerequest/agentContract"]
            self.assertEqual(
                semantic_meta["requiredCapabilities"],
                definition["required_capabilities"],
            )
            self.assertEqual(semantic_meta["ownership"], definition["ownership"])
            self.assertEqual(semantic_meta["approval"], definition["approval"])
            self.assertEqual(semantic_meta["idempotency"], definition["idempotency"])

    def test_fastmcp_and_api_token_forwarding_are_absent(self):
        source = open("feature_request_mcp/server.py").read()
        service_source = open("agent_runtime/service.py").read()
        self.assertNotIn("FastMCP", source)
        self.assertNotIn("ApiToken", source)
        self.assertNotIn("httpx.AsyncClient", source)
        self.assertNotIn("projects.api", service_source)

    def test_api_token_format_is_rejected_by_oauth_verifier(self):
        self.assertIsNone(token_verifier.verify_token_sync("fr_" + "x" * 40))

    def test_untrusted_request_id_is_replaced_before_audit_use(self):
        generated = _request_id(
            type("Context", (), {"headers": {"x-request-id": "person@example.com"}})()
        )
        self.assertRegex(generated, r"^[0-9a-f]{32}$")
        accepted = _request_id(
            type("Context", (), {"headers": {"x-request-id": "safe-id-1234"}})()
        )
        self.assertEqual(accepted, "safe-id-1234")

    @patch("uvicorn.run")
    def test_module_entrypoint_bootstraps_django_settings(self, run):
        runpy.run_module("feature_request_mcp", run_name="__main__")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], "feature_request_mcp.asgi:application")
        self.assertFalse(run.call_args.kwargs["access_log"])

    @override_settings(DEBUG=False, FEATURE_REQUEST_MCP_PRODUCTION_ENABLED=False)
    def test_production_mcp_process_refuses_to_start_before_release_enablement(self):
        with self.assertRaises(ImproperlyConfigured):
            create_application()


@override_settings(OPENAI_API_KEY="")
class FeatureRequestMCPServiceTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="owner@example.com", handle="owner", display_name="Owner"
        )
        self.visitor = User.objects.create_user(
            email="visitor@example.com", handle="visitor", display_name="Visitor"
        )
        self.project = Project.objects.create(owner=self.owner, name="Roadmap")

    def call(self, user, name, arguments, scopes=("read", "write")):
        token = AccessToken(
            token="opaque-test-token",
            client_id="https://client.example/metadata.json",
            scopes=list(scopes),
            subject=str(user.pk),
            resource="http://127.0.0.1:8001/mcp",
        )
        context_token = auth_context_var.set(AuthenticatedUser(token))
        try:
            return async_to_sync(mcp.call_tool)(name, arguments)
        finally:
            auth_context_var.reset(context_token)

    @patch("agent_runtime.service.FeatureRequestAgentService._notify_issue")
    def test_create_request_replay_does_not_duplicate_mutation_or_notification(self, notify):
        arguments = {
            "owner_handle": "owner",
            "project_slug": self.project.slug,
            "title": "Dark mode",
            "description": "Please add dark mode",
            "issue_type": "feature",
            "priority": 2,
            "idempotency_key": "request-create-key-0001",
        }
        with self.captureOnCommitCallbacks(execute=True):
            first = self.call(self.visitor, "create_request", arguments)
        second = self.call(self.visitor, "create_request", arguments)
        self.assertFalse(first.is_error)
        self.assertEqual(first.structured_content, second.structured_content)
        self.assertEqual(Issue.objects.count(), 1)
        self.assertEqual(AgentIdempotencyRecord.objects.count(), 1)
        self.assertEqual(notify.call_count, 1)

    def test_idempotency_conflict_is_contract_error(self):
        arguments = {
            "name": "Alpha",
            "tagline": "",
            "url": "",
            "idempotency_key": "project-create-key-0001",
        }
        # Visitor still has capacity while owner already uses the free slot.
        first = self.call(self.visitor, "create_project", arguments)
        changed = {**arguments, "name": "Beta"}
        second = self.call(self.visitor, "create_project", changed)
        self.assertFalse(first.is_error)
        self.assertTrue(second.is_error)
        self.assertEqual(second.structured_content["code"], "idempotency_conflict")
        conflict_audit = AgentAuditEvent.objects.filter(
            tool_name="create_project", result_code="idempotency_conflict"
        ).get()
        self.assertRegex(conflict_audit.idempotency_id, r"^idem_[0-9a-f]{16}$")

    def test_semantic_input_rejection_happens_before_mutation_reservation(self):
        invalid_project = self.call(
            self.visitor,
            "create_project",
            {
                "name": "   ",
                "idempotency_key": "semantic-project-key-0001",
            },
        )
        self.assertEqual(invalid_project.structured_content["code"], "invalid_input")
        self.assertEqual(invalid_project.structured_content["details"]["fields"], ["name"])
        self.assertFalse(Project.objects.filter(owner=self.visitor).exists())

        issue = Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Credential URL guard",
        )
        invalid_delivery = self.call(
            self.owner,
            "link_delivery_artifact",
            {
                "issue_id": issue.pk,
                "kind": "release",
                "url": "https://user:secret@example.com/release",
                "expected_revision": 1,
                "idempotency_key": "semantic-delivery-key-0001",
            },
        )
        self.assertEqual(invalid_delivery.structured_content["code"], "invalid_input")
        self.assertEqual(invalid_delivery.structured_content["details"]["fields"], ["url"])
        self.assertFalse(IssueDeliveryArtifact.objects.filter(issue=issue).exists())
        self.assertFalse(
            AgentIdempotencyRecord.objects.filter(
                tool_name__in=["create_project", "link_delivery_artifact"]
            ).exists()
        )

    @patch("agent_runtime.service._project_output", return_value={"invalid": True})
    def test_invalid_mutation_receipt_rolls_back_resource_and_idempotency(self, _output):
        with self.assertRaises(MCPError):
            self.call(
                self.visitor,
                "create_project",
                {
                    "name": "Must roll back",
                    "idempotency_key": "invalid-receipt-key-0001",
                },
            )
        self.assertFalse(Project.objects.filter(owner=self.visitor).exists())
        self.assertFalse(
            AgentIdempotencyRecord.objects.filter(tool_name="create_project").exists()
        )
        self.assertTrue(
            AgentAuditEvent.objects.filter(
                tool_name="create_project", result_code="internal_error"
            ).exists()
        )

    @patch(
        "agent_runtime.service.FeatureRequestAgentService.list_projects",
        side_effect=RuntimeError("database detail must not escape"),
    )
    def test_unexpected_tool_failure_is_sanitized_and_audited(self, _failure):
        with self.assertLogs("feature_request_mcp.server", level="ERROR") as logs:
            with self.assertRaises(MCPError) as caught:
                self.call(self.owner, "list_projects", {}, scopes=("read",))
        self.assertEqual(caught.exception.error.message, "Internal server error.")
        self.assertNotIn("database detail", "\n".join(logs.output))
        audit = AgentAuditEvent.objects.get(
            tool_name="list_projects", result_code="internal_error"
        )
        serialized = json.dumps(
            {
                field.name: getattr(audit, field.name)
                for field in audit._meta.fields
            },
            default=str,
        )
        self.assertNotIn("database detail", serialized)

    def test_revision_conflict_and_terminal_delivery_gate(self):
        issue = Issue.objects.create(
            project=self.project,
            author=self.owner,
            title="Ship it",
        )
        conflict = self.call(
            self.owner,
            "update_request",
            {
                "issue_id": issue.pk,
                "title": "Changed",
                "expected_revision": 99,
                "idempotency_key": "request-update-key-0001",
            },
        )
        self.assertEqual(conflict.structured_content["code"], "revision_conflict")
        terminal = self.call(
            self.owner,
            "transition_request",
            {
                "issue_id": issue.pk,
                "status": "done",
                "expected_revision": 1,
                "idempotency_key": "request-transition-key-0001",
            },
        )
        self.assertEqual(terminal.structured_content["code"], "approval_required")
        IssueDeliveryArtifact.objects.create(
            issue=issue,
            added_by=self.owner,
            kind="release",
            url="https://example.com/release/1",
        )
        success = self.call(
            self.owner,
            "transition_request",
            {
                "issue_id": issue.pk,
                "status": "done",
                "expected_revision": 1,
                "idempotency_key": "request-transition-key-0002",
            },
        )
        self.assertFalse(success.is_error)
        self.assertEqual(success.structured_content["revision"], 2)

    def test_project_url_update_clears_stale_favicon_without_fetching(self):
        self.project.url = "https://old.example/product"
        self.project.favicon_url = "https://old.example/favicon.ico"
        self.project.save(update_fields=["url", "favicon_url"])
        result = self.call(
            self.owner,
            "update_project",
            {
                "project_id": self.project.pk,
                "url": "https://new.example/product",
                "expected_revision": 1,
                "idempotency_key": "project-url-update-key-0001",
            },
        )
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["url"], "https://new.example/product")
        self.assertEqual(result.structured_content["favicon_url"], "")
        self.assertEqual(result.structured_content["revision"], 2)

    def test_write_scope_step_up_and_audit_redacts_content(self):
        result = self.call(
            self.visitor,
            "create_request",
            {
                "owner_handle": "owner",
                "project_slug": self.project.slug,
                "title": "Secret looking title",
                "idempotency_key": "request-create-key-0002",
            },
            scopes=("read",),
        )
        self.assertTrue(result.is_error)
        self.assertIn("mcp/www_authenticate", result.meta)
        success = self.call(self.owner, "get_account_capabilities", {}, scopes=("read",))
        self.assertFalse(success.is_error)
        self.assertEqual(success.structured_content["limits"]["project_count"]["limit"], 1)
        audit = AgentAuditEvent.objects.latest("id")
        serialized = json.dumps(
            {
                field.name: getattr(audit, field.name)
                for field in audit._meta.fields
                if field.name != "created_at"
            },
            default=str,
        )
        self.assertNotIn("Secret looking title", serialized)


@override_settings(OPENAI_API_KEY="")
class FeatureRequestContractRuntimeConformanceTest(TestCase):
    """Executable repository bindings for the immutable 1.0.0 vector bundle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        bundle = yaml.safe_load(open("agent/conformance/1.0.0/vectors.yaml"))
        cls.vectors = {item["id"]: item for item in bundle["vectors"]}
        cls.contract = yaml.safe_load(open("agent/contract.yaml"))

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            id=1,
            email="owner-runtime@example.com",
            handle="owner",
            display_name="Owner",
        )
        self.author = User.objects.create_user(
            id=2,
            email="author-runtime@example.com",
            handle="author",
            display_name="Author",
        )
        self.outsider = User.objects.create_user(
            id=3,
            email="outsider-runtime@example.com",
            handle="outsider",
        )
        self.creator = User.objects.create_user(
            id=4,
            email="creator-runtime@example.com",
            handle="creator",
        )
        self.project = Project.objects.create(
            id=1,
            owner=self.owner,
            name="Roadmap",
            tagline="Public roadmap",
            url="https://example.com",
            favicon_url="",
        )
        self.issue = Issue.objects.create(
            id=10,
            project=self.project,
            author=self.author,
            title="Dark mode",
            description="Add dark mode",
        )
        self.canonical = Issue.objects.create(
            id=11,
            project=self.project,
            author=self.owner,
            title="Dark theme",
            description="Canonical dark mode request",
        )
        self.comment = IssueComment.objects.create(
            id=20,
            issue=self.issue,
            author=self.author,
            body="Please add this.",
        )
        self.event = IssueEvent.objects.create(
            id=30,
            issue=self.issue,
            actor=self.author,
            event_type=IssueEvent.Type.CREATED,
            data={"source": "mcp"},
        )
        self.artifact = IssueDeliveryArtifact.objects.create(
            id=40,
            issue=self.issue,
            added_by=self.owner,
            kind=IssueDeliveryArtifact.Kind.PULL_REQUEST,
            url="https://example.com/pull/1",
            label="PR 1",
        )
        reset_sql = connection.ops.sequence_reset_sql(
            no_style(),
            [
                User,
                Project,
                Issue,
                IssueComment,
                IssueEvent,
                IssueDeliveryArtifact,
            ],
        )
        with connection.cursor() as cursor:
            for statement in reset_sql:
                cursor.execute(statement)

    def call(self, user, name, arguments, scopes=("read", "write")):
        token = AccessToken(
            token="opaque-runtime-token",
            client_id="https://client.example/oauth/metadata.json",
            scopes=list(scopes),
            subject=str(user.pk),
            resource="http://127.0.0.1:8001/mcp",
        )
        context_token = auth_context_var.set(AuthenticatedUser(token))
        try:
            return async_to_sync(mcp.call_tool)(name, arguments)
        finally:
            auth_context_var.reset(context_token)

    def _success_user(self, tool):
        if tool == "create_project":
            return self.creator
        if tool in {
            "create_request",
            "get_request",
            "list_request_comments",
            "find_duplicate_candidates",
            "add_request_comment",
        }:
            return self.author
        if tool in {
            "list_request_activity",
            "list_delivery_artifacts",
            "link_duplicate_request",
            "unlink_duplicate_request",
            "link_delivery_artifact",
            "unlink_delivery_artifact",
            "update_request",
            "transition_request",
            "update_request_comment",
        }:
            return self.author
        return self.owner

    def _success_input(self, tool):
        vector = self.vectors[f"{tool}_success"]
        return deepcopy(vector["input"])

    @staticmethod
    def _sensitive_values(arguments):
        for key in (
            "idempotency_key",
            "name",
            "tagline",
            "title",
            "description",
            "body",
            "url",
            "label",
        ):
            value = arguments.get(key)
            if value:
                yield str(value)

    def _state_signature(self):
        return {
            "projects": list(
                Project.objects.order_by("id").values_list("id", "revision", "name")
            ),
            "issues": list(
                Issue.objects.order_by("id").values_list(
                    "id", "revision", "status", "priority", "duplicate_of_id"
                )
            ),
            "comments": list(
                IssueComment.objects.order_by("id").values_list(
                    "id", "revision", "body"
                )
            ),
            "artifacts": list(
                IssueDeliveryArtifact.objects.order_by("id").values_list(
                    "id", "issue_id", "kind", "url", "label"
                )
            ),
            "events": IssueEvent.objects.count(),
            "idempotency": AgentIdempotencyRecord.objects.count(),
        }

    def _prepare_success(self, tool):
        if tool == "link_delivery_artifact":
            IssueDeliveryArtifact.objects.filter(pk=self.artifact.pk).delete()

    def _assert_success_invariant(self, tool, payload):
        if tool == "get_account_capabilities":
            self.assertEqual(payload["limits"]["project_count"]["limit"], 1)
            self.assertTrue(all(payload["capabilities"].values()))
        elif tool == "create_project":
            self.assertEqual(payload["favicon_url"], "")
            self.assertEqual(payload["revision"], 1)
        elif tool == "update_project":
            self.assertEqual(payload["revision"], 2)
        elif tool == "delete_project":
            self.assertEqual(payload["deleted_revision"], 1)
        elif tool == "create_request":
            self.assertEqual(payload["author_id"], self.author.pk)
        elif tool == "link_duplicate_request":
            self.assertTrue(payload["changed"])
            self.assertEqual(payload["request"]["duplicate_of_id"], 11)
        elif tool == "unlink_duplicate_request":
            self.assertFalse(payload["changed"])
        elif tool == "link_delivery_artifact":
            self.assertTrue(payload["created"])
            self.assertEqual(payload["request_revision"], 2)
        elif tool == "unlink_delivery_artifact":
            self.assertTrue(payload["changed"])
            self.assertEqual(payload["request_revision"], 2)
        elif tool == "update_request":
            self.assertEqual(payload["priority"], 3)
            self.assertEqual(payload["revision"], 2)
        elif tool == "transition_request":
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["revision"], 2)
        elif tool == "add_request_comment":
            self.assertEqual(payload["author_id"], self.author.pk)
        elif tool == "update_request_comment":
            self.assertEqual(payload["revision"], 2)

    @patch("agent_runtime.service.FeatureRequestAgentService._notify_issue")
    @patch("agent_runtime.service.FeatureRequestAgentService._notify_comment")
    def test_success_vectors_execute_through_mcp(self, _notify_comment, _notify_issue):
        success_ids = {
            vector_id
            for vector_id, vector in self.vectors.items()
            if vector.get("category") == "success"
        }
        self.assertEqual(
            {f"{name}_success" for name in self.contract["tools"]}, success_ids
        )
        for tool in self.contract["tools"]:
            with self.subTest(vector=f"{tool}_success"):
                sid = transaction.savepoint()
                try:
                    self._prepare_success(tool)
                    arguments = self._success_input(tool)
                    result = self.call(self._success_user(tool), tool, arguments)
                    self.assertFalse(result.is_error, result.structured_content)
                    self._assert_success_invariant(tool, result.structured_content)
                    audit = AgentAuditEvent.objects.latest("id")
                    self.assertEqual(audit.tool_name, tool)
                    self.assertEqual(audit.result_code, "success")
                    self.assertRegex(audit.redacted_input_sha256, r"^[0-9a-f]{64}$")
                    serialized_audit = json.dumps(
                        {
                            field.name: getattr(audit, field.name)
                            for field in audit._meta.fields
                        },
                        default=str,
                    )
                    self.assertNotIn(
                        "https://client.example/oauth/metadata.json",
                        serialized_audit,
                    )
                    for value in self._sensitive_values(arguments):
                        self.assertNotIn(value, serialized_audit)
                finally:
                    transaction.savepoint_rollback(sid)

    def test_invalid_input_matrix_executes_for_all_23_tools(self):
        vector = self.vectors["invalid_input_matrix"]
        self.assertEqual(list(self.contract["tools"]), vector["matrix"]["tools"])
        for tool in vector["matrix"]["tools"]:
            with self.subTest(tool=tool):
                result = self.call(
                    self.owner,
                    tool,
                    deepcopy(vector["input_by_tool"][tool]),
                )
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content["code"], "invalid_input")
                self.assertEqual(
                    result.structured_content["details"], {"fields": ["unexpected"]}
                )

    def test_missing_capability_matrix_executes_for_all_gated_tools(self):
        vector = self.vectors["missing_capability_matrix"]
        with patch(
            "agent_runtime.service.FeatureRequestAgentService._capability_set",
            return_value=frozenset(),
        ):
            for tool in vector["matrix"]["tools"]:
                with self.subTest(tool=tool):
                    result = self.call(
                        self.owner,
                        tool,
                        deepcopy(vector["input_by_tool"][tool]),
                    )
                    self.assertTrue(result.is_error)
                    self.assertEqual(
                        result.structured_content["code"], "feature_unavailable"
                    )
                    self.assertEqual(
                        result.structured_content["details"]["capability"],
                        self.contract["tools"][tool]["required_capabilities"][0],
                    )

    def test_free_and_pro_capability_plan_matrix(self):
        free = self.call(self.owner, "get_account_capabilities", {})
        self.assertEqual(free.structured_content["limits"]["project_count"]["limit"], 1)
        sid = transaction.savepoint()
        try:
            self.owner.subscription_tier = "pro_30"
            self.owner.subscription_status = "active"
            self.owner.save(
                update_fields=["subscription_tier", "subscription_status", "updated_at"]
            )
            pro = self.call(self.owner, "get_account_capabilities", {})
            self.assertEqual(
                pro.structured_content,
                self.vectors["pro_plan_matrix"]["expected"]["result_by_tool"][
                    "get_account_capabilities"
                ],
            )
            catalog = set(pro.structured_content["capabilities"])
            for tool, definition in self.contract["tools"].items():
                with self.subTest(tool=tool):
                    self.assertTrue(
                        set(definition["required_capabilities"]).issubset(catalog)
                    )
        finally:
            transaction.savepoint_rollback(sid)
            self.owner.refresh_from_db()

    def test_ownership_isolation_and_filtering_matrices(self):
        isolation = self.vectors["ownership_isolation_matrix"]
        for tool in isolation["matrix"]["tools"]:
            with self.subTest(tool=tool):
                result = self.call(
                    self.outsider,
                    tool,
                    deepcopy(isolation["input_by_tool"][tool]),
                )
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content["code"], "permission_denied")
        filtering = self.vectors["ownership_filtering_matrix"]
        for tool in filtering["matrix"]["tools"]:
            with self.subTest(tool=tool):
                result = self.call(
                    self.outsider,
                    tool,
                    deepcopy(filtering["input_by_tool"][tool]),
                    scopes=("read",),
                )
                self.assertFalse(result.is_error)
                self.assertEqual(
                    result.structured_content,
                    filtering["expected"]["result_by_tool"][tool],
                )

    def test_revision_conflict_matrix_executes_for_all_existing_resource_mutations(self):
        vector = self.vectors["revision_conflict_matrix"]
        for tool in vector["matrix"]["tools"]:
            with self.subTest(tool=tool):
                sid = transaction.savepoint()
                try:
                    if tool in {"update_project", "delete_project"}:
                        Project.objects.filter(pk=1).update(revision=2)
                    elif tool == "update_request_comment":
                        IssueComment.objects.filter(pk=20).update(revision=2)
                    else:
                        Issue.objects.filter(pk=10).update(revision=2)
                    before = self._state_signature()
                    result = self.call(
                        self._success_user(tool),
                        tool,
                        deepcopy(vector["input_by_tool"][tool]),
                    )
                    self.assertTrue(result.is_error)
                    self.assertEqual(
                        result.structured_content["code"], "revision_conflict"
                    )
                    self.assertEqual(
                        result.structured_content["details"],
                        {"expected_revision": 1, "actual_revision": 2},
                    )
                    self.assertEqual(before, self._state_signature())
                finally:
                    transaction.savepoint_rollback(sid)

    def _mutation_user(self, tool):
        return self._success_user(tool)

    def _prepare_mutation(self, tool):
        self._prepare_success(tool)

    @staticmethod
    def _conflicting_arguments(tool, arguments):
        changed = deepcopy(arguments)
        field_values = {
            "create_project": ("name", "Different roadmap"),
            "update_project": ("tagline", "Different tagline"),
            "delete_project": ("expected_revision", 2),
            "create_request": ("title", "Different request"),
            "link_duplicate_request": ("expected_revision", 2),
            "unlink_duplicate_request": ("expected_revision", 2),
            "link_delivery_artifact": ("label", "Different label"),
            "unlink_delivery_artifact": ("expected_revision", 2),
            "update_request": ("priority", 4),
            "transition_request": ("status", "in_progress"),
            "add_request_comment": ("body", "Different comment"),
            "update_request_comment": ("body", "Different edited comment"),
        }
        field, value = field_values[tool]
        changed[field] = value
        return changed

    @patch("agent_runtime.service.FeatureRequestAgentService._notify_issue")
    @patch("agent_runtime.service.FeatureRequestAgentService._notify_comment")
    def test_mutation_replay_and_conflict_matrices(self, _notify_comment, _notify_issue):
        replay = self.vectors["mutation_replay_matrix"]
        conflict = self.vectors["mutation_conflict_matrix"]
        self.assertEqual(replay["matrix"]["tools"], conflict["matrix"]["tools"])
        for tool in replay["matrix"]["tools"]:
            with self.subTest(tool=tool, case="replay_and_conflict"):
                sid = transaction.savepoint()
                try:
                    self._prepare_mutation(tool)
                    arguments = deepcopy(replay["input_by_tool"][tool])
                    user = self._mutation_user(tool)
                    first = self.call(user, tool, arguments)
                    self.assertFalse(first.is_error, first.structured_content)
                    after_first = self._state_signature()
                    second = self.call(user, tool, deepcopy(arguments))
                    self.assertFalse(second.is_error, second.structured_content)
                    self.assertEqual(first.structured_content, second.structured_content)
                    self.assertEqual(after_first, self._state_signature())
                    conflict_result = self.call(
                        user,
                        tool,
                        self._conflicting_arguments(tool, arguments),
                    )
                    self.assertTrue(conflict_result.is_error)
                    self.assertEqual(
                        conflict_result.structured_content["code"],
                        "idempotency_conflict",
                    )
                    self.assertEqual(after_first, self._state_signature())
                finally:
                    transaction.savepoint_rollback(sid)

    def test_delivery_natural_key_and_absent_unlink_semantics(self):
        Issue.objects.filter(pk=10).update(revision=2)
        reuse = deepcopy(self.vectors["delivery_natural_key_reuse"]["input"])
        result = self.call(self.author, "link_delivery_artifact", reuse)
        self.assertFalse(result.is_error)
        self.assertFalse(result.structured_content["created"])
        self.assertEqual(result.structured_content["request_revision"], 2)
        conflict = self.call(
            self.author,
            "link_delivery_artifact",
            deepcopy(self.vectors["delivery_natural_key_conflict"]["input"]),
        )
        self.assertTrue(conflict.is_error)
        self.assertEqual(conflict.structured_content["code"], "idempotency_conflict")
        absent = self.call(
            self.author,
            "unlink_delivery_artifact",
            {
                "issue_id": 10,
                "artifact_id": 9999,
                "expected_revision": 2,
                "idempotency_key": "unlink-absent-artifact-0001",
            },
        )
        self.assertFalse(absent.is_error)
        self.assertFalse(absent.structured_content["changed"])
        self.assertEqual(absent.structured_content["request_revision"], 2)

    def test_approval_metadata_and_server_owned_preconditions(self):
        vector = self.vectors["approval_matrix"]
        tools = {tool.name: tool for tool in public_registry()}
        for name in vector["matrix"]["tools"]:
            with self.subTest(tool=name):
                approval = tools[name].meta["io.featurerequest/agentContract"][
                    "approval"
                ]
                self.assertEqual(approval["owner"], "agent")
                self.assertIn(
                    "current_turn_explicit_user_intent", approval["conditions"]
                )
        mismatch = self.call(
            self.owner,
            "delete_project",
            {
                "project_id": 1,
                "confirm_project_id": 999,
                "expected_revision": 1,
                "idempotency_key": "delete-confirm-mismatch-0001",
            },
        )
        self.assertEqual(mismatch.structured_content["code"], "confirmation_mismatch")
        self.artifact.delete()
        terminal = self.call(
            self.author,
            "transition_request",
            {
                "issue_id": 10,
                "status": "done",
                "expected_revision": 1,
                "idempotency_key": "terminal-without-evidence-0001",
            },
        )
        self.assertEqual(terminal.structured_content["code"], "approval_required")
        self.assertEqual(Project.objects.filter(pk=1).count(), 1)

    def test_approval_granted_terminal_transition_uses_delivery_evidence(self):
        result = self.call(
            self.author,
            "transition_request",
            deepcopy(
                self.vectors["approval_granted_matrix"]["input_by_tool"][
                    "transition_request"
                ]
            ),
        )
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["status"], "done")

    def test_external_dependency_unavailable_matrix_rolls_back_before_reservation(self):
        vector = self.vectors["external_effect_uncertain_matrix"]
        for tool in vector["matrix"]["tools"]:
            with self.subTest(tool=tool):
                sid = transaction.savepoint()
                try:
                    before = self._state_signature()
                    target = (
                        "agent_runtime.service._moderate_issue_submission"
                        if tool == "create_request"
                        else "agent_runtime.service._moderate_comment_submission"
                    )
                    with patch(
                        target,
                        side_effect=HttpError(
                            503, "Content moderation is temporarily unavailable."
                        ),
                    ):
                        result = self.call(
                            self.author,
                            tool,
                            deepcopy(vector["input_by_tool"][tool]),
                        )
                    self.assertTrue(result.is_error)
                    self.assertEqual(
                        result.structured_content["code"], "dependency_unavailable"
                    )
                    self.assertEqual(
                        result.structured_content["details"],
                        {"dependency": "content_moderation"},
                    )
                    self.assertEqual(before, self._state_signature())
                finally:
                    transaction.savepoint_rollback(sid)

    def test_contract_stage_na_error_paths_execute_at_runtime(self):
        missing = self.call(self.owner, "get_request", {"issue_id": 9999})
        self.assertEqual(missing.structured_content["code"], "not_found")
        with patch(
            "agent_runtime.service._moderate_issue_submission",
            side_effect=HttpError(400, "Rejected"),
        ):
            rejected = self.call(
                self.author,
                "create_request",
                {
                    "owner_handle": "owner",
                    "project_slug": "roadmap",
                    "title": "Rejected content",
                    "idempotency_key": "moderation-rejected-0001",
                },
            )
        self.assertEqual(rejected.structured_content["code"], "moderation_rejected")
        invalid_state = self.call(
            self.author,
            "link_duplicate_request",
            {
                "issue_id": 10,
                "canonical_issue_id": 10,
                "expected_revision": 1,
                "idempotency_key": "invalid-duplicate-state-0001",
            },
        )
        self.assertEqual(invalid_state.structured_content["code"], "invalid_state")
        self.assertFalse(
            AgentIdempotencyRecord.objects.filter(
                tool_name__in=["create_request", "link_duplicate_request"]
            ).exists()
        )

    def test_sequential_free_capacity_guard_is_atomic_on_repository_database(self):
        first = self.call(
            self.creator,
            "create_project",
            {
                "name": "First",
                "idempotency_key": "capacity-first-project-0001",
            },
        )
        second = self.call(
            self.creator,
            "create_project",
            {
                "name": "Second",
                "idempotency_key": "capacity-second-project-0001",
            },
        )
        self.assertFalse(first.is_error)
        self.assertEqual(second.structured_content["code"], "capacity_reached")
        self.assertEqual(Project.objects.filter(owner=self.creator).count(), 1)


@skipUnless(
    connection.vendor == "postgresql",
    "PostgreSQL concurrency evidence is a production-release gate.",
)
@override_settings(OPENAI_API_KEY="")
class FeatureRequestPostgreSQLConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="postgres-concurrency@example.com",
            handle="pgconcurrency",
        )

    def _run_concurrently(self, calls):
        barrier = Barrier(len(calls))
        lock = Lock()
        outcomes = []

        def worker(callback):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                value = callback()
            except Exception as exc:  # Assertions inspect only stable public codes.
                value = exc
            finally:
                connections["default"].close()
            with lock:
                outcomes.append(value)

        threads = [Thread(target=worker, args=(callback,)) for callback in calls]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        return outcomes

    def _create(self, key, name):
        user = get_user_model().objects.get(pk=self.user.pk)
        from agent_runtime.context import AgentContext
        from agent_runtime.errors import ContractApplicationError
        from agent_runtime.service import service

        try:
            return service.call(
                "create_project",
                {"name": name, "idempotency_key": key},
                AgentContext(
                    user=user,
                    authenticated_client_id="postgres-test-client",
                    scopes=frozenset({"write"}),
                    request_id=f"pg-{key}",
                ),
            )
        except ContractApplicationError as exc:
            return exc.envelope

    def test_atomic_capacity_and_same_key_winner_replay(self):
        outcomes = self._run_concurrently(
            [
                lambda: self._create("capacity-a-00000001", "Alpha"),
                lambda: self._create("capacity-b-00000001", "Beta"),
            ]
        )
        self.assertEqual(Project.objects.filter(owner=self.user).count(), 1)
        codes = [
            outcome.get("code", "success")
            if isinstance(outcome, dict)
            else type(outcome).__name__
            for outcome in outcomes
        ]
        self.assertCountEqual(codes, ["success", "capacity_reached"])

        Project.objects.filter(owner=self.user).delete()
        AgentIdempotencyRecord.objects.filter(actor=self.user).delete()
        same_key = self._run_concurrently(
            [
                lambda: self._create("same-key-concurrency-0001", "Gamma"),
                lambda: self._create("same-key-concurrency-0001", "Gamma"),
            ]
        )
        self.assertEqual(Project.objects.filter(owner=self.user).count(), 1)
        self.assertEqual(same_key[0], same_key[1])


@override_settings(OPENAI_API_KEY="", DEBUG=True)
class FeatureRequestModernTransportTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="transport@example.com", handle="transport"
        )
        self.application = OAuthApplication.objects.create(
            client_id="frc_transport_client",
            client_type=AbstractApplication.CLIENT_PUBLIC,
            authorization_grant_type=AbstractApplication.GRANT_AUTHORIZATION_CODE,
            client_secret="",
            hash_client_secret=False,
            name="Transport Test",
            skip_authorization=False,
            redirect_uris="http://127.0.0.1:41234/callback",
            application_type="native",
            metadata={},
            allowed_scopes=["read", "write"],
            callback_profiles=["exact_registered_ip_loopback"],
            registration_source=AbstractApplication.RegistrationSource.DCR,
        )
        OAuthConsent.objects.create(
            user=self.user,
            application=self.application,
            resource="http://127.0.0.1:8001/mcp",
            scopes=["read", "write"],
            decision=OAuthConsent.Decision.APPROVED,
        )
        self.read_tokens = _issue_tokens(
            user=self.user,
            application=self.application,
            scopes=["read"],
        )
        self.read_write_tokens = _issue_tokens(
            user=self.user,
            application=self.application,
            scopes=["read", "write"],
        )
        self.transport = TestClient(
            create_application(), base_url="http://127.0.0.1:8001"
        )
        self.transport.__enter__()

    def tearDown(self):
        self.transport.__exit__(None, None, None)

    @staticmethod
    def _body(method, params=None):
        params = dict(params or {})
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

    @staticmethod
    def _headers(method, token=None, name=None, origin=None):
        headers = {
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": method,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if name:
            headers["Mcp-Name"] = name
        if origin:
            headers["Origin"] = origin
        return headers

    def test_missing_token_is_401_with_bootstrap_challenge(self):
        response = self.transport.post(
            "/mcp",
            json=self._body("server/discover"),
            headers=self._headers("server/discover"),
        )
        self.assertEqual(response.status_code, 401)
        challenge = response.headers["WWW-Authenticate"]
        self.assertIn("resource_metadata=", challenge)
        self.assertIn('scope="read"', challenge)

    def test_modern_discover_and_public_tools_cache_are_stateless(self):
        token = self.read_tokens["access_token"]
        discover = self.transport.post(
            "/mcp",
            json=self._body("server/discover"),
            headers=self._headers("server/discover", token),
        )
        self.assertEqual(discover.status_code, 200, discover.text)
        self.assertIn("2026-07-28", discover.json()["result"]["supportedVersions"])
        self.assertNotIn("Mcp-Session-Id", discover.headers)
        tools = self.transport.post(
            "/mcp",
            json=self._body("tools/list"),
            headers=self._headers("tools/list", token),
        )
        self.assertEqual(tools.status_code, 200, tools.text)
        result = tools.json()["result"]
        self.assertEqual(len(result["tools"]), 23)
        self.assertEqual(result["ttlMs"], 300000)
        self.assertEqual(result["cacheScope"], "public")

    def test_write_scope_step_up_is_transport_native_403(self):
        response = self.transport.post(
            "/mcp",
            json=self._body(
                "tools/call",
                {
                    "name": "create_project",
                    "arguments": {
                        "name": "Denied",
                        "idempotency_key": "transport-write-key-0001",
                    },
                },
            ),
            headers=self._headers(
                "tools/call",
                self.read_tokens["access_token"],
                "create_project",
            ),
        )
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"], "insufficient_scope")
        self.assertEqual(
            payload["_meta"]["mcp/www_authenticate"],
            [response.headers["WWW-Authenticate"]],
        )
        challenge = response.headers["WWW-Authenticate"]
        self.assertIn('error="insufficient_scope"', challenge)
        self.assertIn('scope="write"', challenge)
        self.assertFalse(Project.objects.filter(name="Denied").exists())
        audit = AgentAuditEvent.objects.get(
            tool_name="create_project",
            result_code="insufficient_scope",
        )
        self.assertFalse(audit.scope_decision["granted"])
        self.assertFalse(audit.capability_decision["evaluated"])
        self.assertEqual(audit.ownership_decision, "not_evaluated")

    def test_mcp_name_header_mismatch_is_rejected_before_mutation(self):
        response = self.transport.post(
            "/mcp",
            json=self._body(
                "tools/call",
                {
                    "name": "create_project",
                    "arguments": {
                        "name": "Must not be created",
                        "idempotency_key": "header-mismatch-key-0001",
                    },
                },
            ),
            headers=self._headers(
                "tools/call",
                self.read_write_tokens["access_token"],
                "get_account_capabilities",
            ),
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["error"]["code"], -32020)
        self.assertFalse(Project.objects.filter(name="Must not be created").exists())

    def test_mcp_name_header_is_required_before_tool_mutation(self):
        response = self.transport.post(
            "/mcp",
            json=self._body(
                "tools/call",
                {
                    "name": "create_project",
                    "arguments": {
                        "name": "Must not be created without a named header",
                        "idempotency_key": "header-missing-key-0001",
                    },
                },
            ),
            headers=self._headers(
                "tools/call",
                self.read_write_tokens["access_token"],
            ),
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["error"], "invalid_request")
        self.assertFalse(
            Project.objects.filter(
                name="Must not be created without a named header"
            ).exists()
        )

    def test_bootstrap_call_succeeds_with_read_scope(self):
        response = self.transport.post(
            "/mcp",
            json=self._body(
                "tools/call",
                {"name": "get_account_capabilities", "arguments": {}},
            ),
            headers=self._headers(
                "tools/call",
                self.read_tokens["access_token"],
                "get_account_capabilities",
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()["result"]["structuredContent"]
        self.assertTrue(payload["capabilities"]["project_management"])

    @patch(
        "agent_runtime.service.FeatureRequestAgentService._notify_issue",
        side_effect=RuntimeError("notification unavailable"),
    )
    @patch(
        "agent_runtime.service.FeatureRequestAgentService._notify_comment",
        side_effect=RuntimeError("notification unavailable"),
    )
    def test_post_commit_notification_failure_keeps_mutation_successful_and_audited(
        self,
        _notify_comment,
        _notify_issue,
    ):
        User = get_user_model()
        owner = User.objects.create_user(
            email="notification-owner@example.com",
            handle="notificationowner",
        )
        project = Project.objects.create(owner=owner, name="Notification board")
        issue = Issue.objects.create(
            project=project,
            author=owner,
            title="Existing request",
        )
        token = self.read_write_tokens["access_token"]
        create = self.transport.post(
            "/mcp",
            json=self._body(
                "tools/call",
                {
                    "name": "create_request",
                    "arguments": {
                        "owner_handle": owner.handle,
                        "project_slug": project.slug,
                        "title": "Committed despite email failure",
                        "idempotency_key": "notification-create-0001",
                    },
                },
            ),
            headers=self._headers("tools/call", token, "create_request"),
        )
        self.assertEqual(create.status_code, 200, create.text)
        self.assertFalse(create.json()["result"]["isError"])
        create_audit = AgentAuditEvent.objects.get(
            tool_name="create_request",
            result_code="success",
        )
        self.assertEqual(create_audit.notification_outcome, "failed_best_effort")

        comment = self.transport.post(
            "/mcp",
            json=self._body(
                "tools/call",
                {
                    "name": "add_request_comment",
                    "arguments": {
                        "issue_id": issue.pk,
                        "body": "Committed comment despite email failure",
                        "idempotency_key": "notification-comment-0001",
                    },
                },
            ),
            headers=self._headers("tools/call", token, "add_request_comment"),
        )
        self.assertEqual(comment.status_code, 200, comment.text)
        self.assertFalse(comment.json()["result"]["isError"])
        comment_audit = AgentAuditEvent.objects.get(
            tool_name="add_request_comment",
            result_code="success",
        )
        self.assertEqual(comment_audit.notification_outcome, "failed_best_effort")

    def test_cors_preflight_and_non_header_token_rejection(self):
        preflight = self.transport.options(
            "/mcp",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(preflight.status_code, 204)
        self.assertEqual(
            preflight.headers["Access-Control-Allow-Origin"],
            "http://127.0.0.1:3000",
        )
        query = self.transport.post(
            "/mcp?access_token=not-allowed",
            json=self._body("server/discover"),
            headers=self._headers("server/discover"),
        )
        self.assertEqual(query.status_code, 401)
        self.assertEqual(query.json()["error"], "invalid_token")

        duplicate_origin = self.transport.post(
            "/mcp",
            json=self._body("server/discover"),
            headers=[
                ("MCP-Protocol-Version", "2026-07-28"),
                ("Mcp-Method", "server/discover"),
                ("Accept", "application/json"),
                ("Content-Type", "application/json"),
                ("Authorization", f"Bearer {self.read_tokens['access_token']}"),
                ("Origin", "http://127.0.0.1:3000"),
                ("Origin", "https://attacker.example"),
            ],
        )
        self.assertEqual(duplicate_origin.status_code, 403)
        self.assertEqual(duplicate_origin.json()["error"], "cors_origin_denied")

    def test_legacy_missing_modern_headers_and_api_token_are_rejected(self):
        legacy = self.transport.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.read_tokens['access_token']}",
            },
        )
        self.assertEqual(legacy.status_code, 400)
        api_token = self.transport.post(
            "/mcp",
            json=self._body("server/discover"),
            headers=self._headers("server/discover", "fr_" + "x" * 40),
        )
        self.assertEqual(api_token.status_code, 401)
