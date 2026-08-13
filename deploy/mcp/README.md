# MCP/OAuth native direct-production deployment

FeatureRequest uses the existing production checkout, Python virtual environment, systemd and
Nginx deployment model. Docker, OCI images, a container registry and a separate MCP environment
file are not part of this deployment path. Production acceptance and public release sealing are
separate steps.

The canonical deployment entrypoint is:

```bash
cd .deploy
fab deploy --source-commit=<full-origin-main-sha>
```

The task is idempotent. It verifies that the requested commit is the clean local `HEAD` and exact
`origin/main`, records source-tree, `uv.lock`, deploy-contract and secret-free config fingerprints,
then performs these guarded steps:

1. retain the previous exact commit and a mode-`0600` environment backup, then take and verify a
   pgBackRest full database backup;
2. fail-close the MCP/OAuth Nginx routing include and stop the MCP process;
3. reset the production checkout to the requested commit and install the frozen dependencies;
4. add canonical non-secret MCP keys and exact source identity to the existing project `.env`;
5. validate the native checkout, run Django checks, collect static files and apply additive
   migrations;
6. install/reload the native MCP, cleanup and health systemd units;
7. run cleanup, health and loopback MCP challenge checks before routing;
8. restart the existing socket-activated Django service, enable the MCP/OAuth include, reload
   Nginx and run public discovery/challenge checks.

Deployment evidence is retained under
`/srv/apps/<project>/.deploy-backups/mcp/<timestamp>/deployment.json` without credentials.

Fail-close the public surface without changing code or data:

```bash
cd .deploy
fab disable-mcp-route
```

Rollback starts by disabling the route and never reverses migrations. Restore the exact previous
commit and the environment backup recorded in deployment evidence:

```bash
cd .deploy
fab rollback-mcp --source-commit=<previous-full-sha> --env-backup=<absolute-0600-backup-path>
```

Rollback leaves MCP/OAuth routing disabled. Re-run the canonical `fab deploy` command for an exact
approved commit before enabling it again. Revoked grants, consumed codes, tokens, refresh families,
consents and applications are never reactivated.

After deployment, complete native OAuth code/refresh/revoke and required ChatGPT, Codex,
Claude/Claude Desktop and Claude Code acceptance. Do not create `mcp-v1.0.0`, mark the server
supported, or proceed to Skill Distribution until that immutable evidence and recovery smoke are
complete.
