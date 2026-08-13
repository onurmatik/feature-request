# MCP/OAuth deployment handoff

These files prepare, but do not enable, FeatureRequest MCP/OAuth 1.0. Production remains
blocked until the PostgreSQL process-concurrency, immutable GHCR image, staging rollback,
four-client acceptance, observation-window, and immutable `mcp-v1.0.0` release gates pass.

The same digest-pinned image runs the web, MCP, cleanup, and health commands. Copy
`mcp.env.example` to a root-owned `0600` environment file, replace placeholders, and run:

```bash
python3 scripts/verify_mcp_deploy_config.py --env-file /etc/featurerequest/mcp.env
```

Do not use a mutable image tag. The environment must name
`ghcr.io/onurmatik/feature-request@sha256:<digest>`, PostgreSQL, the canonical public URLs,
and `ADMIN_EMAIL`. Nginx routing is intentionally a separate include so `/mcp`, OAuth and
well-known routes remain disabled until release approval.

Rollback is image-oriented: disable the nginx include first, stop the MCP unit, and return the
web unit to the previously approved digest. Migrations in this implementation are additive;
do not reverse them as an incident response. Never reactivate revoked grants, tokens, refresh
families, consents, or applications. If a later schema is incompatible, roll forward.

Before any production route enablement, run the manual `MCP Staging Rehearsal` workflow with the
candidate's full source commit and bare sha256 digest. It verifies GitHub provenance, starts the
digest only in an ephemeral PostgreSQL 17 environment, exercises discovery/challenge and
cleanup/health, removes the candidate processes, and attests the rehearsal evidence. It must also
prove that the existing production web runtime stayed available while MCP/OAuth remained 404.
