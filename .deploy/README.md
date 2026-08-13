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
6. restarts the existing `app@{PROJECT_NAME}.socket`; and
7. performs a read-only public homepage smoke check.

Local configuration:

- `.credentials.env`: GitHub App ID, installation ID and private-key path.
- `deploy.env`: `PROJECT_NAME`, `DOMAIN`, `GITHUB_APP_REPO`, `DEPLOY_HOST`,
  `KEY_FILENAME`, `DEPLOY_USER` and `APP_USER`.

These local environment files are ignored by Git. This deployment contract
does not provision Docker, systemd units, nginx routes, MCP processes, database
backups, schedulers or rollback infrastructure.
