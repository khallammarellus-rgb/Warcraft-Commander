# Hosted campaign portal

One Cloudflare Pages site with three game tables, turn-gated uploads, Discord notifications, and Gemini Executive Officer.

## Build and deploy

```bash
cd portal && npm install
python3 scripts/publish_portal_site.py --all-games          # build portal/dist
python3 scripts/publish_portal_site.py --deploy --all-games # deploy to Pages
```

## Cloudflare resources

Create in the Cloudflare dashboard (or via wrangler):

1. **KV** namespace → bind as `PORTAL_KV` (update id in `portal/wrangler.toml`)
2. **R2** bucket `wow-commander-turns` → bind as `TURNS_BUCKET`
3. **Pages** project `wow-commander-campaign` (or rename in wrangler.toml)

## Storage limits (R2 free tier)

Cloudflare R2 free tier includes **10 GB** storage. The portal enforces a **9.5 GB hard cap** so you are unlikely to hit billable overage:

| Limit | Value |
|-------|-------|
| Total storage cap | **9.5 GB** (tracked in KV; uploads rejected at cap) |
| Max turn KMZ | **8 MB** per file |
| Max ghost AAR | **512 KB** text |
| Max ad hoc announcement | **256 KB** text |

Check usage: `GET /api/games/table-01/storage` or `status` (includes `storage` object).

Config reference: `config/portal_storage.json`

## Secrets

```bash
cd portal
npx wrangler secret put ORGANIZER_SECRET
npx wrangler secret put SESSION_SECRET
npx wrangler secret put GEMINI_API_KEY
npx wrangler secret put DISCORD_WEBHOOK_URL
npx wrangler secret put DISCORD_WEBHOOK_URL_TURNS      # optional
npx wrangler secret put DISCORD_WEBHOOK_URL_ADMIN      # optional

# Per table (example Table 01):
npx wrangler secret put TOKEN_TABLE_01_BLUE
npx wrangler secret put TOKEN_TABLE_01_RED
npx wrangler secret put ASSISTANT_PASSWORD_TABLE_01
```

## Custom domain

1. Pages → Custom domains → add your domain
2. Functions routes automatically share the domain (`/api/*`)
3. Set per-game hosted URL:

```bash
python3 scripts/configure_hosted_campaign.py --mode hosted \
  --url https://commander.yourdomain.com/games/table-01
```

## Turn sequence

Blue board KMZ → Red board KMZ → White ghost AAR → Turn N+1.

- Upload: `/games/table-01/` (players)
- Admin: `/games/table-01/admin.html` (white cell)
- Discord: `turn.submitted`, `turn.ghost_complete`, `aar.adhoc`, `game.started`, `admin.access_request`, …

## Automated merge (Phase B)

After each board KMZ upload, the portal **auto-queues a merge job** in KV. A merge runner pulls the file from R2, merges into `campaign/<theater>.kml`, rebuilds role-filtered views, and redeploys Pages.

### Option A — GitHub Actions (recommended, primary)

**Poll workflow** (no GitHub PAT on Cloudflare required):

1. Push includes `.github/workflows/merge-portal-poll.yml` — runs every 3 minutes.
2. Add repository secrets at GitHub → Settings → Secrets → Actions:
   - `PORTAL_ORGANIZER_SECRET` — same value as `ORGANIZER_SECRET` on Pages
   - `CLOUDFLARE_ACCOUNT_ID` — `855414bc6c2032e637d52e2c6ce8076e`
   - `CLOUDFLARE_API_TOKEN` — [Create token](https://dash.cloudflare.com/profile/api-tokens) with **Account → Cloudflare Pages → Edit** and **Account → Workers R2 Storage → Read**

Run setup helper:

```bash
python3 scripts/configure_merge_automation.py
```

**Instant dispatch** (optional — merges within seconds of upload):

```bash
python3 scripts/configure_merge_automation.py --github-dispatch-token ghp_YOUR_PAT
```

Requires a GitHub PAT with `repo` scope. Workflow: `.github/workflows/merge-portal-turn.yml`.

### Option B — Local daemon

```bash
export ORGANIZER_SECRET=...
python3 scripts/merge_runner_daemon.py
```

Polls `GET /api/merge/pending` and runs `run_merge_job.py` for each job.

### Option C — Manual one-off

```bash
python3 scripts/run_merge_job.py --job-id <id> --portal-origin https://wow-commander-campaign.pages.dev
# or legacy:
python3 scripts/process_r2_turns.py --game table-01 --from-r2 --merge-latest --deploy
```

### Disable auto-merge

Set Pages secret `AUTO_MERGE_ON_UPLOAD=false` to queue merges only via white-cell **Process merge**.

### Board refresh

When merge completes, Discord posts `turn.merged` with a GEP NetworkLink refresh reminder. Game and admin pages show a green **Board updated** banner.

## Local preview

```bash
cd portal && npx wrangler pages dev dist
```

Open `http://localhost:8788/` — API requires KV/R2 bindings (wrangler dev provides local emulators).