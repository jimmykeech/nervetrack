FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app ./app

# Litestream binary (pinned). Verify the tag against the current release.
COPY --from=litestream/litestream:0.3.13 /usr/local/bin/litestream /usr/local/bin/litestream

COPY litestream.yml /etc/litestream.yml
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# SQLite file lives on a mounted volume.
ENV NERVETRACK_DB_PATH=/data/nervetrack.db
VOLUME ["/data"]

EXPOSE 8000

# Litestream supervises uvicorn (binds IPv6 :: for Fly 6PN; see git history).
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
