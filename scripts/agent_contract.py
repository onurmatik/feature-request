#!/usr/bin/env python3
"""Validate and build deterministic artifacts from the canonical Agent Contract.

The module deliberately depends only on PyYAML and jsonschema.  It does not import
the Django application or the MCP runtime: the Contract gate must remain a
transport-neutral, reproducible build step.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml
from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "agent" / "contract.yaml"
DEFAULT_SCHEMA = REPO_ROOT / "agent" / "contract.schema.json"
DEFAULT_AGENTS = REPO_ROOT / "agents.json"
DEFAULT_RELEASE_SOURCES = REPO_ROOT / "release" / "sources.yaml"
DEFAULT_ROOT_POLICY = REPO_ROOT / "AGENTS.md"
DEFAULT_SKILL_PROJECTIONS = (
    REPO_ROOT / "skills" / "feature-request" / "SKILL.md",
    REPO_ROOT / ".agents" / "skills" / "feature-request" / "SKILL.md",
)

TOOL_FIELDS = {
    "title",
    "description",
    "exposure",
    "input_schema",
    "output_schema",
    "authentication",
    "required_scopes",
    "required_capabilities",
    "resource_type",
    "ownership",
    "side_effect",
    "destructive",
    "open_world",
    "approval",
    "idempotency",
    "errors",
    "data_classification",
    "audit_profile",
    "long_running",
}
SIDE_EFFECTS = {
    "read_only",
    "reversible_write",
    "irreversible_write",
    "external_effect",
}
STANDARD_VECTOR_CATEGORIES = {
    "success",
    "invalid_input",
    "missing_capability",
    "ownership_isolation",
    "capability_plan_matrix",
    "quota_concurrency",
    "idempotent_replay",
    "idempotency_conflict",
    "approval",
    "uncertain_external_effect",
    "redaction",
    "async_status",
}
EXPECTED_TOOLS = {
    "get_account_capabilities",
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
}
MUTATION_TOOLS = {
    "create_project",
    "update_project",
    "delete_project",
    "create_request",
    "link_duplicate_request",
    "unlink_duplicate_request",
    "link_delivery_artifact",
    "unlink_delivery_artifact",
    "update_request",
    "transition_request",
    "add_request_comment",
    "update_request_comment",
}
CREATE_WITHOUT_REVISION_TOOLS = {
    "create_project",
    "create_request",
    "add_request_comment",
}
EXISTING_RESOURCE_MUTATION_TOOLS = MUTATION_TOOLS - CREATE_WITHOUT_REVISION_TOOLS
EXTERNAL_EFFECT_TOOLS = {
    "create_request",
    "add_request_comment",
    "update_request_comment",
}
DESTRUCTIVE_TOOLS = {"delete_project", "transition_request"}
EXPECTED_OWNERSHIP = {
    "get_account_capabilities": "authenticated_actor",
    "list_projects": "project_owner",
    "get_project": "project_owner",
    "create_project": "project_owner",
    "update_project": "project_owner",
    "delete_project": "project_owner",
    "list_requests": "public_board_authenticated",
    "get_request": "public_board_authenticated",
    "list_request_comments": "public_board_authenticated",
    "get_queue_snapshot": "owned_project_feed",
    "find_duplicate_candidates": "public_board_authenticated",
    "list_request_activity": "project_owner_or_request_author",
    "list_request_changes": "owned_project_feed",
    "list_delivery_artifacts": "project_owner_or_request_author",
    "create_request": "public_board_authenticated",
    "link_duplicate_request": "project_owner_or_request_author",
    "unlink_duplicate_request": "project_owner_or_request_author",
    "link_delivery_artifact": "project_owner_or_request_author",
    "unlink_delivery_artifact": "project_owner_or_request_author",
    "update_request": "project_owner_or_request_author",
    "transition_request": "project_owner_or_request_author",
    "add_request_comment": "public_board_authenticated",
    "update_request_comment": "comment_author_or_project_owner",
}
EXPECTED_SIDE_EFFECTS = {
    **{name: "read_only" for name in EXPECTED_TOOLS - MUTATION_TOOLS},
    **{
        name: "reversible_write"
        for name in MUTATION_TOOLS - EXTERNAL_EFFECT_TOOLS - {"delete_project"}
    },
    **{name: "external_effect" for name in EXTERNAL_EFFECT_TOOLS},
    "delete_project": "irreversible_write",
}
EXPECTED_AUDIT_PROFILES = {
    **{name: "read" for name in EXPECTED_TOOLS - MUTATION_TOOLS},
    **{
        name: "write"
        for name in MUTATION_TOOLS - EXTERNAL_EFFECT_TOOLS - DESTRUCTIVE_TOOLS
    },
    **{name: "external" for name in EXTERNAL_EFFECT_TOOLS},
    **{name: "destructive" for name in DESTRUCTIVE_TOOLS},
}
NO_APPROVAL = {
    "mode": "none",
    "owner": "none",
    "conditions": [],
    "confirmation_field": None,
    "preconditions": [],
}
EXTERNAL_EFFECT_APPROVAL = {
    "mode": "always",
    "owner": "agent",
    "conditions": ["current_turn_explicit_user_intent"],
    "confirmation_field": None,
    "preconditions": [],
}
DELETE_PROJECT_APPROVAL = {
    "mode": "always",
    "owner": "agent",
    "conditions": ["current_turn_explicit_user_intent"],
    "confirmation_field": "confirm_project_id",
    "preconditions": ["get_project_same_turn", "confirmation_matches_project_id"],
}
TRANSITION_REQUEST_APPROVAL = {
    "mode": "conditional",
    "owner": "agent",
    "conditions": ["target_status_is_done_or_closed", "current_turn_explicit_user_intent"],
    "confirmation_field": None,
    "preconditions": ["list_delivery_artifacts_same_turn", "delivery_evidence_inspected"],
}
REQUIRED_IDEMPOTENCY = {
    "mode": "required",
    "key_field": "idempotency_key",
    "key_scope": "authenticated_actor_id+tool_name",
    "guarantee_hours": 24,
    "replay": "return_original_result",
    "conflict": "idempotency_conflict",
    "uncertain_result": "authoritative_read_before_retry",
}
NO_IDEMPOTENCY = {
    "mode": "not_required",
    "key_field": None,
    "key_scope": None,
    "guarantee_hours": None,
    "replay": "not_applicable",
    "conflict": "not_applicable",
    "uncertain_result": "not_applicable",
}
PUBLIC_UNTRUSTED_INPUT_TOOLS = {
    "create_project",
    "update_project",
    "find_duplicate_candidates",
    "create_request",
    "link_duplicate_request",
    "unlink_duplicate_request",
    "link_delivery_artifact",
    "update_request",
    "transition_request",
    "add_request_comment",
    "update_request_comment",
}
PUBLIC_UNTRUSTED_OUTPUT_TOOLS = EXPECTED_TOOLS - {
    "get_account_capabilities",
    "delete_project",
    "unlink_delivery_artifact",
}
CAPABILITY_TOOLS = {
    "project_management": {
        "list_projects",
        "get_project",
        "create_project",
        "update_project",
        "delete_project",
    },
    "request_management": {
        "list_requests",
        "get_request",
        "create_request",
        "update_request",
        "transition_request",
    },
    "request_collaboration": {
        "list_request_comments",
        "add_request_comment",
        "update_request_comment",
    },
    "duplicate_evidence": {
        "find_duplicate_candidates",
        "link_duplicate_request",
        "unlink_duplicate_request",
    },
    "delivery_evidence": {
        "list_delivery_artifacts",
        "link_delivery_artifact",
        "unlink_delivery_artifact",
    },
    "activity_feed": {
        "get_queue_snapshot",
        "list_request_activity",
        "list_request_changes",
    },
}
EXPECTED_APPLICATION_ERRORS = {
    "invalid_input",
    "permission_denied",
    "not_found",
    "capacity_reached",
    "quota_exhausted",
    "rate_limited",
    "feature_unavailable",
    "revision_conflict",
    "idempotency_conflict",
    "moderation_rejected",
    "dependency_unavailable",
    "approval_required",
    "confirmation_mismatch",
    "invalid_state",
}
SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CONFORMANCE_DIGEST_FRAMING = "utf8_relative_path_nul_raw_content_nul_v1"
BREAKING_DECISION_FIELDS = {
    "schema_version",
    "decision_id",
    "status",
    "decided_at",
    "effective_at",
    "from_major",
    "to_major",
    "strategy",
    "previous_major_support_until",
    "rationale",
}


class ContractError(RuntimeError):
    """Raised when a Contract-stage gate fails."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects keys hidden by YAML's last-key-wins rule."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ContractError("YAML mapping keys must be scalar/hashable") from exc
        if duplicate:
            raise ContractError(f"duplicate YAML mapping key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _load_yaml(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = yaml.load(handle, Loader=_UniqueKeyLoader)
    except FileNotFoundError as exc:
        raise ContractError(f"required file does not exist: {path}") from exc
    except yaml.YAMLError as exc:
        raise ContractError(f"invalid YAML in {path}: {exc}") from exc
    if value is None:
        raise ContractError(f"empty YAML document: {path}")
    return value


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ContractError(f"required file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {path}: {exc}") from exc


def _json_bytes(value: Any) -> bytes:
    """Return the one canonical JSON representation used by all generated files."""

    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path_for_version(version: str) -> Path:
    return REPO_ROOT / "agent" / "conformance" / version / "vectors.yaml"


def _mapping_path_for_version(version: str) -> Path:
    return REPO_ROOT / "agent" / "mappings" / f"mcp-{version}.json"


def _catalog_keys(value: Any, *, field: str) -> set[str]:
    if isinstance(value, Mapping):
        return {str(item) for item in value}
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            if isinstance(item, str):
                result.add(item)
            elif isinstance(item, Mapping):
                key = item.get("name") or item.get("code") or item.get("id")
                if key:
                    result.add(str(key))
        return result
    raise ContractError(f"{field} must be an object or array")


def _resolve_local_ref(document: Mapping[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        raise ContractError(f"only local JSON Schema refs are allowed, got {reference!r}")
    current: Any = document
    for raw_segment in reference[2:].split("/"):
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or segment not in current:
            raise ContractError(f"unresolved JSON Schema ref: {reference}")
        current = current[segment]
    return current


def _walk_json(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _validate_embedded_schemas(contract: Mapping[str, Any]) -> None:
    definitions = contract.get("$defs", {})
    if not isinstance(definitions, Mapping):
        raise ContractError("contract.$defs must be an object")
    schema_document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": definitions,
    }
    Draft202012Validator.check_schema(schema_document)

    schemas: list[tuple[str, Any]] = [(f"$defs.{name}", value) for name, value in definitions.items()]
    for tool_name, tool in contract.get("tools", {}).items():
        schemas.append((f"tools.{tool_name}.input_schema", tool.get("input_schema")))
        schemas.append((f"tools.{tool_name}.output_schema", tool.get("output_schema")))

    for label, schema in schemas:
        if not isinstance(schema, Mapping):
            raise ContractError(f"{label} must be a JSON Schema object")
        candidate = dict(schema_document)
        candidate["allOf"] = [schema]
        try:
            Draft202012Validator.check_schema(candidate)
        except Exception as exc:
            raise ContractError(f"invalid embedded JSON Schema at {label}: {exc}") from exc
        for node in _walk_json(schema):
            if isinstance(node, Mapping) and "$ref" in node:
                _resolve_local_ref(contract, str(node["$ref"]))
            if isinstance(node, Mapping) and node.get("type") == "object":
                if node.get("additionalProperties") is not False:
                    raise ContractError(
                        f"{label} contains an object schema without additionalProperties: false"
                    )

    error_envelope = definitions.get("application_error_envelope")
    if not isinstance(error_envelope, Mapping):
        raise ContractError("$defs.application_error_envelope is required")
    expected_fields = {"code", "message", "retryable", "request_id", "details"}
    if (
        error_envelope.get("type") != "object"
        or error_envelope.get("additionalProperties") is not False
        or set(error_envelope.get("required", [])) != expected_fields
        or set(error_envelope.get("properties", {})) != expected_fields
    ):
        raise ContractError(
            "$defs.application_error_envelope must be closed and require code, message, retryable, request_id, details"
        )
    code_schema = error_envelope["properties"]["code"]
    code_values: set[str] = set()
    if isinstance(code_schema, Mapping):
        if isinstance(code_schema.get("enum"), list):
            code_values = {str(value) for value in code_schema["enum"]}
        elif isinstance(code_schema.get("$ref"), str):
            resolved = _resolve_local_ref(contract, code_schema["$ref"])
            if isinstance(resolved, Mapping) and isinstance(resolved.get("enum"), list):
                code_values = {str(value) for value in resolved["enum"]}
    if code_values != _catalog_keys(
        contract.get("application_errors", {}), field="application_errors"
    ):
        raise ContractError("application error envelope code enum must equal the error catalog")
    detail_schema = error_envelope["properties"]["details"]
    detail_properties = detail_schema.get("properties", {}) if isinstance(detail_schema, Mapping) else {}
    declared_detail_fields = {
        str(field)
        for application_error in contract.get("application_errors", {}).values()
        if isinstance(application_error, Mapping)
        for field in application_error.get("details", [])
    }
    if not declared_detail_fields <= set(detail_properties):
        missing = sorted(declared_detail_fields - set(detail_properties))
        raise ContractError(
            "application error detail fields are absent from the closed envelope: "
            + ", ".join(missing)
        )


def _effective_object_fields(
    contract: Mapping[str, Any], schema: Any, seen_refs: set[str] | None = None
) -> tuple[set[str], set[str]]:
    """Return required/property names contributed by local refs and allOf branches."""

    if not isinstance(schema, Mapping):
        return set(), set()
    seen = set() if seen_refs is None else set(seen_refs)
    required = {str(item) for item in schema.get("required", [])}
    properties_value = schema.get("properties", {})
    properties = (
        {str(item) for item in properties_value}
        if isinstance(properties_value, Mapping)
        else set()
    )
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/") and reference not in seen:
        seen.add(reference)
        ref_required, ref_properties = _effective_object_fields(
            contract, _resolve_local_ref(contract, reference), seen
        )
        required.update(ref_required)
        properties.update(ref_properties)
    for branch in schema.get("allOf", []):
        branch_required, branch_properties = _effective_object_fields(contract, branch, seen)
        required.update(branch_required)
        properties.update(branch_properties)
    return required, properties


def _expected_approval(tool_name: str) -> Mapping[str, Any]:
    if tool_name == "delete_project":
        return DELETE_PROJECT_APPROVAL
    if tool_name == "transition_request":
        return TRANSITION_REQUEST_APPROVAL
    if tool_name in EXTERNAL_EFFECT_TOOLS:
        return EXTERNAL_EFFECT_APPROVAL
    return NO_APPROVAL


def _validate_tool_catalog(contract: Mapping[str, Any]) -> None:
    tools = contract.get("tools")
    if not isinstance(tools, Mapping) or not tools:
        raise ContractError("contract.tools must be a non-empty object")
    scopes = _catalog_keys(contract.get("scopes", {}), field="scopes")
    capabilities = _catalog_keys(contract.get("capabilities", {}), field="capabilities")
    errors = _catalog_keys(contract.get("application_errors", {}), field="application_errors")
    classifications = _catalog_keys(
        contract.get("data_classifications", {}), field="data_classifications"
    )

    version_major, version_minor, _ = _parse_semver(
        str(contract.get("agent_contract_version", ""))
    )
    strict_v1_0 = version_major == 1 and version_minor == 0
    if strict_v1_0 and set(tools) != EXPECTED_TOOLS:
        missing = sorted(EXPECTED_TOOLS - set(tools))
        extra = sorted(set(tools) - EXPECTED_TOOLS)
        raise ContractError(
            "public tool catalog differs from Agent Contract 1.0.0"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; unknown: {', '.join(extra)}" if extra else "")
        )
    if version_major == 1 and not EXPECTED_TOOLS <= set(tools):
        raise ContractError("Agent Contract 1.x must retain every 1.0 public tool")
    if strict_v1_0 and errors != EXPECTED_APPLICATION_ERRORS:
        raise ContractError("application error catalog differs from Agent Contract 1.0.0")
    if version_major == 1 and not EXPECTED_APPLICATION_ERRORS <= errors:
        raise ContractError("Agent Contract 1.x must retain every 1.0 application error")

    mapping = contract.get("mapping")
    expected_mapping_snapshot = (
        f"agent/mappings/mcp-{contract['agent_contract_version']}.json"
    )
    if not isinstance(mapping, Mapping) or mapping.get("snapshot") != expected_mapping_snapshot:
        raise ContractError(
            f"mapping.snapshot must be {expected_mapping_snapshot}"
        )

    expected_capability_by_tool = {
        tool_name: capability
        for capability, tool_names in CAPABILITY_TOOLS.items()
        for tool_name in tool_names
    }
    mutation_count = 0
    for name, tool in tools.items():
        is_baseline_tool = name in EXPECTED_TOOLS
        if not SNAKE_CASE_RE.fullmatch(str(name)):
            raise ContractError(f"tool name is not stable snake_case: {name!r}")
        if not isinstance(tool, Mapping):
            raise ContractError(f"tools.{name} must be an object")
        missing = sorted(TOOL_FIELDS - set(tool))
        if missing:
            raise ContractError(f"tools.{name} is missing metadata: {', '.join(missing)}")
        if tool["side_effect"] not in SIDE_EFFECTS:
            raise ContractError(f"tools.{name}.side_effect is invalid")
        if tool["exposure"] != "public":
            raise ContractError(f"tools.{name} must remain publicly discoverable")
        if tool["authentication"] != "required":
            raise ContractError(f"tools.{name} must require authentication")
        if is_baseline_tool and tool["ownership"] != EXPECTED_OWNERSHIP[name]:
            raise ContractError(
                f"tools.{name}.ownership must be {EXPECTED_OWNERSHIP[name]}"
            )
        if is_baseline_tool and tool["side_effect"] != EXPECTED_SIDE_EFFECTS[name]:
            raise ContractError(
                f"tools.{name}.side_effect must be {EXPECTED_SIDE_EFFECTS[name]}"
            )
        expected_destructive = name in DESTRUCTIVE_TOOLS
        expected_open_world = name in EXTERNAL_EFFECT_TOOLS
        if is_baseline_tool and tool["destructive"] is not expected_destructive:
            raise ContractError(
                f"tools.{name}.destructive must be {str(expected_destructive).lower()}"
            )
        if is_baseline_tool and tool["open_world"] is not expected_open_world:
            raise ContractError(
                f"tools.{name}.open_world must be {str(expected_open_world).lower()}"
            )
        is_mutation = tool["side_effect"] != "read_only"
        generic_audit_profile = (
            "read"
            if not is_mutation
            else "external"
            if tool["side_effect"] == "external_effect"
            else "destructive"
            if tool["destructive"] or tool["side_effect"] == "irreversible_write"
            else "write"
        )
        expected_audit_profile = (
            EXPECTED_AUDIT_PROFILES[name] if is_baseline_tool else generic_audit_profile
        )
        if tool["audit_profile"] != expected_audit_profile:
            raise ContractError(
                f"tools.{name}.audit_profile must be {expected_audit_profile}"
            )

        required_scopes = tool["required_scopes"]
        required_capabilities = tool["required_capabilities"]
        if not isinstance(required_scopes, list) or not set(required_scopes) <= scopes:
            raise ContractError(f"tools.{name} references an unknown scope")
        if not isinstance(required_capabilities, list) or not set(required_capabilities) <= capabilities:
            raise ContractError(f"tools.{name} references an unknown capability")
        expected_capability = expected_capability_by_tool.get(str(name))
        expected_capabilities = [expected_capability] if expected_capability else []
        if is_baseline_tool and required_capabilities != expected_capabilities:
            raise ContractError(
                f"tools.{name} must require exactly {expected_capabilities}"
            )
        expected_scopes = ["write"] if is_mutation else ["read"]
        if required_scopes != expected_scopes:
            raise ContractError(
                f"tools.{name} violates minimum scope mapping: expected {expected_scopes}"
            )
        if not isinstance(tool["errors"], list) or not set(tool["errors"]) <= errors:
            raise ContractError(f"tools.{name} references an unknown application error")
        resources = contract.get("resources", {})
        ownership_policies = contract.get("authorization_policies", {})
        audit_profiles = contract.get("audit", {}).get("profiles", {})
        if tool["resource_type"] not in resources:
            raise ContractError(f"tools.{name} references an unknown resource_type")
        if tool["ownership"] not in ownership_policies:
            raise ContractError(f"tools.{name} references an unknown ownership policy")
        if tool["audit_profile"] not in audit_profiles:
            raise ContractError(f"tools.{name} references an unknown audit profile")

        classification = tool["data_classification"]
        if not isinstance(classification, Mapping):
            raise ContractError(f"tools.{name}.data_classification must be an object")
        expected_classification_fields = {
            "input",
            "output",
            "untrusted_output",
            "audit_redaction",
        }
        if set(classification) != expected_classification_fields:
            raise ContractError(
                f"tools.{name}.data_classification must declare exactly input, output, untrusted_output, audit_redaction"
            )
        used_classifications: set[str] = set()
        for direction in ("input", "output"):
            values = classification.get(direction, [])
            if not isinstance(values, list):
                raise ContractError(f"tools.{name}.data_classification.{direction} must be an array")
            used_classifications.update(str(value) for value in values)
        if not used_classifications <= classifications:
            raise ContractError(f"tools.{name} references an unknown data classification")
        if used_classifications & {"personal_data", "secret"}:
            raise ContractError(f"tools.{name} must not expose personal_data or secret in tool I/O")
        input_classifications = set(classification["input"])
        output_classifications = set(classification["output"])
        if is_baseline_tool and ("public_untrusted_content" in input_classifications) != (
            name in PUBLIC_UNTRUSTED_INPUT_TOOLS
        ):
            raise ContractError(f"tools.{name} has incorrect untrusted input classification")
        expected_untrusted_output = (
            name in PUBLIC_UNTRUSTED_OUTPUT_TOOLS
            if is_baseline_tool
            else "public_untrusted_content" in output_classifications
        )
        if is_baseline_tool and (
            "public_untrusted_content" in output_classifications
        ) != expected_untrusted_output:
            raise ContractError(f"tools.{name} has incorrect untrusted output classification")
        if classification["untrusted_output"] is not expected_untrusted_output:
            raise ContractError(f"tools.{name}.untrusted_output is inconsistent with its output")
        redaction = classification["audit_redaction"]
        if not isinstance(redaction, list):
            raise ContractError(f"tools.{name}.data_classification.audit_redaction must be an array")
        audit_forbidden = set(contract.get("audit", {}).get("forbidden_fields", []))
        if not set(redaction) <= audit_forbidden:
            raise ContractError(f"tools.{name} audit redaction references a non-forbidden field")
        if (
            "public_untrusted_content" in input_classifications | output_classifications
            and not ({"raw_user_content", "raw_url"} & set(redaction))
        ):
            raise ContractError(f"tools.{name} public untrusted content must be redacted in audit")

        is_read = not is_mutation
        if is_baseline_tool and is_read == (name in MUTATION_TOOLS):
            raise ContractError(f"tools.{name} has the wrong read/mutation classification")
        approval = tool["approval"]
        idempotency = tool["idempotency"]
        if not isinstance(approval, Mapping) or not isinstance(idempotency, Mapping):
            raise ContractError(f"tools.{name} approval/idempotency metadata must be objects")
        if is_baseline_tool:
            if dict(approval) != dict(_expected_approval(str(name))):
                raise ContractError(f"tools.{name}.approval differs from the approved policy")
        elif is_read and dict(approval) != NO_APPROVAL:
            raise ContractError(f"read-only tool {name} must not require approval")
        elif tool["side_effect"] in {"external_effect", "irreversible_write"}:
            if (
                approval.get("owner") != "agent"
                or "current_turn_explicit_user_intent"
                not in approval.get("conditions", [])
            ):
                raise ContractError(
                    f"external/irreversible tool {name} requires agent-owned current-turn approval"
                )
        expected_idempotency = REQUIRED_IDEMPOTENCY if is_mutation else NO_IDEMPOTENCY
        if dict(idempotency) != expected_idempotency:
            raise ContractError(f"tools.{name}.idempotency differs from the approved policy")

        input_required, input_properties = _effective_object_fields(
            contract, tool["input_schema"]
        )
        if is_mutation:
            mutation_count += 1
            if "idempotency_key" not in input_required or "idempotency_key" not in input_properties:
                raise ContractError(
                    f"mutation tool {name} input must require idempotency_key"
                )
            if is_baseline_tool and name in EXISTING_RESOURCE_MUTATION_TOOLS:
                if "expected_revision" not in input_required or "expected_revision" not in input_properties:
                    raise ContractError(
                        f"existing-resource mutation {name} input must require expected_revision"
                    )
            elif is_baseline_tool and (
                "expected_revision" in input_required or "expected_revision" in input_properties
            ):
                raise ContractError(
                    f"create mutation {name} input must not accept or require expected_revision"
                )
            if name == "delete_project" and not {
                "project_id",
                "confirm_project_id",
            } <= input_required:
                raise ContractError(
                    "delete_project input must require project_id and confirm_project_id"
                )
            if name == "transition_request" and "status" not in input_required:
                raise ContractError("transition_request input must require target status")
        elif "idempotency_key" in input_required or "idempotency_key" in input_properties:
            raise ContractError(f"read-only tool {name} input must not accept idempotency_key")

    if strict_v1_0 and mutation_count != 12:
        raise ContractError(f"expected 12 mutation tools, found {mutation_count}")
    if version_major == 1 and mutation_count < 12:
        raise ContractError("Agent Contract 1.x must retain all 1.0 mutation tools")

    external_tools = {
        name for name, tool in tools.items() if tool["side_effect"] == "external_effect"
    }
    if strict_v1_0 and external_tools != EXTERNAL_EFFECT_TOOLS:
        raise ContractError("external-effect tool catalog differs from the approved Contract")
    destructive_tools = {name for name, tool in tools.items() if tool["destructive"]}
    if strict_v1_0 and destructive_tools != DESTRUCTIVE_TOOLS:
        raise ContractError("destructive tool annotations differ from the approved Contract")
    open_world_tools = {name for name, tool in tools.items() if tool["open_world"]}
    if strict_v1_0 and open_world_tools != external_tools:
        raise ContractError("only moderation/notification external-effect tools may be open-world")

    bootstrap = contract.get("bootstrap")
    if not isinstance(bootstrap, Mapping) or not isinstance(bootstrap.get("tool"), str):
        raise ContractError("bootstrap.tool must name the canonical bootstrap tool")
    bootstrap_name = bootstrap["tool"]
    if bootstrap_name != "get_account_capabilities" or bootstrap_name not in tools:
        raise ContractError("bootstrap.tool must be get_account_capabilities")
    bootstrap_tool = tools[bootstrap_name]
    if bootstrap_tool["side_effect"] != "read_only" or bootstrap_tool["required_capabilities"]:
        raise ContractError("bootstrap tool must be read-only and require no capability")

    instructions = contract.get("server_instructions")
    if not isinstance(instructions, Mapping) or not instructions.get("summary"):
        raise ContractError("server_instructions.summary is required")
    rules = instructions.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ContractError("server_instructions.rules must be a non-empty array")
    rule_ids = [rule.get("id") for rule in rules if isinstance(rule, Mapping)]
    if len(rule_ids) != len(rules) or len(set(rule_ids)) != len(rule_ids) or None in rule_ids:
        raise ContractError("server instruction rule ids must be present and unique")


def _declared_plans(contract: Mapping[str, Any]) -> set[str]:
    plans: set[str] = set()
    capabilities = contract.get("capabilities", {})
    if isinstance(capabilities, Mapping):
        for capability in capabilities.values():
            if isinstance(capability, Mapping):
                available_on = capability.get("available_on", [])
                if isinstance(available_on, list):
                    plans.update(str(item) for item in available_on)
    return plans


def _validate_vector_context(
    contract: Mapping[str, Any], vector: Mapping[str, Any], vector_id: str
) -> None:
    context = vector.get("context")
    if not isinstance(context, Mapping):
        raise ContractError(f"vector {vector_id} has no context object")
    required = {
        "authenticated_actor_id",
        "authenticated_client_id",
        "tenant_id",
        "scopes",
        "capabilities",
        "ownership_fixture",
        "plan",
    }
    missing = sorted(required - set(context))
    if missing:
        raise ContractError(f"vector {vector_id} context is missing: {', '.join(missing)}")
    if context["tenant_id"] is not None:
        raise ContractError(f"vector {vector_id} must use tenant_id: null")
    scopes = context["scopes"]
    capabilities = context["capabilities"]
    if not isinstance(scopes, list) or not set(scopes) <= _catalog_keys(
        contract.get("scopes", {}), field="scopes"
    ):
        raise ContractError(f"vector {vector_id} context contains an unknown scope")
    if not isinstance(capabilities, list) or not set(capabilities) <= _catalog_keys(
        contract.get("capabilities", {}), field="capabilities"
    ):
        raise ContractError(f"vector {vector_id} context contains an unknown capability")
    if context["plan"] not in _declared_plans(contract):
        raise ContractError(f"vector {vector_id} context contains an unknown plan")


def _effective_vector_categories(vector: Mapping[str, Any]) -> set[str]:
    result = {str(vector.get("category"))}
    covers = vector.get("covers", [])
    if covers:
        if not isinstance(covers, list):
            raise ContractError(f"vector {vector.get('id')} covers must be an array")
        result.update(str(item) for item in covers)
    if not result <= STANDARD_VECTOR_CATEGORIES:
        raise ContractError(f"vector {vector.get('id')} covers an unknown category")
    return result


def _schema_validator(contract: Mapping[str, Any], schema: Mapping[str, Any]) -> Draft202012Validator:
    document: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$defs": contract["$defs"],
        "allOf": [schema],
    }
    return Draft202012Validator(document, format_checker=FormatChecker())


def _matrix_value(
    vector: Mapping[str, Any], field: str, tool_name: str, *, required: bool = True
) -> Any:
    per_tool_name = f"{field}_by_tool"
    if per_tool_name in vector:
        per_tool = vector[per_tool_name]
        if not isinstance(per_tool, Mapping) or tool_name not in per_tool:
            raise ContractError(
                f"vector {vector.get('id')} {per_tool_name} is missing {tool_name}"
            )
        return per_tool[tool_name]
    if field in vector:
        return vector[field]
    if required:
        raise ContractError(f"vector {vector.get('id')} is missing {field}")
    return None


def _validate_vector_examples(
    contract: Mapping[str, Any],
    vector: Mapping[str, Any],
    vector_tools: set[str],
    effective_categories: set[str],
) -> None:
    vector_id = str(vector["id"])
    expected = vector["expected"]
    audit = expected.get("audit")
    if not isinstance(audit, Mapping):
        raise ContractError(f"vector {vector_id} expected.audit must be an object")
    if not ({"profile", "profile_by_tool"} & set(audit)) or "record_fields" not in audit:
        raise ContractError(
            f"vector {vector_id} expected.audit must declare profile/profile_by_tool and record_fields"
        )
    if not isinstance(audit["record_fields"], list):
        raise ContractError(f"vector {vector_id} audit record_fields must be an array")
    record_fields = {str(item) for item in audit["record_fields"]}
    required_audit_fields = {str(item) for item in contract["audit"]["required_fields"]}
    forbidden_audit_fields = {str(item) for item in contract["audit"]["forbidden_fields"]}
    missing_audit_fields = sorted(required_audit_fields - record_fields)
    if missing_audit_fields:
        raise ContractError(
            f"vector {vector_id} audit is missing required fields: {', '.join(missing_audit_fields)}"
        )
    leaked_fields = sorted(forbidden_audit_fields & record_fields)
    if leaked_fields:
        raise ContractError(
            f"vector {vector_id} audit records forbidden fields: {', '.join(leaked_fields)}"
        )

    for tool_name in vector_tools:
        tool = contract["tools"][tool_name]
        if tool_name in MUTATION_TOOLS and "idempotency_id" not in record_fields:
            raise ContractError(f"mutation vector {vector_id} audit must record idempotency_id")
        audit_profile = _matrix_value(audit, "profile", tool_name)
        if audit_profile != tool["audit_profile"]:
            raise ContractError(
                f"vector {vector_id} audit profile {audit_profile!r} does not match {tool_name}"
            )
        profile = contract["audit"]["profiles"][audit_profile]
        profile_extra_fields = {
            str(item) for item in profile.get("extra_fields", [])
        }
        missing_profile_fields = sorted(profile_extra_fields - record_fields)
        if missing_profile_fields:
            raise ContractError(
                f"vector {vector_id} audit is missing {audit_profile} profile fields for {tool_name}: {', '.join(missing_profile_fields)}"
            )
        input_value = _matrix_value(vector, "input", tool_name)
        input_errors = list(_schema_validator(contract, tool["input_schema"]).iter_errors(input_value))
        if "invalid_input" in effective_categories:
            if not input_errors:
                raise ContractError(f"invalid_input vector {vector_id} input is valid for {tool_name}")
        elif input_errors:
            message = input_errors[0].message
            raise ContractError(f"vector {vector_id} input is invalid for {tool_name}: {message}")

        has_error = "error" in expected or "error_by_tool" in expected
        if has_error:
            expected_error = _matrix_value(expected, "error", tool_name)
            if not isinstance(expected_error, Mapping) or not isinstance(expected_error.get("code"), str):
                raise ContractError(f"vector {vector_id} expected.error needs a stable code")
            envelope_errors = list(
                _schema_validator(
                    contract, contract["$defs"]["application_error_envelope"]
                ).iter_errors(expected_error)
            )
            if envelope_errors:
                raise ContractError(
                    f"vector {vector_id} error envelope is invalid for {tool_name}: {envelope_errors[0].message}"
                )
            code = expected_error["code"]
            if "invalid_input" in effective_categories and code != "invalid_input":
                raise ContractError(f"invalid_input vector {vector_id} must expect invalid_input")
            if code not in tool["errors"]:
                raise ContractError(f"vector {vector_id} expects undeclared {code} for {tool_name}")
            catalog_error = contract["application_errors"][code]
            catalog_retryable = catalog_error["retryable"]
            if expected_error["retryable"] != catalog_retryable:
                raise ContractError(
                    f"vector {vector_id} retryable disagrees with catalog for {code}"
                )
            if expected_error["message"] != catalog_error["message"]:
                raise ContractError(
                    f"vector {vector_id} message disagrees with catalog for {code}"
                )
            if set(expected_error["details"]) != set(catalog_error["details"]):
                raise ContractError(
                    f"vector {vector_id} details disagree with catalog for {code}"
                )
        else:
            result_value = _matrix_value(expected, "result", tool_name)
            result_errors = list(
                _schema_validator(contract, tool["output_schema"]).iter_errors(result_value)
            )
            if result_errors:
                raise ContractError(
                    f"vector {vector_id} result is invalid for {tool_name}: {result_errors[0].message}"
                )


def _validate_category_declarations(categories: Any, vector_ids: set[str]) -> None:
    if isinstance(categories, list):
        declared = set(categories)
        if not STANDARD_VECTOR_CATEGORIES <= declared:
            missing = sorted(STANDARD_VECTOR_CATEGORIES - declared)
            raise ContractError(f"vector categories are missing: {', '.join(missing)}")
        return
    if not isinstance(categories, Mapping):
        raise ContractError("vectors.categories must be an object or array")
    if set(categories) != STANDARD_VECTOR_CATEGORIES:
        missing = sorted(STANDARD_VECTOR_CATEGORIES - set(categories))
        extra = sorted(set(categories) - STANDARD_VECTOR_CATEGORIES)
        raise ContractError(
            "vectors.categories must contain exactly the standard categories"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; unknown: {', '.join(extra)}" if extra else "")
        )
    for name, declaration in categories.items():
        if not isinstance(declaration, Mapping):
            raise ContractError(f"category {name} declaration must be an object")
        status = declaration.get("status")
        if status not in {"covered", "not_applicable"}:
            raise ContractError(f"category {name} status must be covered or not_applicable")
        if status == "not_applicable" and not declaration.get("reason"):
            raise ContractError(f"category {name} needs a not_applicable reason")
        references = declaration.get("vectors", [])
        if references and (not isinstance(references, list) or not set(references) <= vector_ids):
            raise ContractError(f"category {name} references an unknown vector")
        applies_to = declaration.get("applies_to")
        if applies_to != "all" and not isinstance(applies_to, list):
            raise ContractError(f"category {name} applies_to must be all or an array")
        if status == "covered" and not references:
            raise ContractError(f"covered category {name} must reference a concrete vector")


def validate_vectors(contract: Mapping[str, Any], vectors: Mapping[str, Any]) -> None:
    if vectors.get("schema_version") != "1":
        raise ContractError("vector bundle must use schema_version \"1\"")
    if str(vectors.get("agent_contract_version")) != str(contract["agent_contract_version"]):
        raise ContractError("vector bundle version does not match the Contract")
    entries = vectors.get("vectors")
    if not isinstance(entries, list) or not entries:
        raise ContractError("vectors.vectors must be a non-empty array")

    tools = set(contract["tools"])
    ids: list[str] = []
    success_tools: set[str] = set()
    concrete_categories: set[str] = set()
    vector_tools_by_id: dict[str, set[str]] = {}
    vector_categories_by_id: dict[str, set[str]] = {}
    vector_error_codes_by_id: dict[str, set[str]] = {}
    for vector in entries:
        if not isinstance(vector, Mapping):
            raise ContractError("each conformance vector must be an object")
        vector_id = vector.get("id")
        tool_name = vector.get("tool")
        matrix = vector.get("matrix")
        category = vector.get("category")
        if not isinstance(vector_id, str) or not vector_id:
            raise ContractError("each conformance vector needs a stable id")
        ids.append(vector_id)
        has_tool = isinstance(tool_name, str)
        has_matrix = isinstance(matrix, Mapping) and isinstance(matrix.get("tools"), list)
        if has_tool == has_matrix:
            raise ContractError(f"vector {vector_id} must declare exactly one of tool or matrix.tools")
        vector_tools = {str(tool_name)} if has_tool else {str(item) for item in matrix["tools"]}
        if not vector_tools or not vector_tools <= tools:
            raise ContractError(f"vector {vector_id} references an unknown tool")
        vector_tools_by_id[str(vector_id)] = vector_tools
        if category not in STANDARD_VECTOR_CATEGORIES:
            raise ContractError(f"vector {vector_id} has unknown category {category!r}")
        if "input" not in vector and "input_by_tool" not in vector:
            raise ContractError(f"vector {vector_id} must declare input or input_by_tool")
        _validate_vector_context(contract, vector, vector_id)
        expected = vector.get("expected")
        if not isinstance(expected, Mapping) or "audit" not in expected:
            raise ContractError(f"vector {vector_id} must declare expected result/error and audit")
        has_result = "result" in expected or "result_by_tool" in expected
        has_error = "error" in expected or "error_by_tool" in expected
        if has_result == has_error:
            raise ContractError(f"vector {vector_id} must expect exactly one of result or error")
        expected_codes: set[str] = set()
        if has_error:
            if "error_by_tool" in expected:
                error_values = expected["error_by_tool"]
                if isinstance(error_values, Mapping):
                    expected_codes.update(
                        str(value.get("code"))
                        for value in error_values.values()
                        if isinstance(value, Mapping) and value.get("code")
                    )
            elif isinstance(expected.get("error"), Mapping) and expected["error"].get("code"):
                expected_codes.add(str(expected["error"]["code"]))
        vector_error_codes_by_id[str(vector_id)] = expected_codes
        effective_categories = _effective_vector_categories(vector)
        vector_categories_by_id[str(vector_id)] = effective_categories
        concrete_categories.update(effective_categories)
        _validate_vector_examples(contract, vector, vector_tools, effective_categories)
        if "success" in effective_categories:
            success_tools.update(vector_tools)

    if len(ids) != len(set(ids)):
        raise ContractError("conformance vector ids must be unique")
    missing_success = sorted(tools - success_tools)
    if missing_success:
        raise ContractError(f"tools without a success vector: {', '.join(missing_success)}")
    _validate_category_declarations(vectors.get("categories"), set(ids))

    error_coverage = vectors.get("error_coverage")
    error_codes = _catalog_keys(
        contract.get("application_errors", {}), field="application_errors"
    )
    if not isinstance(error_coverage, Mapping) or set(error_coverage) != error_codes:
        missing = sorted(error_codes - set(error_coverage or {}))
        extra = sorted(set(error_coverage or {}) - error_codes)
        raise ContractError(
            "vectors.error_coverage must declare every application error code"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; unknown: {', '.join(extra)}" if extra else "")
        )
    for code, declaration in error_coverage.items():
        if not isinstance(declaration, Mapping):
            raise ContractError(f"error_coverage.{code} must be an object")
        status = declaration.get("status")
        if status == "not_applicable":
            if not declaration.get("reason"):
                raise ContractError(f"error_coverage.{code} needs a precise reason")
            continue
        if status != "covered":
            raise ContractError(f"error_coverage.{code} must be covered or not_applicable")
        references = declaration.get("vectors")
        if not isinstance(references, list) or not references:
            raise ContractError(f"error_coverage.{code} must reference a concrete vector")
        for reference in references:
            if reference not in vector_error_codes_by_id:
                raise ContractError(f"error_coverage.{code} references unknown vector {reference}")
            if code not in vector_error_codes_by_id[reference]:
                raise ContractError(
                    f"error_coverage.{code} vector {reference} does not expect that code"
                )

    vector_by_id = {str(vector["id"]): vector for vector in entries}
    pro_plan_vector = vector_by_id.get("pro_plan_matrix")
    if not isinstance(pro_plan_vector, Mapping) or pro_plan_vector.get("context", {}).get("plan") != "pro_30":
        raise ContractError("pro_plan_matrix must exercise the pro_30 plan")
    pro_result = pro_plan_vector.get("expected", {}).get("result_by_tool", {}).get(
        "get_account_capabilities", {}
    )
    if pro_result.get("limits", {}).get("project_count", {}).get("limit") != 30:
        raise ContractError("pro_plan_matrix must assert project_count limit 30")
    free_bootstrap = vector_by_id.get("get_account_capabilities_success")
    if not isinstance(free_bootstrap, Mapping) or free_bootstrap.get("context", {}).get("plan") != "free":
        raise ContractError("get_account_capabilities_success must exercise the free plan")
    if (
        free_bootstrap.get("expected", {})
        .get("result", {})
        .get("limits", {})
        .get("project_count", {})
        .get("limit")
        != 1
    ):
        raise ContractError("free bootstrap success must assert project_count limit 1")

    for vector in entries:
        effective_categories = vector_categories_by_id[str(vector["id"])]
        if "missing_capability" not in effective_categories:
            continue
        context_capabilities = set(vector["context"]["capabilities"])
        for tool_name in vector_tools_by_id[str(vector["id"])]:
            required_capabilities = set(contract["tools"][tool_name]["required_capabilities"])
            if not required_capabilities or not required_capabilities.isdisjoint(
                context_capabilities
            ):
                raise ContractError(
                    f"missing_capability vector {vector['id']} does not omit {tool_name}'s required capability"
                )

    tool_coverage = vectors.get("tool_coverage")
    if not isinstance(tool_coverage, Mapping):
        raise ContractError("vectors.tool_coverage must declare every category for every tool")
    if set(tool_coverage) != tools:
        missing = sorted(tools - set(tool_coverage))
        extra = sorted(set(tool_coverage) - tools)
        raise ContractError(
            "tool_coverage tool set differs from Contract"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; unknown: {', '.join(extra)}" if extra else "")
        )
    for tool_name, coverage in tool_coverage.items():
        coverage_keys = set(coverage) if isinstance(coverage, Mapping) else set()
        if not isinstance(coverage, Mapping) or coverage_keys != STANDARD_VECTOR_CATEGORIES:
            missing = sorted(STANDARD_VECTOR_CATEGORIES - coverage_keys)
            extra = sorted(coverage_keys - STANDARD_VECTOR_CATEGORIES)
            raise ContractError(
                f"tool_coverage.{tool_name} must declare exactly every standard category"
                + (f"; missing: {', '.join(missing)}" if missing else "")
                + (f"; unknown: {', '.join(extra)}" if extra else "")
            )
        for category, declaration in coverage.items():
            references: list[str]
            if isinstance(declaration, str):
                references = [declaration]
            elif isinstance(declaration, list):
                references = [str(item) for item in declaration]
            elif isinstance(declaration, Mapping):
                status = declaration.get("status")
                if status == "not_applicable":
                    if not declaration.get("reason"):
                        raise ContractError(
                            f"tool_coverage.{tool_name}.{category} needs a not_applicable reason"
                        )
                    continue
                if status != "covered":
                    raise ContractError(
                        f"tool_coverage.{tool_name}.{category} must be covered or not_applicable"
                    )
                references = [str(item) for item in declaration.get("vectors", [])]
            else:
                raise ContractError(
                    f"tool_coverage.{tool_name}.{category} has an invalid declaration"
                )
            if not references:
                raise ContractError(f"tool_coverage.{tool_name}.{category} has no vector reference")
            for reference in references:
                vector = vector_by_id.get(reference)
                if vector is None:
                    raise ContractError(
                        f"tool_coverage.{tool_name}.{category} references unknown vector {reference}"
                    )
                if (
                    tool_name not in vector_tools_by_id[reference]
                    or category not in vector_categories_by_id[reference]
                ):
                    raise ContractError(
                        f"tool_coverage.{tool_name}.{category} reference {reference} has the wrong tool/category"
                    )

    categories = vectors.get("categories")
    if isinstance(categories, Mapping):
        for category in STANDARD_VECTOR_CATEGORIES - concrete_categories:
            declaration = categories.get(category)
            if not isinstance(declaration, Mapping) or declaration.get("status") != "not_applicable":
                raise ContractError(
                    f"category {category} needs a concrete vector or a justified not_applicable declaration"
                )
        for category, declaration in categories.items():
            declared_tools = (
                tools
                if declaration.get("applies_to") == "all"
                else {str(item) for item in declaration.get("applies_to", [])}
            )
            if not declared_tools <= tools:
                raise ContractError(f"category {category} applies_to references an unknown tool")
            covered_tools = {
                tool_name
                for tool_name, coverage in tool_coverage.items()
                if not (
                    isinstance(coverage[category], Mapping)
                    and coverage[category].get("status") == "not_applicable"
                )
            }
            if declaration.get("status") == "covered" and covered_tools != declared_tools:
                raise ContractError(
                    f"category {category} aggregate applies_to disagrees with per-tool coverage"
                )
            if declaration.get("status") == "not_applicable" and covered_tools:
                raise ContractError(
                    f"category {category} is globally not_applicable but has covered tools"
                )


def validate_release_sources(contract: Mapping[str, Any], path: Path = DEFAULT_RELEASE_SOURCES) -> None:
    sources = _load_yaml(path)
    if not isinstance(sources, Mapping) or sources.get("schema_version") != 1:
        raise ContractError("release/sources.yaml must use schema_version 1")
    if sources.get("repository") != "https://github.com/onurmatik/feature-request":
        raise ContractError("release source repository must be the authoritative GitHub repository")
    descriptor = sources.get("descriptors", {}).get("agent_contract", {})
    expected = {
        "authoritative_store": "github_release_asset",
        "immutable_ref_pattern": "agent-contract-v{agent_contract_version}",
        "descriptor_path": "release/contract-release.json",
        "contract_path": "agent/contract.yaml",
        "contract_schema_path": "agent/contract.schema.json",
        "conformance_bundle_path": "agent/conformance/{agent_contract_version}/",
        "digest_algorithm": "sha256",
        "contract_digest_field": "contract_sha256",
        "contract_schema_digest_field": "contract_schema_sha256",
        "conformance_vectors_digest_field": "conformance_vectors_sha256",
        "conformance_vectors_digest_framing": CONFORMANCE_DIGEST_FRAMING,
    }
    if not isinstance(descriptor, Mapping):
        raise ContractError("release source must define descriptors.agent_contract")
    for key, expected_value in expected.items():
        if descriptor.get(key) != expected_value:
            raise ContractError(
                f"release source descriptors.agent_contract.{key} must be {expected_value!r}"
            )
    if not descriptor.get("consumer_resolution"):
        raise ContractError("release source must document immutable digest resolution")

    environments = sources.get("promotion_environments")
    if not isinstance(environments, list):
        raise ContractError("release source must define promotion_environments")
    by_name = {
        item.get("name"): item for item in environments if isinstance(item, Mapping)
    }
    if len(environments) != 3 or set(by_name) != {
        "development",
        "staging",
        "production",
    }:
        raise ContractError(
            "promotion environments must be development, staging, and production"
        )
    development = by_name.get("development", {})
    staging = by_name.get("staging", {})
    production = by_name.get("production", {})
    if development.get("promotes_to") != "staging":
        raise ContractError("development must promote to staging")
    if staging.get("promotes_to") != "production":
        raise ContractError("staging must promote to production")
    if production.get("promotes_to") is not None:
        raise ContractError("production must be the terminal promotion environment")
    required_development = {
        "contract_stage_gate",
        "deterministic_release_descriptor",
        "versioned_conformance_vectors",
    }
    required_production = {
        "immutable_git_tag",
        "github_release",
        "digest_verification",
        "release_approval",
    }
    required_staging = {
        "postgresql_process_concurrency",
        "ghcr_digest_image",
        "image_provenance_verification",
        "isolated_oauth_mcp_smoke",
        "cleanup_and_health_smoke",
        "rollback_to_disabled_route_rehearsal",
        "attested_staging_evidence",
    }
    if not required_development <= set(development.get("requires", [])):
        raise ContractError("development promotion requirements are incomplete")
    if not required_staging <= set(staging.get("requires", [])):
        raise ContractError("staging promotion requirements are incomplete")
    if not required_production <= set(production.get("requires", [])):
        raise ContractError("production promotion requirements are incomplete")


def validate_source_ownership(
    root_policy_path: Path = DEFAULT_ROOT_POLICY,
    skill_paths: Sequence[Path] = DEFAULT_SKILL_PROJECTIONS,
) -> None:
    """Keep human-facing policy/projections explicitly downstream of the Contract."""

    documents = (root_policy_path, *skill_paths)
    for path in documents:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ContractError(f"required source-ownership document does not exist: {path}") from exc
        normalized = " ".join(text.lower().split())
        if "agent/contract.yaml" not in normalized:
            raise ContractError(f"{path} must reference agent/contract.yaml")
        ownership_markers = (
            "sole semantic",
            "sole canonical",
            "semantics live only",
            "semantics live exclusively",
        )
        if not any(marker in normalized for marker in ownership_markers):
            raise ContractError(
                f"{path} must identify agent/contract.yaml as the sole semantic/canonical source"
            )

    for path in skill_paths:
        normalized = " ".join(path.read_text(encoding="utf-8").lower().split())
        if not re.search(r"mcp.{0,80}conformance.{0,80}`pending`", normalized):
            raise ContractError(f"{path} must declare MCP conformance `pending`")


def _validate_projection(contract: Mapping[str, Any], agents_path: Path) -> None:
    if not agents_path.exists():
        raise ContractError(f"required downstream projection does not exist: {agents_path}")
    agents = _load_json(agents_path)
    pointer = agents.get("agent_contract")
    expected_pointer = {
        "source": "agent/contract.yaml",
        "schema": "agent/contract.schema.json",
        "version": str(contract["agent_contract_version"]),
        "role": "canonical_semantic_source",
    }
    if not isinstance(pointer, Mapping) or any(
        pointer.get(key) != value for key, value in expected_pointer.items()
    ):
        raise ContractError("agents.json agent_contract pointer does not match the canonical Contract")
    runtime_conformance = pointer.get("runtime_conformance")
    if (
        not isinstance(runtime_conformance, Mapping)
        or runtime_conformance.get("status") != "pending"
    ):
        raise ContractError("agents.json root runtime conformance must remain pending")
    projection = agents.get("mcp", {}).get("contract_projection")
    expected_projection = {
        "source": "agent/contract.yaml",
        "mapping_snapshot": f"agent/mappings/mcp-{contract['agent_contract_version']}.json",
        "conformance_status": "pending",
        "bootstrap_target": contract["bootstrap"]["tool"],
    }
    if not isinstance(projection, Mapping) or any(
        projection.get(key) != value for key, value in expected_projection.items()
    ):
        raise ContractError("agents.json MCP Contract projection is stale")
    if projection.get("bootstrap_runtime_status") != "pending":
        raise ContractError("agents.json bootstrap runtime status must remain pending")


def validate_contract(
    contract_path: Path = DEFAULT_CONTRACT,
    schema_path: Path = DEFAULT_SCHEMA,
    vectors_path: Path | None = None,
    agents_path: Path = DEFAULT_AGENTS,
    release_sources_path: Path = DEFAULT_RELEASE_SOURCES,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    contract = _load_yaml(contract_path)
    schema = _load_json(schema_path)
    if not isinstance(contract, Mapping) or not isinstance(schema, Mapping):
        raise ContractError("Contract and Contract schema must be objects")
    Draft202012Validator.check_schema(schema)
    validation_errors = sorted(
        Draft202012Validator(schema).iter_errors(contract),
        key=lambda error: [str(item) for item in error.absolute_path],
    )
    if validation_errors:
        lines = []
        for error in validation_errors[:20]:
            location = ".".join(str(item) for item in error.absolute_path) or "<root>"
            lines.append(f"{location}: {error.message}")
        raise ContractError("Contract schema validation failed:\n  " + "\n  ".join(lines))

    version = str(contract.get("agent_contract_version", ""))
    if not SEMVER_RE.fullmatch(version):
        raise ContractError("agent_contract_version must be valid SemVer")
    _validate_embedded_schemas(contract)
    _validate_tool_catalog(contract)

    chosen_vectors = vectors_path or _path_for_version(version)
    vectors = _load_yaml(chosen_vectors)
    if not isinstance(vectors, Mapping):
        raise ContractError("conformance vector bundle must be an object")
    validate_vectors(contract, vectors)
    _validate_projection(contract, agents_path)
    validate_release_sources(contract, release_sources_path)
    validate_source_ownership()
    return contract, vectors


def build_mcp_mapping(contract: Mapping[str, Any]) -> dict[str, Any]:
    security_scheme = "oauth2"
    mapping_config = contract.get("mapping")
    if isinstance(mapping_config, Mapping):
        mcp = mapping_config.get("mcp", mapping_config)
        if isinstance(mcp, Mapping):
            security_scheme = str(
                mcp.get("oauth_security_scheme", mcp.get("security_scheme", security_scheme))
            )

    tools: dict[str, Any] = {}
    for name in sorted(contract["tools"]):
        tool = contract["tools"][name]
        if tool["exposure"] != "public":
            continue
        security: list[dict[str, list[str]]] = []
        if tool["authentication"] == "required":
            security = [{security_scheme: list(tool["required_scopes"])}]
        tools[name] = {
            "annotations": {
                "destructiveHint": bool(tool["destructive"]),
                "openWorldHint": bool(tool["open_world"]),
                "readOnlyHint": tool["side_effect"] == "read_only",
            },
            "security": security,
        }
    return {
        "schema_version": 1,
        "agent_contract_version": str(contract["agent_contract_version"]),
        "source": "agent/contract.yaml",
        "tools": tools,
    }


@dataclass(frozen=True)
class Change:
    level: str
    path: str
    reason: str


_LEVEL_RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}


def _is_schema_relaxation(old: Mapping[str, Any], new: Mapping[str, Any]) -> bool:
    """Recognize simple, provably additive constraint relaxation."""

    changed = False
    old_type = old.get("type")
    new_type = new.get("type")
    if old_type != new_type:
        changed = True
        old_types = {old_type} if isinstance(old_type, str) else set(old_type or [])
        new_types = {new_type} if isinstance(new_type, str) else set(new_type or [])
        if not old_types or not old_types < new_types:
            return False
    old_enum = old.get("enum")
    new_enum = new.get("enum")
    if old_enum != new_enum:
        changed = True
        if not isinstance(old_enum, list) or not isinstance(new_enum, list) or not set(old_enum) < set(new_enum):
            return False
    if old.get("additionalProperties") is False and new.get("additionalProperties") is True:
        changed = True
    elif old.get("additionalProperties") != new.get("additionalProperties"):
        return False
    for lower in ("minimum", "exclusiveMinimum", "minLength", "minItems"):
        if lower in old or lower in new:
            if lower not in old or lower not in new or new[lower] > old[lower]:
                return False
            if new[lower] != old[lower]:
                changed = True
    for upper in ("maximum", "exclusiveMaximum", "maxLength", "maxItems"):
        if upper in old or upper in new:
            if upper not in old or upper not in new or new[upper] < old[upper]:
                return False
            if new[upper] != old[upper]:
                changed = True
    allowed = {
        "type",
        "enum",
        "additionalProperties",
        "minimum",
        "exclusiveMinimum",
        "minLength",
        "minItems",
        "maximum",
        "exclusiveMaximum",
        "maxLength",
        "maxItems",
        "title",
        "description",
        "$comment",
        "examples",
        "default",
    }
    return changed and set(old) <= allowed and set(new) <= allowed


def _schema_changes(old: Any, new: Any, path: str) -> list[Change]:
    if old == new:
        return []
    if not isinstance(old, Mapping) or not isinstance(new, Mapping):
        return [Change("major", path, "schema constraint changed")]
    if _is_schema_relaxation(old, new):
        return [Change("minor", path, "schema constraint relaxed")]
    changes: list[Change] = []
    old_required = set(old.get("required", []))
    new_required = set(new.get("required", []))
    if new_required - old_required:
        changes.append(Change("major", f"{path}.required", "required field added"))
    if old_required - new_required:
        changes.append(Change("minor", f"{path}.required", "required field relaxed"))
    old_props = old.get("properties", {}) if isinstance(old.get("properties", {}), Mapping) else {}
    new_props = new.get("properties", {}) if isinstance(new.get("properties", {}), Mapping) else {}
    for name in sorted(set(old_props) - set(new_props)):
        changes.append(Change("major", f"{path}.properties.{name}", "schema property removed"))
    for name in sorted(set(new_props) - set(old_props)):
        level = "major" if name in new_required else "minor"
        changes.append(Change(level, f"{path}.properties.{name}", "schema property added"))
    for name in sorted(set(old_props) & set(new_props)):
        changes.extend(_schema_changes(old_props[name], new_props[name], f"{path}.properties.{name}"))

    handled = {"title", "description", "$comment", "required", "properties"}
    for key in sorted((set(old) | set(new)) - handled):
        if old.get(key) == new.get(key):
            continue
        if key == "examples":
            changes.append(Change("patch", f"{path}.{key}", "schema documentation changed"))
        elif key == "default":
            changes.append(Change("major", f"{path}.{key}", "schema default behavior changed"))
        elif key == "$ref":
            changes.append(Change("major", f"{path}.$ref", "schema reference changed"))
        elif key == "additionalProperties" and old.get(key) is False and new.get(key) is True:
            changes.append(Change("minor", f"{path}.{key}", "schema accepts additional properties"))
        else:
            changes.append(Change("major", f"{path}.{key}", "schema constraint changed"))
    if old.get("title") != new.get("title") or old.get("description") != new.get("description"):
        changes.append(Change("patch", path, "schema documentation changed"))
    return changes


def _local_def_names(value: Any) -> set[str]:
    """Return local ``#/$defs/<name>`` references found anywhere in a schema."""

    names: set[str] = set()
    prefix = "#/$defs/"
    for node in _walk_json(value):
        if not isinstance(node, Mapping) or not isinstance(node.get("$ref"), str):
            continue
        reference = node["$ref"]
        if not reference.startswith(prefix):
            continue
        encoded_name = reference[len(prefix) :].split("/", 1)[0]
        names.add(encoded_name.replace("~1", "/").replace("~0", "~"))
    return names


def _reachable_contract_defs(contract: Mapping[str, Any]) -> set[str]:
    """Compute transitive schema dependencies of the published tool/error surface."""

    definitions = contract.get("$defs", {})
    if not isinstance(definitions, Mapping):
        return set()
    roots: list[Any] = []
    tools = contract.get("tools", {})
    if isinstance(tools, Mapping):
        for tool in tools.values():
            if isinstance(tool, Mapping):
                roots.extend((tool.get("input_schema"), tool.get("output_schema")))
    if "application_error_envelope" in definitions:
        roots.append({"$ref": "#/$defs/application_error_envelope"})

    pending = list(_local_def_names(roots))
    reachable: set[str] = set()
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        definition = definitions.get(name)
        if definition is not None:
            pending.extend(_local_def_names(definition) - reachable)
    return reachable


def classify_semver(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    changes: list[Change] = []
    old_tools = old.get("tools", {})
    new_tools = new.get("tools", {})
    for name in sorted(set(old_tools) - set(new_tools)):
        changes.append(Change("major", f"tools.{name}", "public tool removed or renamed"))
    for name in sorted(set(new_tools) - set(old_tools)):
        changes.append(Change("minor", f"tools.{name}", "backward-compatible tool added"))
    for name in sorted(set(old_tools) & set(new_tools)):
        old_tool = old_tools[name]
        new_tool = new_tools[name]
        if old_tool.get("title") != new_tool.get("title") or old_tool.get("description") != new_tool.get("description"):
            changes.append(Change("patch", f"tools.{name}", "model-visible documentation changed"))
        changes.extend(
            _schema_changes(old_tool.get("input_schema"), new_tool.get("input_schema"), f"tools.{name}.input_schema")
        )
        changes.extend(
            _schema_changes(old_tool.get("output_schema"), new_tool.get("output_schema"), f"tools.{name}.output_schema")
        )
        old_scopes = set(old_tool.get("required_scopes", []))
        new_scopes = set(new_tool.get("required_scopes", []))
        if new_scopes - old_scopes:
            changes.append(Change("major", f"tools.{name}.required_scopes", "required scope added"))
        elif old_scopes != new_scopes:
            changes.append(Change("minor", f"tools.{name}.required_scopes", "required scope relaxed"))
        old_caps = set(old_tool.get("required_capabilities", []))
        new_caps = set(new_tool.get("required_capabilities", []))
        if new_caps - old_caps:
            changes.append(Change("major", f"tools.{name}.required_capabilities", "required capability added"))
        elif old_caps != new_caps:
            changes.append(Change("minor", f"tools.{name}.required_capabilities", "required capability relaxed"))
        old_errors = set(old_tool.get("errors", []))
        new_errors = set(new_tool.get("errors", []))
        if old_errors - new_errors:
            changes.append(Change("major", f"tools.{name}.errors", "declared application error removed"))
        if new_errors - old_errors:
            changes.append(Change("minor", f"tools.{name}.errors", "declared application error added"))
        breaking_fields = {
            "authentication",
            "exposure",
            "resource_type",
            "ownership",
            "side_effect",
            "destructive",
            "open_world",
            "approval",
            "idempotency",
            "data_classification",
            "audit_profile",
            "long_running",
        }
        for field in sorted(breaking_fields):
            if old_tool.get(field) != new_tool.get(field):
                changes.append(Change("major", f"tools.{name}.{field}", f"{field} semantics changed"))

    for catalog_name in ("scopes", "capabilities", "application_errors"):
        old_catalog = old.get(catalog_name, {})
        new_catalog = new.get(catalog_name, {})
        old_keys = _catalog_keys(old_catalog, field=catalog_name)
        new_keys = _catalog_keys(new_catalog, field=catalog_name)
        for key in sorted(old_keys - new_keys):
            changes.append(Change("major", f"{catalog_name}.{key}", "published catalog entry removed"))
        for key in sorted(new_keys - old_keys):
            changes.append(Change("minor", f"{catalog_name}.{key}", "published catalog entry added"))
        if isinstance(old_catalog, Mapping) and isinstance(new_catalog, Mapping):
            for key in sorted(old_keys & new_keys):
                old_value = old_catalog[key]
                new_value = new_catalog[key]
                if old_value == new_value:
                    continue
                old_semantics = copy.deepcopy(old_value)
                new_semantics = copy.deepcopy(new_value)
                if isinstance(old_semantics, dict) and isinstance(new_semantics, dict):
                    for doc_key in ("title", "description", "message"):
                        old_semantics.pop(doc_key, None)
                        new_semantics.pop(doc_key, None)
                level = "patch" if old_semantics == new_semantics else "major"
                reason = "catalog documentation changed" if level == "patch" else "catalog meaning changed"
                changes.append(Change(level, f"{catalog_name}.{key}", reason))

    old_defs = old.get("$defs", {})
    new_defs = new.get("$defs", {})
    if isinstance(old_defs, Mapping) and isinstance(new_defs, Mapping):
        for name in sorted(_reachable_contract_defs(old)):
            if name not in new_defs:
                changes.append(Change("major", f"$defs.{name}", "referenced schema removed"))
            elif old_defs.get(name) != new_defs.get(name):
                changes.extend(
                    _schema_changes(old_defs.get(name), new_defs.get(name), f"$defs.{name}")
                )

    normative_root_sections = {
        "identity",
        "limits",
        "bootstrap",
        "resources",
        "authorization_policies",
        "data_classifications",
        "audit",
        "idempotency_policy",
        "mapping",
    }
    for section in sorted(normative_root_sections):
        if old.get(section) != new.get(section):
            changes.append(Change("major", section, f"{section} semantics changed"))

    old_product = old.get("product", {})
    new_product = new.get("product", {})
    for field in ("name", "slug", "supported_goals", "excluded_goals"):
        if (
            isinstance(old_product, Mapping)
            and isinstance(new_product, Mapping)
            and old_product.get(field) != new_product.get(field)
        ):
            changes.append(
                Change("major", f"product.{field}", f"product {field} semantics changed")
            )

    old_instructions = old.get("server_instructions", {})
    new_instructions = new.get("server_instructions", {})
    if (
        isinstance(old_instructions, Mapping)
        and isinstance(new_instructions, Mapping)
        and old_instructions.get("rules") != new_instructions.get("rules")
    ):
        changes.append(
            Change(
                "major",
                "server_instructions.rules",
                "cross-tool instruction rules changed",
            )
        )

    if old.get("compatibility") != new.get("compatibility"):
        changes.append(Change("major", "compatibility", "compatibility policy changed"))
    old_without_version = dict(old)
    new_without_version = dict(new)
    old_without_version.pop("agent_contract_version", None)
    new_without_version.pop("agent_contract_version", None)
    if not changes and old_without_version != new_without_version:
        changes.append(Change("patch", "contract", "non-semantic Contract text or metadata changed"))
    classification = max((change.level for change in changes), key=_LEVEL_RANK.get, default="none")
    return {
        "classification": classification,
        "changes": [
            {"level": change.level, "path": change.path, "reason": change.reason}
            for change in sorted(changes, key=lambda item: (item.path, _LEVEL_RANK[item.level], item.reason))
        ],
    }


def _parse_semver(value: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(value)
    if not match:
        raise ContractError(f"invalid SemVer: {value!r}")
    return int(match["major"]), int(match["minor"]), int(match["patch"])


def _iso_date(value: Any, field: str) -> dt.date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ContractError(f"breaking decision {field} must be an ISO date")
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"breaking decision {field} is not a valid ISO date") from exc


def _resolve_decision_path(decision_root: Path, reference: str) -> Path:
    root = decision_root.resolve()
    candidate = (root / reference).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ContractError("breaking decision ref escapes the repository root") from exc
    return candidate


def _validate_breaking_decision(
    compatibility: Mapping[str, Any],
    old_major: int,
    new_major: int,
    decision_root: Path,
) -> None:
    decision_ref = compatibility.get("breaking_decision_ref")
    if not isinstance(decision_ref, str) or not re.fullmatch(
        r"release/decisions/[a-z0-9][a-z0-9._-]*\.ya?ml", decision_ref
    ):
        raise ContractError(
            "breaking release needs compatibility.breaking_decision_ref under release/decisions/"
        )
    decision_path = _resolve_decision_path(decision_root, decision_ref)
    decision = _load_yaml(decision_path)
    if not isinstance(decision, Mapping) or set(decision) != BREAKING_DECISION_FIELDS:
        raise ContractError("breaking decision record must use the exact closed field set")
    if decision["schema_version"] != 1:
        raise ContractError("breaking decision schema_version must be 1")
    if not isinstance(decision["decision_id"], str) or not re.fullmatch(
        r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*", decision["decision_id"]
    ):
        raise ContractError("breaking decision decision_id must be stable")
    if decision["status"] != "approved":
        raise ContractError("breaking decision status must be approved")
    if decision["from_major"] != old_major or decision["to_major"] != new_major:
        raise ContractError("breaking decision major versions do not match the Contract bump")
    strategy = compatibility.get("strategy")
    if decision["strategy"] not in {"versioned_tool", "versioned_endpoint"}:
        raise ContractError("breaking decision strategy is invalid")
    if decision["strategy"] != strategy:
        raise ContractError("breaking decision strategy does not match compatibility.strategy")
    if not isinstance(decision["rationale"], str) or not decision["rationale"].strip():
        raise ContractError("breaking decision rationale must be nonempty")

    decided_at = _iso_date(decision["decided_at"], "decided_at")
    effective_at = _iso_date(decision["effective_at"], "effective_at")
    support_until = _iso_date(
        decision["previous_major_support_until"], "previous_major_support_until"
    )
    if decided_at > effective_at:
        raise ContractError("breaking decision decided_at must not follow effective_at")
    compatibility_support = compatibility.get("previous_major_support_until")
    if decision["previous_major_support_until"] != compatibility_support:
        raise ContractError(
            "breaking decision support date does not match compatibility.previous_major_support_until"
        )
    support_window_days = compatibility.get("support_window_days")
    if not isinstance(support_window_days, int) or support_window_days < 1:
        raise ContractError("compatibility.support_window_days must be positive")
    if support_until < effective_at + dt.timedelta(days=support_window_days):
        raise ContractError(
            "previous major support date is shorter than the compatibility support window"
        )


def _validate_version_bump(
    old_version: str,
    new_version: str,
    classification: str,
    compatibility_strategy: str | None,
    compatibility: Mapping[str, Any] | None = None,
    decision_root: Path = REPO_ROOT,
) -> None:
    old = _parse_semver(old_version)
    new = _parse_semver(new_version)
    if classification == "none":
        if new != old:
            raise ContractError("unchanged Contract semantics must not change version")
        return
    if new <= old:
        raise ContractError("a changed Contract version must increase")
    adequate = False
    if classification == "patch":
        adequate = new[0] > old[0] or new[1] > old[1] or (
            new[:2] == old[:2] and new[2] > old[2]
        )
    elif classification == "minor":
        adequate = new[0] > old[0] or (new[0] == old[0] and new[1] > old[1])
    elif classification == "major":
        adequate = new[0] > old[0]
    if not adequate:
        raise ContractError(
            f"version {new_version} is below the required {classification} bump from {old_version}"
        )
    if classification == "major" and compatibility_strategy == "additive_superset":
        raise ContractError(
            "breaking semantic changes require a recorded versioned_tool or versioned_endpoint strategy; additive_superset is not sufficient"
        )
    if classification == "major":
        compatibility = compatibility or {}
        _validate_breaking_decision(compatibility, old[0], new[0], decision_root)


def _vector_bundle_bytes(vector_paths: Sequence[Path]) -> bytes:
    chunks: list[bytes] = []
    for path in sorted(vector_paths, key=lambda item: item.as_posix()):
        try:
            relative = path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        except ValueError:
            relative = path.name
        data = path.read_bytes()
        chunks.extend((relative.encode("utf-8"), b"\0", data, b"\0"))
    return b"".join(chunks)


def build_release_descriptor(
    contract_path: Path,
    schema_path: Path,
    vectors_path: Path,
    git_commit: str,
) -> dict[str, Any]:
    if not COMMIT_RE.fullmatch(git_commit):
        raise ContractError("git commit must be a full, lowercase 40-character SHA-1")
    contract = _load_yaml(contract_path)
    vectors = _load_yaml(vectors_path)
    version = str(contract["agent_contract_version"])
    if str(vectors.get("agent_contract_version")) != version:
        raise ContractError("vector bundle version does not match the Contract")
    entries = vectors.get("vectors", [])
    vector_ids = sorted(str(vector["id"]) for vector in entries)
    compatibility = contract.get("compatibility", {})
    strategy = compatibility.get("strategy") or compatibility.get("compatibility_strategy")
    return {
        "schema_version": 1,
        "agent_contract_version": version,
        "git_commit": git_commit,
        "contract_sha256": _sha256(contract_path.read_bytes()),
        "contract_schema_sha256": _sha256(schema_path.read_bytes()),
        "contract_schema_version": str(contract.get("schema_version", "1")),
        "compatibility_strategy": strategy,
        "conformance_vectors_sha256": _sha256(_vector_bundle_bytes([vectors_path])),
        "conformance_vectors_digest_framing": CONFORMANCE_DIGEST_FRAMING,
        "conformance_vectors": vector_ids,
    }


def _write_or_check(payload: bytes, output: Path, check: bool) -> None:
    if check:
        try:
            actual = output.read_bytes()
        except FileNotFoundError as exc:
            raise ContractError(f"generated artifact is missing: {output}") from exc
        if actual != payload:
            raise ContractError(f"generated artifact is stale: {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _path(value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=_path, default=DEFAULT_CONTRACT)
    parser.add_argument("--schema", type=_path, default=DEFAULT_SCHEMA)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="run the Contract-stage gate")
    validate_parser.add_argument("--vectors", type=_path)
    validate_parser.add_argument("--agents", type=_path, default=DEFAULT_AGENTS)
    validate_parser.add_argument(
        "--release-sources", type=_path, default=DEFAULT_RELEASE_SOURCES
    )

    mapping_parser = subparsers.add_parser("mapping", help="build the deterministic MCP mapping")
    mapping_parser.add_argument("--output", type=_path)
    mapping_parser.add_argument("--check", action="store_true")

    semver_parser = subparsers.add_parser("semver-diff", help="classify a Contract change")
    semver_parser.add_argument("old", type=_path)
    semver_parser.add_argument("new", type=_path)
    semver_parser.add_argument("--expect", choices=("none", "patch", "minor", "major"))
    semver_parser.add_argument(
        "--classify-only",
        action="store_true",
        help="report classification without enforcing the new Contract version",
    )

    release_parser = subparsers.add_parser(
        "build-release", help="build a deterministic Contract release descriptor"
    )
    release_parser.add_argument("--vectors", type=_path)
    release_parser.add_argument("--git-commit", default=None)
    release_parser.add_argument("--output", type=_path)
    release_parser.add_argument("--check", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            contract, vectors = validate_contract(
                args.contract,
                args.schema,
                args.vectors,
                args.agents,
                args.release_sources,
            )
            version = contract["agent_contract_version"]
            print(f"Agent Contract {version} valid ({len(contract['tools'])} tools, {len(vectors['vectors'])} vectors)")
            return 0

        if args.command == "mapping":
            contract = _load_yaml(args.contract)
            _validate_embedded_schemas(contract)
            _validate_tool_catalog(contract)
            version = str(contract["agent_contract_version"])
            payload = _json_bytes(build_mcp_mapping(contract))
            output = args.output or _mapping_path_for_version(version)
            _write_or_check(payload, output, args.check)
            print(f"MCP mapping {'verified' if args.check else 'wrote'}: {output}")
            return 0

        if args.command == "semver-diff":
            old_contract = _load_yaml(args.old)
            new_contract = _load_yaml(args.new)
            result = classify_semver(old_contract, new_contract)
            sys.stdout.buffer.write(_json_bytes(result))
            if args.expect and result["classification"] != args.expect:
                raise ContractError(
                    f"expected {args.expect} change, classified as {result['classification']}"
                )
            if not args.classify_only:
                compatibility = new_contract.get("compatibility", {})
                strategy = compatibility.get("strategy") if isinstance(compatibility, Mapping) else None
                _validate_version_bump(
                    str(old_contract["agent_contract_version"]),
                    str(new_contract["agent_contract_version"]),
                    result["classification"],
                    strategy,
                    compatibility,
                    REPO_ROOT,
                )
            return 0

        if args.command == "build-release":
            contract, _ = validate_contract(
                args.contract,
                args.schema,
                args.vectors,
                DEFAULT_AGENTS,
                DEFAULT_RELEASE_SOURCES,
            )
            version = str(contract["agent_contract_version"])
            vectors = args.vectors or _path_for_version(version)
            descriptor = build_release_descriptor(
                args.contract, args.schema, vectors, args.git_commit or _git_head()
            )
            payload = _json_bytes(descriptor)
            if args.output:
                _write_or_check(payload, args.output, args.check)
            elif args.check:
                raise ContractError("build-release --check requires --output")
            else:
                sys.stdout.buffer.write(payload)
            return 0
    except (ContractError, OSError, subprocess.CalledProcessError) as exc:
        print(f"agent-contract: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
