# FeatureRequest Frontend (Vite + React)

## Dev setup (Django + Vite proxy/HMR)

1. Run Django:
   ```bash
   .venv/bin/python manage.py runserver 127.0.0.1:8000
   ```
2. Run Vite:
   ```bash
   npm run dev
   ```
3. Open Django page: `http://127.0.0.1:8000/<owner_handle>/`

In development, Django loads `@vite/client` and `src/main.jsx` from `http://127.0.0.1:5173`, so HMR works automatically.

## Environment flags

- `FRONTEND_USE_DEV_SERVER=1` enables Django template to load assets from Vite dev server.
- `FRONTEND_DEV_SERVER_URL=http://127.0.0.1:5173` overrides Vite URL used by Django template.
- `DJANGO_DEV_ORIGIN=http://127.0.0.1:8000` (optional) changes Vite proxy target.

## Build

```bash
npm run build
```

Build output is written into `projects/static/frontend` for Django static serving.
