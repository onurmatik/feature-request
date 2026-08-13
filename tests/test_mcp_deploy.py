from __future__ import annotations

import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.verify_mcp_deploy_config import parse_env, validate


ROOT = Path(__file__).resolve().parents[1]


class MCPDeploymentContractTests(unittest.TestCase):
    def _values(self):
        return {
            "FEATURE_REQUEST_IMAGE_REF": (
                "ghcr.io/onurmatik/feature-request@sha256:" + "a" * 64
            ),
            "DATABASE_URL": "postgresql://user:password@db/feature_request",
            "FEATURE_REQUEST_MCP_PRODUCTION_ENABLED": "true",
            "DEBUG": "false",
            "DJANGO_SECRET_KEY": "s" * 48,
            "PUBLIC_BASE_URL": "https://featurerequest.io",
            "OAUTH_ISSUER": "https://featurerequest.io",
            "MCP_RESOURCE_URL": "https://featurerequest.io/mcp",
            "MCP_RESOURCE_METADATA_URL": (
                "https://featurerequest.io/.well-known/oauth-protected-resource/mcp"
            ),
            "ADMIN_EMAIL": "ops@example.com",
        }

    def test_valid_deployment_requires_digest_postgres_and_canonical_identity(self):
        validate(self._values())
        for field, bad in (
            ("FEATURE_REQUEST_IMAGE_REF", "ghcr.io/onurmatik/feature-request:latest"),
            ("DATABASE_URL", "sqlite:///db.sqlite3"),
            ("FEATURE_REQUEST_MCP_PRODUCTION_ENABLED", "false"),
            ("DEBUG", "true"),
            ("DJANGO_SECRET_KEY", "short"),
            ("MCP_RESOURCE_URL", "https://featurerequest.io/mcp/"),
            ("ADMIN_EMAIL", ""),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                values = copy.deepcopy(self._values())
                values[field] = bad
                validate(values)

    def test_environment_file_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mcp.env"
            path.write_text("A=1\nA=2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_env(path)

    def test_sqlite_production_startup_guard_is_active(self):
        script = "import config.settings"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env={
                "PATH": str(Path(sys.executable).parent),
                "DJANGO_SECRET_KEY": "test",
                "DEBUG": "false",
                "FEATURE_REQUEST_MCP_PRODUCTION_ENABLED": "true",
            },
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PostgreSQL concurrency gate", result.stderr)

    def test_ops_templates_keep_public_route_disabled_and_image_digest_driven(self):
        deployment = ROOT / "deploy" / "mcp"
        units = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(deployment.glob("*.service"))
        )
        self.assertIn("${FEATURE_REQUEST_IMAGE_REF}", units)
        self.assertIn("verify_mcp_deploy_config.py", units)
        self.assertIn("%(U)s", units)
        self.assertNotIn("%(q)s", units)
        nginx = (deployment / "nginx-mcp-oauth.conf").read_text(encoding="utf-8")
        self.assertIn("location = /mcp", nginx)
        self.assertIn("location ^~ /oauth/", nginx)
        self.assertNotIn("location /mcp/", nginx)
        self.assertGreaterEqual(nginx.count("access_log off;"), 2)
        self.assertGreaterEqual(
            nginx.count("proxy_set_header X-Forwarded-For $remote_addr;"), 2
        )
        self.assertNotIn("$proxy_add_x_forwarded_for", nginx)
        readme = (deployment / "README.md").read_text(encoding="utf-8")
        self.assertIn("do not enable", readme.lower())

        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("%(U)s", dockerfile)
        self.assertNotIn("%(q)s", dockerfile)
        self.assertIn("--reinstall-package django-embedded-mcp", dockerfile)


if __name__ == "__main__":
    unittest.main()
