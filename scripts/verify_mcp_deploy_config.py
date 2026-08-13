#!/usr/bin/env python3
"""Fail closed unless an MCP deployment environment is digest-pinned and PostgreSQL-backed."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


IMAGE_RE = re.compile(
    r"^ghcr\.io/onurmatik/feature-request@sha256:[0-9a-f]{64}$"
)


def parse_env(path: Path) -> dict[str, str]:
    values = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key or key in values:
            raise ValueError(f"invalid or duplicate env entry at line {line_number}")
        values[key] = value
    return values


def validate(values: dict[str, str]) -> None:
    if not IMAGE_RE.fullmatch(values.get("FEATURE_REQUEST_IMAGE_REF", "")):
        raise ValueError("FEATURE_REQUEST_IMAGE_REF must be an immutable authoritative GHCR digest")
    if values.get("DATABASE_URL", "").split(":", 1)[0] not in {
        "postgres",
        "postgresql",
    }:
        raise ValueError("production MCP requires a PostgreSQL DATABASE_URL")
    if values.get("FEATURE_REQUEST_MCP_PRODUCTION_ENABLED", "").lower() != "true":
        raise ValueError("FEATURE_REQUEST_MCP_PRODUCTION_ENABLED must be true at route enablement")
    if values.get("DEBUG", "").lower() != "false":
        raise ValueError("DEBUG must be false at MCP route enablement")
    secret = values.get("DJANGO_SECRET_KEY", "")
    if len(secret) < 32 or secret.startswith("REPLACE_"):
        raise ValueError("DJANGO_SECRET_KEY must be an explicit strong production value")
    exact = {
        "PUBLIC_BASE_URL": "https://featurerequest.io",
        "OAUTH_ISSUER": "https://featurerequest.io",
        "MCP_RESOURCE_URL": "https://featurerequest.io/mcp",
        "MCP_RESOURCE_METADATA_URL": (
            "https://featurerequest.io/.well-known/oauth-protected-resource/mcp"
        ),
    }
    for key, expected in exact.items():
        if values.get(key) != expected:
            raise ValueError(f"{key} must be {expected}")
    if not values.get("ADMIN_EMAIL"):
        raise ValueError("ADMIN_EMAIL is required for operational alerts")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate(parse_env(args.env_file))
    except (OSError, ValueError) as exc:
        print(f"MCP deployment config rejected: {exc}", file=sys.stderr)
        return 1
    print("MCP deployment config valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
