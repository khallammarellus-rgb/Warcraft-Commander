/** Shared portal client helpers */

async function fetchGamesManifest() {
  const res = await fetch('/games.json');
  if (!res.ok) throw new Error('Failed to load games.json');
  return res.json();
}

async function fetchGameStatus(gameId) {
  const res = await fetch(`/api/games/${encodeURIComponent(gameId)}/status`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function fetchAllLobbies() {
  const res = await fetch('/api/games/lobby');
  if (!res.ok) return { lobbies: [] };
  return res.json();
}

function cellDisplayName(cell) {
  if (cell === 'blue-cell') return 'Blue Cell';
  if (cell === 'red-cell') return 'Red Cell';
  return cell;
}

function lobbyCardMeta(lobby, game) {
  if (!lobby || lobby.status === 'open') {
    return { badge: 'Open', badgeClass: 'open', detail: 'No stand-up in progress', joinHref: null };
  }
  if (lobby.status === 'waiting_blue' || lobby.status === 'waiting_red') {
    const open = lobby.open_cell;
    const taken = lobby.blue || lobby.red;
    const who = taken
      ? `${(taken.faction_labels || []).join(', ') || 'Player'} (${taken.commander_name})`
      : 'Opponent';
    return {
      badge: `Needs ${cellDisplayName(open)}`,
      badgeClass: open === 'blue-cell' ? 'blue' : 'red',
      detail: `${who} stood up — join as ${cellDisplayName(open)}`,
      joinHref: open ? `/executive-officer/?game=${encodeURIComponent(game.id)}&cell=${encodeURIComponent(open)}&join=1` : null,
    };
  }
  if (lobby.status === 'active' || lobby.status === 'both_ready') {
    return {
      badge: 'Active',
      badgeClass: 'active',
      detail: lobby.matchup || 'Both cells ready',
      joinHref: null,
    };
  }
  return { badge: 'Open', badgeClass: 'open', detail: game.campaign_id, joinHref: null };
}

function fetchTableLobbyByGame(gameId) {
  return fetch(`/api/games/${encodeURIComponent(gameId)}/lobby`)
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => data?.lobby || null)
    .catch(() => null);
}

function lobbyStatusHeadline(lobby) {
  if (!lobby || lobby.status === 'open') return 'Stand-up open — either cell may begin.';
  if (lobby.status === 'waiting_blue' || lobby.status === 'waiting_red') {
    const open = lobby.open_cell;
    const taken = lobby.blue || lobby.red;
    const who = taken
      ? `${(taken.faction_labels || []).join(', ')} (${taken.commander_name})`
      : 'Opponent';
    return `Waiting for ${cellDisplayName(open)} — ${who} has stood up.`;
  }
  if (lobby.status === 'active' || lobby.status === 'both_ready') {
    return lobby.matchup ? `Matchup: ${lobby.matchup}` : 'Both cells ready.';
  }
  return '';
}

function renderLobbyPanel(container, lobby, gameId, opts = {}) {
  if (!container) return;
  const { showJoin = true, compact = false } = opts;
  if (!lobby || lobby.status === 'open') {
    container.innerHTML = `<p class="subtitle">${lobbyStatusHeadline(lobby)}</p>
      <p><a href="/executive-officer/?game=${encodeURIComponent(gameId)}">Begin XO stand-up</a></p>`;
    return;
  }
  const rows = [];
  if (lobby.blue) {
    rows.push(`<li><span class="lobby-cell blue">Blue</span> ${escapeHtmlLite(lobby.blue.faction_labels?.join(', ') || '—')} — ${escapeHtmlLite(lobby.blue.commander_name)} · ${escapeHtmlLite(lobby.blue.force_name)}</li>`);
  }
  if (lobby.red) {
    rows.push(`<li><span class="lobby-cell red">Red</span> ${escapeHtmlLite(lobby.red.faction_labels?.join(', ') || '—')} — ${escapeHtmlLite(lobby.red.commander_name)} · ${escapeHtmlLite(lobby.red.force_name)}</li>`);
  }
  let joinHtml = '';
  if (showJoin && lobby.open_cell) {
    const href = `/executive-officer/?game=${encodeURIComponent(gameId)}&cell=${encodeURIComponent(lobby.open_cell)}&join=1`;
    joinHtml = `<p><a class="btn lobby-join" href="${href}">Join as ${cellDisplayName(lobby.open_cell)}</a></p>`;
  }
  container.innerHTML = `
    <p class="subtitle">${lobbyStatusHeadline(lobby)}</p>
    ${rows.length ? `<ul class="lobby-roster">${rows.join('')}</ul>` : ''}
    ${joinHtml}
    ${compact ? '' : `<p class="subtitle">Turn uploads open after both cells complete stand-up and the campaign is active.</p>`}`;
}

function escapeHtmlLite(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function openGameTableWithToken(gameId, cell, token) {
  if (cell) localStorage.setItem(`wowc_role_${gameId}`, cell);
  if (token) setStoredToken(gameId, cell || 'blue-cell', token);
  window.location.href = `/games/${gameId}/`;
}

function renderHubGameCards(manifest, lobbies) {
  const el = document.getElementById('game-cards');
  if (!el) return;
  el.innerHTML = '';
  const lobbyById = Object.fromEntries((lobbies || []).map((l) => [l.game_id, l]));
  for (const g of manifest.games || []) {
    const lobby = lobbyById[g.id];
    const meta = lobbyCardMeta(lobby, g);
    const card = document.createElement('div');
    card.className = 'game-card-wrap';
    const main = document.createElement('a');
    main.className = 'game-card';
    main.href = `/${g.path_prefix}/`;
    main.innerHTML = `<h2>${g.label}</h2><p>${g.campaign_id}</p><p class="subtitle">${meta.detail}</p>`;
    card.appendChild(main);
    const pill = document.createElement('span');
    pill.className = `lobby-pill ${meta.badgeClass}`;
    pill.textContent = meta.badge;
    card.appendChild(pill);
    if (meta.joinHref) {
      const join = document.createElement('a');
      join.className = 'btn lobby-join';
      join.href = meta.joinHref;
      join.textContent = `Join as ${cellDisplayName(lobby.open_cell)}`;
      card.appendChild(join);
    }
    el.appendChild(card);
  }
}

function cellPillClass(activeCell, phase) {
  if (activeCell === 'white-cell' && phase === 'ghost') return 'ghost';
  if (activeCell === 'blue-cell') return 'blue';
  if (activeCell === 'red-cell') return 'red';
  return 'white';
}

function formatWaitingLabel(state) {
  if (!state || state.status === 'ended') return 'Campaign ended';
  if (state.status === 'pending') return 'Campaign not started';
  const turn = state.turn ?? 1;
  const cell = state.active_cell ?? 'blue-cell';
  if (cell === 'white-cell' && state.phase === 'ghost') {
    return `Waiting for White Cell ghost — Turn ${turn}`;
  }
  const label = cell === 'blue-cell' ? 'Blue Cell' : cell === 'red-cell' ? 'Red Cell' : 'White Cell';
  return `Waiting for ${label} — Turn ${turn}`;
}

function formatPlayerTurnLabel(state, myCell, proxy = false) {
  if (!state || state.status === 'ended') return 'Campaign ended';
  if (state.status === 'pending') return 'Campaign not started — stand up via XO wizard';
  const turn = state.turn ?? 1;
  const active = state.active_cell ?? 'blue-cell';
  const isGhost = state.phase === 'ghost';

  if (isGhost) {
    if (myCell === 'white-cell' || proxy) {
      return `Your turn — submit ghost AAR (Turn ${turn})`;
    }
    return `Waiting for White Cell adjudication — Turn ${turn}`;
  }

  if (myCell === 'blue-cell' || myCell === 'red-cell') {
    const myLabel = myCell === 'blue-cell' ? 'Blue Cell' : 'Red Cell';
    const activeLabel = active === 'blue-cell' ? 'Blue Cell' : active === 'red-cell' ? 'Red Cell' : 'White Cell';
    if (proxy && (active === 'blue-cell' || active === 'red-cell')) {
      return `Proxy upload for ${activeLabel} — Turn ${turn}`;
    }
    if (myCell === active) {
      return `Your turn — upload board KMZ (Turn ${turn}, ${myLabel})`;
    }
    return `Waiting for ${activeLabel} — Turn ${turn}`;
  }

  return formatWaitingLabel(state);
}

function formatMergeStatus(merge) {
  if (!merge) return '';
  if (merge.status === 'pending') return 'Board merge queued…';
  if (merge.status === 'running') return 'Merging board and redeploying…';
  if (merge.status === 'failed') return `Merge failed${merge.error ? `: ${merge.error}` : ''}`;
  if (merge.status === 'complete') return 'Board merge complete';
  return '';
}

function renderBoardRefreshBanner(container, boardRefresh, merge) {
  if (!container) return;
  const showRefresh = boardRefresh?.at || merge?.status === 'complete';
  if (!showRefresh) {
    container.hidden = true;
    container.innerHTML = '';
    return;
  }
  const when = boardRefresh?.at || merge?.completed_at || '';
  const file = boardRefresh?.canonical_name || merge?.canonical_name || 'latest turn';
  container.hidden = false;
  container.className = 'board-refresh-banner';
  container.innerHTML = `
    <strong>Board updated</strong> — ${escapeHtmlLite(file)}${when ? ` (${escapeHtmlLite(when)})` : ''}.
    Refresh NetworkLinks in Google Earth Pro (right-click the campaign folder → Refresh).`;
}

function showMsg(el, text, kind = 'info') {
  if (!el) return;
  el.className = `msg ${kind}`;
  el.textContent = text;
  el.hidden = !text;
}

function getStoredToken(gameId, role) {
  return localStorage.getItem(`wowc_token_${gameId}_${role}`) || '';
}

function setStoredToken(gameId, role, token) {
  if (token) localStorage.setItem(`wowc_token_${gameId}_${role}`, token);
  else localStorage.removeItem(`wowc_token_${gameId}_${role}`);
}

async function apiPost(path, body, headers = {}) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { error: text }; }
  if (!res.ok) throw new Error(data.error || text || res.statusText);
  return data;
}

async function apiPostForm(path, formData, headers = {}) {
  const res = await fetch(path, { method: 'POST', body: formData, headers });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { error: text }; }
  if (!res.ok) throw new Error(data.error || text || res.statusText);
  return data;
}

function renderTimeline(container, history) {
  if (!container) return;
  container.innerHTML = '';
  if (!history || !history.length) {
    container.innerHTML = '<li class="muted">No turns recorded yet.</li>';
    return;
  }
  for (const entry of [...history].reverse()) {
    const li = document.createElement('li');
    const name = entry.canonical_name || entry.type || 'event';
    const when = entry.uploaded_at || entry.posted_at || '';
    li.textContent = `${name}${when ? ' — ' + when : ''}`;
    if (entry.proxy) li.textContent += ' (white proxy)';
    if (entry.merged_at) li.textContent += ' ✓ merged';
    container.appendChild(li);
  }
}