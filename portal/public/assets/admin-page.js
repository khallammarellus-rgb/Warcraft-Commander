/** White cell admin — set window.WOWC_GAME_ID */

const WHITE_CELL_SESSION_KEY = 'wowc_whitecell_unlocked';

function escapeAttr(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;');
}

const TOKEN_ROWS = [
  { id: 'blue', label: 'Blue Cell upload token', key: 'blue_cell', regenKey: 'blue_cell_token' },
  { id: 'red', label: 'Red Cell upload token', key: 'red_cell', regenKey: 'red_cell_token' },
  { id: 'xoai', label: 'XOai / assistant password', key: 'assistant_password', regenKey: 'assistant_password' },
];

function renderTokenPanel(tokens, opts = {}) {
  const { banner = '', source = '', hint = '' } = opts;
  const rows = TOKEN_ROWS.map((row) => {
    const value = tokens[row.regenKey] ?? tokens[row.key] ?? '';
    const fieldId = `token-field-${row.id}`;
    return `
      <div class="token-row">
        <label for="${fieldId}">${row.label}</label>
        <div class="token-copy-row">
          <input type="text" class="token-field" id="${fieldId}" readonly value="${escapeAttr(value)}">
          <button type="button" class="secondary token-copy-btn" data-target="${fieldId}">Copy</button>
        </div>
      </div>`;
  }).join('');

  return `
    ${banner}
    ${source ? `<p>Source: <strong>${source}</strong> (KV overrides env secrets when regenerated)</p>` : ''}
    <div class="token-list">${rows}</div>
    ${hint ? `<p class="subtitle">${hint}</p>` : ''}
    <p class="subtitle">White cell on XOai: you may paste your <strong>admin passcode</strong> (same as this page) instead of the XOai password.</p>`;
}

function bindTokenCopyButtons(root) {
  if (!root) return;
  root.querySelectorAll('.token-copy-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const input = document.getElementById(btn.dataset.target || '');
      if (!input) return;
      const value = input.value;
      let copied = false;
      try {
        await navigator.clipboard.writeText(value);
        copied = true;
      } catch {
        input.focus();
        input.select();
        copied = document.execCommand('copy');
      }
      if (copied) {
        btn.classList.add('copied');
        const prev = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => {
          btn.textContent = prev;
          btn.classList.remove('copied');
        }, 2000);
      }
    });
  });
}

/** @typedef {{ roll_index: number, dice_count: number, dice_sides: number, notation: string, results: number[], total: number, rolled_at: string }} DiceRollEntry */

/**
 * @param {string} formId
 * @param {string} prefix
 */
function setupAarForm(formId, prefix) {
  const form = document.getElementById(formId);
  if (!form || form.dataset.aarEnhanced) return { collectPayload: () => null, reset: () => {} };
  form.dataset.aarEnhanced = '1';

  const oldTextarea = form.querySelector('textarea');
  const submitBtn = form.querySelector('button[type="submit"]');
  if (!oldTextarea || !submitBtn) return { collectPayload: () => null, reset: () => {} };

  const reportId = `${prefix}-report`;
  oldTextarea.id = reportId;
  oldTextarea.placeholder = 'Casualties, effects, rulings, outcome interpretation… (optional)';

  const fragment = document.createDocumentFragment();
  const reasonLabel = document.createElement('label');
  reasonLabel.htmlFor = `${prefix}-reason`;
  reasonLabel.textContent = 'Reason (title)';
  const reasonInput = document.createElement('input');
  reasonInput.type = 'text';
  reasonInput.id = `${prefix}-reason`;
  reasonInput.placeholder = 'e.g. Red ambushes Blue in the defense';
  reasonInput.required = true;

  const rationaleLabel = document.createElement('label');
  rationaleLabel.htmlFor = `${prefix}-rationale`;
  rationaleLabel.textContent = 'Tactical rationale';
  const rationaleArea = document.createElement('textarea');
  rationaleArea.id = `${prefix}-rationale`;
  rationaleArea.placeholder =
    'Explain the situation, modifiers, and how roll outcomes affect play…';
  rationaleArea.required = true;
  rationaleArea.style.minHeight = '6rem';

  const dicePanel = document.createElement('div');
  dicePanel.className = 'dice-panel';
  dicePanel.innerHTML = `
    <label for="${prefix}-dice-count">Dice (nDn)</label>
    <div class="dice-controls">
      <input type="number" id="${prefix}-dice-count" min="1" max="50" value="1" aria-label="Number of dice">
      <span class="dice-notation" id="${prefix}-dice-notation">1d20</span>
      <input type="number" id="${prefix}-dice-sides" min="2" max="1000" value="20" aria-label="Sides per die">
      <button type="button" class="dice-roll-btn">Roll</button>
    </div>
    <div class="dice-log-header">
      <span class="dice-log-title">Dice log</span>
      <button type="button" class="secondary dice-clear-btn" title="Remove all rolls from this report (reason and rationale stay)">Clear dice log</button>
    </div>
    <ul class="dice-log" id="${prefix}-dice-log" aria-live="polite"><li class="dice-log-empty">No rolls yet — adjust dice and roll before publishing.</li></ul>`;

  const reportLabel = document.createElement('label');
  reportLabel.htmlFor = reportId;
  reportLabel.textContent = 'Additional report (optional)';

  fragment.append(reasonLabel, reasonInput, rationaleLabel, rationaleArea, dicePanel, reportLabel);
  form.insertBefore(fragment, oldTextarea);

  /** @type {DiceRollEntry[]} */
  let diceLog = [];
  const countEl = document.getElementById(`${prefix}-dice-count`);
  const sidesEl = document.getElementById(`${prefix}-dice-sides`);
  const notationEl = document.getElementById(`${prefix}-dice-notation`);
  const logEl = document.getElementById(`${prefix}-dice-log`);

  function updateNotation() {
    const n = Math.max(1, parseInt(countEl?.value || '1', 10) || 1);
    const d = Math.max(2, parseInt(sidesEl?.value || '20', 10) || 20);
    if (notationEl) notationEl.textContent = `${n}d${d}`;
  }

  function renderDiceLog() {
    if (!logEl) return;
    if (!diceLog.length) {
      logEl.innerHTML = '<li class="dice-log-empty">No rolls yet — adjust dice and roll before publishing.</li>';
      return;
    }
    logEl.innerHTML = diceLog
      .map(
        (e) =>
          `<li><strong>Roll ${e.roll_index}</strong> — ${escapeHtmlLite(e.notation)} → [${e.results.join(', ')}] (total ${e.total})</li>`,
      )
      .join('');
  }

  countEl?.addEventListener('input', updateNotation);
  sidesEl?.addEventListener('input', updateNotation);
  updateNotation();

  dicePanel.querySelector('.dice-roll-btn')?.addEventListener('click', () => {
    const dice_count = Math.max(1, Math.min(50, parseInt(countEl?.value || '1', 10) || 1));
    const dice_sides = Math.max(2, Math.min(1000, parseInt(sidesEl?.value || '20', 10) || 20));
    const results = [];
    for (let i = 0; i < dice_count; i += 1) {
      results.push(Math.floor(Math.random() * dice_sides) + 1);
    }
    const entry = {
      roll_index: diceLog.length + 1,
      dice_count,
      dice_sides,
      notation: `${dice_count}d${dice_sides}`,
      results,
      total: results.reduce((a, b) => a + b, 0),
      rolled_at: new Date().toISOString(),
    };
    diceLog.push(entry);
    renderDiceLog();
  });

  dicePanel.querySelector('.dice-clear-btn')?.addEventListener('click', () => {
    if (diceLog.length && !confirm(`Clear all ${diceLog.length} roll(s) from the dice log? Reason and rationale will not be changed.`)) {
      return;
    }
    diceLog = [];
    renderDiceLog();
  });

  return {
    collectPayload() {
      const reason = document.getElementById(`${prefix}-reason`)?.value?.trim() || '';
      const tactical_rationale = document.getElementById(`${prefix}-rationale`)?.value?.trim() || '';
      const report = document.getElementById(reportId)?.value?.trim() || '';
      if (!reason) throw new Error('Enter a reason (title) for this report.');
      if (!tactical_rationale) throw new Error('Enter tactical rationale.');
      const payload = { reason, tactical_rationale };
      if (diceLog.length) payload.dice_log = diceLog.map((e) => ({ ...e }));
      if (report) payload.report = report;
      return payload;
    },
    reset() {
      document.getElementById(`${prefix}-reason`).value = '';
      document.getElementById(`${prefix}-rationale`).value = '';
      document.getElementById(reportId).value = '';
      diceLog = [];
      renderDiceLog();
      if (countEl) countEl.value = '1';
      if (sidesEl) sidesEl.value = '20';
      updateNotation();
    },
  };
}

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

/** Keep white cell from manually starting an active campaign (desyncs turn order). */
function updateLifecycleControls(state, lobby) {
  const startBtn = document.getElementById('lifecycle-start');
  const hintEl = document.getElementById('lifecycle-start-hint');
  if (!startBtn) return;

  let disabled = true;
  let hint = 'Campaign auto-starts when Red cell finalizes XO stand-up. Manual start is recovery-only.';

  if (state?.status === 'active') {
    hint = 'Campaign is active — uploads follow the turn log below. Do not click Start again.';
  } else if (state?.status === 'ended') {
    hint = 'Campaign ended. Reset the table lobby or pick another table for a new game.';
  } else if (lobby && lobby.status !== 'both_ready' && lobby.status !== 'active') {
    hint = `${lobbyStatusHeadline(lobby)} — wait for both cells to finish XO stand-up before turns open.`;
  } else if (lobby?.status === 'both_ready' || lobby?.status === 'active') {
    disabled = false;
    hint =
      'Both cells are ready. The campaign should auto-start when Red finalizes. Use Start only if the table still shows “not started”.';
  }

  startBtn.disabled = disabled;
  startBtn.hidden = state?.status === 'active';
  startBtn.title = hint;
  if (hintEl) hintEl.textContent = hint;
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

  let lastTurnState = null;
  let lastLobbyState = null;

  async function refreshStatus() {
    try {
      const state = await fetchGameStatus(gameId);
      lastTurnState = state;
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
      updateLifecycleControls(lastTurnState, lastLobbyState);
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
      lastLobbyState = data?.lobby ?? null;
      renderAdminLobbyDetail(lobbyDetailEl, data);
      wireLobbyButtons();
      updateLifecycleControls(lastTurnState, lastLobbyState);
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
      tokensOut.innerHTML = renderTokenPanel(data.tokens, {
        source: data.source,
        hint: data.hint,
      });
      bindTokenCopyButtons(tokensOut);
    } catch (e) {
      tokensOut.innerHTML = `<p class="msg err">${e.message}</p>`;
    }
  }

  async function bootstrapAdmin() {
    const ghostAar = setupAarForm('ghost-form', 'ghost');
    const adhocAar = setupAarForm('announce-form', 'adhoc');

    document.getElementById('ghost-form')?.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      try {
        const payload = ghostAar.collectPayload();
        await apiPost(`/api/games/${gameId}/ghost-turn`, payload, authHeaders());
        showMsg(msgEl, 'Ghost turn posted to Discord.', 'ok');
        ghostAar.reset();
        await refreshStatus();
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    });

    document.getElementById('announce-form')?.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      try {
        const payload = adhocAar.collectPayload();
        await apiPost(`/api/games/${gameId}/announce`, payload, authHeaders());
        showMsg(msgEl, 'Ad hoc AAR posted to Discord.', 'ok');
        adhocAar.reset();
        await refreshStatus();
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    });

    document.getElementById('lifecycle-start')?.addEventListener('click', async () => {
      if (
        !confirm(
          'Recovery only: campaigns normally auto-start when Red cell finishes XO stand-up. ' +
            'Use Start ONLY if the table still says “not started” after both cells finalized. Continue?',
        )
      ) {
        return;
      }
      try {
        await apiPost(`/api/games/${gameId}/lifecycle`, { action: 'start' }, authHeaders());
        showMsg(msgEl, 'Campaign started.', 'ok');
        await refreshStatus();
      } catch (e) { showMsg(msgEl, e.message, 'err'); }
    });

    document.getElementById('lifecycle-end')?.addEventListener('click', async () => {
      if (!confirm('End this campaign? Turn uploads will be frozen.')) return;
      const purgeIcons = confirm(
        'Delete stored unit icons for this table from portal storage? (Recommended — frees space for the next game.)'
      );
      const purgeArchives = purgeIcons && confirm(
        'Also delete all turn KMZ archives for this table? (Cancel = keep archives, delete icons only.)'
      );
      try {
        const data = await apiPost(
          `/api/games/${gameId}/lifecycle`,
          { action: 'end', purge_icons: purgeIcons, purge_archives: purgeArchives },
          authHeaders(),
        );
        const parts = ['Campaign ended.'];
        if (data.icons_purged?.deleted) {
          parts.push(`${data.icons_purged.deleted} icon(s) purged.`);
        }
        if (data.archives_purged?.deleted) {
          parts.push(`${data.archives_purged.deleted} archive(s) purged.`);
        }
        showMsg(msgEl, parts.join(' '), 'ok');
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
        tokensOut.innerHTML = renderTokenPanel(data, {
          banner: '<p class="msg ok">New tokens issued — use Copy beside each value.</p>',
        });
        bindTokenCopyButtons(tokensOut);
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