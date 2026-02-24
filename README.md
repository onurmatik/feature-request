# FeatureRequest

FeatureRequest is a monorepo-style web application with a Django backend API and a Vite + React frontend.

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
