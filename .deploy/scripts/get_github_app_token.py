"""Generate a short-lived GitHub App installation token for Fabric."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import jwt
import requests


DEPLOY_DIR = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env(DEPLOY_DIR / "deploy.env")
load_env(DEPLOY_DIR / ".credentials.env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", type=int, default=os.environ.get("GITHUB_APP_ID"))
    parser.add_argument(
        "--installation-id",
        type=int,
        default=os.environ.get("GITHUB_APP_INSTALLATION_ID"),
    )
    parser.add_argument(
        "--private-key",
        type=Path,
        default=Path(
            os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "~/.ssh/optbot-app.pem")
        ).expanduser(),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.app_id or not args.installation_id:
        sys.exit("ERROR: app-id and installation-id are required.")
    if not args.private_key.is_file():
        sys.exit(f"ERROR: private key file not found at {args.private_key}")

    now = int(time.time())
    assertion = jwt.encode(
        {"iat": now - 60, "exp": now + 600, "iss": str(args.app_id)},
        args.private_key.read_text(encoding="utf-8"),
        algorithm="RS256",
    )
    response = requests.post(
        f"https://api.github.com/app/installations/{args.installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {assertion}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    )
    response.raise_for_status()
    print(response.json()["token"])


if __name__ == "__main__":
    main()
