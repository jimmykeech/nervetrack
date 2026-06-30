# Deploying NerveTrack

NerveTrack ships as two container images on GHCR:
`ghcr.io/<owner>/nervetrack-backend` and `…/nervetrack-frontend`. The frontend is
the only public service; it proxies `/api/*` to the private backend, which owns a
single SQLite file on a volume.

## Run anywhere with Docker

```bash
cp .env.example .env        # defaults run offline, single-user
docker compose up           # build locally
# or, from published images:
IMAGE_OWNER=<owner> docker compose -f docker-compose.yml -f docker-compose.images.yml up
```

Open http://localhost:3000.

## Choosing an auth mode

- `NERVETRACK_AUTH_MODE=none` — no login, one local user. Best for a private,
  single-person local/LAN install.
- `NERVETRACK_AUTH_MODE=password` — local email+password accounts. Set
  `NERVETRACK_ALLOW_REGISTRATION=false` after creating your accounts to lock it.
- `NERVETRACK_AUTH_MODE=google` — invite-only Google sign-in (needs internet).

### Google OAuth setup (google mode)

1. Google Cloud Console → APIs & Services → Credentials → create an OAuth 2.0
   Client ID (Web application).
2. Authorized redirect URI: `https://<your-domain>/api/v1/auth/google/callback`.
3. Set `NERVETRACK_GOOGLE_CLIENT_ID`, `NERVETRACK_GOOGLE_CLIENT_SECRET`,
   `NERVETRACK_ALLOWED_EMAILS` (comma-separated invite list),
   `NERVETRACK_OAUTH_REDIRECT_URI`, `NERVETRACK_FRONTEND_URL`,
   `NERVETRACK_CORS_ORIGINS`, and `NERVETRACK_COOKIE_SECURE=true` (https).

## Durable backup (optional, recommended for cloud)

The backend streams the SQLite WAL to any S3-compatible bucket via Litestream
when these are present: `BUCKET_NAME`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION`. Unset, the backend
just runs the local file (no backup). On a fresh machine the DB is restored from
the bucket automatically.

## Deploying to Fly.io (worked example)

Templates live in `deploy/fly/`. Copy them, fill in your app names, region, and
domain, then:

```bash
flyctl deploy --config backend/fly.toml --image ghcr.io/<owner>/nervetrack-backend:vX.Y.Z
flyctl deploy --config frontend/fly.toml --image ghcr.io/<owner>/nervetrack-frontend:vX.Y.Z
flyctl secrets set NERVETRACK_GOOGLE_CLIENT_SECRET=... NERVETRACK_ALLOWED_EMAILS=...
```

Run exactly one backend machine (SQLite is single-writer).

## Keeping your deployment in a private repo

Recommended split: keep this public repo generic, and hold your real
`fly.toml`s + secrets in a **private** `nervetrack-deploy` repo that pins a
published image tag. The data lives entirely in Fly resources (the volume and the
backup bucket), not in any repo, so changing which repo drives the deploy never
touches your data.

### Migrating an existing Fly deployment into a private repo (no data loss)

Your data is in two Fly-side places — the volume `nervetrack_data` and (if
enabled) the Litestream backup bucket — both independent of any git repo. App
**secrets stay on the app**, not in the repo. So the migration only repoints the
*deploy trigger*; it never moves data.

1. **Back up first.** Snapshot the volume and pull a copy of the live DB:
   ```bash
   fly volumes list -a <backend-app>            # note the volume id
   fly volumes snapshots create <volume-id>
   fly ssh console -a <backend-app> -C "sqlite3 /data/nervetrack.db '.backup /data/backup.db'"
   fly ssh sftp get /data/backup.db ./nervetrack-backup.db -a <backend-app>
   ```
2. **Confirm app-side resources exist** (don't recreate any):
   `fly apps list`, `fly secrets list -a <backend-app>`, `fly volumes list -a <backend-app>`.
3. **Create the private `nervetrack-deploy` repo.** Copy `deploy/fly/*.example`
   to `backend/fly.toml` / `frontend/fly.toml`. Keep `app = "<existing-app-name>"`
   **exactly** — that targets the existing app + volume rather than creating new
   ones. Add `FLY_API_TOKEN` as a repo secret.
4. **Deploy from the new repo to the same apps:**
   ```bash
   fly deploy -a <backend-app>  --image ghcr.io/<owner>/nervetrack-backend:vX.Y.Z
   fly deploy -a <frontend-app> --image ghcr.io/<owner>/nervetrack-frontend:vX.Y.Z
   ```
5. **Verify** the live site loads and your data is intact before retiring the old
   path.
6. **Decommission the old deploy path:** remove any deploy workflow and
   `FLY_API_TOKEN` from the public repo.

**Never** run `fly launch` or `fly volumes create` in the new repo (that makes a
fresh empty app/volume), and never `fly apps destroy` the existing apps (that
deletes the volume with them). Always `fly deploy -a <existing-app>`.
