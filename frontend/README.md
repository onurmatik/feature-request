# FeatureRequest Frontend (Vite + React)

## Dev setup (Django API + Vite frontend)

1. Run Django:
   ```bash
   .venv/bin/python manage.py runserver 127.0.0.1:8000
   ```
2. Run Vite:
   ```bash
   npm run dev
   ```
3. Open Vite app: `http://127.0.0.1:5173/<owner_handle>/`

## Environment flags

- `DJANGO_DEV_ORIGIN=http://127.0.0.1:8000` (optional) changes Vite proxy target.
- `ADMIN_URL=/admin/` (optional) changes the proxied Django admin route.

## Build

```bash
npm run build
```

Build output is written into `frontend/dist`.
