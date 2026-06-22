export interface PublicGame {
  id: string;
  label: string;
  campaign_id: string;
  path_prefix: string;
  first_mover: string;
  campaign_base_url: string;
}

export interface GamesManifest {
  portal_label: string;
  games: PublicGame[];
}

const FALLBACK_MANIFEST: GamesManifest = {
  portal_label: "WoW Commander Portal",
  games: [
    { id: "table-01", label: "Table 01", campaign_id: "Campaign01", path_prefix: "games/table-01", first_mover: "blue-cell", campaign_base_url: "/games/table-01" },
    { id: "table-02", label: "Table 02", campaign_id: "Campaign02", path_prefix: "games/table-02", first_mover: "blue-cell", campaign_base_url: "/games/table-02" },
    { id: "table-03", label: "Table 03", campaign_id: "Campaign03", path_prefix: "games/table-03", first_mover: "blue-cell", campaign_base_url: "/games/table-03" },
  ],
};

export async function loadGamesManifest(_request: Request): Promise<GamesManifest> {
  return FALLBACK_MANIFEST;
}

export function gameFromManifest(manifest: GamesManifest, gameId: string): PublicGame | undefined {
  return manifest.games.find((g) => g.id === gameId);
}