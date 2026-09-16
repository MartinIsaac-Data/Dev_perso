# Image unique pour l'API et les workers : le même artefact tourne partout,
# seule la commande change.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS builder
RUN pip install --no-cache-dir hatchling
COPY pyproject.toml README.md ./
COPY spp ./spp
RUN pip install --no-cache-dir --prefix=/install .

FROM base AS runtime
RUN useradd --create-home --uid 10001 spp
COPY --from=builder /install /usr/local
COPY spp ./spp
COPY sql ./sql
USER spp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/v1/health')"
CMD ["uvicorn", "spp.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
