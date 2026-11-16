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
2. fetches and pins `origin/main`, requires a clean tracked checkout and consistent
   current migrations, and records `.deploy-previous-revision`;
3. pauses only `/etc/cron.d/stageops-{PROJECT_NAME}` by moving it to the ignored
   `.stageops-{PROJECT_NAME}-deploy-paused` filename, then stops the web socket,
   web service and MCP service before changing the mutable checkout;
4. hard-resets the server checkout to the pinned revision;
5. uploads `../.env-prod` (preferred) or `../.env` to
   `/srv/apps/{PROJECT_NAME}/.env`;
6. creates the existing native virtualenv and runs frozen production dependency
   sync;
7. runs `collectstatic`, Django migrations and `check --deploy`;
8. verifies the revision and absence of pending migrations, then restarts MCP and
   the existing `app@{PROJECT_NAME}.socket`;
9. checks homepage and MCP discovery, verifies the revision and migrations again,
   and restores the project crontab only after these gates pass.

A failed full deploy leaves web/MCP stopped and the project crontab paused, even
after the deploy lock is released. It refuses another deploy while that paused
crontab exists. Recover using the recorded revision only after checking its
compatibility with the current schema, environment and dependencies; otherwise
roll forward. Do not reverse migrations blindly. After recovery checks pass,
restore the saved crontab to its original filename. Static-only releases retain
their automatic previous-revision recovery and don't pause the crontab.

`collectstatic` publishes content-hashed assets and a manifest for Django's
`static` template tag. The widget loader's CSS dependency is rewritten as part of
this step, so CSS-only changes also version the loader. S3 uploads use a one-year
immutable cache policy for hashed files and revalidation for unversioned files
and the manifest.
Keep older hashed assets available for pages or third-party embeds that still
reference them; do not use `collectstatic --clear` during a release. The manifest
must be published successfully before services restart. Local development uses
unhashed paths with `DEBUG=True`; production-style local runs require
`collectstatic`. The test runner uses plain static storage except for the
manifest integration tests.

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
