# MCP/OAuth direct production handoff

The environment model is `local + production`; there is no separate staging gate. These files
prepare, but do not enable, FeatureRequest MCP/OAuth 1.0. Run every reproducible repository,
PostgreSQL 17, OAuth state-machine, MCP transport and Contract-conformance check before promotion.
Production acceptance and public release sealing remain separate steps.

The same digest-pinned image runs the web, MCP, cleanup and health commands. Copy
`mcp.env.example` to a root-owned `0600` environment file, replace placeholders, and run:

```bash
python3 scripts/verify_mcp_deploy_config.py --env-file /etc/featurerequest/mcp.env
```

Do not use a mutable image tag. The environment must name
`ghcr.io/onurmatik/feature-request@sha256:<digest>`, PostgreSQL, the canonical public URLs and
`ADMIN_EMAIL`. Verify the GitHub provenance binds that digest to the intended full source commit.

Before the first direct production deployment, record without secrets:

- exact source commit, image digest and config-file digest;
- a completed database backup and its restore owner/location;
- the previous working immutable image and config digest;
- the route-disable and image rollback commands;
- health checks, alert delivery and the observation owner/window.

Keep the Nginx include absent while installing and validating the digest. Apply additive
migrations, start the digest-pinned web and MCP units, run cleanup and health, then enable the
include and reload Nginx only for the controlled production acceptance window. Do not enable the
public route if any prerequisite or pre-route health check fails.

After routing, verify discovery, the anonymous MCP challenge, read-only bootstrap, OAuth
code/refresh/revoke, required real clients, audit mapping, cleanup metrics and alert delivery.
Do not create `mcp-v1.0.0` or mark the server supported until the acceptance evidence is immutable.

Rollback is image-oriented: disable the Nginx include first, stop the MCP unit, and return the web
unit to the previous approved digest/config. Migrations in this implementation are additive; do
not reverse them as incident response. Never reactivate revoked grants, tokens, refresh families,
consents or applications. Re-run discovery, primary-client bootstrap and audit smoke after rollback.
