#!/usr/bin/env python3
"""Atomically merge non-secret native MCP deployment identity into a dotenv file."""

from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
from pathlib import Path


def update_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    rendered: list[str] = []
    written: set[str] = set()
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0]
            if key in updates:
                if key not in written:
                    rendered.append(f"{key}={updates[key]}")
                    written.add(key)
                continue
        rendered.append(raw)
    for key in sorted(updates):
        if key not in written:
            rendered.append(f"{key}={updates[key]}")
    content = "\n".join(rendered) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=".env.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--values-base64", required=True)
    args = parser.parse_args(argv)
    updates = json.loads(base64.b64decode(args.values_base64).decode())
    if not isinstance(updates, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in updates.items()
    ):
        raise ValueError("deployment environment updates must be a string mapping")
    update_env(args.env_file, updates)
    print("Native MCP environment identity updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
