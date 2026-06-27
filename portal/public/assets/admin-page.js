/** White cell admin — set window.WOWC_GAME_ID */

const WHITE_CELL_SESSION_KEY = 'wowc_whitecell_unlocked';

function renderAdminLobbyDetail(container, data) {
  if (!container) return;
  if (!data || data.error) {
    container.innerHTML = '<p class="subtitle">Unlock the admin console to view the XO stand-up lobby.</p>';
    return;
  }
  const { lobby, sessions, setup_registered, game } = data;
  const headline = lobbyStatusHeadline(lobby);
  const cells = [
    { key: 'blue', label: 'Blue Cell', summary: lobby.blue, latest: sessions?.blue },
    { key: 'red', label: 'Red Cell', summary: lobby.red, latest: sessions?.red },
  ];
  const blocks = cells.map(({ label, summary, latest }) => {
    if (!summary && !latest) {
      return `<div class="admin-cell-block"><h3>${label}</h3><p class="subtitle">Not finalized yet.</p></div>`;
    }
    const session = latest?.session || {};
    const warnO = session.warn_o || summary?.warn_o_excerpt || '';
    const opord = session.operation_order || summary?.opord_excerpt || '';
    const factions = (summary?.faction_labels || session.factions || []).join(', ') || '—';
    return `<div class="admin-cell-block">
      <h3>${label}</h3>
      <dl class="eo-review">
        <dt>Commander</dt><dd>${escapeHtmlLite(summary?.commander_name || session.commander_name || '—')}</dd>
        <dt>Force</dt><dd>${escapeHtmlLite(summary?.force_name || session.force_name || '—')}</dd>
        <dt>Factions</dt><dd>${escapeHtmlLite(factions)}</dd>
        <dt>Theater</dt><dd>${escapeHtmlLite(summary?.theater || session.theater || '—')}</dd>
        <dt>Finalized</dt><dd>${escapeHtmlLite(summary?.finalized_at || latest?.at || '—')}</dd>
      </dl>
      ${warnO ? `<h4>WarnO</h4><pre class="admin-excerpt">${escapeHtmlLite(String(warnO))}</pre>` : '<p class="subtitle">No WarnO on file.</p>'}
      ${opord ? `<h4>OpOrd</h4><pre class="admin-excerpt">${escapeHtmlLite(String(opord))}</pre>` : '<p class="subtitle">No OpOrd on file.</p>'}
    </div>`;
  }).join('');

  const setupLine = setup_registered
    ? `<p class="msg ok">Campaign setup registered ${escapeHtmlLite(setup_registered.registered_at || '')}.</p>`
    : '<p class="subtitle">When both cells are done, register setup for export / local apply.</p>';

  container.innerHTML = `
    <p class="subtitle">${escapeHtmlLite(headline)}</p>
    <div class="admin-lobby-grid">${blocks}</div>
    ${setupLine}
    <div class="eo-actions">
      <button type="button" id="lobby-register-setup" class="eo-btn-continue">Register campaign setup</button>
      <button type="button" id="lobby-download-bundle" class="secondary">Download setup bundle</button>
      <button type="button" id="lobby-reset" class="eo-btn-danger">Reset table lobby</button>
    </div>`;
}

function showAdminGate() {
  const gate = document.getElementById('admin-gate');
  const app = document.getElementById('admin-app');
  if (gate) gate.hidden = false;
  if (app) app.hidden = true;
}

function showAdminApp() {
  const gate = document.getElementById('admin-gate');
  const app = document.getElementById('admin-app');
  if (gate) gate.hidden = true;
  if (app) app.hidden = false;
}

async function verifyWhiteCellPasscode(passcode) {
  const gameId = window.WOWC_GAME_ID || 'table-01';
  const res = await fetch(`/api/admin/tokens?game_id=${encodeURIComponent(gameId)}`, {
    headers: { Authorization: `Bearer ${passcode}` },
  });
  if (res.status === 401) return false;
  const data = await res.json().catch(() => ({}));
  return !data.error;
}

async function initAdminPage() {
  const gameId = window.WOWC_GAME_ID;
  if (!gameId) return;

  const passKey = `wowc_whitecell_pass_${gameId}`;
  const gateForm = document.getElementById('admin-gate-form');
  const gateInput = document.getElementById('admin-passcode');
  const gateMsg = document.getElementById('admin-gate-msg');
  const orgToken = document.getElementById('org-token');
  const msgEl = document.getElementById('admin-msg');
  const lobbyDetailEl = document.getElementById('lobby-detail');
  let lobbyAdminData = null;
  let passcode = sessionStorage.getItem(passKey) || '';

  function authHeaders() {
    const t = orgToken?.value?.trim() || passcode;
    return t ? { Authorization: `Bearer ${t}` } : {};
  }

  async function unlockAdmin(code) {
    const ok = await verifyWhiteCellPasscode(code);
    if (!ok) {
      showMsg(gateMsg, 'Incorrect passcode.', 'err');
      return false;
    }
    passcode = code;
    sessionStorage.setItem(passKey, code);
    sessionStorage.setItem(WHITE_CELL_SESSION_KEY, '1');
    if (orgToken) orgToken.value = code;
    showAdminApp();
    await bootstrapAdmin();
    return true;
  }

  gateForm?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const code = gateInput?.value?.trim() || '';
    if (!code) return showMsg(gateMsg, 'Enter the white cell passcode.', 'err');
    await unlockAdmin(code);
  });

  async function refreshStatus() {
    try {
      const state = await fetchGameStatus(gameId);
      const el = document.getElementById('admin-status');
      if (el) {
        const base = formatWaitingLabel(state);
        const mergeLine = formatMergeStatus(state.merge);
        el.innerHTML = mergeLine
          ? `${escapeHtmlLite(base)}<div class="merge-status-line">${escapeHtmlLite(mergeLine)}</div>`
          : escapeHtmlLite(base);
      }
      renderBoardRefreshBanner(document.getElementById('board-refresh-banner'), state.board_refresh, state.merge);
      renderTimeline(document.getElementById('admin-timeline'), state.history);
    } catch (_) {}
  }

  async function refreshLobbyAdmin() {
    if (!passcode) {
      renderAdminLobbyDetail(lobbyDetailEl, null);
      return;
    }
    try {
      const res = await fetch(`/api/games/${encodeURIComponent(gameId)}/lobby/admin`, {
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || res.statusText);
      lobbyAdminData = data;
      renderAdminLobbyDetail(lobbyDetailEl, data);
      wireLobbyButtons();
    } catch (e) {
      if (lobbyDetailEl) lobbyDetailEl.innerHTML = `<p class="msg err">${escapeHtmlLite(e.message)}</p>`;
    }
  }

  function wireLobbyButtons() {
    document.getElementById('lobby-reset')?.addEventListener('click', async () => {
      if (!confirm('Reset this table\'s stand-up lobby? Players will need to run the XO wizard again.')) return;
      const alsoSessions = confirm('Also delete saved XO session files for both cells? (Cancel = lobby only.)');
      try {
        await apiPost(`/api/games/${gameId}/lobby/reset`, { clear_sessions: alsoSessions }, authHeaders());
        showMsg(msgEl, 'Table lobby reset.', 'ok');
        await refreshLobbyAdmin();
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    }, { once: true });

    document.getElementById('lobby-register-setup')?.addEventListener('click', async () => {
      try {
        const data = await apiPost(`/api/games/${gameId}/apply-setup`, {}, authHeaders());
        showMsg(msgEl, 'Campaign setup registered on portal.', 'ok');
        lobbyAdminData = { ...lobbyAdminData, setup_registered: data.bundle };
        renderAdminLobbyDetail(lobbyDetailEl, lobbyAdminData);
        wireLobbyButtons();
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    }, { once: true });

    document.getElementById('lobby-download-bundle')?.addEventListener('click', () => {
      if (!lobbyAdminData?.sessions?.blue?.session || !lobbyAdminData?.sessions?.red?.session) {
        showMsg(msgEl, 'Both cells must complete stand-up before downloading the bundle.', 'err');
        return;
      }
      const bundle = {
        game_id: gameId,
        exported_at: new Date().toISOString(),
        blue_session: lobbyAdminData.sessions.blue.session,
        red_session: lobbyAdminData.sessions.red.session,
        matchup: lobbyAdminData.lobby?.matchup,
        apply_hint: 'python3 scripts/apply_web_setup.py --file <cell>_session.json per player, then publish_portal_site.py --deploy --all-games',
      };
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${gameId}_setup_bundle.json`;
      a.click();
      URL.revokeObjectURL(url);
      showMsg(msgEl, 'Setup bundle downloaded.', 'ok');
    }, { once: true });
  }

  const tokensOut = document.getElementById('token-output');

  async function loadTokenSummary() {
    if (!tokensOut || !passcode) return;
    try {
      const data = await fetch(`/api/admin/tokens?game_id=${encodeURIComponent(gameId)}`, {
        headers: authHeaders(),
      }).then((r) => r.json());
      if (data.error) throw new Error(data.error);
      tokensOut.innerHTML = `
        <p>Source: <strong>${data.source}</strong> (KV overrides env secrets when regenerated)</p>
        <ul>
          <li>Blue Cell: <code>${data.tokens.blue_cell}</code></li>
          <li>Red Cell: <code>${data.tokens.red_cell}</code></li>
          <li>XO Advisor password: <code>${data.tokens.assistant_password}</code></li>
        </ul>
        <p class="subtitle">${data.hint}</p>`;
    } catch (e) {
      tokensOut.innerHTML = `<p class="msg err">${e.message}</p>`;
    }
  }

  async function bootstrapAdmin() {
    document.getElementById('ghost-form')?.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const body = document.getElementById('ghost-aar')?.value?.trim();
      if (!body) return showMsg(msgEl, 'Enter ghost turn AAR text.', 'err');
      try {
        await apiPost(`/api/games/${gameId}/ghost-turn`, { body }, authHeaders());
        showMsg(msgEl, 'Ghost turn posted.', 'ok');
        document.getElementById('ghost-aar').value = '';
        await refreshStatus();
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    });

    document.getElementById('announce-form')?.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const body = document.getElementById('adhoc-aar')?.value?.trim();
      if (!body) return showMsg(msgEl, 'Enter announcement text.', 'err');
      try {
        await apiPost(`/api/games/${gameId}/announce`, { body }, authHeaders());
        showMsg(msgEl, 'Announcement posted.', 'ok');
        document.getElementById('adhoc-aar').value = '';
        await refreshStatus();
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    });

    document.getElementById('lifecycle-start')?.addEventListener('click', async () => {
      try {
        await apiPost(`/api/games/${gameId}/lifecycle`, { action: 'start' }, authHeaders());
        showMsg(msgEl, 'Campaign started.', 'ok');
        await refreshStatus();
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    });

    document.getElementById('lifecycle-end')?.addEventListener('click', async () => {
      try {
        await apiPost(`/api/games/${gameId}/lifecycle`, { action: 'end' }, authHeaders());
        showMsg(msgEl, 'Campaign ended.', 'ok');
        await refreshStatus();
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    });

    document.getElementById('merge-btn')?.addEventListener('click', async () => {
      try {
        showMsg(msgEl, 'Queueing merge jobs…', 'info');
        const data = await apiPost(`/api/games/${gameId}/merge`, {}, authHeaders());
        const count = (data.jobs || []).length;
        const hint = data.triggered
          ? 'Merge runner triggered — board will redeploy shortly.'
          : (data.runner_hint || 'Job queued — start merge_runner_daemon.py or configure GitHub dispatch.');
        showMsg(msgEl, `${count} job(s) queued. ${hint}`, 'ok');
        await refreshStatus();
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    });

    document.getElementById('token-regenerate')?.addEventListener('click', async () => {
      if (!confirm('Regenerate all player tokens for this table? Old tokens stop working immediately.')) return;
      try {
        const data = await apiPost('/api/admin/tokens/regenerate', { game_id: gameId }, authHeaders());
        tokensOut.innerHTML = `
          <p class="msg ok">New tokens — copy now; they will not be shown again in full.</p>
          <ul>
            <li>Blue Cell: <code>${data.blue_cell_token}</code></li>
            <li>Red Cell: <code>${data.red_cell_token}</code></li>
            <li>XO Advisor password: <code>${data.assistant_password}</code></li>
          </ul>`;
        showMsg(msgEl, 'Tokens regenerated and saved to portal KV.', 'ok');
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    });

    await Promise.all([refreshStatus(), refreshLobbyAdmin(), loadTokenSummary()]);
  }

  if (passcode) {
    const ok = await verifyWhiteCellPasscode(passcode);
    if (ok) {
      if (orgToken) orgToken.value = passcode;
      showAdminApp();
      await bootstrapAdmin();
      return;
    }
    sessionStorage.removeItem(passKey);
  }

  showAdminGate();
}

document.addEventListener('DOMContentLoaded', initAdminPage);