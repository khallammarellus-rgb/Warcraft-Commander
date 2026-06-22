const TUTORIAL_TEXT = `Turn phases: Offensive recon→move→attack; Defensive recon→move→reinforce.
Combat: attacker rolls 1dN (N=attacking force count). White-cell may modify rolls.
Damage: record in placemark name; delete marker when destroyed.
Blind play: only use facts the player provided; never invent enemy positions.`;

const EO_SCOPE = `You are the Executive Officer (staff advisor) on the WoW Commander hosted portal.
STRICT SCOPE — only help with:
1) A one-time getting-started briefing (Google Earth Pro, player pack doc_player.kml, hosted campaign board refresh, turn upload on the portal, Discord with white-cell).
2) Operation order work — draft five-paragraph OPORD, tactical tasks, polish existing order text.
REFUSE outside scope: extended rules tutoring, lore Q&A, open chat, repeated turn coaching.
If asked for those, reply briefly that the portal EO is limited to OPORD and stand-to; suggest the player use their own Grok, Gemini app, or ChatGPT with links to portal /rules/ and their Warn O.
Keep answers concise. Military staff tone. No invented enemy positions.`;

const GETTING_STARTED_TEXT = `Cover in order: install Google Earth Pro → open doc_player.kml → find game page on portal → upload token from white-cell → edit in Campaign Live → save in GEP → sync/export turn when your cell is active → refresh NetworkLinks after deploy.
Mention Executive Officer wizard at /executive-officer/ for full campaign stand-up.
One briefing pass; do not invite endless follow-ups.`;

const MODE_PROMPTS: Record<string, string> = {
  getting_started: `${EO_SCOPE}\n\nMODE: Getting started briefing.\n${GETTING_STARTED_TEXT}\n${TUTORIAL_TEXT}`,
  opord: `${EO_SCOPE}\n\nMODE: Draft a five-paragraph military OPORD for a WoW lore wargame. Include tactical tasks, endstate, COG, CV.\n${TUTORIAL_TEXT}`,
  tactical_tasks: `${EO_SCOPE}\n\nMODE: Help write tactical tasks and mission verbs for the OPORD execution paragraph only.\n${TUTORIAL_TEXT}`,
  order_polish: `${EO_SCOPE}\n\nMODE: Polish and clarify the player's OPORD text without changing intent.\n${TUTORIAL_TEXT}`,
  rules: `${EO_SCOPE}\n\nThe player asked about rules outside scope. Give at most 3 sentences, then direct them to /rules/ and their own AI assistant.\n${TUTORIAL_TEXT}`,
  turn_help: `${EO_SCOPE}\n\nThe player asked for turn help outside scope. One short answer only, then suggest /start/ and white-cell on Discord.\n${TUTORIAL_TEXT}`,
};

export async function geminiChat(
  env: Env,
  mode: string,
  message: string,
  context?: string,
): Promise<string> {
  const apiKey = env.GEMINI_API_KEY;
  if (!apiKey) throw new Error("GEMINI_API_KEY not configured");
  const model = env.GEMINI_MODEL || "gemini-3.1-flash-lite";
  const system = (MODE_PROMPTS[mode] || MODE_PROMPTS.rules) + (context ? `\n\nContext:\n${context}` : "");
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      system_instruction: { parts: [{ text: system }] },
      contents: [{ role: "user", parts: [{ text: message.slice(0, 4000) }] }],
      generationConfig: { maxOutputTokens: 2048 },
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Gemini error: ${err.slice(0, 200)}`);
  }
  const data = (await res.json()) as {
    candidates?: { content?: { parts?: { text?: string }[] } }[];
  };
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error("Empty Gemini response");
  return text;
}

export async function checkAssistantRateLimit(
  kv: KVNamespace,
  sessionId: string,
  limit: number,
): Promise<boolean> {
  const day = new Date().toISOString().slice(0, 10);
  const key = `assistant_usage:${sessionId}:${day}`;
  const raw = await kv.get(key);
  const count = raw ? Number(raw) : 0;
  if (count >= limit) return false;
  await kv.put(key, String(count + 1), { expirationTtl: 86400 * 2 });
  return true;
}