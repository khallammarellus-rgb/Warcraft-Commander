import { buildSessionFromAnswers, type WizardAnswers } from "./eo_session";
import { geminiChat } from "./assistant";
import {
  loadPortalTokens,
  randomToken,
  savePortalTokens,
  type PortalTokens,
} from "./auth";
import type { Cell } from "./turn_state";

export function eoSessionKey(gameId: string, cell: string, sessionId: string): string {
  return `eo_draft:${gameId}:${cell}:${sessionId}`;
}

export function eoLatestKey(gameId: string, cell: string): string {
  return `eo_finalized_latest:${gameId}:${cell}`;
}

export async function loadLatestCellSession(
  kv: KVNamespace,
  gameId: string,
  cell: string,
): Promise<{ session: Record<string, unknown>; at: string; download_key: string } | null> {
  const raw = await kv.get(eoLatestKey(gameId, cell));
  if (!raw) return null;
  const parsed = JSON.parse(raw) as { session: Record<string, unknown>; at: string; download_key: string };
  if (!parsed.session) return null;
  return parsed;
}

export function maskToken(token: string): string {
  if (token.length <= 8) return "****";
  return `${token.slice(0, 4)}…${token.slice(-4)}`;
}

export async function loadOrCreatePortalTokens(
  kv: KVNamespace,
  gameId: string,
  env: Env,
): Promise<PortalTokens> {
  const existing = await loadPortalTokens(kv, gameId);
  if (existing) return existing;
  const gid = gameId.replace(/-/g, "_").toUpperCase();
  const envRec = env as Record<string, string | undefined>;
  return {
    "blue-cell": envRec[`TOKEN_${gid}_BLUE`] || randomToken(),
    "red-cell": envRec[`TOKEN_${gid}_RED`] || randomToken(),
    assistant_password: envRec[`ASSISTANT_PASSWORD_${gid}`] || randomToken(),
  };
}

export function regeneratePortalTokens(): PortalTokens {
  return {
    "blue-cell": randomToken(),
    "red-cell": randomToken(),
    assistant_password: randomToken(),
  };
}

export function buildOpordPrompt(answers: WizardAnswers, factionLabel: string): string {
  const forceSize = answers.force_size || "battalion";
  const body =
    `I need a military style five paragraph operational order for my ${factionLabel} ${forceSize} force ` +
    "complete with tactical tasks, a commander's endstate, center of gravity, and critical vulnerability. " +
    "This is for a wargame done in the context, landscape, and fanfiction of World of Warcraft Lore.";
  const warnO = (answers.warn_o as string | undefined)?.trim();
  if (warnO) return `This is the Warn O from higher. ${warnO}\n\n${body}`;
  return body;
}

export async function finalizeWizardSession(
  kv: KVNamespace,
  answers: WizardAnswers,
  eoData: { games: { id: string; campaign_id: string; campaign_base_url: string }[] },
): Promise<{ session: Record<string, unknown>; download_key: string }> {
  const session = buildSessionFromAnswers(answers, eoData);
  const gameId = (answers.game_id as string) || "table-01";
  const cell = (answers.player_cell as string) || "blue-cell";
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const downloadKey = `eo_finalized:${gameId}:${cell}:${stamp}`;
  await kv.put(downloadKey, JSON.stringify(session));
  await kv.put(eoLatestKey(gameId, cell), JSON.stringify({ session, at: new Date().toISOString(), download_key: downloadKey }));
  return { session, download_key: downloadKey };
}

export async function draftOpordWithGemini(env: Env, answers: WizardAnswers, factionLabel: string): Promise<string> {
  const custom = (answers.message as string | undefined)?.trim() || (answers.casual_opord_prompt as string | undefined)?.trim();
  const prompt = custom || buildOpordPrompt(answers, factionLabel);
  const context = [
    answers.commander_name ? `Commander: ${answers.commander_name}` : "",
    answers.force_name ? `Force: ${answers.force_name}` : "",
    answers.theater ? `Theater: ${answers.theater}` : "",
  ]
    .filter(Boolean)
    .join("\n");
  return geminiChat(env, "opord", prompt, context);
}

export function tokenSummary(tokens: PortalTokens): Record<string, string> {
  return {
    blue_cell: maskToken(tokens["blue-cell"] || ""),
    red_cell: maskToken(tokens["red-cell"] || ""),
    assistant_password: maskToken(tokens.assistant_password || ""),
  };
}

export function fullTokenPayload(gameId: string, tokens: PortalTokens): Record<string, string> {
  return {
    game_id: gameId,
    blue_cell_token: tokens["blue-cell"] || "",
    red_cell_token: tokens["red-cell"] || "",
    assistant_password: tokens.assistant_password || "",
    note: "Copy these now — masked values are shown in admin after you leave this page.",
  };
}

export type EoDraftPayload = {
  session_id: string;
  game_id: string;
  cell: Cell;
  answers: WizardAnswers;
  updated_at: string;
};