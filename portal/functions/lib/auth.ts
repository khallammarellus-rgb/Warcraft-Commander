import type { Cell } from "./turn_state";

export function tokenEnvKey(gameId: string, cell: Cell): string {
  const gid = gameId.replace(/-/g, "_").toUpperCase();
  const cellPart = cell.replace("-cell", "").toUpperCase();
  return `TOKEN_${gid}_${cellPart}`;
}

export function assistantPasswordKey(gameId: string): string {
  return `ASSISTANT_PASSWORD_${gameId.replace(/-/g, "_").toUpperCase()}`;
}

export function extractBearer(request: Request): string {
  const h = request.headers.get("Authorization") || "";
  if (h.startsWith("Bearer ")) return h.slice(7).trim();
  return "";
}

export type PortalTokens = Record<string, string>;

export async function loadPortalTokens(kv: KVNamespace, gameId: string): Promise<PortalTokens | null> {
  const raw = await kv.get(`portal_tokens:${gameId}`);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PortalTokens;
  } catch {
    return null;
  }
}

export async function savePortalTokens(kv: KVNamespace, gameId: string, tokens: PortalTokens): Promise<void> {
  await kv.put(`portal_tokens:${gameId}`, JSON.stringify(tokens));
}

export function randomToken(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes)).replace(/[+/=]/g, "").slice(0, 32);
}

export async function validateToken(
  env: Env,
  gameId: string,
  cell: Cell,
  token: string,
  kv?: KVNamespace | null,
): Promise<boolean> {
  if (!token) return false;
  const key = tokenEnvKey(gameId, cell);
  const expected = (env as Record<string, string | undefined>)[key];
  if (expected && timingSafeEqual(token, expected)) return true;
  if (kv) {
    const portal = await loadPortalTokens(kv, gameId);
    const kvKey = cell === "white-cell" ? "organizer" : cell;
    if (portal?.[kvKey] && timingSafeEqual(token, portal[kvKey])) return true;
  }
  if (env.ORGANIZER_SECRET && cell === "white-cell" && timingSafeEqual(token, env.ORGANIZER_SECRET)) {
    return true;
  }
  return false;
}

const WHITE_CELL_PASSCODE_DEFAULT = "charlamagne";

export function validateOrganizer(env: Env, token: string): boolean {
  return !!(env.ORGANIZER_SECRET && token && timingSafeEqual(token, env.ORGANIZER_SECRET));
}

/** White cell admin: passcode gate (default charlamagne) or legacy organizer secret. */
export function validateWhiteCell(env: Env, passcode: string): boolean {
  if (!passcode) return false;
  const expected = (env as Record<string, string | undefined>).WHITE_CELL_PASSCODE || WHITE_CELL_PASSCODE_DEFAULT;
  if (timingSafeEqual(passcode, expected)) return true;
  return validateOrganizer(env, passcode);
}

export async function validateAssistantAuth(
  env: Env,
  gameId: string,
  opts: { token?: string; cell?: Cell; password?: string },
  kv?: KVNamespace | null,
): Promise<"organizer" | "player" | "password" | null> {
  const token = opts.token?.trim() || "";
  if (validateOrganizer(env, token)) return "organizer";
  if (opts.cell && (await validateToken(env, gameId, opts.cell, token, kv))) return "player";
  const pwKey = assistantPasswordKey(gameId);
  let expectedPw = (env as Record<string, string | undefined>)[pwKey] || env.ASSISTANT_PASSWORD;
  if (kv) {
    const portal = await loadPortalTokens(kv, gameId);
    if (portal?.assistant_password) expectedPw = portal.assistant_password;
  }
  if (opts.password && expectedPw && timingSafeEqual(opts.password, expectedPw)) return "password";
  if (token && expectedPw && timingSafeEqual(token, expectedPw)) return "password";
  return null;
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}

export async function signActionToken(
  env: Env,
  payload: Record<string, string>,
  ttlSeconds = 86400,
): Promise<string> {
  const secret = env.SESSION_SECRET || env.ORGANIZER_SECRET || "dev-secret";
  const exp = String(Math.floor(Date.now() / 1000) + ttlSeconds);
  const body = new URLSearchParams({ ...payload, exp }).toString();
  const sig = await hmacHex(secret, body);
  return btoa(`${body}|${sig}`);
}

export async function verifyActionToken(
  env: Env,
  token: string,
): Promise<Record<string, string> | null> {
  try {
    const decoded = atob(token);
    const idx = decoded.lastIndexOf("|");
    if (idx < 0) return null;
    const body = decoded.slice(0, idx);
    const sig = decoded.slice(idx + 1);
    const secret = env.SESSION_SECRET || env.ORGANIZER_SECRET || "dev-secret";
    const expected = await hmacHex(secret, body);
    if (!timingSafeEqual(sig, expected)) return null;
    const params = Object.fromEntries(new URLSearchParams(body));
    const exp = Number(params.exp || 0);
    if (exp < Math.floor(Date.now() / 1000)) return null;
    return params;
  } catch {
    return null;
  }
}

async function hmacHex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}