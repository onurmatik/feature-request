
cd .deploy/
fab deploy --source-commit=<full-origin-main-sha>

# Deploy will upload ../.env-prod (preferred) or ../.env to /srv/apps/{PROJECT_NAME}/.env

# Files
- `.credentials.env`: GitHub App credentials used by `scripts/get_github_app_token.py`
- `deploy.env`: per-project deploy config (PROJECT_NAME, GITHUB_APP_REPO, DEPLOY_HOST, DOMAIN, etc.)

# Tip
Copy `.deploy` between projects and only edit `deploy.env` to point at the new repo/host/domain.

# MCP/OAuth production controls
- `fab disable-mcp-route` fail-closes the public MCP/OAuth surface and stops MCP.
- `fab rollback-mcp --source-commit=<sha> --env-backup=<path>` restores exact native source/config
  while leaving the public surface disabled.
- The canonical deploy takes a verified pgBackRest backup before changing source or configuration.
