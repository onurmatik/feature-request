from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import rfc8785
import yaml
from django.conf import settings
from jsonschema import Draft202012Validator, FormatChecker
from mcp.types import Tool, ToolAnnotations


CONTRACT_PATH = Path(settings.BASE_DIR) / "agent" / "contract.yaml"
PIN_PATH = Path(settings.BASE_DIR) / "integration" / "agent-contract-pin.json"
SERVER_VERSION = "1.0.0"


@lru_cache(maxsize=1)
def contract():
    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def contract_pin():
    return json.loads(PIN_PATH.read_text(encoding="utf-8"))


def verify_contract_pin():
    payload = CONTRACT_PATH.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    expected = contract_pin()["contract_sha256"]
    if actual != expected:
        raise RuntimeError("Runtime Agent Contract does not match the immutable release pin.")
    if contract()["agent_contract_version"] != contract_pin()["agent_contract_version"]:
        raise RuntimeError("Runtime Agent Contract version does not match the release pin.")


def standalone_schema(schema: dict) -> dict:
    result = copy.deepcopy(schema)
    reference = result.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/$defs/"):
        encoded = reference.removeprefix("#/$defs/").split("/", 1)[0]
        name = encoded.replace("~1", "/").replace("~0", "~")
        definition = contract()["$defs"].get(name)
        if not isinstance(definition, dict):
            raise RuntimeError(f"Unknown root Contract schema reference: {reference}")
        siblings = {key: value for key, value in result.items() if key != "$ref"}
        result = copy.deepcopy(definition)
        result.update(siblings)
    result["$defs"] = copy.deepcopy(contract()["$defs"])
    result.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    return result


def validate_tool_input(name: str, arguments: dict):
    definition = contract()["tools"][name]
    validator = Draft202012Validator(
        standalone_schema(definition["input_schema"]),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(arguments), key=lambda item: list(item.path))
    if errors:
        fields = set()
        additional_fields = set()
        for error in errors:
            prefix = ".".join(str(part) for part in error.absolute_path)
            if error.validator == "additionalProperties" and isinstance(
                error.instance, dict
            ):
                allowed = set(error.schema.get("properties", {}))
                extras = set(error.instance) - allowed
                additional_fields.update(
                    f"{prefix}.{field}" if prefix else field for field in extras
                )
            elif error.validator == "required" and isinstance(error.instance, dict):
                missing = set(error.validator_value) - set(error.instance)
                fields.update(
                    f"{prefix}.{field}" if prefix else field for field in missing
                )
            else:
                fields.add(prefix or "$")
        # A closed-schema violation is the most actionable and stable diagnosis.
        # Contract 1.0.0 vectors intentionally report the unexpected fields first
        # instead of also enumerating every required field omitted by that payload.
        fields = sorted(additional_fields or fields)
        return fields

    semantic_fields = set()
    for field in ("name", "title", "body"):
        value = arguments.get(field)
        if isinstance(value, str) and value and not value.strip():
            semantic_fields.add(field)
    url = arguments.get("url")
    if isinstance(url, str) and url:
        try:
            parsed = urlsplit(url)
            _ = parsed.port
        except ValueError:
            semantic_fields.add("url")
        else:
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or "\\" in url
                or any(ord(char) <= 0x20 or ord(char) == 0x7F for char in url)
            ):
                semantic_fields.add("url")
    return sorted(semantic_fields)


def validate_tool_output(name: str, result: dict):
    definition = contract()["tools"][name]
    Draft202012Validator(
        standalone_schema(definition["output_schema"]),
        format_checker=FormatChecker(),
    ).validate(result)


def _tool(name: str, definition: dict) -> Tool:
    side_effect = definition["side_effect"]
    idempotency = definition["idempotency"]["mode"]
    scopes = list(definition["required_scopes"])
    return Tool(
        name=name,
        title=definition["title"],
        description=definition["description"],
        inputSchema=standalone_schema(definition["input_schema"]),
        outputSchema=standalone_schema(definition["output_schema"]),
        annotations=ToolAnnotations(
            title=definition["title"],
            readOnlyHint=side_effect == "read_only",
            destructiveHint=bool(definition["destructive"]),
            idempotentHint=side_effect == "read_only" or idempotency == "required",
            openWorldHint=bool(definition["open_world"]),
        ),
        _meta={
            "securitySchemes": [
                {
                    "type": "oauth2",
                    "scopes": scopes,
                }
            ],
            "agentContractVersion": contract()["agent_contract_version"],
            "exposure": definition["exposure"],
            "io.featurerequest/agentContract": {
                "requiredCapabilities": list(definition["required_capabilities"]),
                "resourceType": definition["resource_type"],
                "ownership": definition["ownership"],
                "approval": copy.deepcopy(definition["approval"]),
                "idempotency": copy.deepcopy(definition["idempotency"]),
                "dataClassification": copy.deepcopy(
                    definition["data_classification"]
                ),
                "auditProfile": definition["audit_profile"],
            },
        },
    )


@lru_cache(maxsize=1)
def public_registry() -> tuple[Tool, ...]:
    verify_contract_pin()
    return tuple(
        _tool(name, definition)
        for name, definition in contract()["tools"].items()
        if definition["exposure"] == "public"
    )


def registry_payload():
    return [tool.model_dump(by_alias=True, exclude_none=True) for tool in public_registry()]


def registry_digest():
    return hashlib.sha256(rfc8785.dumps(registry_payload())).hexdigest()


def server_instructions():
    instructions = contract()["server_instructions"]
    return " ".join(
        [instructions["summary"], *[rule["text"] for rule in instructions["rules"]]]
    )
