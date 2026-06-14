#!/bin/sh
set -e

# Rebuild the DB from Tigris if the volume has none (fresh/host-replaced machine).
# -if-db-not-exists: skip when the DB is already on the volume.
# -if-replica-exists: on the very first deploy the bucket is empty — exit 0 (no-op)
# instead of erroring, so `set -e` doesn't crash-loop before replicate seeds it.
litestream restore -if-db-not-exists -if-replica-exists -config /etc/litestream.yml /data/nervetrack.db

# Run the app under Litestream so the WAL streams to Tigris continuously.
exec litestream replicate -config /etc/litestream.yml \
  -exec "uvicorn app.main:app --host :: --port 8000"
