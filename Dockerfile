# Single-stage image. There is no build step to separate out: the backend is
# pure Python, and a multi-stage build here would add complexity for no size
# saving worth having.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# Dependencies are installed from pyproject alone, before the source is
# copied, so that editing application code does not invalidate the layer that
# downloads packages.
COPY pyproject.toml ./
COPY backend/app/__init__.py backend/app/__init__.py
RUN pip install --no-cache-dir ".[dev,postgres,analytics]"

COPY alembic.ini ./
COPY backend/ backend/
COPY sql/ sql/

# The SQLite file and Parquet exports live on mounted volumes, not in the
# image. Created here so the container starts cleanly on a fresh checkout.
RUN mkdir -p /app/data /app/exports

EXPOSE 8000

# Migrations and seeding run on start rather than in the image build: the
# database lives on a volume that does not exist at build time.
#
# `upgrade head` is a no-op when the schema is current, and `seed ensure` does
# nothing when the taxonomy is already loaded — so both are safe on every
# restart. Without the seed step a fresh `docker compose up` serves an empty
# taxonomy, which looks like a broken application rather than an unseeded one.
CMD ["sh", "-c", "python -m alembic upgrade head \
  && python -m app.cli seed ensure \
  && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
