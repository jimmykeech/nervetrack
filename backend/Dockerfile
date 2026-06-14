FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app ./app

# DuckDB file lives on a mounted volume.
ENV NERVETRACK_DB_PATH=/data/nervetrack.duckdb
VOLUME ["/data"]

EXPOSE 8000

# Bind IPv6 (::), not 0.0.0.0. Fly's private network (<app>.internal, used by the
# frontend to reach this service) is IPv6-only; a 0.0.0.0 bind is IPv4-only and
# silently unreachable over 6PN. On Linux `::` is dual-stack, so IPv4 health
# checks and the local docker-compose IPv4 path keep working too.
CMD ["uvicorn", "app.main:app", "--host", "::", "--port", "8000"]
