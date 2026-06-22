/** Build game_session-shaped payload from web Executive Officer wizard answers. */

export interface WizardAnswers {
  game_id?: string;
  theater?: string;
  game_format?: string;
  deploy_mode?: string;
  campaign_base_url?: string;
  player_cell?: string;
  factions?: string[];
  commander_name?: string;
  force_name?: string;
  force_size?: string;
  knowledge_level?: string;
  opord_mode?: string;
  tutorial_completed?: string;
  warn_o?: string;
  operation_order?: string;
  [key: string]: unknown;
}

export function resolveForceName(answers: WizardAnswers): string {
  const designator = (answers.unit_designator as string | undefined)?.trim();
  const nickname = (answers.unit_nickname as string | undefined)?.trim();
  if (designator && nickname) return `${designator} "${nickname}"`;
  if (designator) return designator;
  if (nickname) return nickname;
  const legacy = (answers.force_name as string | undefined)?.trim();
  if (legacy) return legacy;
  const faction = Array.isArray(answers.factions) ? answers.factions[0] : "";
  const echelon = answers.force_size || "battalion";
  if (faction) return `${faction} ${echelon}`;
  return "Task Force";
}

export function hostedBaseForGame(gameId: string, portalBase: string): string {
  return `${portalBase.replace(/\/$/, "")}/games/${gameId}`;
}

export function buildSessionFromAnswers(answers: WizardAnswers, eoData: {
  games: { id: string; campaign_id: string; campaign_base_url: string }[];
}): Record<string, unknown> {
  const gameId = answers.game_id || "table-01";
  const game = eoData.games.find((g) => g.id === gameId);
  const deploy = answers.deploy_mode || "hosted";
  let baseUrl = (answers.campaign_base_url as string) || game?.campaign_base_url || "";
  if (deploy !== "hosted") baseUrl = "";
  else baseUrl = String(baseUrl).replace(/\/$/, "");

  const factions = Array.isArray(answers.factions) ? answers.factions : [];
  if (!factions.length) throw new Error("Select at least one faction");

  let opordText = answers.operation_order as string | undefined;
  let opordMode = answers.opord_mode as string | undefined;
  let opordSections: Record<string, string> | null = null;

  const forceSize = answers.force_size || "battalion";
  const forceName = resolveForceName(answers);

  const knowledge = answers.knowledge_level || "casual";
  const approach = answers.opord_approach as string | undefined;

  if (knowledge === "tactician" && approach === "own") {
    opordText = (answers.opord_share as string) || (answers.operation_order as string) || opordText;
    opordSections = null;
  } else if (knowledge === "tactician" && approach === "scribe") {
    opordMode = undefined;
    opordSections = {};
    for (const [k, v] of Object.entries(answers)) {
      if (k.startsWith("opord_") && k !== "opord_approach" && k !== "opord_share" && typeof v === "string" && v.trim()) {
        opordSections[k] = v.trim();
      }
    }
    opordText = Object.values(opordSections).filter(Boolean).join("\n\n") || undefined;
  } else if (knowledge === "casual") {
    if (approach === "skip") {
      opordMode = "skip";
      opordText = undefined;
    } else {
      opordMode = approach === "ai" ? "ai" : undefined;
      opordText = (answers.operation_order as string) || (answers.opord_share as string) || opordText;
    }
  }

  if (approach === "skip") {
    opordMode = "skip";
    opordText = undefined;
    opordSections = null;
  }

  const title = (answers.commander_title as string | undefined)?.trim();
  const name = (answers.commander_name as string | undefined)?.trim() || "";

  return {
    game_format: answers.game_format || "double-blind",
    campaign_deploy_mode: deploy,
    campaign_base_url: baseUrl,
    theater: answers.theater,
    player_cell: answers.player_cell,
    commander_name: name,
    commander_title: title || null,
    unit_designator: (answers.unit_designator as string) || null,
    unit_nickname: (answers.unit_nickname as string) || null,
    force_name: forceName,
    force_size: forceSize,
    hq_name: `${forceSize} HQ ${forceName}`,
    factions,
    primary_faction: factions[0],
    executive_officer: (answers.executive_officer as string) || null,
    knowledge_level: knowledge,
    opord_mode: opordMode,
    tutorial_completed: answers.tutorial_completed === "yes" || answers.xo_briefing_seen === true,
    warn_o: answers.warn_o || null,
    operation_order: opordText || null,
    opord_sections: opordSections,
    portal_game_id: gameId,
    campaign_id: game?.campaign_id,
  };
}