from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from scripts import mcp_release


class MCPReleaseRepositoryGateTests(unittest.TestCase):
    def test_repository_gate_is_valid_and_truthfully_pending(self):
        state = mcp_release.validate_repository()
        self.assertEqual(
            ["chatgpt", "claude", "claude_code", "codex"],
            state["pending_clients"],
        )
        self.assertRegex(state["tool_registry_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(state["runtime_conformance_sha256"], r"^[0-9a-f]{64}$")

    def test_runtime_conformance_binds_every_immutable_vector_to_a_real_test(self):
        digest = mcp_release.validate_runtime_conformance()
        self.assertEqual(
            digest,
            mcp_release._sha256(mcp_release.RUNTIME_CONFORMANCE_PATH.read_bytes()),
        )
        manifest = mcp_release._load_yaml(mcp_release.RUNTIME_CONFORMANCE_PATH)
        vectors = mcp_release._load_yaml(mcp_release.VECTOR_PATH)["vectors"]
        self.assertEqual(
            [item["id"] for item in vectors],
            [item["id"] for item in manifest["bindings"]],
        )

    def test_agent_contract_pin_is_immutable_and_digest_verified(self):
        pin = mcp_release.validate_contract_pin()
        self.assertEqual("agent-contract-v1.0.0", pin["tag"])
        self.assertEqual(
            mcp_release._sha256(mcp_release.PINNED_DESCRIPTOR_PATH.read_bytes()),
            pin["descriptor"]["sha256"],
        )

    def test_production_descriptor_rejects_pending_acceptance(self):
        with self.assertRaises(mcp_release.ReleaseGateError):
            mcp_release.build_release_descriptor(
                source_commit=mcp_release._git_head(),
            )

    def test_pending_client_cannot_carry_fabricated_evidence(self):
        manifest = copy.deepcopy(mcp_release._load_yaml(mcp_release.COMPATIBILITY_PATH))
        manifest["clients"][0]["evidence"] = {
            "url": "https://example.com/evidence.json",
            "sha256": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "compatibility.yaml"
            path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            with self.assertRaises(mcp_release.ReleaseGateError):
                mcp_release.validate_compatibility(path)

    def test_accepted_evidence_url_rejects_path_traversal(self):
        manifest = copy.deepcopy(mcp_release._load_yaml(mcp_release.COMPATIBILITY_PATH))
        manifest["status"] = "accepted"
        for entry in manifest["clients"]:
            entry["support_status"] = "accepted"
            entry["tested_version"] = "test-client-1.0"
            entry["tested_at"] = "2026-08-12T12:00:00Z"
            entry["evidence"] = {
                "url": (
                    "https://github.com/onurmatik/feature-request/releases/download/"
                    "mcp-v1.0.0/../wrong-release.json"
                ),
                "sha256": "a" * 64,
            }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "compatibility.yaml"
            path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            with self.assertRaises(mcp_release.ReleaseGateError):
                mcp_release.validate_compatibility(path)

    def test_sealed_release_descriptor_is_byte_deterministic(self):
        manifest = copy.deepcopy(mcp_release._load_yaml(mcp_release.COMPATIBILITY_PATH))
        manifest["status"] = "accepted"
        for entry in manifest["clients"]:
            entry["support_status"] = "accepted"
            entry["tested_version"] = "test-client-1.0"
            entry["tested_at"] = "2026-08-12T12:00:00Z"
            entry["evidence"] = {
                "url": (
                    "https://github.com/onurmatik/feature-request/releases/download/"
                    f"mcp-v1.0.0/{entry['client']}-acceptance.json"
                ),
                "sha256": mcp_release._sha256(entry["client"].encode()),
            }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "compatibility.yaml"
            path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            first = mcp_release.build_release_descriptor(
                source_commit=mcp_release._git_head(),
                compatibility_path=path,
            )
            second = mcp_release.build_release_descriptor(
                source_commit=mcp_release._git_head(),
                compatibility_path=path,
            )
        self.assertEqual(mcp_release._json_bytes(first), mcp_release._json_bytes(second))
        schema = mcp_release._load_json(mcp_release.RELEASE_SCHEMA_PATH)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(first)

    def test_dependency_lock_keeps_required_exact_versions(self):
        mcp_release.validate_dependencies()

    def test_native_deploy_consumes_stageops_mcp_without_owning_infrastructure(self):
        deploy_source = (mcp_release.ROOT / ".deploy" / "fabfile.py").read_text()
        settings_source = (mcp_release.ROOT / "config" / "settings.py").read_text()
        expected_steps = (
            "git reset --hard origin/main",
            "sync --frozen --no-dev",
            "manage.py collectstatic --noinput",
            "manage.py migrate --noinput",
            "manage.py check --deploy",
            "systemctl start {quote(socket)}",
        )
        for expected in expected_steps:
            self.assertIn(expected, deploy_source)
        for expected in (
            "restart_mcp_runtime",
            "MCP_SERVICE",
            "systemctl cat",
            "systemctl is-enabled --quiet",
            "FeatureRequest public MCP discovery smoke",
        ):
            self.assertIn(expected, deploy_source)
        for forbidden in (
            "pgbackrest",
            "take_database_backup",
            "Dockerfile",
            "systemctl reload nginx",
            "install_mcp_runtime",
        ):
            self.assertNotIn(forbidden, deploy_source)
        self.assertFalse(any((mcp_release.ROOT / ".deploy" / "systemd").glob("*")))
        self.assertFalse(any((mcp_release.ROOT / ".deploy" / "nginx").glob("*")))
        self.assertTrue((mcp_release.ROOT / "docs" / "mcp-deployment-handoff.md").is_file())
        handoff = (mcp_release.ROOT / "docs" / "mcp-deployment-handoff.md").read_text()
        self.assertIn("StageOps `app.yaml` owns", handoff)
        self.assertIn('"REFRESH_TOKEN_REUSE_PROTECTION": True', settings_source)

    def test_release_descriptor_binds_source_and_dependency_lock(self):
        manifest = copy.deepcopy(mcp_release._load_yaml(mcp_release.COMPATIBILITY_PATH))
        manifest["status"] = "accepted"
        for entry in manifest["clients"]:
            entry["support_status"] = "accepted"
            entry["tested_version"] = "test-client-1.0"
            entry["tested_at"] = "2026-08-12T12:00:00Z"
            entry["evidence"] = {
                "url": (
                    "https://github.com/onurmatik/feature-request/releases/download/"
                    f"mcp-v1.0.0/{entry['client']}-acceptance.json"
                ),
                "sha256": mcp_release._sha256(entry["client"].encode()),
            }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "compatibility.yaml"
            path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            descriptor = mcp_release.build_release_descriptor(
                source_commit=mcp_release._git_head(), compatibility_path=path
            )
        for field in (
            "source_tree_sha256",
            "dependency_lock_sha256",
        ):
            self.assertRegex(descriptor[field], r"^[0-9a-f]{64}$")

if __name__ == "__main__":
    unittest.main()
