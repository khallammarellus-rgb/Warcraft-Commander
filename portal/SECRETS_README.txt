WoW Commander Portal — secrets (DO NOT COMMIT)
================================================

Your tokens are in: portal/.deploy-secrets.env (gitignored)

Give players ONLY their table's blue/red token and assistant password.
Keep ORGANIZER_SECRET and SESSION_SECRET private (white cell only).

Player tokens (web UI — preferred):
  Open /games/table-01/admin.html → enter organizer token → Player tokens
  Click "Regenerate tokens" to issue new tokens (saved in KV, no redeploy).

Player tokens (initial / env fallback):
  Tokens in portal/.deploy-secrets.env were uploaded via wrangler pages secret bulk.
  KV tokens override env secrets once regenerated in admin.

Discord webhook (optional):
  cd portal
  npx wrangler pages secret put DISCORD_WEBHOOK_URL --project-name wow-commander-campaign
  (paste webhook URL when prompted, then redeploy)

Gemini Executive Officer (optional):
  npx wrangler pages secret put GEMINI_API_KEY --project-name wow-commander-campaign

After adding Discord/Gemini secrets, redeploy:
  python3 scripts/publish_portal_site.py --deploy --all-games