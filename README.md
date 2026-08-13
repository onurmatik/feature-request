# FeatureRequest

FeatureRequest helps indie builders manage feedback for all their projects in one place. Receive feature requests and bug reports for multiple projects, let your users contact you directly, and connect with other indie founders to share ideas, learn from each other, and keep shipping faster.

## Tech Stack

- Backend: Django, Django Ninja
- Frontend: Django templates, Tailwind CSS, vanilla JavaScript
- Auth/Utilities: django-sesame, django-oauth-toolkit, repo-internal django-embedded-mcp
- Package manager: `uv` with the frozen `uv.lock`; Node is only needed when regenerating Tailwind CSS

## Prerequisites

- Python 3.11
- `uv` 0.9.26
- Node.js (optional, for rebuilding Tailwind CSS)
- Optional: a virtual environment tool (`venv`, `virtualenv`, etc.)

## Backend Setup

1. Install the frozen Python dependency graph:

   ```bash
   uv sync --frozen --reinstall-package django-embedded-mcp
   ```

2. Apply migrations:

   ```bash
   uv run python manage.py migrate
   ```

3. Run the Django server:

   ```bash
   uv run python manage.py runserver 127.0.0.1:8000
   ```

## Frontend Setup

The frontend is served by Django from `projects/templates/projects/app.html` and
`projects/static/projects/`. No separate frontend dev server is required.

Open the app at:

```text
http://127.0.0.1:8000/<owner_handle>/
```

## Embed Widget

Project owners can generate a non-persisted widget snippet from **Project Settings →
Embed Widget**. The loader is isolated from host-page CSS with Shadow DOM and opens the
FeatureRequest form in a same-service iframe. Replace the owner and project values in this
example, or copy the generated snippet from settings:

```html
<script
  src="https://featurerequest.io/static/projects/embed-widget.js"
  data-fr-origin="https://featurerequest.io"
  data-fr-owner="owner_handle"
  data-fr-project="project-slug"
  data-fr-position="right"
  data-fr-color="#06B6D4"
  defer
></script>
```

The widget uses an icon-only conversation-bubble launcher and accepts `left` or `right`
placement plus a six-digit hex accent color. It never
receives an API token and only submits to the FeatureRequest origin. A request remains
pending until the visitor opens the email link and confirms publication with the CSRF-
protected **Publish request** form. Published widget requests use server-assigned Medium
priority.

For a host site with a strict Content Security Policy, add the FeatureRequest/static origin
to `script-src` and `style-src`, and the FeatureRequest application origin to `frame-src`.
For the example above, the minimum additions are:

```text
script-src https://featurerequest.io
style-src https://featurerequest.io
frame-src https://featurerequest.io
```

Set both `TURNSTILE_SITEKEY` and `TURNSTILE_SECRETKEY`. The Turnstile widget hostname must
match the FeatureRequest deployment hostname because the challenge runs inside the iframe.
Every submission is validated server-side against Cloudflare Siteverify with the
`embed_submission` action before moderation or email delivery.

Public widget routes:

- `GET /embed/{owner_handle}/{project_slug}/`
- `POST /api/embed/projects/{owner_handle}/{project_slug}/submissions`
- `GET|POST /embed/submissions/{token}/verify/`
- `/static/projects/embed-widget.js`

## Environment Notes

- `ADMIN_URL` configures the Django admin route (defaults to `/admin/`).

## Environment Configuration

Create a `.env` file at the repository root (or set environment variables) for local runs:

- `DJANGO_SECRET_KEY`
- `DEBUG` (defaults to `True` in dev examples)
- `ALLOWED_HOSTS`
- `ADMIN_URL` (default `/admin/`)
- `OPENAI_API_KEY`
- `STRIPE_PUBLIC_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_PRICE_ID_30`
- `STRIPE_WEBHOOK_SECRET`
- `TURNSTILE_SITEKEY`
- `TURNSTILE_SECRETKEY`
- `SITEHITS_BOT_KEY` (server-side bot-event collector key)
- `FEATURE_REQUEST_API_BASE_URL` (defaults to `http://127.0.0.1:8000/api`)
- `FEATURE_REQUEST_MCP_HOST` (defaults to `127.0.0.1`)
- `FEATURE_REQUEST_MCP_PORT` (defaults to `8001`)
- `PUBLIC_BASE_URL` (canonical browser/OAuth origin; local default `http://127.0.0.1:8000`)
- `OAUTH_ISSUER` (must exactly equal `PUBLIC_BASE_URL`)
- `MCP_RESOURCE_URL` (local default `http://127.0.0.1:8001/mcp`)
- `MCP_RESOURCE_METADATA_URL`
- `FEATURE_REQUEST_MCP_CORS_ORIGINS` (comma-separated exact origins)
- `FEATURE_REQUEST_TRUSTED_PROXY_IPS` (comma-separated exact proxy addresses)
- `FEATURE_REQUEST_MCP_PRODUCTION_ENABLED` (fails closed on SQLite)
- `DATABASE_URL` (optional locally; production MCP requires PostgreSQL)
- `EMAIL_BACKEND`
- `ADMIN_EMAIL`
- `STATIC_URL`, `STATIC_ROOT`
- `CSRF_TRUSTED_ORIGINS`

## Useful Commands

- Django admin shell:

  ```bash
  uv run python manage.py shell
  ```

- Rebuild Tailwind CSS after editing template/static frontend classes:

  ```bash
  npx --yes tailwindcss@3.4.17 -c tailwind.config.js \
    -i projects/static/projects/app.tailwind.css \
    -o projects/static/projects/app.css \
    --minify
  ```

- Collect static files for deployment:

  ```bash
  uv run python manage.py collectstatic
  ```

## API Access

The API is available under `/api` and auto-docs are exposed at:

- `http://127.0.0.1:8000/api/docs`

Auth/session endpoints remain outside `/api`:

- `POST /auth/sign-in`
- `POST /auth/sign-up`
- `POST /auth/logout`
- `GET /auth/me`

### API authentication

- Session-authenticated users can call API endpoints from the web app after sign in.
- Bearer token authentication is also supported for `/api/*`.
  - Header format:
    - `Authorization: Bearer <TOKEN>`
  - Create/manage tokens via:
    - `GET /api/auth/tokens`
    - `POST /api/auth/tokens`
    - `DELETE /api/auth/tokens/{token_id}`
  - POST body for creating a token:
    - `{"name": "Agent token", "can_write": true}`
  - Response includes full token once on creation (`fr_...` format). The UI stores only a preview `token_prefix` for list responses.
  - Read-only tokens (`can_write: false`) receive `403` on write methods (`POST`, `PUT`, `PATCH`, `DELETE`).

### Common routes

Project responses include `open_issues_count`, which counts issues with status `open`.

- `GET /api/health`
- `GET /api/public/featured-projects?limit=3`
- `GET /api/owners/{owner_handle}/projects`
- `GET /api/owners/{owner_handle}/interacted-projects`
- `GET /api/owners/{owner_handle}/issues`
- `GET /api/projects/{owner_handle}/{project_slug}/issues`
- `GET /api/projects/{owner_handle}/{project_slug}/duplicate-candidates`
- `POST /api/projects/{owner_handle}/{project_slug}/issues`
- `GET /api/issues/{issue_id}`
- `PATCH /api/issues/{issue_id}`
- `GET /api/issues/{issue_id}/activity`
- `PATCH|DELETE /api/issues/{issue_id}/duplicate`
- `GET|POST /api/issues/{issue_id}/delivery-artifacts`
- `DELETE /api/issues/{issue_id}/delivery-artifacts/{artifact_id}`
- `GET /api/me/request-queue`
- `GET /api/me/issue-changes`
- `POST /api/issues/{issue_id}/upvote/toggle`
- `GET /api/issues/{issue_id}/comments`
- `POST /api/issues/{issue_id}/comments`
- `PATCH /api/issues/{issue_id}/comments/{comment_id}`
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{project_id}`
- `PATCH /api/projects/{project_id}`
- `DELETE /api/projects/{project_id}`
- `GET /api/billing/plans`
- `POST /api/billing/checkout`
- `POST /api/owners/{owner_handle}/messages`
- `GET /api/me/messages`

## MCP Server

FeatureRequest includes an explicit Python `MCPServer[None]` exposing the Agent Contract 1.0.0
request operating workflow over stateless Streamable HTTP. It implements modern MCP 2026-07-28
`server/discover`, per-request protocol headers, and a deterministic 23-tool registry. FastMCP,
loopback HTTP API forwarding, and legacy initialize transport are not used.

`/mcp` is protected by OAuth 2.1 Authorization Code + PKCE S256. Client ID Metadata Documents
(CIMD) are preferred; controlled public-client Dynamic Client Registration (DCR) remains as a
fallback. The initial challenge requests only `read`; mutation tools return an OAuth `write`
step-up challenge. Existing `fr_...` API tokens continue to work under `/api` and are explicitly
rejected by `/mcp`.

The MCP server supplies deterministic queue signals, explainable duplicate candidates,
activity events, and delivery evidence records. It does not make semantic priority or
duplicate decisions for the calling agent, and a stored delivery URL is not verification.
The activity/change feed starts recording with the P1 migration; it does not reconstruct
historical events for existing requests.

Run Django and the MCP server as separate local processes from the same frozen environment:

```bash
uv run python manage.py migrate
uv run python manage.py runserver 127.0.0.1:8000
uv run python -m feature_request_mcp
```

The MCP endpoint is then available at:

```text
http://127.0.0.1:8001/mcp
```

Alternatively, run the ASGI application directly:

```bash
uv run uvicorn feature_request_mcp.asgi:application --host 127.0.0.1 --port 8001
```

OAuth discovery is published at:

- `/.well-known/oauth-protected-resource/mcp`
- `/.well-known/oauth-authorization-server`
- `/.well-known/openid-configuration`

Authorization, token, revocation and public-client registration use `/oauth/authorize`,
`/oauth/token`, `/oauth/revoke`, and `/oauth/register`. Tokens, authorization codes,
refresh-family members, idempotency keys, and client identities in audit data are stored only as
digests or stable redacted identifiers.

The repository is a dual-format agent plugin:

- Agent Plugins 1.0.0 portable package: `plugin.json`, `mcp.json`, and
  `skills/feature-request/SKILL.md`.
- Codex-native companion package: `.codex-plugin/plugin.json` and `.mcp.json`.

Both `mcp.json` and `.mcp.json` contain the local Streamable HTTP URL and no static credential
reference. A compatible client discovers OAuth from the server challenge and metadata. Before a
production plugin release, change both URLs to `https://featurerequest.io/mcp` only after the
immutable MCP release and required real-client acceptance gates pass.

Repository validation commands:

```bash
uv run python scripts/agent_contract.py validate
uv run python scripts/agent_contract.py mapping --check
uv run python scripts/mcp_release.py validate
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py test
```

The MCP release builder intentionally refuses to create a production descriptor while ChatGPT,
Codex, Claude remote/Desktop, or Claude Code evidence remains pending. Deployment templates,
SQLite production guard, rollback contract, cleanup/health timers, and the disabled nginx include
live under `deploy/mcp/`. This implementation task does not enable the production route.

Bootstrap tool:

- `get_account_capabilities` (bootstrap; capability catalog and project-count limit)

Project tools:

- `list_projects`
- `get_project`
- `create_project`
- `update_project`
- `delete_project` (destructive; requires `get_project`, explicit user direction, and a matching confirmation id)

Request and evidence tools:

- `list_requests`
- `get_request`
- `list_request_comments`
- `get_queue_snapshot`
- `find_duplicate_candidates`
- `list_request_activity`
- `list_request_changes`
- `list_delivery_artifacts`
- `create_request`
- `update_request`
- `transition_request`
- `add_request_comment`
- `update_request_comment`
- `link_duplicate_request`
- `unlink_duplicate_request`
- `link_delivery_artifact`
- `unlink_delivery_artifact`

Token create/revoke, billing/checkout, bulk close, and bulk mutation are intentionally not
exposed as MCP tools.

### Quick curl examples

```bash
BASE_URL=http://127.0.0.1:8000
TOKEN=YOUR_TOKEN

curl -H "Authorization: Bearer ${TOKEN}" "${BASE_URL}/api/projects"
curl -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name":"My Product Board","tagline":"Roadmap","url":"https://example.com"}' \
  "${BASE_URL}/api/projects"
curl -X POST -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"title":"Add webhook support","issue_type":"feature","priority":2}' \
  "${BASE_URL}/api/projects/<owner_handle>/<project_slug>/issues"
```
