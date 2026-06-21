# WoW Commander — game repo template

Use this folder as a **separate repository** for live campaign state. Players upload turn `.kmz` files; automation merges cell folders, rebuilds role-filtered views, and deploys to your hosted site.

## Set up the repo

1. Create a new repository (for example `wow-commander-table-01`).
2. Copy this folder's contents into the repository root.
3. Copy your live `03-kml/wowcommanderalpha/campaign/*.kml` files into `campaign/`.
4. Add repository secrets for your hosting deploy token and account ID.
5. Push to `main`. The workflow deploys when `campaign/` or `submissions/` changes.

## Player turn upload

Players upload through the repository web UI (no git required):

```
submissions/red-cell/turn03_commandername.kmz
submissions/blue-cell/turn03_commandername.kmz
```

The workflow merges each submission into the matching `campaign/<theater>.kml` master file, rebuilds `view/{cell}/` files, and deploys.

## Local organizer workflow

From the full project on your machine:

```bash
python3 scripts/sync_campaign_live.py --push
python3 scripts/publish_portal_site.py --deploy
```

## URLs after deploy

- Players: `https://<your-host>/view/red-cell/kalimdor.kml`
- Organizer master: `https://<your-host>/campaign/kalimdor.kml`

---

## Credits

This project exports map imagery from World of Warcraft using **wow.export**. None of this work would be possible without the creator of wow.export.

## Legal notices

- All trademarks and images associated with **Blizzard Entertainment** and **World of Warcraft** remain the property of their respective owners. The publisher uses them here only to build and view fan maps; they are **not** presented as the publisher's original work.
- **Google Earth** products are used under their applicable licenses. The publisher uses them as a viewer only and does **not** claim Google Earth or related marks as the publisher's intellectual property.

## About the publisher

The publisher has no formal background in programming or software development. **Grok AI CLI Build** and **Cloudflare AI Plugins** were used to author the scripts, JSON configuration, and build steps that produce this project.