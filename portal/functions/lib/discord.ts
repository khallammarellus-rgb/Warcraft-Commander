export type DiscordEvent =
  | "turn.submitted"
  | "turn.merged"
  | "turn.ghost_complete"
  | "aar.adhoc"
  | "game.started"
  | "game.ended"
  | "eo.blue_complete"
  | "eo.red_complete"
  | "eo.wargame_initiated"
  | "admin.access_request"
  | "admin.access_granted"
  | "admin.access_denied"
  | "system.deploy"
  | "system.update";

const COLORS: Record<string, number> = {
  "turn.submitted": 0x5b9bd5,
  "turn.merged": 0x5dce8a,
  "turn.ghost_complete": 0xb8a8e8,
  "aar.adhoc": 0xe8b84a,
  "game.started": 0xc9a227,
  "game.ended": 0x8b9cb3,
  "eo.blue_complete": 0x5b9bd5,
  "eo.red_complete": 0xf07178,
  "eo.wargame_initiated": 0xc9a227,
  "admin.access_request": 0x6eb5ff,
  "admin.access_granted": 0x5dce8a,
  "admin.access_denied": 0xf07178,
  "system.deploy": 0x8b9cb3,
  "system.update": 0x8b9cb3,
};

export interface DiscordPayload {
  title: string;
  description?: string;
  fields?: { name: string; value: string; inline?: boolean }[];
  url?: string;
}

function pickWebhook(env: Env, gameId: string, event: DiscordEvent): string | undefined {
  const gameKey = `DISCORD_WEBHOOK_URL_${gameId.replace(/-/g, "_").toUpperCase()}`;
  const gameSpecific = (env as Record<string, string | undefined>)[gameKey];
  if (gameSpecific) return gameSpecific;
  if (event.startsWith("turn.") && env.DISCORD_WEBHOOK_URL_TURNS) return env.DISCORD_WEBHOOK_URL_TURNS;
  if (event.startsWith("eo.") && env.DISCORD_WEBHOOK_URL_ADMIN) return env.DISCORD_WEBHOOK_URL_ADMIN;
  if ((event.startsWith("admin.") || event.startsWith("aar.")) && env.DISCORD_WEBHOOK_URL_ADMIN) {
    return env.DISCORD_WEBHOOK_URL_ADMIN;
  }
  return env.DISCORD_WEBHOOK_URL;
}

export async function discordNotify(
  env: Env,
  gameId: string,
  event: DiscordEvent,
  payload: DiscordPayload,
): Promise<void> {
  const url = pickWebhook(env, gameId, event);
  if (!url) return;
  try {
    const body = {
      embeds: [
        {
          title: payload.title,
          description: payload.description?.slice(0, 4000),
          url: payload.url,
          color: COLORS[event] ?? 0x8b9cb3,
          fields: payload.fields?.slice(0, 10),
          timestamp: new Date().toISOString(),
        },
      ],
    };
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    console.error("discord_notify_failed", event, err);
  }
}