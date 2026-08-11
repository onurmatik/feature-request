# FeatureRequest

FeatureRequest helps indie builders manage feedback for all their projects in one place. Receive feature requests and bug reports for multiple projects, let your users contact you directly, and connect with other indie founders to share ideas, learn from each other, and keep shipping faster.

## Tech Stack

- Backend: Django, Django Ninja
- Frontend: Django templates, Tailwind CSS, vanilla JavaScript
- Auth/Utilities: django-sesame, python-slugify
- Package manager: `pip` for Python; Node is only needed when regenerating Tailwind CSS

## Prerequisites

- Python 3
- Node.js (optional, for rebuilding Tailwind CSS)
- Optional: a virtual environment tool (`venv`, `virtualenv`, etc.)

## Backend Setup

1. Create and activate a virtual environment.
2. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Apply migrations:

   ```bash
   python manage.py migrate
   ```

4. Run the Django server:

   ```bash
   python manage.py runserver 127.0.0.1:8000
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
- `FEATURE_REQUEST_MCP_SERVER_URL` (defaults to `http://127.0.0.1:8001/mcp`)
- `FEATURE_REQUEST_MCP_AUTH_ISSUER_URL` (defaults to `http://127.0.0.1:8000`)
- `FEATURE_REQUEST_MCP_API_TIMEOUT_SECONDS` (defaults to `20`)
- `EMAIL_BACKEND`
- `ADMIN_EMAIL`
- `STATIC_URL`, `STATIC_ROOT`
- `CSRF_TRUSTED_ORIGINS`

## Useful Commands

- Django admin shell:

  ```bash
  python manage.py shell
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
  python3 manage.py collectstatic
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

FeatureRequest includes a Python MCPServer exposing the P1 request operating workflow over
Streamable HTTP. It uses the existing `fr_...` bearer tokens and preserves their
current `can_write` behavior; it does not define a separate MCP permission model.

The MCP server supplies deterministic queue signals, explainable duplicate candidates,
activity events, and delivery evidence records. It does not make semantic priority or
duplicate decisions for the calling agent, and a stored delivery URL is not verification.
The activity/change feed starts recording with the P1 migration; it does not reconstruct
historical events for existing requests.

Run Django and the MCP server as separate local processes:

```bash
python manage.py runserver 127.0.0.1:8000
python -m feature_request_mcp
```

The MCP endpoint is then available at:

```text
http://127.0.0.1:8001/mcp
```

Alternatively, run the ASGI application directly:

```bash
uvicorn feature_request_mcp.asgi:application --host 127.0.0.1 --port 8001
```

Every MCP request must include:

```text
Authorization: Bearer <FeatureRequest API token>
```

The repository is a dual-format agent plugin:

- Agent Plugins 1.0.0 portable package: `plugin.json`, `mcp.json`, and
  `skills/feature-request/SKILL.md`.
- Codex-native companion package: `.codex-plugin/plugin.json` and `.mcp.json`.

The portable `mcp.json` uses the Agent Plugins 1.0.0 `streamable-http` transport and
leaves authentication to the MCP client, as required by the portable specification.
The Codex-native `.mcp.json` connects to the same local server and reads the bearer
token from `FEATURE_REQUEST_API_TOKEN`:

```bash
export FEATURE_REQUEST_API_TOKEN=fr_your_existing_token
```

For plugin development, run the two processes above before connecting. Clients using
the portable package must be configured to send the same bearer token. Before a
production plugin release, change both MCP configuration URLs, set
`FEATURE_REQUEST_MCP_SERVER_URL=https://featurerequest.io/mcp`, and expose that
Streamable HTTP route over HTTPS.

P1 project tools:

- `list_projects`
- `get_project`
- `create_project`
- `update_project`
- `delete_project` (destructive; requires `get_project`, explicit user direction, and a matching confirmation id)

P1 request and evidence tools:

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
