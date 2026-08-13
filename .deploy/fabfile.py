from __future__ import annotations

import base64
import os
import re
import shlex
import subprocess
import sys
import time
from contextlib import contextmanager
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


@task
def deploy(_context):
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

    with timed_step("Repository update"):
        ensure_checkout(connection, source_url=source_url, token=token)
    with timed_step("Environment upload"):
        upload_environment(connection)
    with timed_step("Production dependency sync"):
        install_dependencies(connection)
    with timed_step("Django release steps"):
        run_django_release(connection)
    with timed_step("Web service restart"):
        restart_web(connection)
    with timed_step("Public smoke"):
        public_smoke(connection)


ns = Collection(deploy)
