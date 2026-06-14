# Deploying NerveTrack to Fly.io

Two Fly apps:

| App | Visibility | Notes |
|-----|-----------|-------|
| `nervetrack-backend` | **Private** (6PN only) | FastAPI + DuckDB. One always-on machine + one volume. Never scale past 1. |
| `nervetrack-frontend` | **Public** (`nervetrack.jameskeech.io`) | SvelteKit. Stateless, scales to zero, proxies `/api/*` to the backend. |

The browser only ever talks to the frontend; it proxies `/api` to
`http://nervetrack-backend.internal:8000` over Fly's private network
(`frontend/src/hooks.server.ts`). The backend is never exposed to the internet.

---

## 0. Prerequisites (once)

```bash
brew install flyctl          # or: curl -L https://fly.io/install.sh | sh
fly auth login
```

The public site is served at **https://nervetrack.jameskeech.io** (custom domain,
configured in step 6). The Fly app names are internal plumbing — if
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

DuckDB lives here. One volume, one region, matched to the backend's machine.

```bash
fly volumes create nervetrack_data --app nervetrack-backend --region syd --size 1
```

> A `--size 1` (1 GB) volume is plenty for this dataset; grow later with
> `fly volumes extend`. Fly takes **automatic daily snapshots (5-day retention)** —
> see Backups below.

## 3. Set secrets

These are encrypted and injected at runtime — never put them in `fly.toml`.

```bash
fly secrets set --app nervetrack-backend \
  NERVETRACK_GOOGLE_CLIENT_ID="<google-web-client-id>" \
  NERVETRACK_GOOGLE_CLIENT_SECRET="<google-web-client-secret>" \
  NERVETRACK_ALLOWED_EMAILS="james.a.keech@gmail.com,other@example.com"

# Phase 2 (in-app Claude chat) — add when you get there:
# fly secrets set --app nervetrack-backend ANTHROPIC_API_KEY="sk-ant-..."
```

Non-secret config (DB path, timezone, cookie/HTTPS, public URLs, CORS) is already
in `backend/fly.toml` under `[env]`.

## 4. Configure Google OAuth

In Google Cloud Console → Credentials → your Web OAuth client, add the **authorized
redirect URI**:

```
https://nervetrack.jameskeech.io/api/v1/auth/google/callback
```

This must exactly match `NERVETRACK_OAUTH_REDIRECT_URI` in `backend/fly.toml`.

## 5. First deploy (manual, to verify)

Backend first (it owns the DB), then frontend:

```bash
cd backend  && fly deploy && cd ..
cd frontend && fly deploy && cd ..
```

Before DNS is set up you can smoke-test on the temporary
`https://nervetrack-frontend.fly.dev` address, but **sign-in will only work once
the custom domain in step 6 is live** (the OAuth redirect points at it).

## 6. Point nervetrack.jameskeech.io at the frontend

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

## 7. CI and deployment (GitHub Actions)

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

The DuckDB file is your only copy of the data — back it up.

- **Automatic:** Fly snapshots the volume daily, kept 5 days. Restore with
  `fly volumes list` → `fly volumes snapshots list <vol-id>` →
  `fly volumes create nervetrack_data --snapshot-id <id> ...`.
- **Manual off-box copy (recommended periodically):**
  ```bash
  fly ssh console --app nervetrack-backend -C "cat /data/nervetrack.duckdb" > backup-$(date +%F).duckdb
  ```
  Store it somewhere off Fly (e.g. cloud drive, or Fly's Tigris S3 buckets) for a
  longer retention window than 5 days.

---

## Operations cheatsheet

```bash
fly logs        --app nervetrack-backend      # tail logs
fly status      --app nervetrack-backend      # machine + check health
fly ssh console --app nervetrack-backend      # shell into the machine
fly secrets list --app nervetrack-backend     # names only (values hidden)
fly dashboard   --app nervetrack-frontend     # open web dashboard
```

### Why the backend must stay at one machine
`backend/app/db.py` opens a single DuckDB connection guarded by a lock — DuckDB is
single-writer. Two machines would mean two writers against one file = corruption.
Keep `min_machines_running = 1` and never run `fly scale count 2` on the backend.

### Why the backend deploys with `strategy = "immediate"`
A single machine with an attached volume can't be rolled (the volume can't be on
two machines at once), so the default `rolling` strategy updates in place and then
sits in a health-check wait that intermittently times out with
`net/http: request canceled` — failing the deploy in CI and the Fly dashboard even
though the app comes up healthy. `backend/fly.toml` sets `[deploy] strategy =
"immediate"`, which replaces the machine all at once (a few seconds of downtime)
for a clean, reliable release. The frontend has no volume and keeps the default
rolling strategy.

---

## Troubleshooting

### Frontend loads but pages are blank / `/api/*` returns a 500 with `{"message":"Internal Error"}`
The backend must listen on **IPv6** — Fly's private `<app>.internal` network is
IPv6-only. The backend `Dockerfile` runs `uvicorn --host ::` (dual-stack) for this
reason. A `--host 0.0.0.0` (IPv4-only) bind is the classic trap: Fly's IPv4 health
checks pass and the app looks healthy, but the frontend's `.internal` calls go over
IPv6 and get connection-refused, so the proxy `fetch` throws and SvelteKit returns
its own `{"message":"Internal Error"}` 500. Verify from outside with
`curl -i https://nervetrack.jameskeech.io/api/v1/auth/me` — a healthy backend
returns **401** (not signed in), not 500.
