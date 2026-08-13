# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.9.26 AS uv

FROM python:3.11.13-slim-bookworm AS builder
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
COPY packages/django-embedded-mcp ./packages/django-embedded-mcp
RUN uv sync --frozen --no-dev --no-install-project --reinstall-package django-embedded-mcp

FROM python:3.11.13-slim-bookworm AS runtime
RUN addgroup --system feature-request \
    && adduser --system --ingroup feature-request --home /app feature-request
WORKDIR /app
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=builder --chown=feature-request:feature-request /app/.venv /app/.venv
COPY --chown=feature-request:feature-request . /app
USER feature-request
EXPOSE 8000 8001
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--access-logformat", "%(p)s %(h)s %(m)s %(U)s %(H)s %(s)s %(L)s"]
