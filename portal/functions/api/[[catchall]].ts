import {
  validateToken,
  validateWhiteCell,
  validateOrganizer,
  validateAssistantAuth,
  extractBearer,
  signActionToken,
  verifyActionToken,
  loadPortalTokens,
  savePortalTokens,
} from "../lib/auth";
import {
  draftOpordWithGemini,
  eoLatestKey,
  eoSessionKey,
  finalizeWizardSession,
  fullTokenPayload,
  loadLatestCellSession,
  loadOrCreatePortalTokens,
  regeneratePortalTokens,
  fullTokenSummary,
  type EoDraftPayload,
} from "../lib/eo_wizard_api";
import type { WizardAnswers } from "../lib/eo_session";
import {
  cellDisplayName,
  buildMatchup,
  campaignSetupKey,
  loadAllLobbies,
  loadLobby,
  lobbyPublicView,
  registerLobbyFinalize,
  resetLobby,
  type CampaignSetupBundle,
  type EoCellSummary,
  type EoLobbyFinalizeEvent,
  type EoTableLobby,
} from "../lib/eo_lobby";
import { composeAarMarkdown, discordFieldsForAar, parseAarRequest } from "../lib/aar_compose";
import { discordNotify, type DiscordPayload } from "../lib/discord";
import { gameFromManifest, loadGamesManifest } from "../lib/games";
import { geminiChat, checkAssistantRateLimit } from "../lib/assistant";
import { xoaiCoach, xoaiDigest, xoaiQuery, checkXoaiRateLimit } from "../lib/xoai";
import type { DigestEntry } from "../lib/xoai_types";
import { handleDiscordInteraction, verifyDiscordSignature } from "../lib/discord_interactions";
import {
  initialState,
  stateKey,
  archiveKey,
  canonicalBoardName,
  canonicalGhostName,
  canAcceptBoardUpload,
  canAcceptGhost,
  advanceAfterBoardUpload,
  advanceAfterGhost,
  reconcileTurnState,
  type TurnState,
  type TurnLogEntry,
  type Cell,
} from "../lib/turn_state";
import {
  autoMergeEnabled,
  cellFromCanonicalName,
  claimMergeJob,
  completeMergeJob,
  enqueueMergeJob,
  getBoardRefreshNotice,
  getLatestMergeSummary,
  listPendingJobs,
  loadMergeJob,
  mergeRunnerHint,
  resolveTheater,
  triggerMergeRunner,
  type MergeJob,
} from "../lib/merge_jobs";
import {
  iconR2Key,
  purgeGameArchives,
  purgeGameIcons,
  storeIconsFromKmzBuffer,
} from "../lib/campaign_icons";
import {
  assertCanStore,
  addStorageUsage,
  subtractStorageUsage,
  getStorageUsage,
  MAX_KMZ_UPLOAD_BYTES,
  MAX_GHOST_AAR_BYTES,
  MAX_ADHOC_ANNOUNCE_BYTES,
  formatBytes,
} from "../lib/storage_quota";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function kvOrNull(env: Env): KVNamespace | null {
  return env.PORTAL_KV ?? null;
}

async function loadState(env: Env, gameId: string, campaignId: string): Promise<TurnState> {
  const kv = kvOrNull(env);
  if (!kv) return initialState(campaignId);
  const raw = await kv.get(stateKey(gameId));
  const state = raw ? (JSON.parse(raw) as TurnState) : initialState(campaignId);
  const { state: reconciled, changed } = reconcileTurnState(state);
  if (changed) await saveState(env, gameId, reconciled);
  return reconciled;
}

async function saveState(env: Env, gameId: string, state: TurnState): Promise<void> {
  const kv = kvOrNull(env);
  if (!kv) throw new Error("PORTAL_KV not configured — bind KV namespace in Cloudflare Pages settings");
  await kv.put(stateKey(gameId), JSON.stringify(state));
}

async function scheduleBoardMerge(
  env: Env,
  request: Request,
  gameId: string,
  campaignId: string,
  entry: TurnLogEntry,
  triggeredBy: "auto" | "manual",
): Promise<{ job: MergeJob | null; runner: { triggered: boolean; method?: string } }> {
  const kv = kvOrNull(env);
  if (!kv || !entry.canonical_name) return { job: null, runner: { triggered: false } };

  const cell = entry.cell === "blue-cell" || entry.cell === "red-cell"
    ? entry.cell
    : cellFromCanonicalName(entry.canonical_name);
  if (!cell) return { job: null, runner: { triggered: false } };

  const theater = await resolveTheater(kv, gameId);
  const variant = (env as Record<string, string | undefined>).PORTAL_DEFAULT_VARIANT || "wowcommanderalpha";
  const job = await enqueueMergeJob(kv, {
    game_id: gameId,
    campaign_id: campaignId,
    variant,
    turn: entry.turn,
    cell,
    canonical_name: entry.canonical_name,
    r2_key: archiveKey(gameId, entry.canonical_name),
    theater,
    triggered_by: triggeredBy,
  });
  if (!job) return { job: null, runner: { triggered: false } };

  const runner = await triggerMergeRunner(env, job, origin(request, env));
  return { job, runner };
}

function origin(request: Request, env: Env): string {
  return env.PORTAL_ORIGIN || new URL(request.url).origin;
}

function pathParts(catchall: string | string[] | undefined): string[] {
  if (Array.isArray(catchall)) return catchall.filter(Boolean);
  if (typeof catchall === "string" && catchall.length) return catchall.split("/").filter(Boolean);
  return [];
}

function eoDiscordPayload(
  event: EoLobbyFinalizeEvent,
  gameLabel: string,
  summary: EoCellSummary,
  lobby: EoTableLobby,
  portalOrigin: string,
  gameId: string,
): DiscordPayload {
  const cellName = cellDisplayName(summary.cell);
  const factions = summary.faction_labels.join(", ") || "—";
  const commander = summary.commander_title
    ? `${summary.commander_title} ${summary.commander_name}`
    : summary.commander_name;

  if (event === "wargame_initiated") {
    return {
      title: `Wargame initiated — ${gameLabel}`,
      description: lobby.matchup || `${factions} — both cells ready`,
      url: `${portalOrigin}/games/${gameId}/`,
      fields: [
        { name: "Blue Cell", value: lobby.blue ? `${lobby.blue.faction_labels.join(", ")} (${lobby.blue.commander_name})` : "—", inline: true },
        { name: "Red Cell", value: lobby.red ? `${lobby.red.faction_labels.join(", ")} (${lobby.red.commander_name})` : "—", inline: true },
        { name: "Table", value: gameLabel, inline: true },
      ],
    };
  }

  const eventTitle = event === "blue_complete" ? "Blue Cell stand-up complete" : "Red Cell stand-up complete";
  const fields: DiscordPayload["fields"] = [
    { name: "Commander", value: commander, inline: true },
    { name: "Force", value: summary.force_name, inline: true },
    { name: "Factions", value: factions, inline: true },
    { name: "Theater", value: summary.theater || "—", inline: true },
  ];
  if (summary.warn_o_excerpt) {
    fields.push({ name: "WarnO (excerpt)", value: summary.warn_o_excerpt.slice(0, 900) });
  }
  if (summary.opord_excerpt) {
    fields.push({ name: "OpOrd (excerpt)", value: summary.opord_excerpt.slice(0, 900) });
  }
  if (lobby.open_cell) {
    fields.push({
      name: "Waiting for",
      value: `${cellDisplayName(lobby.open_cell)} — ${portalOrigin}/executive-officer/?game=${gameId}&cell=${lobby.open_cell}&join=1`,
    });
  }

  return {
    title: `${eventTitle} — ${gameLabel}`,
    description: `${cellName} · ${summary.force_name}`,
    url: `${portalOrigin}/executive-officer/?game=${gameId}`,
    fields,
  };
}

function mapEoEventToDiscord(event: EoLobbyFinalizeEvent): "eo.blue_complete" | "eo.red_complete" | "eo.wargame_initiated" {
  if (event === "blue_complete") return "eo.blue_complete";
  if (event === "red_complete") return "eo.red_complete";
  return "eo.wargame_initiated";
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env } = context;
  const url = new URL(request.url);
  const parts = pathParts(context.params.catchall as string | string[] | undefined);
  const method = request.method.toUpperCase();

  try {
    if (parts[0] === "games" && parts[1] === "lobby" && method === "GET") {
      const kv = kvOrNull(env);
      if (!kv) return json({ error: "PORTAL_KV not configured" }, 503);
      const manifest = await loadGamesManifest(request);
      const lobbies = await loadAllLobbies(kv, manifest.games.map((g) => g.id));
      return json({ lobbies });
    }

    if (parts[0] === "games" && parts.length >= 2) {
      const gameId = parts[1];
      const manifest = await loadGamesManifest(request);
      const game = gameFromManifest(manifest, gameId);
      if (!game) return json({ error: "Unknown game" }, 404);

      const action = parts[2] || "status";

      if (action === "icons" && parts[3] && method === "GET") {
        if (!env.TURNS_BUCKET) return json({ error: "R2 not configured" }, 503);
        const filename = parts[3].replace(/[/\\]/g, "");
        const obj = await env.TURNS_BUCKET.get(iconR2Key(gameId, filename));
        if (!obj) return json({ error: "Icon not found" }, 404);
        const headers = new Headers();
        headers.set("Content-Type", "image/png");
        headers.set("Cache-Control", "public, max-age=3600");
        return new Response(obj.body, { status: 200, headers });
      }

      if (action === "lobby" && parts[3] === "admin" && method === "GET") {
        const token = extractBearer(request);
        if (!validateWhiteCell(env, token)) return json({ error: "Unauthorized" }, 401);
        const kv = kvOrNull(env);
        if (!kv) return json({ error: "PORTAL_KV not configured" }, 503);
        const lobby = await loadLobby(kv, gameId);
        const blueLatest = await loadLatestCellSession(kv, gameId, "blue-cell");
        const redLatest = await loadLatestCellSession(kv, gameId, "red-cell");
        const setupRaw = await kv.get(campaignSetupKey(gameId));
        return json({
          lobby,
          sessions: {
            blue: blueLatest,
            red: redLatest,
          },
          setup_registered: setupRaw ? JSON.parse(setupRaw) : null,
          game: { id: game.id, label: game.label, campaign_id: game.campaign_id },
        });
      }

      if (action === "lobby" && parts[3] === "reset" && method === "POST") {
        const token = extractBearer(request);
        if (!validateWhiteCell(env, token)) return json({ error: "Unauthorized" }, 401);
        const kv = kvOrNull(env);
        if (!kv) return json({ error: "PORTAL_KV not configured" }, 503);
        const body = (await request.json().catch(() => ({}))) as { clear_sessions?: boolean };
        const lobby = await resetLobby(kv, gameId, !!body.clear_sessions);
        await discordNotify(env, gameId, "system.update", {
          title: `Table lobby reset — ${game.label}`,
          description: body.clear_sessions
            ? "Stand-up lobby and saved EO sessions cleared."
            : "Stand-up lobby cleared (EO session files kept).",
        });
        return json({ ok: true, lobby: lobbyPublicView(lobby) });
      }

      if (action === "lobby" && method === "GET") {
        const kv = kvOrNull(env);
        if (!kv) return json({ error: "PORTAL_KV not configured" }, 503);
        const lobby = lobbyPublicView(await loadLobby(kv, gameId));
        return json({ lobby, game: { id: game.id, label: game.label } });
      }

      if (action === "apply-setup" && method === "POST") {
        const token = extractBearer(request);
        if (!validateWhiteCell(env, token)) return json({ error: "Unauthorized" }, 401);
        const kv = kvOrNull(env);
        if (!kv) return json({ error: "PORTAL_KV not configured" }, 503);
        const blueLatest = await loadLatestCellSession(kv, gameId, "blue-cell");
        const redLatest = await loadLatestCellSession(kv, gameId, "red-cell");
        if (!blueLatest?.session || !redLatest?.session) {
          return json({
            error: "Both Blue and Red cells must complete Executive Officer stand-up before registering campaign setup.",
          }, 409);
        }
        const lobby = await loadLobby(kv, gameId);
        const bundle: CampaignSetupBundle = {
          game_id: gameId,
          registered_at: new Date().toISOString(),
          blue_session: blueLatest.session,
          red_session: redLatest.session,
          matchup: buildMatchup(lobby) || undefined,
          note: "Register on portal for white-cell export. Local apply: run apply_web_setup.py per cell, then publish_portal_site.py --deploy.",
        };
        await kv.put(campaignSetupKey(gameId), JSON.stringify(bundle));
        await discordNotify(env, gameId, "system.update", {
          title: `Campaign setup registered — ${game.label}`,
          description: bundle.matchup || "Both EO sessions stored on portal.",
          fields: [
            {
              name: "White cell",
              value: "Download setup bundle from admin, or run apply_web_setup.py locally per cell.",
            },
          ],
        });
        return json({ ok: true, bundle });
      }

      if (action === "status" && method === "GET") {
        const state = await loadState(env, gameId, game.campaign_id);
        const kv = kvOrNull(env);
        const storage = kv ? await getStorageUsage(kv) : null;
        const merge = kv ? await getLatestMergeSummary(kv, gameId) : null;
        const board_refresh = kv ? await getBoardRefreshNotice(kv, gameId) : null;
        return json({ ...state, storage, merge, board_refresh });
      }

      if (action === "merge" && method === "GET") {
        const kv = kvOrNull(env);
        if (!kv) return json({ error: "PORTAL_KV not configured" }, 503);
        const merge = await getLatestMergeSummary(kv, gameId);
        const board_refresh = await getBoardRefreshNotice(kv, gameId);
        return json({
          merge,
          board_refresh,
          runner_hint: mergeRunnerHint(env),
        });
      }

      if (action === "storage" && method === "GET") {
        const kv = kvOrNull(env);
        if (!kv) return json({ error: "PORTAL_KV not configured" }, 503);
        return json(await getStorageUsage(kv));
      }

      if (action === "upload" && method === "POST") {
        const form = await request.formData();
        const token = (form.get("token") as string) || extractBearer(request);
        const cell = (form.get("cell") as string) as Cell;
        const proxy = form.get("proxy") === "1";
        const file = form.get("file");
        if (!file || typeof file === "string") return json({ error: "Missing file" }, 400);

        const state = await loadState(env, gameId, game.campaign_id);
        let effectiveCell: Cell;
        const kvAuth = kvOrNull(env);
        if (proxy) {
          if (!validateWhiteCell(env, token)) return json({ error: "Unauthorized" }, 401);
          effectiveCell = state.active_cell;
        } else {
          if (!(await validateToken(env, gameId, cell, token, kvAuth))) return json({ error: "Unauthorized" }, 401);
          effectiveCell = cell;
        }
        if (effectiveCell !== "blue-cell" && effectiveCell !== "red-cell") {
          return json({ error: "Invalid cell for board upload" }, 400);
        }

        const check = canAcceptBoardUpload(state, effectiveCell, proxy);
        if (!check.ok) return json({ error: check.error }, 409);

        const filename = canonicalBoardName(game.campaign_id, state.turn, effectiveCell);
        const key = archiveKey(gameId, filename);
        if (!env.TURNS_BUCKET) {
          return json({ error: "R2 not configured — enable R2 in Cloudflare Dashboard and redeploy" }, 503);
        }
        const uploadFile = file as File;
        const fileSize = uploadFile.size;
        if (fileSize > MAX_KMZ_UPLOAD_BYTES) {
          return json({
            error: `KMZ too large (${formatBytes(fileSize)}). Max per turn: ${formatBytes(MAX_KMZ_UPLOAD_BYTES)}.`,
          }, 413);
        }
        const kvUpload = kvOrNull(env);
        if (!kvUpload) return json({ error: "PORTAL_KV not configured" }, 503);
        const quota = await assertCanStore(kvUpload, fileSize, "Turn upload");
        if (!quota.ok) return json({ error: quota.error, storage: quota.usage }, 507);

        const existing = await env.TURNS_BUCKET.head(key);
        if (existing) return json({ error: "Turn already archived" }, 409);

        const kmzBytes = new Uint8Array(await uploadFile.arrayBuffer());
        await env.TURNS_BUCKET.put(key, kmzBytes, {
          httpMetadata: { contentType: "application/vnd.google-earth.kmz" },
        });
        await addStorageUsage(kvUpload, fileSize);

        let iconsStored = { count: 0, bytes: 0, filenames: [] as string[] };
        try {
          iconsStored = await storeIconsFromKmzBuffer(env.TURNS_BUCKET, gameId, kmzBytes);
          if (iconsStored.bytes > 0) {
            await addStorageUsage(kvUpload, iconsStored.bytes);
          }
        } catch (iconErr) {
          console.error("Icon extract from KMZ failed:", iconErr);
        }

        const entry = {
          type: "board_upload",
          turn: state.turn,
          cell: effectiveCell,
          canonical_name: filename,
          original_filename: (file as File).name,
          uploaded_at: new Date().toISOString(),
          uploaded_by: proxy ? ("white-cell" as const) : cell,
          proxy,
          proxy_for: proxy ? effectiveCell : undefined,
        };
        const next = advanceAfterBoardUpload({ ...state, history: [...state.history, entry] }, effectiveCell);
        await saveState(env, gameId, next);

        const cellName = effectiveCell === "blue-cell" ? "Blue Cell" : "Red Cell";
        await discordNotify(env, gameId, "turn.submitted", {
          title: `Turn ${state.turn} — ${cellName} complete`,
          description: filename,
          url: `${origin(request, env)}/games/${gameId}/`,
          fields: [{ name: "Campaign", value: game.label, inline: true }],
        });

        let mergeJob: MergeJob | null = null;
        let mergeRunner = { triggered: false as boolean, method: undefined as string | undefined };
        if (autoMergeEnabled(env)) {
          const scheduled = await scheduleBoardMerge(env, request, gameId, game.campaign_id, entry, "auto");
          mergeJob = scheduled.job;
          mergeRunner = scheduled.runner;
          if (mergeJob) {
            await discordNotify(env, gameId, "system.update", {
              title: `Board merge queued — ${game.label}`,
              description: `${filename} — ${mergeRunner.triggered ? "runner triggered" : mergeRunnerHint(env)}`,
              fields: [
                { name: "Job", value: mergeJob.id, inline: true },
                { name: "Cell", value: cellName, inline: true },
              ],
            });
          }
        }

        return json({
          ok: true,
          canonical_name: filename,
          state: next,
          merge_job: mergeJob,
          merge_runner: mergeRunner,
          icons_stored: iconsStored.count,
        });
      }

      if (action === "ghost-turn" && method === "POST") {
        const token = extractBearer(request);
        if (!validateWhiteCell(env, token)) return json({ error: "Unauthorized" }, 401);
        const rawBody = await request.json();
        const parsed = parseAarRequest(rawBody);
        if (!parsed.ok) return json({ error: parsed.error }, 400);
        const aar = parsed.data;
        const markdown = composeAarMarkdown(aar);

        const state = await loadState(env, gameId, game.campaign_id);
        const check = canAcceptGhost(state);
        if (!check.ok) return json({ error: check.error }, 409);

        const bodyBytes = new TextEncoder().encode(markdown).length;
        if (bodyBytes > MAX_GHOST_AAR_BYTES) {
          return json({ error: `AAR too large. Max ${formatBytes(MAX_GHOST_AAR_BYTES)}.` }, 413);
        }
        const kvGhost = kvOrNull(env);
        if (!kvGhost) return json({ error: "PORTAL_KV not configured" }, 503);
        const ghostQuota = await assertCanStore(kvGhost, bodyBytes, "Ghost AAR");
        if (!ghostQuota.ok) return json({ error: ghostQuota.error, storage: ghostQuota.usage }, 507);

        const filename = canonicalGhostName(game.campaign_id, state.turn);
        const key = archiveKey(gameId, filename);
        if (!env.TURNS_BUCKET) return json({ error: "R2 not configured" }, 503);
        await env.TURNS_BUCKET.put(key, markdown, {
          httpMetadata: { contentType: "text/markdown" },
        });
        await addStorageUsage(kvGhost, bodyBytes);

        const entry = {
          type: "ghost_turn",
          turn: state.turn,
          cell: "white-cell" as Cell,
          canonical_name: filename,
          uploaded_at: new Date().toISOString(),
          uploaded_by: "white-cell" as const,
          body_excerpt: aar.reason.slice(0, 280),
        };
        const next = advanceAfterGhost({ ...state, history: [...state.history, entry] });
        await saveState(env, gameId, next);

        await discordNotify(env, gameId, "turn.ghost_complete", {
          title: `Turn ${state.turn} ghost AAR — ${aar.reason}`,
          description: aar.tactical_rationale.slice(0, 500),
          fields: discordFieldsForAar(aar),
          url: `${origin(request, env)}/games/${gameId}/`,
        });

        return json({ ok: true, canonical_name: filename, state: next });
      }

      if (action === "announce" && method === "POST") {
        const token = extractBearer(request);
        if (!validateWhiteCell(env, token)) return json({ error: "Unauthorized" }, 401);
        const rawBody = await request.json();
        const parsed = parseAarRequest(rawBody);
        if (!parsed.ok) return json({ error: parsed.error }, 400);
        const aar = parsed.data;
        const markdown = composeAarMarkdown(aar);

        const state = await loadState(env, gameId, game.campaign_id);
        const announceBytes = new TextEncoder().encode(markdown).length;
        if (announceBytes > MAX_ADHOC_ANNOUNCE_BYTES) {
          return json({ error: `Announcement too large. Max ${formatBytes(MAX_ADHOC_ANNOUNCE_BYTES)}.` }, 413);
        }
        const kvAnn = kvOrNull(env);
        if (!kvAnn) return json({ error: "PORTAL_KV not configured" }, 503);
        const annQuota = await assertCanStore(kvAnn, announceBytes, "Announcement");
        if (!annQuota.ok) return json({ error: annQuota.error, storage: annQuota.usage }, 507);

        const stamp = new Date().toISOString().replace(/[:.]/g, "-");
        const key = `games/${gameId}/announcements/${stamp}.md`;
        if (!env.TURNS_BUCKET) return json({ error: "R2 not configured" }, 503);
        await env.TURNS_BUCKET.put(key, markdown, { httpMetadata: { contentType: "text/markdown" } });
        await addStorageUsage(kvAnn, announceBytes);

        const entry = {
          type: "aar_adhoc",
          turn: state.turn,
          uploaded_at: new Date().toISOString(),
          uploaded_by: "white-cell" as const,
          body_excerpt: aar.reason.slice(0, 280),
        };
        state.history = [...state.history, entry];
        await saveState(env, gameId, state);

        await discordNotify(env, gameId, "aar.adhoc", {
          title: `Ad hoc AAR — ${aar.reason}`,
          description: aar.tactical_rationale.slice(0, 500),
          fields: discordFieldsForAar(aar),
        });

        return json({ ok: true, state });
      }

      if (action === "lifecycle" && method === "POST") {
        const token = extractBearer(request);
        if (!validateWhiteCell(env, token)) return json({ error: "Unauthorized" }, 401);
        const body = (await request.json()) as {
          action?: string;
          purge_icons?: boolean;
          purge_archives?: boolean;
        };
        const actionName = body.action;
        const state = await loadState(env, gameId, game.campaign_id);

        if (actionName === "start") {
          if (state.status === "active") {
            return json(
              {
                error:
                  "Campaign is already active — do not use Start again (it can desync turn order). " +
                  "Games auto-start when both cells finish XO stand-up.",
              },
              409,
            );
          }
          if (state.status === "ended") {
            return json(
              { error: "Campaign has ended. Reset the table lobby or use another table for a new game." },
              409,
            );
          }
          const kvLifecycle = kvOrNull(env);
          if (kvLifecycle) {
            const lobby = await loadLobby(kvLifecycle, gameId);
            if (lobby.status !== "both_ready" && lobby.status !== "active") {
              return json(
                {
                  error:
                    "Both cells must finish XO stand-up first. The campaign auto-starts when Red cell finalizes — manual Start is not needed.",
                },
                409,
              );
            }
          }
          state.status = "active";
          if (!state.history.some((h) => h.type === "board_upload")) {
            state.turn = 1;
            state.active_cell = "blue-cell";
            state.phase = "board";
          } else {
            const { state: reconciled } = reconcileTurnState(state);
            Object.assign(state, reconciled);
          }
          await saveState(env, gameId, state);
          await discordNotify(env, gameId, "game.started", {
            title: `Campaign started — ${game.label}`,
            url: `${origin(request, env)}/games/${gameId}/`,
          });
          return json({ ok: true, state });
        }
        if (actionName === "end") {
          state.status = "ended";
          await saveState(env, gameId, state);

          const kv = kvOrNull(env);
          const purgeIcons = body.purge_icons !== false;
          const purgeArchives = !!body.purge_archives;
          let iconsPurged = { deleted: 0, bytes: 0 };
          let archivesPurged = { deleted: 0, bytes: 0 };

          if (env.TURNS_BUCKET && kv) {
            if (purgeIcons) {
              iconsPurged = await purgeGameIcons(env.TURNS_BUCKET, gameId);
              if (iconsPurged.bytes > 0) {
                await subtractStorageUsage(kv, iconsPurged.bytes);
              }
            }
            if (purgeArchives) {
              archivesPurged = await purgeGameArchives(env.TURNS_BUCKET, gameId);
              if (archivesPurged.bytes > 0) {
                await subtractStorageUsage(kv, archivesPurged.bytes);
              }
            }
          }

          const purgeNote = [
            purgeIcons && iconsPurged.deleted
              ? `${iconsPurged.deleted} icon(s) removed (${formatBytes(iconsPurged.bytes)})`
              : null,
            purgeArchives && archivesPurged.deleted
              ? `${archivesPurged.deleted} archive file(s) removed (${formatBytes(archivesPurged.bytes)})`
              : null,
          ]
            .filter(Boolean)
            .join("; ");

          await discordNotify(env, gameId, "game.ended", {
            title: `Campaign ended — ${game.label}`,
            description: purgeNote
              ? `Final turn: ${state.turn}. Storage purged: ${purgeNote}`
              : `Final turn: ${state.turn}`,
          });
          return json({
            ok: true,
            state,
            icons_purged: iconsPurged,
            archives_purged: archivesPurged,
          });
        }
        return json({ error: "Unknown lifecycle action" }, 400);
      }

      if (action === "merge" && method === "POST") {
        const token = extractBearer(request);
        if (!validateWhiteCell(env, token)) return json({ error: "Unauthorized" }, 401);
        const kv = kvOrNull(env);
        if (!kv) return json({ error: "PORTAL_KV not configured" }, 503);

        const state = await loadState(env, gameId, game.campaign_id);
        const pending = state.history.filter((h) => h.type === "board_upload" && !h.merged_at);
        if (!pending.length) {
          return json({ error: "No unmerged board uploads for this table." }, 409);
        }

        const jobs: MergeJob[] = [];
        let anyTriggered = false;
        for (const entry of pending) {
          const scheduled = await scheduleBoardMerge(env, request, gameId, game.campaign_id, entry, "manual");
          if (scheduled.job) {
            jobs.push(scheduled.job);
            if (scheduled.runner.triggered) anyTriggered = true;
          }
        }

        await discordNotify(env, gameId, "system.update", {
          title: `Board merge queued — ${game.label}`,
          description: `${jobs.length} job(s) — ${anyTriggered ? "runner triggered" : mergeRunnerHint(env)}`,
          fields: jobs.slice(0, 3).map((j) => ({
            name: j.canonical_name,
            value: `Job ${j.id} (${j.status})`,
            inline: false,
          })),
        });

        return json({
          ok: true,
          jobs,
          runner_hint: mergeRunnerHint(env),
          triggered: anyTriggered,
        });
      }
    }

    if (parts[0] === "merge" && parts.length >= 2) {
      const jobId = parts[1];
      const sub = parts[2] || "";
      const token = extractBearer(request);
      if (!validateOrganizer(env, token)) return json({ error: "Unauthorized" }, 401);
      const kv = kvOrNull(env);
      if (!kv) return json({ error: "PORTAL_KV not configured" }, 503);

      if (jobId === "runner-env" && method === "GET") {
        const envMap = env as Record<string, string | undefined>;
        const cfToken = envMap.MERGE_CLOUDFLARE_API_TOKEN || envMap.CLOUDFLARE_API_TOKEN;
        const cfAccount = envMap.MERGE_CLOUDFLARE_ACCOUNT_ID || "855414bc6c2032e637d52e2c6ce8076e";
        if (!cfToken) {
          return json({ error: "Merge Cloudflare API token not configured on Pages" }, 503);
        }
        return json({
          cloudflare_api_token: cfToken,
          cloudflare_account_id: cfAccount,
        });
      }

      if (jobId === "pending" && method === "GET") {
        const jobs = await listPendingJobs(kv);
        return json({ jobs });
      }

      if (sub === "claim" && method === "POST") {
        const job = await claimMergeJob(kv, jobId);
        if (!job) return json({ error: "Job not found or not pending" }, 404);
        return json({ ok: true, job });
      }

      if (sub === "complete" && method === "POST") {
        const body = (await request.json()) as { ok?: boolean; error?: string; deploy_url?: string };
        const job = await completeMergeJob(kv, jobId, {
          ok: !!body.ok,
          error: body.error,
          deploy_url: body.deploy_url,
        });
        if (!job) return json({ error: "Job not found" }, 404);

        if (body.ok) {
          const state = await loadState(env, job.game_id, job.campaign_id);
          for (const entry of state.history) {
            if (entry.type === "board_upload" && entry.canonical_name === job.canonical_name && !entry.merged_at) {
              entry.merged_at = job.completed_at;
            }
          }
          await saveState(env, job.game_id, state);

          await discordNotify(env, job.game_id, "turn.merged", {
            title: `Board updated — ${job.game_id}`,
            description: `${job.canonical_name} merged and deployed.`,
            url: job.deploy_url || `${origin(request, env)}/games/${job.game_id}/`,
            fields: [
              {
                name: "Google Earth",
                value: "Refresh NetworkLinks (right-click campaign folder → Refresh) to load the new board.",
              },
            ],
          });
        }

        return json({ ok: true, job });
      }

      if (method === "GET") {
        const job = await loadMergeJob(kv, jobId);
        if (!job) return json({ error: "Job not found" }, 404);
        return json({ job });
      }
    }

    if (parts[0] === "discord" && parts[1] === "interactions" && method === "POST") {
      const sig = request.headers.get("X-Signature-Ed25519") || "";
      const ts = request.headers.get("X-Signature-Timestamp") || "";
      const bodyText = await request.text();
      const pubKey = env.DISCORD_PUBLIC_KEY;
      if (!pubKey || !(await verifyDiscordSignature(pubKey, sig, ts, bodyText))) {
        return json({ error: "Invalid signature" }, 401);
      }
      const kvDiscord = kvOrNull(env);
      return handleDiscordInteraction(env, bodyText, kvDiscord, origin(request, env));
    }

    if (parts[0] === "xoai") {
      const sub = parts[1] || "";

      if (sub === "query" && method === "POST") {
        const body = (await request.json()) as {
          game_id?: string;
          collection?: string;
          message?: string;
          token?: string;
          cell?: Cell;
          password?: string;
        };
        const gameId = body.game_id || "table-01";
        const kvX = kvOrNull(env);
        const role = await validateAssistantAuth(env, gameId, body, kvX);
        if (!role) return json({ error: "Unauthorized — token or password required" }, 401);

        const collection = (body.collection || "rules").toLowerCase();
        if (collection !== "tactics" && collection !== "lore" && collection !== "rules") {
          return json({ error: "collection must be tactics, lore, or rules" }, 400);
        }
        if (!body.message?.trim()) return json({ error: "message required" }, 400);

        const limit = role === "organizer" ? 100 : 30;
        const sessionId = `${role}:${gameId}:${body.cell || "guest"}:query`;
        if (!kvX) return json({ error: "PORTAL_KV not configured" }, 503);
        const allowed = await checkXoaiRateLimit(kvX, sessionId, limit);
        if (!allowed) return json({ error: "Daily XOai limit reached" }, 429);

        const result = await xoaiQuery({
          env,
          collection,
          message: body.message,
          gameId,
          kv: kvX,
          origin: origin(request, env),
        });
        return json(result);
      }

      if (sub === "digest" && method === "POST") {
        const body = (await request.json()) as {
          game_id?: string;
          token?: string;
          cell?: Cell;
          password?: string;
          entries?: DigestEntry[];
        };
        const gameId = body.game_id || "table-01";
        const kvDig = kvOrNull(env);
        const role = await validateAssistantAuth(env, gameId, body, kvDig);
        if (!role) return json({ error: "Unauthorized — token or password required" }, 401);
        if (!body.entries?.length) return json({ error: "entries required" }, 400);

        const limit = role === "organizer" ? 100 : 30;
        const sessionId = `${role}:${gameId}:${body.cell || "guest"}:query`;
        if (!kvDig) return json({ error: "PORTAL_KV not configured" }, 503);
        const allowed = await checkXoaiRateLimit(kvDig, sessionId, limit);
        if (!allowed) return json({ error: "Daily XOai limit reached" }, 429);

        const result = await xoaiDigest(env, body.entries.slice(-40));
        return json(result);
      }

      if (sub === "coach" && method === "POST") {
        const body = (await request.json()) as {
          game_id?: string;
          message?: string;
          player_notes?: string;
          token?: string;
          cell?: Cell;
          password?: string;
          kml_xml?: string;
          kmz_base64?: string;
          game_format?: string;
        };
        const gameId = body.game_id || "table-01";
        const kvCoach = kvOrNull(env);
        const role = await validateAssistantAuth(env, gameId, body, kvCoach);
        if (!role) return json({ error: "Unauthorized — token or password required" }, 401);

        const viewer = body.cell || "blue-cell";
        if (viewer !== "blue-cell" && viewer !== "red-cell" && viewer !== "white-cell") {
          return json({ error: "cell must be blue-cell, red-cell, or white-cell" }, 400);
        }
        if (!body.message?.trim()) return json({ error: "message required" }, 400);

        const limit = role === "organizer" ? 100 : 30;
        const sessionId = `${role}:${gameId}:${viewer}:coach`;
        if (!kvCoach) return json({ error: "PORTAL_KV not configured" }, 503);
        const allowed = await checkXoaiRateLimit(kvCoach, sessionId, limit);
        if (!allowed) return json({ error: "Daily XOai coach limit reached" }, 429);

        const result = await xoaiCoach({
          env,
          kv: kvCoach,
          gameId,
          origin: origin(request, env),
          viewer,
          message: body.message,
          playerNotes: body.player_notes,
          kmlXml: body.kml_xml,
          kmzBase64: body.kmz_base64,
          gameFormatOverride: body.game_format,
        });
        return json(result);
      }

      if (sub === "session" && method === "GET") {
        const gameId = url.searchParams.get("game_id") || "table-01";
        const token = url.searchParams.get("token") || extractBearer(request);
        const cell = (url.searchParams.get("cell") || "blue-cell") as Cell;
        const kvSess = kvOrNull(env);
        const role = await validateAssistantAuth(env, gameId, { token, cell }, kvSess);
        if (!role) return json({ error: "Unauthorized" }, 401);
        if (!kvSess) return json({ error: "PORTAL_KV not configured" }, 503);
        const { loadGameFormat } = await import("../lib/xoai");
        const game_format = await loadGameFormat(kvSess, gameId);
        return json({ game_id: gameId, game_format, cell });
      }
    }

    if (parts[0] === "assistant") {
      const sub = parts[1] || "";

      if (sub === "auth" && method === "POST") {
        const body = (await request.json()) as {
          game_id?: string;
          token?: string;
          cell?: Cell;
          password?: string;
        };
        const gameId = body.game_id || "table-01";
        const kvAuth = kvOrNull(env);
        const role = await validateAssistantAuth(env, gameId, body, kvAuth);
        if (!role) return json({ error: "Unauthorized" }, 401);
        return json({ ok: true, role });
      }

      if (sub === "chat" && method === "POST") {
        const body = (await request.json()) as {
          game_id?: string;
          mode?: string;
          message?: string;
          context?: string;
          token?: string;
          cell?: Cell;
          password?: string;
        };
        const gameId = body.game_id || "table-01";
        const kvChat = kvOrNull(env);
        const role = await validateAssistantAuth(env, gameId, body, kvChat);
        if (!role) return json({ error: "Unauthorized — token or password required" }, 401);

        const limit = role === "organizer" ? 100 : 30;
        const sessionId = `${role}:${gameId}:${body.cell || "guest"}`;
        const kv = kvOrNull(env);
        if (!kv) return json({ error: "PORTAL_KV not configured" }, 503);
        const allowed = await checkAssistantRateLimit(kv, sessionId, limit);
        if (!allowed) return json({ error: "Daily assistant limit reached" }, 429);

        const reply = await geminiChat(env, body.mode || "rules", body.message || "", body.context);
        return json({ reply });
      }

      if (sub === "request-access" && method === "POST") {
        const body = (await request.json()) as {
          game_id?: string;
          name?: string;
          email?: string;
          message?: string;
        };
        const gameId = body.game_id || "table-01";
        const email = (body.email || "").trim().toLowerCase();
        if (!email || !body.name) return json({ error: "Name and email required" }, 400);

        const reqKey = `access_request:${gameId}:${email}`;
        const kvReq = kvOrNull(env);
        if (!kvReq) return json({ error: "PORTAL_KV not configured" }, 503);
        await kvReq.put(
          reqKey,
          JSON.stringify({ ...body, email, status: "pending", at: new Date().toISOString() }),
        );

        const base = origin(request, env);
        const approve = await signActionToken(env, { action: "approve", gameId, email });
        const deny = await signActionToken(env, { action: "deny", gameId, email });

        await discordNotify(env, gameId, "admin.access_request", {
          title: `Assistant access request — ${gameId}`,
          description: `${body.name} <${email}>\n${body.message || ""}`,
          fields: [
            { name: "Approve", value: `${base}/api/assistant/approve?token=${encodeURIComponent(approve)}` },
            { name: "Deny", value: `${base}/api/assistant/approve?token=${encodeURIComponent(deny)}` },
          ],
        });

        return json({ ok: true, message: "Request submitted — white cell notified on Discord" });
      }

      if (sub === "approve" && method === "GET") {
        const token = url.searchParams.get("token") || "";
        const params = await verifyActionToken(env, token);
        if (!params) return json({ error: "Invalid or expired link" }, 400);
        const { action, gameId, email } = params;
        const reqKey = `access_request:${gameId}:${email}`;

        if (action === "approve") {
          const kvAp = kvOrNull(env);
          if (kvAp) {
            await kvAp.put(`assistant_allowlist:${gameId}:${email}`, "1");
            await kvAp.put(reqKey, JSON.stringify({ email, status: "approved", at: new Date().toISOString() }));
          }
          await discordNotify(env, gameId, "admin.access_granted", { title: `Access granted: ${email}` });
          return new Response(`<html><body><p>Approved ${email} for ${gameId}. <a href="/assistant/">Open assistant</a></p></body></html>`, {
            headers: { "Content-Type": "text/html" },
          });
        }
        if (action === "deny") {
          const kvDn = kvOrNull(env);
          if (kvDn) {
            await kvDn.put(reqKey, JSON.stringify({ email, status: "denied", at: new Date().toISOString() }));
          }
          await discordNotify(env, gameId, "admin.access_denied", { title: `Access denied: ${email}` });
          return new Response(`<html><body><p>Denied ${email}.</p></body></html>`, {
            headers: { "Content-Type": "text/html" },
          });
        }
      }
    }

    if (parts[0] === "executive-officer") {
      const sub = parts[1] || "";
      const kvEo = kvOrNull(env);
      if (!kvEo) return json({ error: "PORTAL_KV not configured" }, 503);

      if (sub === "draft" && method === "POST") {
        const body = (await request.json()) as WizardAnswers & { faction_label?: string };
        const factionLabel = body.faction_label || "friendly force";
        try {
          const draft = await draftOpordWithGemini(env, body, factionLabel);
          return json({ ok: true, draft, gemini: true });
        } catch (err) {
          const msg = err instanceof Error ? err.message : "Draft failed";
          if (msg.includes("GEMINI_API_KEY")) {
            return json({
              ok: false,
              error: "Gemini not configured — paste your OPORD manually or ask white-cell to add GEMINI_API_KEY",
              prompt: body,
            }, 503);
          }
          return json({ error: msg }, 500);
        }
      }

      if (sub === "save-draft" && method === "POST") {
        const body = (await request.json()) as EoDraftPayload;
        if (!body.session_id || !body.game_id || !body.cell) {
          return json({ error: "session_id, game_id, and cell required" }, 400);
        }
        const payload: EoDraftPayload = {
          ...body,
          updated_at: new Date().toISOString(),
        };
        await kvEo.put(eoSessionKey(body.game_id, body.cell, body.session_id), JSON.stringify(payload), {
          expirationTtl: 86400 * 30,
        });
        return json({ ok: true });
      }

      if (sub === "load-draft" && method === "GET") {
        const gameId = url.searchParams.get("game_id") || "table-01";
        const cell = url.searchParams.get("cell") || "blue-cell";
        const sessionId = url.searchParams.get("session_id") || "";
        if (!sessionId) return json({ error: "session_id required" }, 400);
        const raw = await kvEo.get(eoSessionKey(gameId, cell, sessionId));
        if (!raw) return json({ error: "No saved draft" }, 404);
        return json(JSON.parse(raw));
      }

      if (sub === "lobby" && method === "GET") {
        const gameId = url.searchParams.get("game_id") || "table-01";
        const lobby = lobbyPublicView(await loadLobby(kvEo, gameId));
        return json({ lobby });
      }

      if (sub === "finalize" && method === "POST") {
        const body = (await request.json()) as WizardAnswers & {
          eo_data?: { games: { id: string; campaign_id: string; campaign_base_url: string }[] };
          faction_labels?: string[];
        };
        const eoData = body.eo_data;
        if (!eoData?.games?.length) return json({ error: "eo_data.games required" }, 400);
        try {
          const gameId = (body.game_id as string) || "table-01";
          const cell = (body.player_cell as string) || "blue-cell";
          const game = eoData.games.find((g) => g.id === gameId);
          const gameLabel = game?.campaign_id || gameId;
          const factionLabels = Array.isArray(body.faction_labels) ? body.faction_labels : [];

          const { lobby, event, initiated } = await registerLobbyFinalize(
            kvEo,
            gameId,
            cell as Cell,
            body,
            factionLabels,
          );

          const { session, download_key } = await finalizeWizardSession(kvEo, body, eoData);
          const portalTokens = await loadOrCreatePortalTokens(kvEo, gameId, env);
          const uploadToken = portalTokens[cell as "blue-cell" | "red-cell"] || "";

          const blueLatest = await loadLatestCellSession(kvEo, gameId, "blue-cell");
          const redLatest = await loadLatestCellSession(kvEo, gameId, "red-cell");
          const setupBundle: CampaignSetupBundle = {
            game_id: gameId,
            registered_at: new Date().toISOString(),
            blue_session: blueLatest?.session ?? null,
            red_session: redLatest?.session ?? null,
            matchup: lobby.matchup,
            note: "XOai reads game_format from this bundle for blind-aware coach.",
            game_format:
              (body.game_format as string) ||
              (blueLatest?.session?.game_format as string) ||
              (redLatest?.session?.game_format as string) ||
              "double-blind",
          };
          await kvEo.put(campaignSetupKey(gameId), JSON.stringify(setupBundle));

          const portalOrigin = origin(request, env);
          const summary = cell === "blue-cell" ? lobby.blue! : lobby.red!;
          const discordEvent = mapEoEventToDiscord(event);
          await discordNotify(
            env,
            gameId,
            discordEvent,
            eoDiscordPayload(event, gameLabel, summary, lobby, portalOrigin, gameId),
          );

          if (initiated) {
            const campaignId = game?.campaign_id || gameId;
            const state = await loadState(env, gameId, campaignId);
            if (state.status !== "active") {
              state.status = "active";
              state.turn = 1;
              state.active_cell = "blue-cell";
              state.phase = "board";
              await saveState(env, gameId, state);
            }
            await discordNotify(env, gameId, "game.started", {
              title: `Campaign started — ${gameLabel}`,
              description: lobby.matchup || "Both cells completed Executive Officer stand-up.",
              url: `${portalOrigin}/games/${gameId}/`,
              fields: [
                { name: "Turn", value: "1 — waiting for Blue Cell board upload", inline: false },
              ],
            });
          }

          return json({
            ok: true,
            session,
            download_key,
            lobby: lobbyPublicView(lobby),
            initiated,
            waiting_for: lobby.open_cell,
            upload_token: uploadToken,
            player_cell: cell,
            game_page_url: `${portalOrigin}/games/${gameId}/`,
          });
        } catch (err) {
          return json({ error: err instanceof Error ? err.message : "Finalize failed" }, 400);
        }
      }

      if (sub === "latest" && method === "GET") {
        const token = extractBearer(request);
        if (!validateWhiteCell(env, token)) return json({ error: "Unauthorized" }, 401);
        const gameId = url.searchParams.get("game_id") || "table-01";
        const cell = url.searchParams.get("cell") || "blue-cell";
        const raw = await kvEo.get(eoLatestKey(gameId, cell));
        if (!raw) return json({ error: "No finalized session for this cell" }, 404);
        return json(JSON.parse(raw));
      }
    }

    if (parts[0] === "admin" && parts[1] === "tokens") {
      const token = extractBearer(request);
      if (!validateWhiteCell(env, token)) return json({ error: "Unauthorized" }, 401);
      const kvTok = kvOrNull(env);
      if (!kvTok) return json({ error: "PORTAL_KV not configured" }, 503);

      if (method === "GET") {
        const gameId = url.searchParams.get("game_id") || "table-01";
        const tokens = await loadOrCreatePortalTokens(kvTok, gameId, env);
        const stored = await loadPortalTokens(kvTok, gameId);
        return json({
          game_id: gameId,
          source: stored ? "kv" : "env",
          tokens: fullTokenSummary(tokens),
          hint:
            "Use Copy beside each token. Blue/Red tokens upload turns; XOai password works for assistant access. " +
            "White cell may also use this admin passcode on XOai. Regenerate revokes old tokens instantly.",
        });
      }

      if (method === "POST" && (parts[2] === "regenerate" || parts.length === 2)) {
        const body = (await request.json()) as { game_id?: string };
        const gameId = body.game_id || "table-01";
        const tokens = regeneratePortalTokens();
        await savePortalTokens(kvTok, gameId, tokens);
        await discordNotify(env, gameId, "admin.access_granted", {
          title: `Player tokens regenerated — ${gameId}`,
          description: "Copy tokens from the admin page now. Previous tokens are revoked.",
        });
        return json({ ok: true, ...fullTokenPayload(gameId, tokens) });
      }
    }

    return json({ error: "Not found" }, 404);
  } catch (err) {
    console.error(err);
    return json({ error: err instanceof Error ? err.message : "Server error" }, 500);
  }
};