import type { WizardAnswers } from "./eo_session";
import { resolveForceName } from "./eo_session";
import type { Cell } from "./turn_state";

export type EoLobbyStatus = "open" | "waiting_blue" | "waiting_red" | "both_ready" | "active";

export interface EoCellSummary {
  cell: "blue-cell" | "red-cell";
  commander_name: string;
  commander_title?: string;
  factions: string[];
  faction_labels: string[];
  force_name: string;
  theater?: string;
  warn_o_excerpt?: string;
  opord_excerpt?: string;
  finalized_at: string;
}

export interface EoTableLobby {
  game_id: string;
  status: EoLobbyStatus;
  open_cell: "blue-cell" | "red-cell" | null;
  blue: EoCellSummary | null;
  red: EoCellSummary | null;
  matchup?: string;
  initiated_at?: string;
  updated_at: string;
}

export type EoLobbyFinalizeEvent = "blue_complete" | "red_complete" | "wargame_initiated";

export function lobbyKey(gameId: string): string {
  return `eo_table_lobby:${gameId}`;
}

export function emptyLobby(gameId: string): EoTableLobby {
  return {
    game_id: gameId,
    status: "open",
    open_cell: null,
    blue: null,
    red: null,
    updated_at: new Date().toISOString(),
  };
}

export async function loadLobby(kv: KVNamespace, gameId: string): Promise<EoTableLobby> {
  const raw = await kv.get(lobbyKey(gameId));
  if (!raw) return emptyLobby(gameId);
  return JSON.parse(raw) as EoTableLobby;
}

export async function saveLobby(kv: KVNamespace, lobby: EoTableLobby): Promise<void> {
  lobby.updated_at = new Date().toISOString();
  await kv.put(lobbyKey(lobby.game_id), JSON.stringify(lobby));
}

function excerpt(text: string | undefined, max = 400): string | undefined {
  const t = text?.trim();
  if (!t) return undefined;
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

function opordTextFromAnswers(answers: WizardAnswers): string | undefined {
  const direct = (answers.operation_order as string | undefined)?.trim()
    || (answers.opord_share as string | undefined)?.trim();
  if (direct) return direct;
  const parts: string[] = [];
  for (const [k, v] of Object.entries(answers)) {
    if (k.startsWith("opord_") && k !== "opord_approach" && k !== "opord_share" && typeof v === "string" && v.trim()) {
      parts.push(v.trim());
    }
  }
  return parts.length ? parts.join("\n\n") : undefined;
}

export function buildCellSummary(
  answers: WizardAnswers,
  cell: "blue-cell" | "red-cell",
  factionLabels: string[],
): EoCellSummary {
  const title = (answers.commander_title as string | undefined)?.trim();
  const name = (answers.commander_name as string | undefined)?.trim() || "Commander";
  const factions = Array.isArray(answers.factions) ? answers.factions : [];
  return {
    cell,
    commander_name: name,
    commander_title: title || undefined,
    factions,
    faction_labels: factionLabels.length ? factionLabels : factions,
    force_name: resolveForceName(answers),
    theater: (answers.theater as string | undefined) || undefined,
    warn_o_excerpt: excerpt(answers.warn_o as string | undefined),
    opord_excerpt: excerpt(opordTextFromAnswers(answers)),
    finalized_at: new Date().toISOString(),
  };
}

function commanderLine(summary: EoCellSummary): string {
  if (summary.commander_title) return `${summary.commander_title} ${summary.commander_name}`;
  return summary.commander_name;
}

function factionLine(summary: EoCellSummary): string {
  return summary.faction_labels.join(", ") || summary.factions.join(", ") || "—";
}

export function buildMatchup(lobby: EoTableLobby): string | undefined {
  if (!lobby.blue || !lobby.red) return undefined;
  const blue = `${factionLine(lobby.blue)} (${commanderLine(lobby.blue)})`;
  const red = `${factionLine(lobby.red)} (${commanderLine(lobby.red)})`;
  return `${blue} vs ${red}`;
}

function recomputeLobby(lobby: EoTableLobby): void {
  const hasBlue = !!lobby.blue;
  const hasRed = !!lobby.red;
  if (hasBlue && hasRed) {
    lobby.status = lobby.status === "active" ? "active" : "both_ready";
    lobby.open_cell = null;
    lobby.matchup = buildMatchup(lobby);
  } else if (hasBlue) {
    lobby.status = "waiting_red";
    lobby.open_cell = "red-cell";
    lobby.matchup = undefined;
  } else if (hasRed) {
    lobby.status = "waiting_blue";
    lobby.open_cell = "blue-cell";
    lobby.matchup = undefined;
  } else {
    lobby.status = "open";
    lobby.open_cell = null;
    lobby.matchup = undefined;
  }
}

export function lobbyPublicView(lobby: EoTableLobby): EoTableLobby {
  return {
    ...lobby,
    blue: lobby.blue
      ? { ...lobby.blue, warn_o_excerpt: undefined, opord_excerpt: undefined }
      : null,
    red: lobby.red
      ? { ...lobby.red, warn_o_excerpt: undefined, opord_excerpt: undefined }
      : null,
  };
}

export async function registerLobbyFinalize(
  kv: KVNamespace,
  gameId: string,
  cell: Cell,
  answers: WizardAnswers,
  factionLabels: string[],
): Promise<{ lobby: EoTableLobby; event: EoLobbyFinalizeEvent; initiated: boolean }> {
  if (cell !== "blue-cell" && cell !== "red-cell") {
    throw new Error("player_cell must be blue-cell or red-cell");
  }
  const lobby = await loadLobby(kv, gameId);
  if (cell === "blue-cell" && lobby.blue) {
    throw new Error("Blue Cell has already completed stand-up for this table. Join as Red Cell or ask white-cell to reset the table.");
  }
  if (cell === "red-cell" && lobby.red) {
    throw new Error("Red Cell has already completed stand-up for this table. Join as Blue Cell or ask white-cell to reset the table.");
  }

  const summary = buildCellSummary(answers, cell, factionLabels);
  if (cell === "blue-cell") lobby.blue = summary;
  else lobby.red = summary;

  recomputeLobby(lobby);

  let event: EoLobbyFinalizeEvent = cell === "blue-cell" ? "blue_complete" : "red_complete";
  let initiated = false;
  if (lobby.status === "both_ready") {
    lobby.initiated_at = new Date().toISOString();
    lobby.status = "active";
    event = "wargame_initiated";
    initiated = true;
  }

  await saveLobby(kv, lobby);
  return { lobby, event, initiated };
}

export async function loadAllLobbies(kv: KVNamespace, gameIds: string[]): Promise<EoTableLobby[]> {
  const out: EoTableLobby[] = [];
  for (const id of gameIds) {
    const lobby = await loadLobby(kv, id);
    out.push(lobbyPublicView(lobby));
  }
  return out;
}

export function cellDisplayName(cell: string): string {
  if (cell === "blue-cell") return "Blue Cell";
  if (cell === "red-cell") return "Red Cell";
  return cell;
}

export function campaignSetupKey(gameId: string): string {
  return `campaign_setup:${gameId}`;
}

export async function resetLobby(kv: KVNamespace, gameId: string, clearSessions = false): Promise<EoTableLobby> {
  const lobby = emptyLobby(gameId);
  await saveLobby(kv, lobby);
  if (clearSessions) {
    await kv.delete(`eo_finalized_latest:${gameId}:blue-cell`);
    await kv.delete(`eo_finalized_latest:${gameId}:red-cell`);
    await kv.delete(campaignSetupKey(gameId));
  }
  return lobby;
}

export interface CampaignSetupBundle {
  game_id: string;
  registered_at: string;
  blue_session: Record<string, unknown> | null;
  red_session: Record<string, unknown> | null;
  matchup?: string;
  note: string;
}