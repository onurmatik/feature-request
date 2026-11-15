Run the existing native Django deployment from this directory:

```bash
cd .deploy/
fab deploy
```

For a release limited to `projects/static/` (plus this deployment contract and
its tests), use:

```bash
fab deploy --static-only
```

This path holds the same cron/deploy lock, checks the exact incoming revision,
requires a clean tracked server checkout, unchanged environment, and no pending
migrations or model changes. It records `.deploy-previous-revision` before
activation. It skips environment upload, dependency sync, and migration writes.
If activation or verification fails, it restores that revision, republishes its
static files, restarts the existing services, and verifies public health and
migration consistency before reporting the failed release. Non-static changes
are rejected before checkout mutation.

The task:

1. refreshes the GitHub App token when the local helper is configured;
2. clones or hard-resets the server checkout to `origin/main`;
3. uploads `../.env-prod` (preferred) or `../.env` to
   `/srv/apps/{PROJECT_NAME}/.env`;
4. creates the existing native virtualenv and runs frozen production dependency
   sync;
5. runs `collectstatic`, Django migrations and `check --deploy`;
6. verifies and restarts the StageOps-managed FeatureRequest MCP service;
7. restarts the existing `app@{PROJECT_NAME}.socket`; and
8. performs read-only homepage plus MCP discovery smoke checks.

Local configuration:

- `.credentials.env`: GitHub App ID, installation ID and private-key path.
- `deploy.env`: `PROJECT_NAME`, `DOMAIN`, `GITHUB_APP_REPO`, `DEPLOY_HOST`,
  `KEY_FILENAME`, `DEPLOY_USER` and `APP_USER`.

These local environment files are ignored by Git. StageOps owns the native MCP
service, plain cron entries for OAuth cleanup/health checks, exact `/mcp` nginx
routing and OAuth-safe access logging. Cron invocations write per-job logs under
`/var/log/featurerequest/` and latest state under
`/var/lib/stageops/cron/featurerequest/`; the StageOps full health check monitors
them. The deploy holds the shared cron/deploy lock as `APP_USER` while the mutable
checkout is updated, matching the cron lock's ownership. This contract does not
create or mutate systemd/nginx configuration, Docker, database backups or rollback
infrastructure.
