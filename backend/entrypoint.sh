#!/bin/sh
set -e

DB_PATH="${NERVETRACK_DB_PATH:-/data/nervetrack.db}"
SERVE="uvicorn app.main:app --host :: --port 8000"

# Litestream is opt-in: enabled only when an S3 bucket is configured (BUCKET_NAME
# + credentials, as injected by `fly storage create`). Without it the image runs
# uvicorn directly, so it works fully offline / for local self-hosting.
if [ -n "${BUCKET_NAME:-}" ] && [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
  # Rebuild the DB from the bucket if the volume has none (fresh machine).
  # -if-replica-exists: on the very first deploy the bucket is empty — exit 0
  # (no-op) instead of erroring under `set -e` before replicate seeds it.
  litestream restore -if-db-not-exists -if-replica-exists -config /etc/litestream.yml "$DB_PATH"
  # Run the app under Litestream so the WAL streams to the bucket continuously.
  exec litestream replicate -config /etc/litestream.yml -exec "$SERVE"
fi

exec $SERVE
