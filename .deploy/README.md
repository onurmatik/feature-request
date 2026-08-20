Run the existing native Django deployment from this directory:

```bash
cd .deploy/
fab deploy
```

The task:

1. refreshes the GitHub App token when the local helper is configured;
2. clones or hard-resets the server checkout to `origin/main`;
3. uploads `../.env-prod` (preferred) or `../.env` to
   `/srv/apps/{PROJECT_NAME}/.env`;
4. creates the existing native virtualenv and runs frozen production dependency
   sync;
5. runs `collectstatic`, Django migrations and `check --deploy`;
6. verifies and restarts the StageOps-managed FeatureRequest MCP service;
7. verifies the StageOps-managed OAuth cleanup and health timers;
8. restarts the existing `app@{PROJECT_NAME}.socket`; and
9. performs read-only homepage plus MCP discovery smoke checks.

Local configuration:

- `.credentials.env`: GitHub App ID, installation ID and private-key path.
- `deploy.env`: `PROJECT_NAME`, `DOMAIN`, `GITHUB_APP_REPO`, `DEPLOY_HOST`,
  `KEY_FILENAME`, `DEPLOY_USER` and `APP_USER`.

These local environment files are ignored by Git. StageOps owns the native MCP
unit, OAuth maintenance timers, exact `/mcp` nginx routing and OAuth-safe access
logging. This deployment contract consumes that infrastructure; it does not
create or mutate systemd/nginx configuration, Docker, database backups or
rollback infrastructure.
