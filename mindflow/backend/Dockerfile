# syntax=docker/dockerfile:1.7
# Multi-stage: the runtime image carries no build toolchain and no uv.
# Non-root, read-only-friendly, no shell tools beyond what the app needs.

FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies are copied and installed before the source so a code change does
# not invalidate the dependency layer.
COPY pyproject.toml uv.lock* README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev 2>/dev/null || \
    uv sync --no-install-project --no-dev

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-editable 2>/dev/null || uv sync --no-dev


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# ffmpeg is required by the self-hosted Whisper path to decode container formats.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1001 mindflow \
    && useradd --uid 1001 --gid 1001 --no-create-home --shell /usr/sbin/nologin mindflow

WORKDIR /app

COPY --from=builder --chown=1001:1001 /app/.venv /app/.venv
COPY --chown=1001:1001 app ./app
COPY --chown=1001:1001 migrations ./migrations
COPY --chown=1001:1001 alembic.ini ./

# Writable object root for the local storage adapter (dev only).
RUN mkdir -p /var/lib/mindflow/objects && chown -R 1001:1001 /var/lib/mindflow

USER 1001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
