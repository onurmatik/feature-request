#!/usr/bin/env python3
"""Validate and build immutable FeatureRequest MCP/OAuth 1.0 release metadata."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PIN_PATH = ROOT / "integration" / "agent-contract-pin.json"
PINNED_DESCRIPTOR_PATH = ROOT / "integration" / "agent-contract-release.json"
COMPATIBILITY_PATH = ROOT / "integration" / "client-compatibility.yaml"
RUNTIME_CONFORMANCE_PATH = ROOT / "integration" / "runtime-conformance.yaml"
CONTRACT_PATH = ROOT / "agent" / "contract.yaml"
CONTRACT_SCHEMA_PATH = ROOT / "agent" / "contract.schema.json"
MAPPING_PATH = ROOT / "agent" / "mappings" / "mcp-1.0.0.json"
VECTOR_PATH = ROOT / "agent" / "conformance" / "1.0.0" / "vectors.yaml"
RELEASE_SOURCES_PATH = ROOT / "release" / "sources.yaml"
RELEASE_SCHEMA_PATH = ROOT / "release" / "mcp-release.schema.json"
PYPROJECT_PATH = ROOT / "pyproject.toml"
LOCK_PATH = ROOT / "uv.lock"
SERVER_SOURCE_PATH = ROOT / "feature_request_mcp" / "server.py"
AGENT_SERVICE_SOURCE_PATH = ROOT / "agent_runtime" / "service.py"
CODEOWNERS_PATH = ROOT / ".github" / "CODEOWNERS"
CONFORMANCE_FRAMING = "utf8_relative_path_nul_raw_content_nul_v1"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2026-07-28"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
EVIDENCE_RE = re.compile(
    r"^https://github\.com/onurmatik/feature-request/releases/download/"
    r"mcp-v1\.0\.0/[A-Za-z0-9][A-Za-z0-9._~-]*$"
)

EXPECTED_CLIENTS = {
    ("chatgpt", "web"): {
        "tier": "primary",
        "callback_profile": "chatgpt_exact_connector_callback",
    },
    ("codex", "desktop_and_cli"): {
        "tier": "primary",
        "callback_profile": "exact_registered_ip_loopback",
    },
    ("claude", "remote_connector_and_desktop"): {
        "tier": "cross_agent",
        "callback_profile": "claude_exact_https_callbacks",
    },
    ("claude_code", "cli"): {
        "tier": "cross_agent",
        "callback_profile": "claude_code_localhost_callback",
    },
}

EXPECTED_LIVE_GATES = [
    "postgresql_process_concurrency",
    "separate_deployment_complete",
    "required_real_client_acceptance",
    "immutable_mcp_release",
]

EXPECTED_PROMOTION_ENVIRONMENTS = [
    {
        "name": "local",
        "promotes_to": "production",
        "requires": [
            "contract_stage_gate",
            "deterministic_release_descriptor",
            "versioned_conformance_vectors",
            "pinned_agent_contract_release",
            "oauth_mcp_repository_suite",
            "postgresql_process_concurrency",
            "exact_source_tree_digest",
            "dependency_lock_digest",
            "deployment_handoff",
        ],
    },
    {
        "name": "production",
        "promotes_to": None,
        "requires": [
            "separate_deployment_complete",
            "required_client_acceptance_evidence",
            "immutable_git_tag",
            "github_release",
            "digest_verification",
            "release_approval",
        ],
    },
]

EXACT_DEPENDENCIES = {
    "Django": "5.2.17",
    "django-oauth-toolkit": "3.4.0",
    "mcp": "2.0.0",
    "django-embedded-mcp": "0.3.0",
    "rfc8785": "0.1.4",
    "psycopg": "3.2.12",
}


class ReleaseGateError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseGateError(f"invalid or missing JSON artifact: {path}") from exc


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ReleaseGateError(f"invalid or missing YAML artifact: {path}") from exc


def _git_bytes(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def source_tree_sha256(commit: str) -> str:
    listing = _git_bytes("ls-tree", "-r", "-z", "--full-tree", commit)
    digest = hashlib.sha256()
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, object_type, object_id = metadata.split(b" ", 2)
        if object_type != b"blob":
            raise ReleaseGateError("source tree contains an unsupported non-blob entry")
        content = _git_bytes("cat-file", "blob", object_id.decode("ascii"))
        digest.update(raw_path)
        digest.update(b"\0")
        digest.update(mode)
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def dependency_lock_sha256(commit: str) -> str:
    return _sha256(_git_bytes("show", f"{commit}:uv.lock"))


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ReleaseGateError(f"{label} keys differ; missing={missing}, extra={extra}")


def _vector_digest(path: Path) -> str:
    relative = path.resolve().relative_to(ROOT.resolve()).as_posix().encode()
    return _sha256(relative + b"\0" + path.read_bytes() + b"\0")


def validate_contract_pin(*, check_git_tag: bool = True) -> dict[str, Any]:
    pin = _load_json(PIN_PATH)
    _exact_keys(
        pin,
        {
            "schema_version",
            "agent_contract_version",
            "tag",
            "release_url",
            "git_commit",
            "descriptor",
            "contract_sha256",
            "contract_schema_sha256",
            "conformance_vectors_sha256",
            "conformance_vectors_digest_framing",
            "mapping_sha256",
        },
        "Agent Contract pin",
    )
    if pin["schema_version"] != 1 or pin["agent_contract_version"] != "1.0.0":
        raise ReleaseGateError("Agent Contract pin must identify schema 1 / Contract 1.0.0")
    if pin["tag"] != "agent-contract-v1.0.0" or not COMMIT_RE.fullmatch(
        str(pin["git_commit"])
    ):
        raise ReleaseGateError("Agent Contract pin tag or immutable commit is invalid")
    if pin["release_url"] != (
        "https://github.com/onurmatik/feature-request/releases/tag/agent-contract-v1.0.0"
    ):
        raise ReleaseGateError("Agent Contract pin must reference the authoritative release")
    descriptor_ref = pin["descriptor"]
    if not isinstance(descriptor_ref, Mapping):
        raise ReleaseGateError("Agent Contract descriptor pin must be an object")
    _exact_keys(descriptor_ref, {"url", "sha256"}, "Agent Contract descriptor pin")
    if descriptor_ref["url"] != (
        "https://github.com/onurmatik/feature-request/releases/download/"
        "agent-contract-v1.0.0/contract-release.json"
    ):
        raise ReleaseGateError("Agent Contract descriptor URL is not immutable")
    local_digests = {
        "contract_sha256": _sha256(CONTRACT_PATH.read_bytes()),
        "contract_schema_sha256": _sha256(CONTRACT_SCHEMA_PATH.read_bytes()),
        "conformance_vectors_sha256": _vector_digest(VECTOR_PATH),
        "mapping_sha256": _sha256(MAPPING_PATH.read_bytes()),
    }
    for field, actual in local_digests.items():
        if pin.get(field) != actual or not SHA256_RE.fullmatch(actual):
            raise ReleaseGateError(f"pinned {field} does not match the released local asset")
    if pin["conformance_vectors_digest_framing"] != CONFORMANCE_FRAMING:
        raise ReleaseGateError("Agent Contract vector digest framing is unsupported")
    descriptor_bytes = PINNED_DESCRIPTOR_PATH.read_bytes()
    if descriptor_ref["sha256"] != _sha256(descriptor_bytes):
        raise ReleaseGateError("vendored immutable Contract descriptor digest is invalid")
    descriptor = _load_json(PINNED_DESCRIPTOR_PATH)
    for field in (
        "agent_contract_version",
        "git_commit",
        "contract_sha256",
        "contract_schema_sha256",
        "conformance_vectors_sha256",
        "conformance_vectors_digest_framing",
    ):
        expected = pin["git_commit"] if field == "git_commit" else pin[field]
        if descriptor.get(field) != expected:
            raise ReleaseGateError(f"Contract descriptor and pin disagree on {field}")
    if check_git_tag:
        result = subprocess.run(
            ["git", "rev-parse", f"{pin['tag']}^{{}}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode or result.stdout.strip() != pin["git_commit"]:
            raise ReleaseGateError("local immutable Agent Contract tag does not match its pin")
    return pin


def validate_compatibility(path: Path = COMPATIBILITY_PATH) -> tuple[dict[str, Any], list[str]]:
    manifest = _load_yaml(path)
    if not isinstance(manifest, Mapping):
        raise ReleaseGateError("client compatibility manifest must be an object")
    _exact_keys(
        manifest,
        {
            "schema_version",
            "server_version",
            "status",
            "registration_policy",
            "clients",
            "legacy_transport",
        },
        "client compatibility manifest",
    )
    if manifest["schema_version"] != 1 or str(manifest["server_version"]) != SERVER_VERSION:
        raise ReleaseGateError("compatibility manifest version must match MCP 1.0.0")
    policy = manifest["registration_policy"]
    if not isinstance(policy, Mapping):
        raise ReleaseGateError("registration_policy must be an object")
    if (
        policy.get("preferred") != "cimd"
        or policy.get("fallback") != "dcr"
        or policy.get("review_interval_days") != 90
        or policy.get("removal_gate", {}).get(
            "consecutive_production_days_without_successful_dcr_use"
        )
        != 90
    ):
        raise ReleaseGateError("CIMD/DCR lifecycle policy drifted from the approved decision")
    clients = manifest["clients"]
    if not isinstance(clients, list) or len(clients) != len(EXPECTED_CLIENTS):
        raise ReleaseGateError("compatibility manifest must contain the four required clients")
    by_key = {}
    pending: list[str] = []
    for entry in clients:
        if not isinstance(entry, Mapping):
            raise ReleaseGateError("each compatibility client must be an object")
        _exact_keys(
            entry,
            {
                "client",
                "surface",
                "tier",
                "tested_version",
                "transport",
                "registration_method",
                "callback_profile",
                "support_status",
                "tested_at",
                "evidence",
            },
            "compatibility client",
        )
        key = (str(entry["client"]), str(entry["surface"]))
        if key in by_key or key not in EXPECTED_CLIENTS:
            raise ReleaseGateError(f"unknown or duplicate compatibility client: {key}")
        expected = EXPECTED_CLIENTS[key]
        if (
            entry["tier"] != expected["tier"]
            or entry["callback_profile"] != expected["callback_profile"]
            or entry["transport"] != "streamable-http"
            or entry["registration_method"] != "cimd_preferred_dcr_fallback"
        ):
            raise ReleaseGateError(f"compatibility policy drift for {key[0]}")
        status = entry["support_status"]
        if status == "pending":
            if any(entry[field] is not None for field in ("tested_version", "tested_at", "evidence")):
                raise ReleaseGateError(f"pending client {key[0]} must not carry fabricated evidence")
            pending.append(key[0])
        elif status == "accepted":
            evidence = entry["evidence"]
            if not entry["tested_version"] or not entry["tested_at"] or not isinstance(
                evidence, Mapping
            ):
                raise ReleaseGateError(f"accepted client {key[0]} requires immutable evidence")
            _exact_keys(evidence, {"url", "sha256"}, f"{key[0]} acceptance evidence")
            if not EVIDENCE_RE.fullmatch(str(evidence["url"])) or not SHA256_RE.fullmatch(
                str(evidence["sha256"])
            ):
                raise ReleaseGateError(f"accepted client {key[0]} evidence is not immutable")
        else:
            raise ReleaseGateError(f"unsupported compatibility status for {key[0]}")
        by_key[key] = entry
    if set(by_key) != set(EXPECTED_CLIENTS):
        raise ReleaseGateError("required compatibility client set is incomplete")
    legacy = manifest["legacy_transport"]
    if not isinstance(legacy, Mapping) or legacy.get("enabled") is not False:
        raise ReleaseGateError("legacy initialize transport may only be enabled by evidence")
    expected_status = "implementation_complete_release_pending" if pending else "accepted"
    if manifest["status"] != expected_status:
        raise ReleaseGateError(
            f"compatibility manifest status must be {expected_status} for its evidence state"
        )
    return dict(manifest), sorted(pending)


def validate_dependencies() -> None:
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    declared = pyproject.get("project", {}).get("dependencies", [])
    versions: dict[str, str] = {}
    for dependency in declared:
        if "==" not in dependency:
            continue
        name, version = dependency.split("==", 1)
        versions[name.split("[", 1)[0]] = version
    for name, expected in EXACT_DEPENDENCIES.items():
        if versions.get(name) != expected:
            raise ReleaseGateError(f"{name} must be exactly pinned to {expected}")
    sources = pyproject.get("tool", {}).get("uv", {}).get("sources", {})
    if sources.get("django-embedded-mcp", {}).get("path") != "packages/django-embedded-mcp":
        raise ReleaseGateError("django-embedded-mcp must resolve from the repository package")
    lock = tomllib.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked = {entry["name"]: entry["version"] for entry in lock.get("package", []) if "version" in entry}
    normalized = {
        "Django": "django",
        "django-oauth-toolkit": "django-oauth-toolkit",
        "mcp": "mcp",
        "django-embedded-mcp": "django-embedded-mcp",
        "rfc8785": "rfc8785",
        "psycopg": "psycopg",
    }
    for name, expected in EXACT_DEPENDENCIES.items():
        if locked.get(normalized[name]) != expected:
            raise ReleaseGateError(f"uv.lock does not freeze {name} at {expected}")


def validate_registry() -> str:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from agent_runtime.contract import contract, public_registry, registry_digest

    definitions = contract()["tools"]
    tools = public_registry()
    if [tool.name for tool in tools] != list(definitions) or len(tools) != 23:
        raise ReleaseGateError("runtime registry tool names/order do not match Agent Contract 1.0.0")
    for tool in tools:
        definition = definitions[tool.name]
        annotations = tool.annotations
        scheme = tool.meta["securitySchemes"]
        if scheme != [{"type": "oauth2", "scopes": definition["required_scopes"]}]:
            raise ReleaseGateError(f"OAuth security metadata drift for {tool.name}")
        semantic_meta = tool.meta.get("io.featurerequest/agentContract", {})
        expected_semantic_meta = {
            "requiredCapabilities": definition["required_capabilities"],
            "resourceType": definition["resource_type"],
            "ownership": definition["ownership"],
            "approval": definition["approval"],
            "idempotency": definition["idempotency"],
            "dataClassification": definition["data_classification"],
            "auditProfile": definition["audit_profile"],
        }
        if semantic_meta != expected_semantic_meta:
            raise ReleaseGateError(f"Agent Contract metadata drift for {tool.name}")
        if (
            annotations.read_only_hint != (definition["side_effect"] == "read_only")
            or annotations.destructive_hint != bool(definition["destructive"])
            or annotations.open_world_hint != bool(definition["open_world"])
        ):
            raise ReleaseGateError(f"MCP annotations drift for {tool.name}")
    digest = registry_digest()
    if not SHA256_RE.fullmatch(digest):
        raise ReleaseGateError("tool registry digest is invalid")
    return digest


def validate_runtime_conformance() -> str:
    manifest = _load_yaml(RUNTIME_CONFORMANCE_PATH)
    if not isinstance(manifest, Mapping):
        raise ReleaseGateError("runtime conformance manifest must be an object")
    _exact_keys(
        manifest,
        {
            "schema_version",
            "server_version",
            "agent_contract_version",
            "vector_bundle_sha256",
            "status",
            "bindings",
            "live_acceptance",
        },
        "runtime conformance manifest",
    )
    if (
        manifest["schema_version"] != 1
        or str(manifest["server_version"]) != SERVER_VERSION
        or str(manifest["agent_contract_version"]) != "1.0.0"
        or manifest["status"] != "repository_complete_release_pending"
    ):
        raise ReleaseGateError("runtime conformance version/status is invalid")
    pin = _load_json(PIN_PATH)
    if manifest["vector_bundle_sha256"] != pin["conformance_vectors_sha256"]:
        raise ReleaseGateError("runtime conformance does not bind the pinned vector bundle")
    vector_bundle = _load_yaml(VECTOR_PATH)
    expected_ids = [item["id"] for item in vector_bundle["vectors"]]
    bindings = manifest["bindings"]
    if not isinstance(bindings, list) or len(bindings) != len(expected_ids):
        raise ReleaseGateError("runtime conformance must bind all 39 vectors exactly once")
    found_ids = []
    allowed_modes = {
        "runtime_dispatch",
        "runtime_policy",
        "agent_owned_precondition",
        "postgresql_process_concurrency",
        "audit_redaction",
    }
    for binding in bindings:
        if not isinstance(binding, Mapping):
            raise ReleaseGateError("runtime conformance binding must be an object")
        _exact_keys(
            binding,
            {"id", "repository_test", "evidence_mode", "repository_status"},
            "runtime conformance binding",
        )
        vector_id = str(binding["id"])
        found_ids.append(vector_id)
        if (
            binding["repository_status"] != "covered"
            or binding["evidence_mode"] not in allowed_modes
        ):
            raise ReleaseGateError(f"runtime conformance binding is incomplete: {vector_id}")
        test_ref = str(binding["repository_test"])
        parts = test_ref.split(".")
        if len(parts) < 3:
            raise ReleaseGateError(f"invalid runtime test reference: {test_ref}")
        module_name = ".".join(parts[:-2])
        class_name, method_name = parts[-2:]
        try:
            test_class = getattr(importlib.import_module(module_name), class_name)
            test_method = getattr(test_class, method_name)
        except (ImportError, AttributeError) as exc:
            raise ReleaseGateError(
                f"runtime test reference does not resolve: {test_ref}"
            ) from exc
        if not callable(test_method) or not method_name.startswith("test_"):
            raise ReleaseGateError(f"runtime test reference is not executable: {test_ref}")
    if found_ids != expected_ids or len(set(found_ids)) != len(found_ids):
        raise ReleaseGateError("runtime conformance vector order/set differs from the pin")
    live_acceptance = manifest["live_acceptance"]
    if not isinstance(live_acceptance, Mapping):
        raise ReleaseGateError("runtime conformance live acceptance gate must be an object")
    _exact_keys(
        live_acceptance,
        {"status", "required_gates"},
        "runtime live acceptance gate",
    )
    if (
        live_acceptance["status"] != "pending"
        or live_acceptance["required_gates"] != EXPECTED_LIVE_GATES
    ):
        raise ReleaseGateError("runtime live acceptance gates must remain truthfully pending")
    return _sha256(RUNTIME_CONFORMANCE_PATH.read_bytes())


def validate_static_security() -> None:
    source = SERVER_SOURCE_PATH.read_text(encoding="utf-8")
    for forbidden in ("FastMCP", "ApiToken", "httpx.AsyncClient"):
        if forbidden in source:
            raise ReleaseGateError(f"MCP runtime contains forbidden compatibility path: {forbidden}")
    agent_service = AGENT_SERVICE_SOURCE_PATH.read_text(encoding="utf-8")
    if "projects.api" in agent_service:
        raise ReleaseGateError(
            "MCP domain adapter must use shared project services, not the HTTP API module"
        )
    config = _load_json(ROOT / ".mcp.json")
    serialized = json.dumps(config).lower()
    if "bearer_token_env_var" in serialized or "feature_request_api_token" in serialized:
        raise ReleaseGateError("Codex MCP config must use OAuth discovery, not an API token")
    owners = CODEOWNERS_PATH.read_text(encoding="utf-8")
    for path in (
        "/agent/",
        "/feature_request_mcp/",
        "/mcp_oauth/",
        "/agent_runtime/",
        "/packages/django-embedded-mcp/",
        "/integration/",
        "/release/",
        "/scripts/mcp_release.py",
        "/projects/services.py",
    ):
        if f"{path} @onurmatik" not in owners:
            raise ReleaseGateError(f"CODEOWNERS is missing {path}")


def validate_release_sources() -> None:
    sources = _load_yaml(RELEASE_SOURCES_PATH)
    mcp = sources.get("descriptors", {}).get("mcp", {})
    expected = {
        "authoritative_store": "github_release_asset",
        "immutable_ref_pattern": "mcp-v{server_version}",
        "descriptor_schema_path": "release/mcp-release.schema.json",
        "descriptor_asset_name": "mcp-release.json",
        "runtime_artifact": "exact_native_git_checkout",
        "source_reference_format": "full_git_commit_sha1",
        "source_tree_digest_format": "git_tree_path_mode_content_nul_sha256",
        "deployment_handoff_path": "docs/mcp-deployment-handoff.md",
        "client_acceptance_store": "github_release_asset",
        "contract_pin_path": "integration/agent-contract-pin.json",
        "compatibility_manifest_path": "integration/client-compatibility.yaml",
        "runtime_conformance_manifest_path": "integration/runtime-conformance.yaml",
        "dependency_lock_path": "uv.lock",
        "digest_algorithm": "sha256",
    }
    for field, value in expected.items():
        if mcp.get(field) != value:
            raise ReleaseGateError(f"release source MCP field {field} must be {value!r}")
    if not mcp.get("consumer_resolution"):
        raise ReleaseGateError("MCP release source must document immutable resolution")
    if sources.get("promotion_environments") != EXPECTED_PROMOTION_ENVIRONMENTS:
        raise ReleaseGateError(
            "release promotion environments must preserve the gated local/production chain"
        )


def validate_repository(
    *, compatibility_path: Path = COMPATIBILITY_PATH, check_git_tag: bool = True
) -> dict[str, Any]:
    pin = validate_contract_pin(check_git_tag=check_git_tag)
    compatibility, pending = validate_compatibility(compatibility_path)
    validate_dependencies()
    registry_sha256 = validate_registry()
    runtime_conformance_sha256 = validate_runtime_conformance()
    validate_static_security()
    validate_release_sources()
    return {
        "pin": pin,
        "compatibility": compatibility,
        "pending_clients": pending,
        "tool_registry_sha256": registry_sha256,
        "runtime_conformance_sha256": runtime_conformance_sha256,
    }


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_release_descriptor(
    *,
    source_commit: str,
    compatibility_path: Path = COMPATIBILITY_PATH,
    check_git_tag: bool = True,
) -> dict[str, Any]:
    if not COMMIT_RE.fullmatch(source_commit):
        raise ReleaseGateError("source commit must be a full lowercase 40-character SHA-1")
    try:
        source_digest = source_tree_sha256(source_commit)
        dependency_digest = dependency_lock_sha256(source_commit)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ReleaseGateError("cannot resolve exact source identity") from exc
    state = validate_repository(
        compatibility_path=compatibility_path,
        check_git_tag=check_git_tag,
    )
    if state["pending_clients"]:
        raise ReleaseGateError(
            "public release requires immutable acceptance evidence for: "
            + ", ".join(state["pending_clients"])
        )
    clients = {}
    for entry in state["compatibility"]["clients"]:
        clients[entry["client"]] = {
            "surface": entry["surface"],
            "tier": entry["tier"],
            "tested_version": entry["tested_version"],
            "tested_at": entry["tested_at"],
            "transport": entry["transport"],
            "registration_method": entry["registration_method"],
            "callback_profile": entry["callback_profile"],
            "evidence": dict(entry["evidence"]),
        }
    pin = state["pin"]
    descriptor = {
        "schema_version": 1,
        "server": {"name": "feature-request", "version": SERVER_VERSION},
        "protocol_version": PROTOCOL_VERSION,
        "source_commit": source_commit,
        "source_tree_sha256": source_digest,
        "agent_contract": {
            "version": pin["agent_contract_version"],
            "tag": pin["tag"],
            "git_commit": pin["git_commit"],
            "release_url": pin["release_url"],
            "descriptor_url": pin["descriptor"]["url"],
            "descriptor_sha256": pin["descriptor"]["sha256"],
            "contract_sha256": pin["contract_sha256"],
            "contract_schema_sha256": pin["contract_schema_sha256"],
            "conformance_vectors_sha256": pin["conformance_vectors_sha256"],
            "mapping_sha256": pin["mapping_sha256"],
        },
        "tool_registry_sha256": state["tool_registry_sha256"],
        "runtime_conformance_sha256": state["runtime_conformance_sha256"],
        "client_compatibility_sha256": _sha256(compatibility_path.read_bytes()),
        "dependency_lock_sha256": dependency_digest,
        "acceptance": dict(sorted(clients.items())),
        "release_status": "ready",
    }
    schema = _load_json(RELEASE_SCHEMA_PATH)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(descriptor)
    return descriptor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="run repository MCP/OAuth stage gates")
    validate.add_argument("--compatibility", type=Path, default=COMPATIBILITY_PATH)
    build = subparsers.add_parser("build-release", help="build a sealed public descriptor")
    build.add_argument("--source-commit", default=None)
    build.add_argument("--compatibility", type=Path, default=COMPATIBILITY_PATH)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            state = validate_repository(compatibility_path=args.compatibility)
            suffix = (
                "release pending: " + ", ".join(state["pending_clients"])
                if state["pending_clients"]
                else "client acceptance complete"
            )
            print(f"MCP/OAuth {SERVER_VERSION} repository gate valid (23 tools; {suffix})")
            return 0
        descriptor = build_release_descriptor(
            source_commit=args.source_commit or _git_head(),
            compatibility_path=args.compatibility,
        )
        payload = _json_bytes(descriptor)
        if args.check:
            if args.output.read_bytes() != payload:
                raise ReleaseGateError(f"generated MCP release descriptor is stale: {args.output}")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(payload)
        return 0
    except (ReleaseGateError, OSError, subprocess.SubprocessError) as exc:
        print(f"MCP/OAuth release gate failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
