# FeatureRequest

FeatureRequest helps indie builders manage feedback for all their projects in one place. Receive feature requests and bug reports for multiple projects, let your users contact you directly, and connect with other indie founders to share ideas, learn from each other, and keep shipping faster.

## Tech Stack

- Backend: Django, Django Ninja
- Frontend: React 19, Vite, Tailwind CSS
- Auth/Utilities: django-sesame, python-slugify
- Package manager: `pip` for Python, `npm` for frontend

## Prerequisites

- Python 3
- Node.js (for the Vite frontend)
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

1. Install frontend dependencies:

   ```bash
   cd frontend
   npm install
   ```

2. Start Vite dev server:

   ```bash
   npm run dev
   ```

3. Open the app at:

   ```text
   http://127.0.0.1:5173/<owner_handle>/
   ```

## Environment Notes

- `frontend/` provides additional frontend-specific setup notes and build guidance.
- `DJANGO_DEV_ORIGIN` can be used to point Vite at a different Django host, e.g.:

  ```bash
  export DJANGO_DEV_ORIGIN=http://127.0.0.1:8000
  ```
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

- Build frontend for production:

  ```bash
  cd frontend
  npm run build
  ```

- Start production preview (after build):

  ```bash
  cd frontend
  npm run preview
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
