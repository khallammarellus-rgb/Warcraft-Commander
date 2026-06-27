/** Per-game portal page — set window.WOWC_GAME_ID before loading */

async function initGamePage() {
  const gameId = window.WOWC_GAME_ID;
  if (!gameId) return;

  const params = new URLSearchParams(location.search);
  const statusEl = document.getElementById('status-label');
  const pillEl = document.getElementById('status-pill');
  const timelineEl = document.getElementById('timeline');
  const lobbyEl = document.getElementById('lobby-panel');
  const msgEl = document.getElementById('form-msg');
  const refreshBannerEl = document.getElementById('board-refresh-banner');
  const mergeStatusEl = document.getElementById('merge-status');
  const uploadForm = document.getElementById('upload-form');
  const tokenInput = document.getElementById('upload-token');
  const cellSelect = document.getElementById('upload-cell');
  const proxyCheck = document.getElementById('proxy-upload');

  const urlCell = params.get('cell');
  const storedRole = urlCell || localStorage.getItem(`wowc_role_${gameId}`) || 'blue-cell';
  if (cellSelect) cellSelect.value = storedRole;
  if (tokenInput) tokenInput.value = getStoredToken(gameId, cellSelect?.value || storedRole);
  if (urlCell) localStorage.setItem(`wowc_role_${gameId}`, urlCell);

  cellSelect?.addEventListener('change', () => {
    localStorage.setItem(`wowc_role_${gameId}`, cellSelect.value);
    if (tokenInput) tokenInput.value = getStoredToken(gameId, cellSelect.value);
  });

  tokenInput?.addEventListener('change', () => {
    setStoredToken(gameId, cellSelect?.value || 'blue-cell', tokenInput.value.trim());
  });

  async function refreshLobby() {
    const lobby = await fetchTableLobbyByGame(gameId);
    renderLobbyPanel(lobbyEl, lobby, gameId, { showJoin: true, compact: true });
  }

  async function refreshStatus() {
    try {
      const [state] = await Promise.all([
        fetchGameStatus(gameId),
        refreshLobby(),
      ]);
      const myCell = cellSelect?.value || storedRole;
      const proxy = proxyCheck?.checked;
      const label = formatPlayerTurnLabel(state, myCell, proxy);
      if (statusEl) statusEl.textContent = label;
      if (pillEl) {
        const isYourTurn = state.status === 'active' && (
          (myCell === state.active_cell && state.phase === 'board' && (myCell === 'blue-cell' || myCell === 'red-cell')) ||
          (proxy && state.phase === 'board' && (state.active_cell === 'blue-cell' || state.active_cell === 'red-cell'))
        );
        pillEl.textContent = isYourTurn ? 'Your turn'
          : (state.active_cell === 'white-cell' && state.phase === 'ghost' ? 'Ghost turn' : (state.active_cell || '').replace('-cell', ''));
        pillEl.className = 'status-pill ' + (isYourTurn ? 'ok' : cellPillClass(state.active_cell, state.phase));
      }
      renderBoardRefreshBanner(refreshBannerEl, state.board_refresh, state.merge);
      if (mergeStatusEl) {
        const mergeLine = formatMergeStatus(state.merge);
        mergeStatusEl.textContent = mergeLine;
        mergeStatusEl.hidden = !mergeLine;
      }
      renderTimeline(timelineEl, state.history);
      if (uploadForm && cellSelect) {
        const isGhost = state.phase === 'ghost';
        const active = state.active_cell;
        const canUpload = state.status === 'active' && (
          (myCell === active && !isGhost && (myCell === 'blue-cell' || myCell === 'red-cell')) ||
          (proxy && (active === 'blue-cell' || active === 'red-cell'))
        );
        const submitBtn = uploadForm.querySelector('button[type=submit]');
        if (submitBtn) {
          submitBtn.disabled = !canUpload;
          submitBtn.textContent = canUpload ? 'Submit turn' : 'Not your turn';
        }
      }
    } catch (e) {
      if (statusEl) statusEl.textContent = 'Status unavailable (API not deployed yet)';
    }
  }

  uploadForm?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    showMsg(msgEl, 'Uploading…', 'info');
    const file = document.getElementById('turn-file')?.files?.[0];
    const token = tokenInput?.value?.trim();
    const cell = cellSelect?.value;
    if (!file || !token) {
      showMsg(msgEl, 'Select a KMZ and enter your upload token.', 'err');
      return;
    }
    const fd = new FormData();
    fd.append('file', file);
    fd.append('token', token);
    fd.append('cell', cell);
    if (proxyCheck?.checked) fd.append('proxy', '1');
    try {
      const data = await apiPostForm(`/api/games/${gameId}/upload`, fd, {
        Authorization: `Bearer ${token}`,
      });
      showMsg(msgEl, `Uploaded ${data.canonical_name}`, 'ok');
      await refreshStatus();
    } catch (e) {
      showMsg(msgEl, e.message, 'err');
    }
  });

  await refreshStatus();
  setInterval(refreshStatus, 30000);
}

document.addEventListener('DOMContentLoaded', initGamePage);