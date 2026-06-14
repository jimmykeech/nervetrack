#!/bin/sh
set -e

# Rebuild the DB from Tigris if the volume has none (fresh/host-replaced machine).
litestream restore -if-db-not-exists -config /etc/litestream.yml /data/nervetrack.db

# Run the app under Litestream so the WAL streams to Tigris continuously.
exec litestream replicate -config /etc/litestream.yml \
  -exec "uvicorn app.main:app --host :: --port 8000"
