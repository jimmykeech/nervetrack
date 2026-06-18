# Deploying NerveTrack to Fly.io

Two Fly apps:

| App | Visibility | Notes |
|-----|-----------|-------|
| `nervetrack-backend` | **Private** (6PN only) | FastAPI + SQLite (WAL), replicated to a Tigris bucket via Litestream. One always-on machine + one volume. Never scale past 1. |
| `nervetrack-frontend` | **Public** (`nervetrack.jameskeech.io`) | SvelteKit. Stateless, scales to zero, proxies `/api/*` to the backend. |

The browser only ever talks to the frontend; it proxies `/api` to
`http://nervetrack-backend.internal:8000` over Fly's private network
(`frontend/src/hooks.server.ts`). The backend is never exposed to the internet.

**Data durability** is handled by [Litestream](https://litestream.io): the backend
runs `litestream replicate -exec "uvicorn …"` (see `backend/entrypoint.sh`), which
streams the SQLite WAL to a Tigris S3 bucket continuously. On a fresh or
host-replaced machine the entrypoint first runs `litestream restore` to rebuild the
DB from the bucket before the app starts. The Fly volume holds the live database;
Tigris holds the off-box replica.

---

## 0. Prerequisites (once)

```bash
brew install flyctl          # or: curl -L https://fly.io/install.sh | sh
fly auth login
```

The public site is served at **https://nervetrack.jameskeech.io** (custom domain,
configured in step 7). The Fly app names are internal plumbing — if
`nervetrack-backend` / `nervetrack-frontend` are taken globally, pick new names and
update them in **both** `fly.toml` files and the `BACKEND_URL`
(`<backend-name>.internal`); the public domain is unaffected.

---

## 1. Create the apps (once, no deploy yet)

```bash
fly apps create nervetrack-backend
fly apps create nervetrack-frontend
```

## 2. Create the backend data volume (once)

The live SQLite database lives here. One volume, one region, matched to the
backend's machine.

```bash
fly volumes create nervetrack_data --app nervetrack-backend --region syd --size 1
```

> A `--size 1` (1 GB) volume is plenty for this dataset; grow later with
> `fly volumes extend`. Fly takes **automatic daily snapshots (5-day retention)** —
> see Backups below.

## 3. Create the Tigris bucket for Litestream (once)

Litestream replicates the SQLite WAL to a Tigris (S3-compatible) bucket. Fly's Tigris
integration provisions a bucket and **injects the credentials as secrets on the
backend app automatically**:

```bash
fly storage create --app nervetrack-backend
```

This sets `BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_ENDPOINT_URL_S3`, and `AWS_REGION` — exactly the variables
`backend/litestream.yml` expands. You don't set these by hand; confirm them with
`fly secrets list --app nervetrack-backend` after running the command.

> On the very first deploy the bucket is empty. `entrypoint.sh` uses
> `litestream restore -if-db-not-exists -if-replica-exists`, so a missing replica is
> a no-op (exit 0) rather than an error — `replicate` then seeds the bucket from the
> fresh DB.

## 4. Set secrets

These are encrypted and injected at runtime — never put them in `fly.toml`.

```bash
fly secrets set --app nervetrack-backend \
  NERVETRACK_GOOGLE_CLIENT_ID="<google-web-client-id>" \
  NERVETRACK_GOOGLE_CLIENT_SECRET="<google-web-client-secret>" \
  NERVETRACK_ALLOWED_EMAILS="james.a.keech@gmail.com,other@example.com"

# Phase 2 (in-app Claude chat) — add when you get there:
# fly secrets set --app nervetrack-backend NERVETRACK_ANTHROPIC_API_KEY="sk-ant-..."
```

Non-secret config (DB path, timezone, cookie/HTTPS, public URLs, CORS) is already
in `backend/fly.toml` under `[env]`. The Litestream/Tigris credentials from step 3
are already set as secrets — don't duplicate them here.

## 5. Configure Google OAuth

In Google Cloud Console → Credentials → your Web OAuth client, add the **authorized
redirect URI**:

```
https://nervetrack.jameskeech.io/api/v1/auth/google/callback
```

This must exactly match `NERVETRACK_OAUTH_REDIRECT_URI` in `backend/fly.toml`.

## 6. First deploy (manual, to verify)

Backend first (it owns the DB), then frontend:

```bash
cd backend  && fly deploy && cd ..
cd frontend && fly deploy && cd ..
```

Before DNS is set up you can smoke-test on the temporary
`https://nervetrack-frontend.fly.dev` address, but **sign-in will only work once
the custom domain in step 7 is live** (the OAuth redirect points at it).

## 7. Point nervetrack.jameskeech.io at the frontend

`nervetrack` is a subdomain, so a CNAME is the simplest mapping.

1. **DNS** — at your `jameskeech.io` DNS provider, add:

   | Type | Name | Value |
   |------|------|-------|
   | CNAME | `nervetrack` | `nervetrack-frontend.fly.dev` |

2. **Issue the TLS certificate** (Fly handles Let's Encrypt automatically):

   ```bash
   fly certs add nervetrack.jameskeech.io --app nervetrack-frontend
   fly certs show nervetrack.jameskeech.io --app nervetrack-frontend   # watch until "Status: Ready"
   ```

   Once the cert shows **Ready**, `https://nervetrack.jameskeech.io` is live with
   auto-renewing HTTPS. The `force_https` in `frontend/fly.toml` upgrades any
   http:// hit to https://.

> If you later move to the **apex** `jameskeech.io` (no subdomain), CNAMEs aren't
> allowed there — allocate dedicated IPs (`fly ips allocate-v4 --app
> nervetrack-frontend` and `... allocate-v6`) and create `A`/`AAAA` records
> pointing at them instead.

---

## 8. CI and deployment (GitHub Actions)

Two workflows, with deploys kept deliberate (migrations auto-apply on deploy, so
shipping is an explicit act — not a side effect of merging):

- **`.github/workflows/ci.yml`** — runs on every PR and push to `main`: backend
  `ruff check` + `pytest`, frontend `lint` + `check` + `test`. Keeps `main`
  always-releasable. Does **not** deploy.
- **`.github/workflows/fly-deploy.yml`** — runs on a `v*` **tag** push: deploys
  backend → frontend.

One-time setup for deploys:

```bash
# Create a deploy token scoped to your org and add it to GitHub:
fly tokens create deploy -x 8760h        # prints a token
```

Then in the GitHub repo: **Settings → Secrets and variables → Actions → New
repository secret**, name it `FLY_API_TOKEN`, paste the token.

### Release flow

```bash
# work on a branch → open a PR → CI goes green → merge to main
git checkout main && git pull
git tag v0.2.0 && git push origin v0.2.0    # ← this deploys
```

You can also trigger a deploy manually from the Actions tab (`workflow_dispatch`).

### Rollback

```bash
fly releases --app nervetrack-backend       # find the previous good release
# redeploy the prior tag from your machine:
git checkout v0.1.0 && cd backend && fly deploy && cd ../frontend && fly deploy
```

---

## Backups

Two independent layers protect the data:

- **Continuous off-box replica (primary):** Litestream streams the WAL to the Tigris
  bucket from step 3 on a rolling basis, so the off-box copy is never more than a few
  seconds behind. This is what a host-replaced machine restores from automatically.
  To pull a copy to your machine or recover to a point in time:

  ```bash
  fly ssh console --app nervetrack-backend \
    -C "litestream restore -o /tmp/restore.db /data/nervetrack.db"
  # then copy /tmp/restore.db off the machine, e.g. via `fly sftp get`
  ```

- **Fly volume snapshots (secondary):** Fly snapshots the volume daily, kept 5 days.
  Restore with `fly volumes list` → `fly volumes snapshots list <vol-id>` →
  `fly volumes create nervetrack_data --snapshot-id <id> ...`.

> Avoid `cat /data/nervetrack.db` to grab a backup: the live DB is in WAL mode, so a
> raw file copy can miss un-checkpointed pages and produce a torn snapshot. Use
> `litestream restore` (or `sqlite3 /data/nervetrack.db ".backup '/tmp/x.db'"`),
> which are WAL-consistent.

---

## Operations cheatsheet

```bash
fly logs        --app nervetrack-backend      # tail logs (Litestream + uvicorn)
fly status      --app nervetrack-backend      # machine + check health
fly ssh console --app nervetrack-backend      # shell into the machine
fly secrets list --app nervetrack-backend     # names only (values hidden)
fly storage list                              # Tigris buckets
fly dashboard   --app nervetrack-frontend     # open web dashboard
```

### Why the backend must stay at one machine
SQLite is single-writer per file: WAL mode lets many readers run concurrently, but
only one process may write. The Fly volume can attach to only one machine anyway, and
two machines would mean two writers (and two Litestream replicators) against one
database = corruption. Keep `min_machines_running = 1` and never run
`fly scale count 2` on the backend.

### Why the backend deploys with `strategy = "immediate"`
A single machine with an attached volume can't be rolled (the volume can't be on
two machines at once), so the default `rolling` strategy updates in place and then
sits in a health-check wait that intermittently times out with
`net/http: request canceled` — failing the deploy in CI and the Fly dashboard even
though the app comes up healthy. `backend/fly.toml` sets `[deploy] strategy =
"immediate"`, which replaces the machine all at once (a few seconds of downtime)
for a clean, reliable release. The health check uses a generous `grace_period` so
the boot-time Litestream restore can finish before the check runs. The frontend has
no volume and keeps the default rolling strategy.

---

## Troubleshooting

### Frontend loads but pages are blank / `/api/*` returns a 500 with `{"message":"Internal Error"}`
The backend must listen on **IPv6** — Fly's private `<app>.internal` network is
IPv6-only. The backend runs `uvicorn --host ::` (dual-stack) for this reason (see
`backend/entrypoint.sh`). A `--host 0.0.0.0` (IPv4-only) bind is the classic trap:
Fly's IPv4 health checks pass and the app looks healthy, but the frontend's
`.internal` calls go over IPv6 and get connection-refused, so the proxy `fetch`
throws and SvelteKit returns its own `{"message":"Internal Error"}` 500. Verify from
outside with `curl -i https://nervetrack.jameskeech.io/api/v1/auth/me` — a healthy
backend returns **401** (not signed in), not 500.

### Backend boot-loops on a fresh machine / Litestream errors about credentials
The Tigris secrets from step 3 must be present. Check
`fly secrets list --app nervetrack-backend` for `BUCKET_NAME`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, and `AWS_REGION`. If they're missing,
re-run `fly storage create --app nervetrack-backend`. The names must match the
`${…}` placeholders in `backend/litestream.yml`.
