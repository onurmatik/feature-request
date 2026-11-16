from __future__ import annotations

import base64
import os
import re
import shlex
import subprocess
import sys
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fabric import Connection, task
from invoke import Collection


DEPLOY_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DEPLOY_DIR.parent

load_dotenv(DEPLOY_DIR / ".credentials.env")
load_dotenv(DEPLOY_DIR / "deploy.env")


def get_env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def require_env(*names: str) -> str:
    value = get_env(*names)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")
    return value


USER = get_env("DEPLOY_USER") or "ubuntu"
APP_USER = get_env("APP_USER") or USER
PROJECT_NAME = get_env("PROJECT_NAME") or PROJECT_ROOT.name

if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", PROJECT_NAME):
    raise RuntimeError("PROJECT_NAME must be a safe systemd identifier")

PROJECT_DIR = f"/srv/apps/{PROJECT_NAME}"
VENV_DIR = f"{PROJECT_DIR}/venv"
PYTHON_BIN = f"{VENV_DIR}/bin/python"
ENV_FILE = f"{PROJECT_DIR}/.env"
UV_VERSION = "0.9.26"
MCP_SERVICE = "feature-request-mcp.service"
STAGEOPS_CRON_LOCK = f"/run/lock/stageops-{PROJECT_NAME}-deploy.lock"
STAGEOPS_CRONTAB = f"/etc/cron.d/stageops-{PROJECT_NAME}"
PAUSED_CRONTAB = f"/etc/cron.d/.stageops-{PROJECT_NAME}-deploy-paused"


def debug(message: str) -> None:
    print(f"[fab] {message}", flush=True)


@contextmanager
def timed_step(label: str):
    started_at = time.monotonic()
    debug(f"{label} started")
    try:
        yield
    except Exception:
        debug(f"{label} failed after {time.monotonic() - started_at:.2f}s")
        raise
    debug(f"{label} completed in {time.monotonic() - started_at:.2f}s")


def quote(value: str) -> str:
    return shlex.quote(value)


@contextmanager
def pause_stageops_cron(connection: Connection):
    """Prevent StageOps cron commands from overlapping a mutable deploy."""

    connection.open()
    channel = connection.client.get_transport().open_session()
    channel.settimeout(15)
    try:
        lock_command = (
            f"flock -n {quote(STAGEOPS_CRON_LOCK)} "
            + quote("sh")
            + " -c "
            + quote("printf 'LOCKED\\n'; cat >/dev/null")
        )
        if USER != APP_USER:
            lock_command = f"sudo -n -H -u {quote(APP_USER)} -- {lock_command}"
        channel.exec_command(lock_command)
        received = b""
        while b"\n" not in received:
            block = channel.recv(32)
            if not block:
                detail = channel.recv_stderr(4096).decode("utf-8", errors="replace").strip()
                raise RuntimeError(
                    "A StageOps cron job is running, or the cron/deploy lock could not be acquired"
                    + (f": {detail}" if detail else "")
                )
            received += block
        if received != b"LOCKED\n":
            raise RuntimeError("Could not acquire the StageOps cron/deploy lock")
        yield
    finally:
        channel.close()


def run_as_app_user(
    connection: Connection,
    command: str,
    *,
    cwd: Optional[str] = None,
    warn: bool = False,
    hide: bool = False,
):
    if USER == APP_USER:
        if cwd:
            with connection.cd(cwd):
                return connection.run(command, warn=warn, hide=hide, pty=False)
        return connection.run(command, warn=warn, hide=hide, pty=False)

    snippet = command if cwd is None else f"cd {quote(cwd)} && {command}"
    if USER == "root":
        return connection.run(
            f"sudo -n -H -u {quote(APP_USER)} -- bash -lc {quote(snippet)}",
            warn=warn,
            hide=hide,
            pty=False,
        )
    return connection.sudo(
        f"bash -lc {quote(snippet)}",
        user=APP_USER,
        warn=warn,
        hide=hide,
        pty=False,
    )


def get_github_token() -> Optional[str]:
    helper = DEPLOY_DIR / "scripts" / "get_github_app_token.py"
    if not helper.is_file():
        debug("GitHub token helper is absent; using unauthenticated Git access")
        return None
    result = subprocess.run(
        [sys.executable, str(helper)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        debug(f"GitHub token helper failed: {message or result.returncode}")
        return None
    return result.stdout.strip() or None


def repo_url() -> str:
    return f"https://github.com/{require_env('GITHUB_APP_REPO')}.git"


def git_command(
    connection: Connection,
    arguments: str,
    *,
    cwd: Optional[str] = None,
    token: Optional[str] = None,
) -> None:
    if token:
        authorization = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        command = (
            "GIT_TERMINAL_PROMPT=0 git -c credential.helper= "
            f"-c http.extraHeader={quote('Authorization: Basic ' + authorization)} "
            f"{arguments}"
        )
    else:
        command = f"git {arguments}"
    run_as_app_user(connection, command, cwd=cwd)


def ensure_checkout(
    connection: Connection,
    *,
    source_url: str,
    token: Optional[str],
    expected_revision: Optional[str] = None,
) -> None:
    connection.run(f"mkdir -p {quote(PROJECT_DIR)}")
    if USER != APP_USER:
        connection.sudo(f"chown {quote(APP_USER)}:{quote(APP_USER)} {quote(PROJECT_DIR)}")

    has_git = connection.run(
        f"test -d {quote(PROJECT_DIR + '/.git')}",
        warn=True,
        hide=True,
    ).ok
    if not has_git:
        is_empty = connection.run(
            f'test -z "$(find {quote(PROJECT_DIR)} -mindepth 1 -maxdepth 1 -print -quit)"',
            warn=True,
            hide=True,
        ).ok
        if not is_empty:
            raise RuntimeError(f"{PROJECT_DIR} exists and is not an empty Git checkout")
        git_command(
            connection,
            f"clone {quote(source_url)} {quote(PROJECT_DIR)}",
            token=token,
        )
        run_as_app_user(
            connection,
            f"git remote set-url origin {quote(source_url)}",
            cwd=PROJECT_DIR,
        )
        return

    git_command(connection, "fetch origin main --prune", cwd=PROJECT_DIR, token=token)
    if expected_revision is not None:
        fetched_revision = run_as_app_user(
            connection, "git rev-parse origin/main", cwd=PROJECT_DIR, hide=True
        ).stdout.strip()
        if fetched_revision != expected_revision:
            raise RuntimeError("origin/main changed after release preflight")
    run_as_app_user(connection, "git checkout main", cwd=PROJECT_DIR)
    run_as_app_user(connection, "git reset --hard origin/main", cwd=PROJECT_DIR)


def upload_environment(connection: Connection) -> None:
    source = next(
        (
            candidate
            for candidate in (PROJECT_ROOT / ".env-prod", PROJECT_ROOT / ".env")
            if candidate.is_file()
        ),
        None,
    )
    if source is None:
        debug("No .env-prod or .env found; preserving the server environment")
        return

    temporary = f"/tmp/{PROJECT_NAME}-{source.name}"
    connection.put(str(source), temporary)
    connection.sudo(
        f"install -o {quote(APP_USER)} -g {quote(APP_USER)} -m 600 "
        f"{quote(temporary)} {quote(ENV_FILE)}"
    )
    connection.run(f"rm -f {quote(temporary)}", warn=True, hide=True)


def install_dependencies(connection: Connection) -> None:
    created = connection.run(
        f"test -x {quote(PYTHON_BIN)}",
        warn=True,
        hide=True,
    ).failed
    if created:
        run_as_app_user(connection, f"python3 -m venv {quote(VENV_DIR)}")
        run_as_app_user(connection, f"{quote(VENV_DIR + '/bin/pip')} install --upgrade pip")

    run_as_app_user(
        connection,
        f"{quote(VENV_DIR + '/bin/pip')} install {quote('uv==' + UV_VERSION)}",
        cwd=PROJECT_DIR,
    )
    run_as_app_user(
        connection,
        f"UV_PROJECT_ENVIRONMENT={quote(VENV_DIR)} {quote(VENV_DIR + '/bin/uv')} "
        "sync --frozen --no-dev",
        cwd=PROJECT_DIR,
    )


def run_django_release(connection: Connection) -> None:
    run_as_app_user(
        connection,
        f"{quote(PYTHON_BIN)} manage.py collectstatic --noinput",
        cwd=PROJECT_DIR,
    )
    run_as_app_user(
        connection,
        f"{quote(PYTHON_BIN)} manage.py migrate --noinput",
        cwd=PROJECT_DIR,
    )
    run_as_app_user(
        connection,
        f"{quote(PYTHON_BIN)} manage.py check --deploy",
        cwd=PROJECT_DIR,
    )


def restart_mcp_runtime(connection: Connection) -> None:
    result = connection.sudo(
        f"systemctl cat {quote(MCP_SERVICE)}",
        warn=True,
        hide=True,
    )
    if result.failed:
        raise RuntimeError(
            f"StageOps-managed unit is missing: {MCP_SERVICE}. "
            "Apply the featurerequest app in StageOps before deploying."
        )

    connection.sudo(f"systemctl restart {quote(MCP_SERVICE)}")
    connection.sudo(f"systemctl is-active --quiet {quote(MCP_SERVICE)}")


def restart_web(connection: Connection) -> None:
    socket = f"app@{PROJECT_NAME}.socket"
    service = f"app@{PROJECT_NAME}.service"
    connection.sudo(f"systemctl stop {quote(socket)}")
    connection.sudo(f"systemctl stop {quote(service)}", warn=True)
    connection.sudo(f"systemctl start {quote(socket)}")
    connection.sudo(f"systemctl reset-failed {quote(service)} {quote(socket)}", warn=True)
    connection.sudo(f"systemctl is-active --quiet {quote(socket)}")


def public_smoke(connection: Connection) -> None:
    domain = require_env("DOMAIN_NAME", "DOMAIN")
    connection.run(
        "curl --fail --silent --show-error --location "
        "--connect-timeout 10 --max-time 30 "
        f"{quote('https://' + domain.rstrip('/') + '/')} >/dev/null"
    )
    headers = connection.run(
        "curl --silent --show-error --dump-header - --output /dev/null "
        "--connect-timeout 10 --max-time 30 "
        f"{quote('https://' + domain.rstrip('/') + '/mcp')}",
        hide=True,
    ).stdout
    status_line = headers.splitlines()[0] if headers else ""
    if " 401" not in status_line or "www-authenticate: bearer" not in headers.lower():
        raise RuntimeError("FeatureRequest public MCP discovery smoke did not return a Bearer 401")


def prepare_release(
    connection: Connection, token: Optional[str], *, static_only: bool = False,
) -> tuple[str, str]:
    """Pin the incoming revision and record the previous checkout before mutation."""

    previous = run_as_app_user(
        connection, "git rev-parse HEAD", cwd=PROJECT_DIR, hide=True
    ).stdout.strip()
    dirty = run_as_app_user(
        connection, "git status --porcelain --untracked-files=no", cwd=PROJECT_DIR, hide=True
    ).stdout.strip()
    if dirty:
        raise RuntimeError("Release requires a clean server checkout")
    git_command(connection, "fetch origin main --prune", cwd=PROJECT_DIR, token=token)
    target = run_as_app_user(
        connection, "git rev-parse origin/main", cwd=PROJECT_DIR, hide=True
    ).stdout.strip()
    changed_paths = run_as_app_user(
        connection,
        f"git diff --name-only {quote(previous)} {quote(target)}",
        cwd=PROJECT_DIR,
        hide=True,
    ).stdout.splitlines()
    allowed_support_files = {".deploy/fabfile.py", ".deploy/README.md", "tests/test_deploy.py"}
    unsupported = [
        path for path in changed_paths
        if not path.startswith("projects/static/") and path not in allowed_support_files
    ]
    if static_only and unsupported:
        raise RuntimeError("Static release contains non-static changes: " + ", ".join(unsupported))
    source = next(
        (path for path in (PROJECT_ROOT / ".env-prod", PROJECT_ROOT / ".env") if path.is_file()),
        None,
    )
    if static_only and source is not None:
        with connection.sftp().open(ENV_FILE, "rb") as remote_file:
            environment_matches = remote_file.read() == source.read_bytes()
        if not environment_matches:
            raise RuntimeError("Static release cannot change the server environment")
    for command in ("migrate --check", "makemigrations --check --dry-run", "check --deploy"):
        run_as_app_user(connection, f"{quote(PYTHON_BIN)} manage.py {command}", cwd=PROJECT_DIR)
    public_smoke(connection)
    run_as_app_user(
        connection,
        f"printf '%s\\n' {quote(previous)} > .deploy-previous-revision",
        cwd=PROJECT_DIR,
    )
    debug(f"Release previous={previous} target={target}")
    return previous, target


def prepare_static_release(connection: Connection, token: Optional[str]) -> tuple[str, str]:
    """Prove that restoring the previous checkout cannot change schema or dependencies."""
    return prepare_release(connection, token, static_only=True)


def stop_runtime(connection: Connection) -> None:
    units = (f"app@{PROJECT_NAME}.socket", f"app@{PROJECT_NAME}.service", MCP_SERVICE)
    connection.sudo("systemctl stop " + " ".join(quote(unit) for unit in units))


@contextmanager
def quiesce_runtime(connection: Connection):
    """Keep mutable-checkout consumers stopped across code and schema changes."""
    # A leading dot makes cron ignore the saved file. Leave it paused on failure
    # so releasing the deploy lock cannot launch code against an uncertain schema.
    cron_present = connection.sudo(
        f"test -f {quote(STAGEOPS_CRONTAB)}", warn=True, hide=True,
    ).ok
    if cron_present:
        connection.sudo(f"mv -- {quote(STAGEOPS_CRONTAB)} {quote(PAUSED_CRONTAB)}")
    try:
        stop_runtime(connection)
        yield
        if cron_present:
            connection.sudo(f"mv -- {quote(PAUSED_CRONTAB)} {quote(STAGEOPS_CRONTAB)}")
    except BaseException:
        stop_runtime(connection)
        debug(
            "Release failed: web and MCP remain stopped, and project cron remains paused. "
            "Check schema/config compatibility before recovery; the previous revision is "
            "recorded in .deploy-previous-revision."
        )
        raise


def verify_revision(connection: Connection, expected: str) -> None:
    observed = run_as_app_user(
        connection, "git rev-parse HEAD", cwd=PROJECT_DIR, hide=True
    ).stdout.strip()
    if observed != expected:
        raise RuntimeError(f"Deployed revision mismatch: expected {expected}, observed {observed}")
    run_as_app_user(
        connection, f"{quote(PYTHON_BIN)} manage.py migrate --check", cwd=PROJECT_DIR
    )
    debug(f"Verified revision {observed}; no pending migrations")


def restore_static_release(connection: Connection, previous: str) -> None:
    debug(f"Restoring previous static release {previous}")
    run_as_app_user(connection, f"git reset --hard {quote(previous)}", cwd=PROJECT_DIR)
    run_as_app_user(
        connection, f"{quote(PYTHON_BIN)} manage.py collectstatic --noinput", cwd=PROJECT_DIR
    )
    run_as_app_user(
        connection, f"{quote(PYTHON_BIN)} manage.py check --deploy", cwd=PROJECT_DIR
    )
    verify_revision(connection, previous)
    restart_mcp_runtime(connection)
    restart_web(connection)
    public_smoke(connection)
    debug("Previous static release restored and verified")


@task
def deploy(_context, static_only=False):
    """Deploy FeatureRequest through its existing native Django contract."""

    source_url = repo_url()
    token = get_github_token()
    host = require_env("DEPLOY_HOST", "HOST")
    key_filename = require_env("KEY_FILENAME")
    connection = Connection(
        host=host,
        user=USER,
        connect_kwargs={
            "key_filename": str(Path(f"~/.ssh/{key_filename}").expanduser()),
        },
    )

    with pause_stageops_cron(connection):
        if not static_only and connection.sudo(
            f"test -e {quote(PAUSED_CRONTAB)}", warn=True, hide=True,
        ).ok:
            raise RuntimeError("A previous release left cron paused; recover it before deploying")
        boundary = (
            prepare_static_release(connection, token)
            if static_only else prepare_release(connection, token)
        )
        try:
            with nullcontext() if static_only else quiesce_runtime(connection):
                with timed_step("Repository update"):
                    ensure_checkout(
                        connection, source_url=source_url, token=token,
                        expected_revision=boundary[1],
                    )
                if not static_only:
                    with timed_step("Environment upload"):
                        upload_environment(connection)
                    with timed_step("Production dependency sync"):
                        install_dependencies(connection)
                    with timed_step("Django release steps"):
                        run_django_release(connection)
                else:
                    with timed_step("Static files"):
                        run_as_app_user(
                            connection, f"{quote(PYTHON_BIN)} manage.py collectstatic --noinput",
                            cwd=PROJECT_DIR,
                        )
                verify_revision(connection, boundary[1])
                with timed_step("StageOps-managed MCP restart"):
                    restart_mcp_runtime(connection)
                with timed_step("Web service restart"):
                    restart_web(connection)
                with timed_step("Public smoke"):
                    public_smoke(connection)
                verify_revision(connection, boundary[1])
        except Exception:
            if static_only:
                restore_static_release(connection, boundary[0])
            raise


ns = Collection(deploy)
