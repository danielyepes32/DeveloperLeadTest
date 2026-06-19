# syntax=docker/dockerfile:1
# Fast, reproducible builds with uv. The dependency layer is cached and only
# rebuilds when pyproject.toml / uv.lock change, so iterating on app code is fast.

# ---- builder: resolve & install locked deps into /app/.venv ----------------
FROM python:3.12-slim AS builder

# Bring the uv binary in from the official image (no install step needed).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Only the lockfiles are needed to build the venv -> this layer is cached until
# dependencies change. The uv cache is a BuildKit cache mount (persists across builds).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-install-project

# ---- runtime: slim, non-root, healthchecked --------------------------------
FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# The venv is built against /usr/local/bin/python3.12, identical in both stages,
# so it is portable between them.
COPY --from=builder /app/.venv /app/.venv
COPY app ./app

RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
