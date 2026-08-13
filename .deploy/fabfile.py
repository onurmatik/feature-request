from __future__ import annotations

import base64
import io
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fabric import Connection, task
from invoke import Collection


if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.verify_mcp_deploy_config import (
    config_fingerprint_sha256,
    repository_identity,
)


DEPLOY_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DEPLOY_DIR.parent

load_dotenv(DEPLOY_DIR / ".credentials.env")
load_dotenv(DEPLOY_DIR / "deploy.env")


def get_env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value is None:
            continue
        value = value.strip()
        if value:
            return value
    return None


def env_value(
    *names: str,
    default: Optional[str] = None,
    required: bool = False,
    hint: Optional[str] = None,
) -> Optional[str]:
    value = get_env(*names)
    if value:
        return value
    if required:
        if hint:
            raise RuntimeError(f"Missing required environment variable: {hint}")
        raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")
    return default


def require_env(*names: str, hint: Optional[str] = None) -> str:
    value = env_value(*names, required=True, hint=hint)
    assert value is not None
    return value


ENV_GITHUB_APP_REPO = ("GITHUB_APP_REPO",)
ENV_DOMAIN = ("DOMAIN_NAME", "DOMAIN")
ENV_HOST = ("DEPLOY_HOST", "HOST")
ENV_DEPLOY_USER = ("DEPLOY_USER",)
ENV_APP_USER = ("APP_USER",)
ENV_KEY_FILENAME = ("KEY_FILENAME",)
ENV_PROJECT_NAME = ("PROJECT_NAME",)
ENV_APP_GROUP = ("APP_GROUP",)
ENV_NGINX_SITE = ("NGINX_SITE",)
ENV_PGBACKREST_STANZA = ("PGBACKREST_STANZA",)


USER = env_value(*ENV_DEPLOY_USER, default="ubuntu")
APP_USER = env_value(*ENV_APP_USER, default=USER)
APP_GROUP = env_value(*ENV_APP_GROUP, default="www-data")


PROJECT_NAME = env_value(*ENV_PROJECT_NAME, default=PROJECT_ROOT.name)


def debug(msg: str) -> None:
    print(f"[fab] {msg}")


def get_github_token() -> Optional[str]:
    debug("Refreshing GitHub token via helper script")
    script_path = Path(__file__).resolve().parent / "scripts" / "get_github_app_token.py"
    if not script_path.is_file():
        debug(f"Token helper {script_path} missing")
        return None
    debug(f"Running token helper {script_path}")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        if stderr:
            debug(f"Token helper failed: {stderr}")
        elif stdout:
            debug(f"Token helper failed: {stdout}")
        else:
            debug(f"Token helper failed with exit code {result.returncode}")
        return None
    token = result.stdout.strip()
    if token:
        debug("Fetched GitHub App installation token via helper")
    else:
        debug("Helper returned empty token")
    return token or None


GITHUB_TOKEN = get_github_token()


def get_repo_url() -> str:
    github_repo = require_env(*ENV_GITHUB_APP_REPO)
    return f"https://github.com/{github_repo}.git"


PROJECT_DIR = f"/srv/apps/{PROJECT_NAME}"
VENV_DIR = f"{PROJECT_DIR}/venv"
PYTHON_BIN = f"{VENV_DIR}/bin/python"
ENV_FILE = f"{PROJECT_DIR}/.env"
MCP_SERVICE = "feature-request-mcp.service"
MCP_CLEANUP_SERVICE = "feature-request-oauth-cleanup.service"
MCP_CLEANUP_TIMER = "feature-request-oauth-cleanup.timer"
MCP_HEALTH_SERVICE = "feature-request-oauth-health.service"
MCP_HEALTH_TIMER = "feature-request-oauth-health.timer"
MCP_NGINX_INCLUDE = f"/etc/nginx/snippets/{PROJECT_NAME}-mcp-routing.conf"
MCP_BACKUP_ROOT = f"{PROJECT_DIR}/.deploy-backups/mcp"
PERSISTED_PATHS = [
    ".env",
    "db.sqlite3",
    "media",
    "venv",
    "staticfiles",
]


def quote(value: str) -> str:
    return shlex.quote(value)


def run_as_app_user(
    c,
    command: str,
    *,
    cwd: Optional[str] = None,
    warn: bool = False,
):
    if USER == APP_USER:
        if cwd:
            with c.cd(cwd):
                return c.run(command, warn=warn)
        return c.run(command, warn=warn)

    snippet = command
    if cwd:
        snippet = f"cd {quote(cwd)} && {command}"
    return c.sudo(f"bash -lc {quote(snippet)}", user=APP_USER, warn=warn)


def remote_exists(c, path: str) -> bool:
    return c.run(f"test -e {quote(path)}", warn=True, hide=True).ok


def remote_dir_is_empty(c, path: str) -> bool:
    return c.run(
        f"test -z \"$(find {quote(path)} -mindepth 1 -maxdepth 1 -print -quit)\"",
        warn=True,
        hide=True,
    ).ok


def ensure_project_dir(c) -> None:
    c.run(f"mkdir -p {quote(PROJECT_DIR)}")
    if USER != APP_USER:
        c.sudo(f"chown {quote(APP_USER)}:{quote(APP_USER)} {quote(PROJECT_DIR)}")


def upload_env_file(c) -> None:
    candidates = [
        PROJECT_ROOT / ".env-prod",
        PROJECT_ROOT / ".env",
    ]
    source = next((path for path in candidates if path.is_file()), None)
    if not source:
        debug("No .env file found; skipping environment upload")
        return

    remote_tmp = f"/tmp/{source.name}"
    debug(f"Uploading env file {source} to {ENV_FILE}")
    c.put(str(source), remote_tmp)
    c.sudo(f"mv {remote_tmp} {ENV_FILE}")
    c.sudo(f"chown {quote(APP_USER)}:{quote(APP_USER)} {quote(ENV_FILE)}")
    c.sudo(f"chmod 600 {ENV_FILE}")


def connection() -> Connection:
    key_filename = require_env(*ENV_KEY_FILENAME)
    host = require_env(*ENV_HOST)
    debug(f"Connecting to {USER}@{host} with key {key_filename}; app user={APP_USER}")
    return Connection(
        host=host,
        user=USER,
        connect_kwargs={
            "key_filename": str(Path(f"~/.ssh/{key_filename}").expanduser())
        },
    )


def local_git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=PROJECT_ROOT, text=True
    ).strip()


def resolve_source_commit(source_commit: Optional[str]) -> str:
    commit = source_commit or local_git("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("source_commit must be a full lowercase SHA-1")
    head = local_git("rev-parse", "HEAD")
    upstream = local_git("rev-parse", "origin/main")
    status = local_git("status", "--porcelain")
    if status:
        raise RuntimeError("deployment requires a clean tracked working tree")
    if head != commit or upstream != commit:
        raise RuntimeError(
            f"deployment source mismatch: requested={commit} local={head} origin/main={upstream}"
        )
    return commit


def update_remote_env(c, values: dict[str, str]) -> None:
    payload = base64.b64encode(json.dumps(values, sort_keys=True).encode()).decode()
    script = """
import base64, json, os, sys, tempfile
path = sys.argv[1]
updates = json.loads(base64.b64decode(sys.argv[2]).decode())
with open(path, encoding='utf-8') as handle:
    lines = handle.read().splitlines()
rendered = []
written = set()
for raw in lines:
    stripped = raw.strip()
    if stripped and not stripped.startswith('#') and '=' in stripped:
        key = stripped.split('=', 1)[0]
        if key in updates:
            if key not in written:
                rendered.append(f'{key}={updates[key]}')
                written.add(key)
            continue
    rendered.append(raw)
for key in sorted(updates):
    if key not in written:
        rendered.append(f'{key}={updates[key]}')
content = '\n'.join(rendered) + '\n'
directory = os.path.dirname(path)
descriptor, temporary = tempfile.mkstemp(prefix='.env.', dir=directory)
try:
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
"""
    run_as_app_user(
        c,
        f"python3 -c {quote(script)} {quote(ENV_FILE)} {quote(payload)}",
    )


def write_remote_json(c, path: str, payload: dict) -> None:
    encoded = base64.b64encode(
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    ).decode()
    script = """
import base64, os, sys, tempfile
path = sys.argv[1]
content = base64.b64decode(sys.argv[2])
descriptor, temporary = tempfile.mkstemp(prefix='.deployment.', dir=os.path.dirname(path))
try:
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
"""
    run_as_app_user(
        c,
        f"python3 -c {quote(script)} {quote(path)} {quote(encoded)}",
    )


def render_asset(relative_path: str) -> str:
    return (
        (PROJECT_ROOT / relative_path)
        .read_text(encoding="utf-8")
        .replace("__PROJECT_NAME__", PROJECT_NAME)
        .replace("__APP_USER__", APP_USER or USER)
        .replace("__APP_GROUP__", APP_GROUP or "www-data")
    )


def install_text(c, content: str, destination: str, *, mode: str = "0644") -> None:
    remote_tmp = f"/tmp/{Path(destination).name}.{os.getpid()}"
    c.put(io.StringIO(content), remote_tmp)
    c.sudo(f"install -o root -g root -m {mode} {quote(remote_tmp)} {quote(destination)}")
    c.run(f"rm -f {quote(remote_tmp)}")


def install_systemd_contract(c) -> None:
    assets = {
        "feature-request-mcp.service": MCP_SERVICE,
        "feature-request-oauth-cleanup.service": MCP_CLEANUP_SERVICE,
        "feature-request-oauth-cleanup.timer": MCP_CLEANUP_TIMER,
        "feature-request-oauth-health.service": MCP_HEALTH_SERVICE,
        "feature-request-oauth-health.timer": MCP_HEALTH_TIMER,
    }
    for source, destination in assets.items():
        install_text(
            c,
            render_asset(f"deploy/mcp/{source}"),
            f"/etc/systemd/system/{destination}",
        )
    dropin_dir = f"/etc/systemd/system/app@{PROJECT_NAME}.service.d"
    c.sudo(f"install -d -o root -g root -m 0755 {quote(dropin_dir)}")
    install_text(
        c,
        render_asset("deploy/mcp/gunicorn-mcp-log-safety.conf"),
        f"{dropin_dir}/20-mcp-log-safety.conf",
    )
    c.sudo("systemctl daemon-reload")


def install_nginx_contract(c, *, enabled: bool) -> None:
    source = (
        "deploy/mcp/nginx-mcp-oauth.conf"
        if enabled
        else "deploy/mcp/nginx-mcp-disabled.conf"
    )
    install_text(c, render_asset(source), MCP_NGINX_INCLUDE)
    site = env_value(
        *ENV_NGINX_SITE,
        default=f"/etc/nginx/sites-available/{PROJECT_NAME}.conf",
    )
    assert site is not None
    helper_tmp = f"/tmp/{PROJECT_NAME}-install-mcp-nginx.{os.getpid()}.py"
    c.put(
        io.StringIO(render_asset("scripts/install_mcp_nginx.py")),
        helper_tmp,
    )
    try:
        c.sudo(
            f"python3 {quote(helper_tmp)} --site-config {quote(site)} "
            f"--include-path {quote(MCP_NGINX_INCLUDE)}"
        )
    finally:
        c.run(f"rm -f {quote(helper_tmp)}", warn=True)
    c.sudo("nginx -t")
    c.sudo("systemctl reload nginx")


def set_mcp_route(c, *, enabled: bool) -> None:
    if not enabled:
        c.sudo(f"systemctl stop {MCP_SERVICE}", warn=True)
    install_nginx_contract(c, enabled=enabled)
    debug(f"MCP/OAuth public route enabled={enabled}")


def take_database_backup(c) -> str:
    stanza = env_value(*ENV_PGBACKREST_STANZA, default="stageops")
    assert stanza is not None
    c.run("command -v pgbackrest")
    debug(f"Taking verified pgBackRest full backup for stanza {stanza}")
    c.sudo(
        f"pgbackrest --stanza={quote(stanza)} --type=full backup",
        user="postgres",
    )
    result = c.sudo(
        f"pgbackrest --stanza={quote(stanza)} --output=json info",
        user="postgres",
        hide=True,
    )
    info = json.loads(result.stdout)
    try:
        backup = info[0]["backup"][-1]
        label = backup["label"]
        status_code = info[0]["status"]["code"]
    except (IndexError, KeyError, TypeError) as exc:
        raise RuntimeError("pgBackRest did not report the completed backup") from exc
    if status_code != 0:
        raise RuntimeError("pgBackRest stanza is not healthy after backup")
    debug(f"Verified pgBackRest backup label {label}")
    return label


def prepare_backup_directory(c) -> tuple[str, str, str]:
    timestamp = c.run("date -u +%Y%m%dT%H%M%SZ", hide=True).stdout.strip()
    directory = f"{MCP_BACKUP_ROOT}/{timestamp}"
    c.sudo(f"install -d -o {quote(APP_USER)} -g {quote(APP_GROUP)} -m 0700 {quote(directory)}")
    previous_commit = run_as_app_user(
        c, "git rev-parse HEAD", cwd=PROJECT_DIR
    ).stdout.strip()
    env_backup = f"{directory}/environment.env"
    run_as_app_user(c, f"cp {quote(ENV_FILE)} {quote(env_backup)}")
    run_as_app_user(c, f"chmod 0600 {quote(env_backup)}")
    return directory, previous_commit, env_backup


def update_checkout(c, repo_url: str, source_commit: str) -> None:
    ensure_project_dir(c)
    if not c.run(f"test -d {PROJECT_DIR}/.git", warn=True, hide=True).ok:
        if remote_dir_is_empty(c, PROJECT_DIR):
            clone_repo(c, repo_url, PROJECT_DIR)
        else:
            bootstrap_existing_non_git_dir(c, repo_url)
    use_token = bool(GITHUB_TOKEN and repo_url.startswith("https://"))
    run_git_command(
        c,
        "fetch origin main --prune",
        cwd=PROJECT_DIR,
        use_token=use_token,
    )
    run_as_app_user(
        c,
        f"git merge-base --is-ancestor {quote(source_commit)} origin/main",
        cwd=PROJECT_DIR,
    )
    run_git_command(c, "checkout main", cwd=PROJECT_DIR, use_token=False)
    run_git_command(c, f"reset --hard {quote(source_commit)}", cwd=PROJECT_DIR)
    resolved = run_as_app_user(c, "git rev-parse HEAD", cwd=PROJECT_DIR).stdout.strip()
    if resolved != source_commit:
        raise RuntimeError(
            f"production checkout mismatch: expected={source_commit} resolved={resolved}"
        )


def install_dependencies(c) -> None:
    if c.run(f"test -d {VENV_DIR}", warn=True, hide=True).failed:
        debug("Creating virtualenv")
        run_as_app_user(c, f"python3 -m venv {quote(VENV_DIR)}")
    if not (
        remote_exists(c, f"{PROJECT_DIR}/pyproject.toml")
        and remote_exists(c, f"{PROJECT_DIR}/uv.lock")
    ):
        raise RuntimeError("native MCP deploy requires pyproject.toml and uv.lock")
    run_as_app_user(
        c,
        f"{quote(VENV_DIR)}/bin/pip install uv==0.9.26",
        cwd=PROJECT_DIR,
    )
    run_as_app_user(
        c,
        f"UV_PROJECT_ENVIRONMENT={quote(VENV_DIR)} {quote(VENV_DIR)}/bin/uv sync --frozen --no-dev",
        cwd=PROJECT_DIR,
    )


def validate_native_runtime(c) -> None:
    run_as_app_user(
        c,
        f"{quote(PYTHON_BIN)} scripts/verify_mcp_deploy_config.py "
        f"--env-file {quote(ENV_FILE)} --project-dir {quote(PROJECT_DIR)}",
        cwd=PROJECT_DIR,
    )
    run_as_app_user(c, f"{quote(PYTHON_BIN)} manage.py check", cwd=PROJECT_DIR)
    run_as_app_user(
        c,
        f"{quote(PYTHON_BIN)} manage.py makemigrations --check --dry-run",
        cwd=PROJECT_DIR,
    )


def run_release_steps(c) -> None:
    run_as_app_user(
        c, f"{quote(PYTHON_BIN)} manage.py migrate --plan", cwd=PROJECT_DIR
    )
    run_as_app_user(
        c, f"{quote(PYTHON_BIN)} manage.py collectstatic --noinput", cwd=PROJECT_DIR
    )
    run_as_app_user(c, f"{quote(PYTHON_BIN)} manage.py migrate", cwd=PROJECT_DIR)


def restart_web(c) -> None:
    c.sudo(f"systemctl stop app@{PROJECT_NAME}.service", warn=True)
    c.sudo(f"systemctl restart app@{PROJECT_NAME}.socket")
    c.sudo(f"systemctl reset-failed app@{PROJECT_NAME}.service app@{PROJECT_NAME}.socket")


def check_loopback_mcp(c) -> None:
    script = """
from urllib.error import HTTPError
from urllib.request import Request, urlopen
request = Request('http://127.0.0.1:8001/mcp', headers={'Host': 'featurerequest.io'})
try:
    urlopen(request, timeout=10)
except HTTPError as exc:
    challenge = exc.headers.get('WWW-Authenticate', '')
    if exc.code != 401 or 'resource_metadata=' not in challenge or not challenge.startswith('Bearer '):
        raise SystemExit(f'unexpected MCP challenge: status={exc.code}')
else:
    raise SystemExit('anonymous MCP request unexpectedly succeeded')
print('loopback_mcp_challenge=passed')
"""
    c.run(f"python3 -c {quote(script)}")


def check_public_surfaces(c) -> None:
    domain = require_env(*ENV_DOMAIN)
    script = """
import json, sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
base = sys.argv[1]
for path in ('/.well-known/oauth-authorization-server', '/.well-known/oauth-protected-resource/mcp'):
    with urlopen(base + path, timeout=15) as response:
        if response.status != 200:
            raise SystemExit(f'{path} status={response.status}')
        json.load(response)
try:
    urlopen(Request(base + '/mcp'), timeout=15)
except HTTPError as exc:
    challenge = exc.headers.get('WWW-Authenticate', '')
    if exc.code != 401 or 'resource_metadata=' not in challenge:
        raise SystemExit(f'/mcp status={exc.code}')
else:
    raise SystemExit('/mcp unexpectedly allowed anonymous access')
print('public_mcp_oauth_health=passed')
"""
    c.run(f"python3 -c {quote(script)} {quote('https://' + domain)}")


def config_values(source_commit: str) -> dict[str, str]:
    values = repository_identity(PROJECT_ROOT, source_commit)
    values.update(
        {
            "PUBLIC_BASE_URL": "https://featurerequest.io",
            "OAUTH_ISSUER": "https://featurerequest.io",
            "MCP_RESOURCE_URL": "https://featurerequest.io/mcp",
            "MCP_RESOURCE_METADATA_URL": (
                "https://featurerequest.io/.well-known/oauth-protected-resource/mcp"
            ),
            "FEATURE_REQUEST_MCP_PRODUCTION_ENABLED": "true",
            "FEATURE_REQUEST_MCP_HOST": "127.0.0.1",
            "FEATURE_REQUEST_MCP_PORT": "8001",
            "FEATURE_REQUEST_MCP_CORS_ORIGINS": (
                "https://chatgpt.com,https://claude.ai,https://claude.com"
            ),
            "FEATURE_REQUEST_TRUSTED_PROXY_IPS": "127.0.0.1,::1",
        }
    )
    values["FEATURE_REQUEST_CONFIG_FINGERPRINT_SHA256"] = config_fingerprint_sha256(
        {
            **values,
            "DEBUG": "false",
            "DATABASE_URL": "postgresql://configured",
            "ADMIN_EMAIL": "configured",
        }
    )
    return values


def git_with_header(c, git_command: str, token: str, cwd: Optional[str] = None) -> bool:
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    cmd = (
        f'GIT_TERMINAL_PROMPT=0 git -c credential.helper= -c http.extraHeader="Authorization: Basic {auth}" {git_command}'
    )
    location = cwd or "current directory"
    debug(f"Running git command in {location}: git {git_command}")
    result = run_as_app_user(c, cmd, cwd=cwd, warn=True)

    if result.failed:
        debug(f"git command failed with exit code {result.return_code}")
        return False
    return True


def run_plain_git(c, git_command: str, cwd: Optional[str] = None) -> None:
    debug(f"Running git command without token: git {git_command}")
    run_as_app_user(c, f"git {git_command}", cwd=cwd)


def run_git_command(c, git_command: str, cwd: Optional[str] = None, use_token: bool = False) -> None:
    global GITHUB_TOKEN
    if use_token and GITHUB_TOKEN:
        debug("Executing git command")
        if git_with_header(c, git_command, GITHUB_TOKEN, cwd=cwd):
            return
        raise RuntimeError("Git command failed")
    else:
        run_plain_git(c, git_command, cwd=cwd)


def clone_repo(c, repo_url: str, target_dir: str) -> None:
    clone_command = f"clone {quote(repo_url)} {quote(target_dir)}"
    if GITHUB_TOKEN and repo_url.startswith("https://"):
        debug("Cloning repository over HTTPS with token")
        run_git_command(c, clone_command, use_token=True)
        run_as_app_user(c, f"git -C {quote(target_dir)} remote set-url origin {quote(repo_url)}")
    else:
        debug(f"Cloning repository using {repo_url}")
        run_git_command(c, clone_command)


def bootstrap_existing_non_git_dir(c, repo_url: str) -> None:
    timestamp = c.run("date +%Y%m%d%H%M%S", hide=True).stdout.strip()
    backup_dir = f"{PROJECT_DIR}.pre-git-{timestamp}"

    debug(
        f"{PROJECT_DIR} exists but is not a git checkout; "
        f"moving it to {backup_dir} before cloning."
    )
    c.sudo(f"mv {quote(PROJECT_DIR)} {quote(backup_dir)}")
    c.sudo(f"mkdir -p {quote(PROJECT_DIR)}")
    c.sudo(f"chown {quote(APP_USER)}:{quote(APP_USER)} {quote(PROJECT_DIR)}")

    clone_repo(c, repo_url, PROJECT_DIR)

    for item in PERSISTED_PATHS:
        source = f"{backup_dir}/{item}"
        target = f"{PROJECT_DIR}/{item}"
        if not remote_exists(c, source):
            continue
        debug(f"Restoring persisted path: {item}")
        c.sudo(f"rm -rf {quote(target)}", warn=True)
        c.sudo(f"mv {quote(source)} {quote(target)}")
        c.sudo(f"chown -R {quote(APP_USER)}:{quote(APP_USER)} {quote(target)}")

    debug(f"Left one-time bootstrap backup at {backup_dir}")


@task(help={"source_commit": "Exact full origin/main SHA to deploy"})
def deploy(c, source_commit=None):
    """Deploy the exact native checkout and enable guarded MCP/OAuth production routing."""
    source_commit = resolve_source_commit(source_commit)
    repo_url = get_repo_url()
    values = config_values(source_commit)
    debug(f"Native MCP deployment source: {source_commit}")
    debug(f"Using repo URL: {repo_url}")
    c = connection()

    backup_directory = ""
    previous_commit = ""
    env_backup = ""
    backup_label = ""
    try:
        ensure_project_dir(c)
        if not remote_exists(c, ENV_FILE):
            raise RuntimeError(f"production environment file is missing: {ENV_FILE}")

        backup_directory, previous_commit, env_backup = prepare_backup_directory(c)
        backup_label = take_database_backup(c)
        set_mcp_route(c, enabled=False)

        update_checkout(c, repo_url, source_commit)
        upload_env_file(c)
        update_remote_env(c, values)
        install_dependencies(c)
        validate_native_runtime(c)
        run_release_steps(c)

        install_systemd_contract(c)
        c.sudo(f"systemctl enable {MCP_SERVICE} {MCP_CLEANUP_TIMER} {MCP_HEALTH_TIMER}")
        c.sudo(f"systemctl restart {MCP_SERVICE}")
        c.sudo(f"systemctl start {MCP_CLEANUP_SERVICE}")
        c.sudo(f"systemctl start {MCP_HEALTH_SERVICE}")
        c.sudo(f"systemctl restart {MCP_CLEANUP_TIMER} {MCP_HEALTH_TIMER}")
        check_loopback_mcp(c)

        restart_web(c)
        set_mcp_route(c, enabled=True)
        check_public_surfaces(c)

        evidence = {
            "schema_version": 1,
            "status": "candidate_deployed_production_acceptance_pending",
            "source_commit": source_commit,
            "source_tree_sha256": values["FEATURE_REQUEST_SOURCE_TREE_SHA256"],
            "dependency_lock_sha256": values[
                "FEATURE_REQUEST_DEPENDENCY_LOCK_SHA256"
            ],
            "deploy_contract_sha256": values[
                "FEATURE_REQUEST_DEPLOY_CONTRACT_SHA256"
            ],
            "config_fingerprint_sha256": values[
                "FEATURE_REQUEST_CONFIG_FINGERPRINT_SHA256"
            ],
            "previous_source_commit": previous_commit,
            "database_backup": {
                "provider": "pgbackrest",
                "type": "full",
                "label": backup_label,
            },
            "environment_backup": env_backup,
            "route_disable_command": "cd .deploy && fab disable-mcp-route",
            "rollback_command": (
                "cd .deploy && fab rollback-mcp "
                f"--source-commit={previous_commit} --env-backup={env_backup}"
            ),
            "health": {
                "django_check": "passed",
                "cleanup": "passed",
                "cleanup_health": "passed",
                "loopback_mcp_challenge": "passed",
                "public_discovery_and_challenge": "passed",
            },
            "public_route_enabled": True,
        }
        write_remote_json(c, f"{backup_directory}/deployment.json", evidence)
        debug(f"Deployment evidence: {backup_directory}/deployment.json")
        debug(f"Production source verified: {source_commit}")
    except Exception:
        debug("Deployment failed; forcing MCP/OAuth route closed")
        try:
            set_mcp_route(c, enabled=False)
        except Exception as rollback_error:
            debug(f"Route fail-close also failed: {rollback_error}")
        raise


@task
def disable_mcp_route(c):
    """Fail-close public MCP/OAuth routing without changing code or data."""
    c = connection()
    set_mcp_route(c, enabled=False)


@task(
    help={
        "source_commit": "Exact previous full SHA",
        "env_backup": "Absolute environment backup recorded in deployment evidence",
    }
)
def rollback_mcp(c, source_commit, env_backup):
    """Restore a prior exact native checkout/config and leave MCP/OAuth routing disabled."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit or ""):
        raise RuntimeError("rollback source_commit must be a full lowercase SHA-1")
    allowed_prefix = f"{MCP_BACKUP_ROOT}/"
    if not env_backup.startswith(allowed_prefix) or not env_backup.endswith(
        "/environment.env"
    ):
        raise RuntimeError("rollback env_backup is outside the MCP backup root")
    c = connection()
    set_mcp_route(c, enabled=False)
    if not remote_exists(c, env_backup):
        raise RuntimeError(f"rollback environment backup does not exist: {env_backup}")
    c.sudo(f"systemctl stop {MCP_SERVICE}", warn=True)
    run_as_app_user(c, f"cp {quote(env_backup)} {quote(ENV_FILE)}")
    run_as_app_user(c, f"chmod 0600 {quote(ENV_FILE)}")
    update_checkout(c, get_repo_url(), source_commit)
    install_dependencies(c)
    run_as_app_user(c, f"{quote(PYTHON_BIN)} manage.py check", cwd=PROJECT_DIR)
    run_as_app_user(
        c, f"{quote(PYTHON_BIN)} manage.py collectstatic --noinput", cwd=PROJECT_DIR
    )
    restart_web(c)
    debug(
        f"Rollback restored {source_commit}; migrations were not reversed and MCP/OAuth remains disabled"
    )


ns = Collection(deploy, disable_mcp_route, rollback_mcp)
