from __future__ import annotations

import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.install_mcp_nginx import render_site
from scripts.update_mcp_env import update_env
from scripts.verify_mcp_deploy_config import (
    config_fingerprint_sha256,
    parse_env,
    repository_identity,
    validate,
)


ROOT = Path(__file__).resolve().parents[1]


class MCPDeploymentContractTests(unittest.TestCase):
    def _values(self):
        values = {
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
            "FEATURE_REQUEST_MCP_HOST": "127.0.0.1",
            "FEATURE_REQUEST_MCP_PORT": "8001",
            "FEATURE_REQUEST_MCP_CORS_ORIGINS": (
                "https://chatgpt.com,https://claude.ai,https://claude.com"
            ),
            "FEATURE_REQUEST_TRUSTED_PROXY_IPS": "127.0.0.1,::1",
            "ADMIN_EMAIL": "ops@example.com",
            "FEATURE_REQUEST_SOURCE_COMMIT": "a" * 40,
            "FEATURE_REQUEST_SOURCE_TREE_SHA256": "b" * 64,
            "FEATURE_REQUEST_DEPENDENCY_LOCK_SHA256": "c" * 64,
            "FEATURE_REQUEST_DEPLOY_CONTRACT_SHA256": "d" * 64,
        }
        values["FEATURE_REQUEST_CONFIG_FINGERPRINT_SHA256"] = (
            config_fingerprint_sha256(values)
        )
        return values

    def test_valid_deployment_requires_native_identity_postgres_and_canonical_urls(self):
        validate(self._values())
        for field, bad in (
            ("DATABASE_URL", "sqlite:///db.sqlite3"),
            ("FEATURE_REQUEST_MCP_PRODUCTION_ENABLED", "false"),
            ("DEBUG", "true"),
            ("DJANGO_SECRET_KEY", "short"),
            ("MCP_RESOURCE_URL", "https://featurerequest.io/mcp/"),
            ("FEATURE_REQUEST_MCP_PORT", "9000"),
            ("FEATURE_REQUEST_SOURCE_COMMIT", "short"),
            ("FEATURE_REQUEST_SOURCE_TREE_SHA256", "short"),
            ("ADMIN_EMAIL", ""),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                values = copy.deepcopy(self._values())
                values[field] = bad
                validate(values)

    def test_config_fingerprint_normalizes_boolean_spelling(self):
        values = self._values()
        values["DEBUG"] = "False"
        values["FEATURE_REQUEST_MCP_PRODUCTION_ENABLED"] = "TRUE"
        values["FEATURE_REQUEST_CONFIG_FINGERPRINT_SHA256"] = (
            config_fingerprint_sha256(values)
        )
        validate(values)

    def test_environment_file_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("A=1\nA=2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_env(path)

    def test_native_environment_update_is_atomic_and_preserves_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("SECRET=keep\nMCP_VALUE=old\n", encoding="utf-8")
            path.chmod(0o644)
            update_env(path, {"MCP_VALUE": "new", "SOURCE_ID": "exact"})
            self.assertEqual(
                "SECRET=keep\nMCP_VALUE=new\nSOURCE_ID=exact\n",
                path.read_text(encoding="utf-8"),
            )
            self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_native_repository_identity_is_deterministic(self):
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        first = repository_identity(ROOT, commit)
        second = repository_identity(ROOT, commit)
        self.assertEqual(first, second)
        self.assertEqual(commit, first["FEATURE_REQUEST_SOURCE_COMMIT"])
        for key, value in first.items():
            if key != "FEATURE_REQUEST_SOURCE_COMMIT":
                self.assertRegex(value, r"^[0-9a-f]{64}$")

    def test_sqlite_production_startup_guard_is_active(self):
        result = subprocess.run(
            [sys.executable, "-c", "import config.settings"],
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

    def test_native_ops_contract_is_idempotent_fail_closed_and_container_free(self):
        deployment = ROOT / "deploy" / "mcp"
        units = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(deployment.glob("*.service"))
        )
        fabfile = (ROOT / ".deploy" / "fabfile.py").read_text(encoding="utf-8")
        combined = units + fabfile + (deployment / "README.md").read_text()
        self.assertNotIn("FEATURE_REQUEST_IMAGE_REF", combined)
        self.assertNotIn("/usr/bin/docker", combined)
        self.assertNotIn("ghcr.io/", combined)
        self.assertIn("/srv/apps/__PROJECT_NAME__/venv/bin/python", units)
        self.assertIn("verify_mcp_deploy_config.py", units)
        for marker in (
            "take_database_backup",
            "disable_mcp_route",
            "rollback_mcp",
            "check_loopback_oauth",
            "check_public_surfaces",
        ):
            self.assertIn(marker, fabfile)

        socket_stop = f'systemctl stop app@{{PROJECT_NAME}}.socket'
        service_stop = f'systemctl stop app@{{PROJECT_NAME}}.service'
        socket_start = f'systemctl start app@{{PROJECT_NAME}}.socket'
        self.assertLess(fabfile.index(socket_stop), fabfile.index(service_stop))
        self.assertLess(fabfile.index(service_stop), fabfile.index(socket_start))

        nginx = (deployment / "nginx-mcp-oauth.conf").read_text(encoding="utf-8")
        self.assertIn("location = /mcp", nginx)
        self.assertIn("location ^~ /oauth/", nginx)
        self.assertNotIn("openid-configuration", nginx)
        self.assertNotIn("$proxy_add_x_forwarded_for", nginx)
        disabled = (deployment / "nginx-mcp-disabled.conf").read_text()
        self.assertGreaterEqual(disabled.count("return 404;"), 9)

    def test_nginx_site_attachment_is_idempotent_and_https_scoped(self):
        site = """
server {
    listen 80;
    server_name featurerequest.io;
}
server {
    listen 443 ssl http2;
    server_name featurerequest.io;
    client_max_body_size 20M;
    location / { return 200; }
}
"""
        include = "/etc/nginx/snippets/featurerequest-mcp-routing.conf"
        first = render_site(site, include)
        second = render_site(first, include)
        self.assertEqual(first, second)
        self.assertEqual(1, first.count(include))
        self.assertGreater(first.index(include), first.index("listen 443 ssl"))


if __name__ == "__main__":
    unittest.main()
