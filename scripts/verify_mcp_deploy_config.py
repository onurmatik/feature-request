#!/usr/bin/env python3
"""Validate a native MCP deployment and its exact checked-out source identity."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEPLOY_CONTRACT_PATHS = (
    ".deploy/README.md",
    ".deploy/fabfile.py",
    "deploy/mcp",
    "scripts/install_mcp_nginx.py",
    "scripts/update_mcp_env.py",
    "scripts/verify_mcp_deploy_config.py",
)
CONFIG_FINGERPRINT_FIELDS = (
    "DEBUG",
    "FEATURE_REQUEST_MCP_PRODUCTION_ENABLED",
    "PUBLIC_BASE_URL",
    "OAUTH_ISSUER",
    "MCP_RESOURCE_URL",
    "MCP_RESOURCE_METADATA_URL",
    "FEATURE_REQUEST_MCP_HOST",
    "FEATURE_REQUEST_MCP_PORT",
    "FEATURE_REQUEST_MCP_CORS_ORIGINS",
    "FEATURE_REQUEST_TRUSTED_PROXY_IPS",
    "FEATURE_REQUEST_SOURCE_COMMIT",
    "FEATURE_REQUEST_SOURCE_TREE_SHA256",
    "FEATURE_REQUEST_DEPENDENCY_LOCK_SHA256",
    "FEATURE_REQUEST_DEPLOY_CONTRACT_SHA256",
)


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key or key in values:
            raise ValueError(f"invalid or duplicate env entry at line {line_number}")
        values[key] = value
    return values


def _git(project_dir: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=not binary,
    )
    return result.stdout


def source_tree_sha256(project_dir: Path, commit: str) -> str:
    listing = _git(project_dir, "ls-tree", "-r", "-z", "--full-tree", commit, binary=True)
    assert isinstance(listing, bytes)
    digest = hashlib.sha256()
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, object_type, object_id = metadata.split(b" ", 2)
        if object_type != b"blob":
            raise ValueError("source tree contains an unsupported non-blob entry")
        content = _git(
            project_dir,
            "cat-file",
            "blob",
            object_id.decode("ascii"),
            binary=True,
        )
        assert isinstance(content, bytes)
        digest.update(raw_path)
        digest.update(b"\0")
        digest.update(mode)
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def dependency_lock_sha256(project_dir: Path, commit: str = "HEAD") -> str:
    content = _git(project_dir, "show", f"{commit}:uv.lock", binary=True)
    assert isinstance(content, bytes)
    return hashlib.sha256(content).hexdigest()


def deploy_contract_sha256(project_dir: Path, commit: str = "HEAD") -> str:
    output = _git(
        project_dir,
        "ls-tree",
        "-r",
        "--name-only",
        "-z",
        commit,
        "--",
        *DEPLOY_CONTRACT_PATHS,
        binary=True,
    )
    assert isinstance(output, bytes)
    paths = sorted(path for path in output.split(b"\0") if path)
    if not paths:
        raise ValueError("native deploy contract has no tracked files")
    digest = hashlib.sha256()
    for raw_path in paths:
        path = raw_path.decode("utf-8")
        digest.update(raw_path)
        digest.update(b"\0")
        content = _git(project_dir, "show", f"{commit}:{path}", binary=True)
        assert isinstance(content, bytes)
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def repository_identity(project_dir: Path, commit: str) -> dict[str, str]:
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError("source commit must be a full lowercase SHA-1")
    return {
        "FEATURE_REQUEST_SOURCE_COMMIT": commit,
        "FEATURE_REQUEST_SOURCE_TREE_SHA256": source_tree_sha256(project_dir, commit),
        "FEATURE_REQUEST_DEPENDENCY_LOCK_SHA256": dependency_lock_sha256(
            project_dir, commit
        ),
        "FEATURE_REQUEST_DEPLOY_CONTRACT_SHA256": deploy_contract_sha256(
            project_dir, commit
        ),
    }


def config_fingerprint_sha256(values: dict[str, str]) -> str:
    payload = {key: values.get(key, "") for key in CONFIG_FINGERPRINT_FIELDS}
    payload["DATABASE_ENGINE"] = values.get("DATABASE_URL", "").split(":", 1)[0]
    payload["ADMIN_EMAIL"] = "configured" if values.get("ADMIN_EMAIL") else "missing"
    serialized = "{" + ",".join(
        f'{key!r}:{payload[key]!r}' for key in sorted(payload)
    ) + "}"
    return hashlib.sha256(serialized.encode()).hexdigest()


def validate(values: dict[str, str]) -> None:
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
        "FEATURE_REQUEST_MCP_HOST": "127.0.0.1",
        "FEATURE_REQUEST_MCP_PORT": "8001",
        "FEATURE_REQUEST_MCP_CORS_ORIGINS": (
            "https://chatgpt.com,https://claude.ai,https://claude.com"
        ),
        "FEATURE_REQUEST_TRUSTED_PROXY_IPS": "127.0.0.1,::1",
    }
    for key, expected in exact.items():
        if values.get(key) != expected:
            raise ValueError(f"{key} must be {expected}")
    if not values.get("ADMIN_EMAIL"):
        raise ValueError("ADMIN_EMAIL is required for operational alerts")
    if not COMMIT_RE.fullmatch(values.get("FEATURE_REQUEST_SOURCE_COMMIT", "")):
        raise ValueError("FEATURE_REQUEST_SOURCE_COMMIT must be a full lowercase SHA-1")
    for key in (
        "FEATURE_REQUEST_SOURCE_TREE_SHA256",
        "FEATURE_REQUEST_DEPENDENCY_LOCK_SHA256",
        "FEATURE_REQUEST_DEPLOY_CONTRACT_SHA256",
        "FEATURE_REQUEST_CONFIG_FINGERPRINT_SHA256",
    ):
        if not SHA256_RE.fullmatch(values.get(key, "")):
            raise ValueError(f"{key} must be a lowercase SHA-256")
    if values["FEATURE_REQUEST_CONFIG_FINGERPRINT_SHA256"] != config_fingerprint_sha256(
        values
    ):
        raise ValueError("FEATURE_REQUEST_CONFIG_FINGERPRINT_SHA256 is stale or invalid")


def validate_repository_identity(values: dict[str, str], project_dir: Path) -> None:
    commit = values["FEATURE_REQUEST_SOURCE_COMMIT"]
    head = str(_git(project_dir, "rev-parse", "HEAD")).strip()
    if head != commit:
        raise ValueError(f"checked-out source differs from FEATURE_REQUEST_SOURCE_COMMIT: {head}")
    status = str(_git(project_dir, "status", "--porcelain", "--untracked-files=no")).strip()
    if status:
        raise ValueError("checked-out source contains tracked working-tree changes")
    expected = repository_identity(project_dir, commit)
    for key, actual in expected.items():
        if values.get(key) != actual:
            raise ValueError(f"{key} does not match the checked-out native runtime")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--project-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        values = parse_env(args.env_file)
        validate(values)
        if args.project_dir is not None:
            validate_repository_identity(values, args.project_dir.resolve())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"MCP deployment config rejected: {exc}", file=sys.stderr)
        return 1
    print("Native MCP deployment config and source identity valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
