export type Cell = "blue-cell" | "red-cell" | "white-cell";
export type Phase = "board" | "ghost";
export type CampaignStatus = "pending" | "active" | "ended";

export interface TurnLogEntry {
  type: string;
  turn: number;
  cell?: Cell;
  canonical_name?: string;
  original_filename?: string;
  uploaded_at: string;
  uploaded_by?: Cell | "white-cell";
  proxy?: boolean;
  proxy_for?: Cell;
  merged_at?: string;
  body_excerpt?: string;
}

export interface TurnState {
  campaign_id: string;
  turn: number;
  active_cell: Cell;
  phase: Phase;
  first_mover: Cell;
  status: CampaignStatus;
  history: TurnLogEntry[];
}

export function initialState(campaignId: string): TurnState {
  return {
    campaign_id: campaignId,
    turn: 1,
    active_cell: "blue-cell",
    phase: "board",
    first_mover: "blue-cell",
    status: "pending",
    history: [],
  };
}

export function cellLabel(cell: Cell): string {
  if (cell === "blue-cell") return "BlueCell";
  if (cell === "red-cell") return "RedCell";
  return "WhiteCell";
}

export function canonicalBoardName(campaignId: string, turn: number, cell: Cell): string {
  return `${campaignId}_Turn${turn}_${cellLabel(cell)}.kmz`;
}

export function canonicalGhostName(campaignId: string, turn: number): string {
  return `${campaignId}_Turn${turn}_WhiteCell_Ghost.aar`;
}

export function archiveKey(gameId: string, filename: string): string {
  return `games/${gameId}/archive/${filename}`;
}

export function stateKey(gameId: string): string {
  return `turn_state:${gameId}`;
}

export function advanceAfterBoardUpload(state: TurnState, cell: Cell): TurnState {
  const next = { ...state, history: [...state.history] };
  if (cell === "blue-cell") {
    next.active_cell = "red-cell";
    next.phase = "board";
  } else if (cell === "red-cell") {
    next.active_cell = "white-cell";
    next.phase = "ghost";
  }
  return next;
}

export function advanceAfterGhost(state: TurnState): TurnState {
  return {
    ...state,
    turn: state.turn + 1,
    active_cell: "blue-cell",
    phase: "board",
    history: [...state.history],
  };
}

function boardUploadsForTurn(state: TurnState, turn: number): { blue: boolean; red: boolean } {
  const uploads = state.history.filter((h) => h.type === "board_upload" && h.turn === turn);
  return {
    blue: uploads.some((h) => h.cell === "blue-cell"),
    red: uploads.some((h) => h.cell === "red-cell"),
  };
}

/** Derive active_cell/phase from history when KV state drifted (e.g. after lifecycle start). */
export function reconcileTurnState(state: TurnState): { state: TurnState; changed: boolean } {
  if (state.status !== "active") return { state, changed: false };

  const turn = state.turn;
  const { blue: blueDone, red: redDone } = boardUploadsForTurn(state, turn);
  const ghostDone = state.history.some((h) => h.type === "ghost_turn" && h.turn === turn);

  const next = { ...state };
  let changed = false;

  if (state.phase === "ghost") {
    if (!ghostDone && blueDone && redDone) {
      if (next.active_cell !== "white-cell" || next.phase !== "ghost") {
        next.active_cell = "white-cell";
        next.phase = "ghost";
        changed = true;
      }
    }
  } else {
    if (!blueDone) {
      if (next.active_cell !== "blue-cell" || next.phase !== "board") {
        next.active_cell = "blue-cell";
        next.phase = "board";
        changed = true;
      }
    } else if (!redDone) {
      if (next.active_cell !== "red-cell" || next.phase !== "board") {
        next.active_cell = "red-cell";
        next.phase = "board";
        changed = true;
      }
    } else if (!ghostDone) {
      if (next.active_cell !== "white-cell" || next.phase !== "ghost") {
        next.active_cell = "white-cell";
        next.phase = "ghost";
        changed = true;
      }
    }
  }

  return { state: next, changed };
}

export function canAcceptBoardUpload(
  state: TurnState,
  cell: Cell,
  proxy: boolean,
): { ok: boolean; error?: string } {
  if (state.status !== "active") return { ok: false, error: "Campaign is not active" };
  if (state.phase === "ghost") {
    return { ok: false, error: "Ghost turn in progress — white cell must submit AAR first" };
  }
  if (cell !== "blue-cell" && cell !== "red-cell") {
    return { ok: false, error: "Board uploads are for blue or red cell only" };
  }
  if (!proxy && state.active_cell !== cell) {
    const waiting =
      state.active_cell === "blue-cell" ? "Blue Cell" : state.active_cell === "red-cell" ? "Red Cell" : "White Cell";
    return { ok: false, error: `Waiting for ${waiting} — Turn ${state.turn}` };
  }
  if (proxy && state.active_cell !== cell) {
    return { ok: false, error: `Proxy upload must target active cell (${state.active_cell})` };
  }
  const existing = state.history.find(
    (h) => h.turn === state.turn && h.cell === cell && h.type === "board_upload",
  );
  if (existing) {
    return { ok: false, error: `${cellLabel(cell)} already submitted Turn ${state.turn}` };
  }
  return { ok: true };
}

export function canAcceptGhost(state: TurnState): { ok: boolean; error?: string } {
  if (state.status !== "active") return { ok: false, error: "Campaign is not active" };
  if (state.phase !== "ghost" || state.active_cell !== "white-cell") {
    return { ok: false, error: "Not waiting for white cell ghost turn" };
  }
  const existing = state.history.find(
    (h) => h.turn === state.turn && h.type === "ghost_turn",
  );
  if (existing) return { ok: false, error: `Ghost turn already submitted for Turn ${state.turn}` };
  return { ok: true };
}