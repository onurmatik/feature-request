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
  data-fr-label="Feedback"
  data-fr-position="right"
  data-fr-color="#06B6D4"
  defer
></script>
```

The widget accepts `left` or `right` placement and a six-digit hex accent color. It never
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
- `POST /api/projects/{owner_handle}/{project_slug}/issues`
- `GET /api/issues/{issue_id}`
- `PATCH /api/issues/{issue_id}`
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
