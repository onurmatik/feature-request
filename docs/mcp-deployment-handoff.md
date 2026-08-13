# FeatureRequest MCP deployment handoff

This is a runtime-requirements document, not a deployment contract. Agentic
implementation and distribution must not create or edit Fabric/fabfiles,
deployment workflows, Docker/OCI files, systemd units, reverse-proxy config,
environment/secrets wiring, migration order, backups, schedulers, health checks
or rollback procedures.

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

Production activation is a separate explicit deployment task. After that task,
verify unauthenticated `/mcp` discovery, OAuth code/refresh/revoke, client-native
`tools/list`, the read-only bootstrap tool and credential-safe audit output.
