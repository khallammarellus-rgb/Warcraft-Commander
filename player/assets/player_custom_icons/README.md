# Player custom icons

Unit marker PNGs built in the [icon builder](https://wow-commander-campaign.pages.dev/tools/icon-builder/) or imported from an opponent's icon pack.

## Install path

Save exports here (relative to your install root):

```
assets/player_custom_icons/my-unit.png
```

In Google Earth Pro, set placemark icon href to:

```
assets/player_custom_icons/my-unit.png
```

## Sharing between red and blue cell

| Method | When |
|--------|------|
| **Turn KMZ** | Icons are embedded automatically when you export a turn (`package_wargame_client.py`). |
| **Portal upload** | Icons are extracted from the KMZ and hosted for both cells on board refresh. |
| **Icon pack zip** | Before turn 1: player menu → `p` to package, opponent → `m` to import. |

## Tips

- Use **128 px** exports for most map markers; **64 px** for dense tactical maps.
- Name files by faction or unit (e.g. `red-infantry-01.png`) so both sides stay unique.
- PNGs are gitignored — they stay on your machine, not in the GitHub repo.