# FeatureRequest MCP deployment handoff

StageOps `app.yaml` owns the FeatureRequest MCP process, exact `/mcp` nginx
routing, OAuth-safe access logging, bounded cleanup and cleanup-health timers.
The native `.deploy` task only restarts and verifies those units after the app
release; it does not create infrastructure or introduce Docker/OCI, database
backups, migration-order changes or rollback infrastructure.

## Runtime requirements

- MCP entrypoint: `python -m feature_request_mcp`
- Default loopback bind: `127.0.0.1:8001`
- Canonical issuer: `https://featurerequest.io`
- Canonical resource: `https://featurerequest.io/mcp`
- Database: the configured Django PostgreSQL database
- Environment keys: see `config/settings.py` and `.env.example`

The Django application owns OAuth, metadata and consent routes. Checked-in
migrations and these management commands are application artifacts:

```bash
python manage.py migrate
python manage.py cleanup_mcp_oauth
python manage.py check_mcp_oauth_health
```

Every deployment restarts the StageOps-owned MCP process and verifies the
unauthenticated `/mcp` Bearer challenge. Release acceptance additionally verifies
OAuth code/refresh/revoke, client-native `tools/list`, the read-only bootstrap
tool and credential-safe audit output.
