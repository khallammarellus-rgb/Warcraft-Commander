/** Executive Officer (XO) web campaign stand-up wizard */

const OSMEAC_IDS = [
  'opord_orientation',
  'opord_situation',
  'opord_mission',
  'opord_execution',
  'opord_admin',
  'opord_command',
];

const OSMEAC_LABELS = {
  opord_orientation: 'Orientation',
  opord_situation: 'Situation',
  opord_mission: "Mission / Commander's Intent",
  opord_execution: 'Execution / Tasking Order',
  opord_admin: 'Administration & Logistics',
  opord_command: 'Command & Signal',
};

const STEP_ORDER = [
  'welcome',
  'knowledge_level',
  'faction_menu',
  'commander_intro',
  'warn_o',
  'theater',
  'force_size',
  'unit_identity',
  'opord_approach',
  'opord_share',
  'opord_casual',
  ...OSMEAC_IDS,
  'xo_briefing',
  'review_confirm',
  'game_format',
  'deploy_mode',
  'campaign_base_url',
  'player_cell',
  'game_id',
  'finalize_setup',
  'review_edit',
];

function commanderAddress(a, fallback = 'Commander') {
  const title = (a.commander_title || '').trim();
  const name = (a.commander_name || '').trim();
  if (title && name) return `${title} ${name}`;
  if (name) return name;
  return fallback;
}

function xoName(data, answers) {
  const factions = answers.factions || [];
  if (!factions.length) return 'Your XO';
  return data.executive_officers?.[factions[0]] || 'XO';
}

function factionLabel(data, id) {
  for (const cat of Object.keys(data.factions_by_category || {})) {
    const hit = data.factions_by_category[cat].find((f) => f.id === id);
    if (hit) return hit.label;
  }
  return id;
}

function resolvedForceName(data, answers) {
  const d = (answers.unit_designator || '').trim();
  const n = (answers.unit_nickname || '').trim();
  if (d && n) return `${d} "${n}"`;
  if (d) return d;
  if (n) return n;
  const f = answers.factions?.[0];
  const e = answers.force_size || '';
  if (f && e) return `${factionLabel(data, f)} ${e}`;
  if (f) return factionLabel(data, f);
  return '(default: faction + echelon)';
}

function stepVisible(id, a) {
  if (id === 'welcome' || id === 'review_edit') return id === 'welcome' || id === 'review_edit';
  if (id === 'campaign_base_url') return a.deploy_mode === 'hosted';
  if (id === 'opord_share') return a.knowledge_level === 'tactician' && a.opord_approach === 'own';
  if (id === 'opord_casual') return a.knowledge_level === 'casual' && a.opord_approach !== 'skip';
  if (OSMEAC_IDS.includes(id)) return a.knowledge_level === 'tactician' && a.opord_approach === 'scribe';
  if (id === 'finalize_setup') return !!a.game_id;
  return true;
}

function sessionId() {
  const key = 'wowc_eo_session_id';
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID?.() || String(Date.now());
    localStorage.setItem(key, id);
  }
  return id;
}

function draftKey(gameId, cell) {
  return `wowc_eo_draft_${gameId}_${cell || 'pending'}`;
}

function defaultHostedUrl(data, gameId) {
  const game = (data.games || []).find((g) => g.id === gameId);
  return game?.campaign_base_url || `${data.hosted_portal_base}/games/${gameId}`;
}

function draftPayload(answers, index) {
  return { answers, index, savedAt: Date.now() };
}

function saveLocalDraft(answers, index = 0) {
  localStorage.setItem(
    draftKey(answers.game_id, answers.player_cell),
    JSON.stringify(draftPayload(answers, index)),
  );
}

function loadLocalDraft(gameId, cell) {
  try {
    const raw = localStorage.getItem(draftKey(gameId, cell || 'pending'));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && parsed.answers) return parsed;
    return { answers: parsed, index: 0, savedAt: null };
  } catch { return null; }
}

function clearLocalDraft(gameId, cell) {
  localStorage.removeItem(draftKey(gameId, cell || 'pending'));
}

function clearAllEoDrafts() {
  const keys = [];
  for (let i = 0; i < localStorage.length; i += 1) {
    const k = localStorage.key(i);
    if (k && k.startsWith('wowc_eo_draft_')) keys.push(k);
  }
  keys.forEach((k) => localStorage.removeItem(k));
}

function hasMeaningfulDraft(draft) {
  if (!draft?.answers) return false;
  const a = draft.answers;
  return !!(
    a.knowledge_level
    || (a.factions && a.factions.length)
    || a.commander_name
    || a.warn_o
    || a.theater
    || a.force_size
    || a.unit_designator
    || a.unit_nickname
    || a.opord_approach
    || a.operation_order
    || a.casual_opord_prompt
    || OSMEAC_IDS.some((id) => a[id])
  );
}

function formatSavedAt(ts) {
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleString();
  } catch { return ''; }
}

function cellDisplayName(cell) {
  if (cell === 'blue-cell') return 'Blue Cell';
  if (cell === 'red-cell') return 'Red Cell';
  return cell;
}

async function fetchTableLobby(gameId) {
  if (!gameId) return null;
  const res = await fetch(`/api/executive-officer/lobby?game_id=${encodeURIComponent(gameId)}`);
  if (!res.ok) return null;
  const data = await res.json();
  return data.lobby || null;
}

async function saveDraftRemote(answers) {
  await apiPost('/api/executive-officer/save-draft', {
    session_id: sessionId(),
    game_id: answers.game_id || 'table-01',
    cell: answers.player_cell || 'blue-cell',
    answers,
  }).catch(() => {});
}

function briefingFor(stepId, data, answers) {
  const addr = commanderAddress(answers, '…');
  const b = data.briefings || {};
  const map = {
    welcome: b.welcome || 'Commander — stand to for campaign setup.',
    knowledge_level: 'How hands-on should your XO be?',
    faction_menu: 'Pick the faction(s) you will be commanding. This will give you access to the appropriate force identifiers and markers to place on your gameboard.',
    commander_intro: "Greetings, uh… sorry, I don't think we formally met. I am your Executive Officer — your XO. You must be…?",
    warn_o: "Upload your Warning Order (WarnO) from your Higher Command. This will be used to help build your Operational Order (OpOrd) which sets up the game and helps facilitate play and tactics throughout turns. Don't worry if you don't have it now — you can deliver it later to me.",
    theater: `Where is our Area of Operations?\n\n*(This information will be added to the skeleton of your operational order.)*`,
    force_size: `How many PAX, ${addr}? Hopefully the brass gives us enough.\n\n*(The echelon you choose doctrinally represents the size of your force, but it could be larger or smaller. For example, a Platoon might be 36 people doctrinally — but if your force is 50, it's better to choose Platoon than Company as it's closer in size.)*`,
    unit_identity: 'You have any unit designator or nickname for the troops? Both fields are optional — if left blank, default is faction and echelon.',
    opord_approach: answers.knowledge_level === 'tactician'
      ? `Very well ${addr}, I think it's time to cut the order for the troops, hmm?`
      : `I can help throw this together for you, boss — just let me know how you want to proceed.`,
    opord_share: 'Paste your OpOrd or share a link (Google Doc, etc.).',
    opord_casual: 'Describe the basics for your OpOrd, or paste from an external AI. WarnO reference is on the left if you uploaded one.',
    xo_briefing: 'Review the stand-to workflow on the right. Acknowledge when you are ready to continue.',
    review_confirm: "Let's go over the plan, shall we, Commander?",
    game_format: 'Blind mode controls who sees enemy markers on turn export.\n\n· no-blind — both sides see everything\n· single-blind — red-cell sees all; blue-cell filtered\n· double-blind — both sides filtered',
    deploy_mode: 'How will players sync campaign markers between turns?',
    campaign_base_url: 'Hosted campaign board URL for this table (no trailing slash).',
    player_cell: 'Which cell are you? Blind play filters by cell folder — not WoW faction.',
    game_id: 'Select your wargame table on the hosted portal.',
    finalize_setup: 'Admin complete — finalize when ready.',
    review_edit: 'Pick a step to change.',
  };
  if (OSMEAC_IDS.includes(stepId)) {
    const sec = (data.tactician_sections || []).find((s) => s.step_id === stepId);
    return sec?.briefing || OSMEAC_LABELS[stepId];
  }
  if (stepId === 'theater' && answers.commander_name) {
    return `${addr}, where is our Area of Operations?\n\n*(This information will be added to the skeleton of your operational order.)*`;
  }
  if (stepId === 'force_size' && answers.commander_name) {
    return map.force_size;
  }
  return map[stepId] || '';
}

function titleFor(stepId, data, answers) {
  const addr = commanderAddress(answers, 'Commander');
  const titles = {
    welcome: 'Stand to',
    knowledge_level: 'Experience level',
    faction_menu: 'Faction',
    commander_intro: 'Introductions',
    warn_o: 'Did the boss cut the Warning Order yet?',
    theater: `${addr}, where is our Area of Operations?`,
    force_size: `How many PAX, ${addr}?`,
    unit_identity: 'Unit designator & nickname',
    opord_approach: 'Cut the order',
    opord_share: 'Share your OpOrd',
    opord_casual: 'OpOrd assistance',
    xo_briefing: 'Stand-to briefing',
    review_confirm: 'Confirm your plan',
    game_format: 'Blind mode',
    deploy_mode: 'Campaign sync',
    campaign_base_url: 'Hosted base URL',
    player_cell: 'Your cell',
    game_id: 'Wargame table',
    finalize_setup: 'Finalize',
    review_edit: 'Change a selection',
  };
  return OSMEAC_LABELS[stepId] || titles[stepId] || stepId;
}

function phaseFor(stepId) {
  if (['welcome', 'knowledge_level', 'faction_menu', 'commander_intro'].includes(stepId)) return 'Phase I · Command';
  if (['warn_o', 'theater', 'force_size', 'unit_identity'].includes(stepId)) return 'Phase II · Battlespace';
  if (stepId.startsWith('opord_') || stepId === 'opord_approach' || stepId === 'opord_casual' || stepId === 'opord_share') return 'Phase III · Orders (OSMEAC)';
  if (stepId === 'xo_briefing') return 'Phase IV · Briefing';
  if (stepId === 'review_confirm' || stepId === 'review_edit') return 'Review';
  if (['game_format', 'deploy_mode', 'campaign_base_url', 'player_cell', 'game_id', 'finalize_setup'].includes(stepId)) return 'Phase V · Admin';
  return '';
}

function trackEntries(data, answers) {
  const rows = [];
  const add = (k, v) => { if (v != null && String(v).trim()) rows.push([k, String(v).trim()]); };
  if (answers.knowledge_level) {
    add('XO style', answers.knowledge_level === 'tactician' ? 'Hands off' : 'Hands on');
  }
  if (answers.factions?.length) {
    add('Factions', answers.factions.map((f) => factionLabel(data, f)).join(', '));
    if (answers.factions.length) add('XO', xoName(data, answers));
  }
  if (answers.commander_name) {
    add('Commander', commanderAddress(answers));
  }
  if (answers.warn_o) add('WarnO', answers.warn_o.slice(0, 80) + (answers.warn_o.length > 80 ? '…' : ''));
  if (answers.theater) {
    const t = (data.theaters || []).find((x) => x.id === answers.theater);
    add('AO', t?.label || answers.theater);
  }
  if (answers.force_size) add('Echelon', answers.force_size);
  add('Unit', resolvedForceName(data, answers));
  if (answers.opord_approach) add('OpOrd', answers.opord_approach);
  if (answers.game_format) add('Blind', answers.game_format);
  if (answers.deploy_mode) add('Sync', answers.deploy_mode);
  if (answers.player_cell) add('Cell', answers.player_cell);
  if (answers.game_id) {
    const g = (data.games || []).find((x) => x.id === answers.game_id);
    add('Table', g?.label || answers.game_id);
  }
  return rows;
}

class EoWizard {
  constructor(data) {
    this.data = data;
    this.steps = STEP_ORDER;
    this.index = 0;
    this.answers = {
      game_id: new URLSearchParams(location.search).get('game') || '',
      player_cell: new URLSearchParams(location.search).get('cell') || '',
      deploy_mode: 'hosted',
      game_format: 'double-blind',
      factions: [],
    };
    this.savedDraft = loadLocalDraft(this.answers.game_id, this.answers.player_cell);
    if (!hasMeaningfulDraft(this.savedDraft)) this.savedDraft = null;
    this.lastSavedAt = this.savedDraft?.savedAt || null;
    if (!this.answers.campaign_base_url && this.answers.game_id) {
      this.answers.campaign_base_url = defaultHostedUrl(data, this.answers.game_id);
    }
    this.editingFromReview = false;
    this.finalized = false;
    this.toolbarBound = false;
    this.toastTimer = null;
    this.lobby = null;
    this.joinMode = new URLSearchParams(location.search).get('join') === '1';
    this.forcedCell = null;
  }

  async loadLobby() {
    if (!this.answers.game_id) {
      this.lobby = null;
      return;
    }
    this.lobby = await fetchTableLobby(this.answers.game_id);
    this.applyLobbyConstraints();
  }

  applyLobbyConstraints() {
    const params = new URLSearchParams(location.search);
    const urlCell = params.get('cell');
    if (urlCell === 'blue-cell' || urlCell === 'red-cell') {
      this.forcedCell = urlCell;
      this.answers.player_cell = urlCell;
      return;
    }
    if (this.joinMode && this.lobby?.open_cell) {
      this.forcedCell = this.lobby.open_cell;
      this.answers.player_cell = this.lobby.open_cell;
    }
  }

  lobbySummaryLine() {
    if (!this.lobby) return '';
    if (this.lobby.status === 'active' || this.lobby.status === 'both_ready') {
      return this.lobby.matchup ? `Active: ${this.lobby.matchup}` : 'Both cells ready — wargame initiated.';
    }
    if (this.lobby.open_cell) {
      const taken = this.lobby.blue || this.lobby.red;
      const who = taken
        ? `${taken.faction_labels?.join(', ') || 'Opponent'} (${taken.commander_name})`
        : 'Opponent';
      return `Waiting for ${cellDisplayName(this.lobby.open_cell)} — ${who} has stood up.`;
    }
    return 'Table open — first player picks either cell.';
  }

  visibleSteps() {
    return this.steps.filter((id) => stepVisible(id, this.answers) && id !== 'review_edit');
  }

  currentStepId() {
    return this.visibleSteps()[this.index] || 'finalize_setup';
  }

  syncForceName() {
    this.answers.force_name = resolvedForceName(this.data, this.answers);
  }

  updateChrome() {
    const id = this.currentStepId();
    const hasFaction = (this.answers.factions || []).length > 0;
    document.getElementById('eo-officer-name').textContent = hasFaction ? xoName(this.data, this.answers) : 'XO';
    document.getElementById('eo-briefing').textContent = briefingFor(id, this.data, this.answers);
    document.getElementById('eo-phase').textContent = phaseFor(id);
    const vis = this.visibleSteps();
    const pct = Math.round(((this.index + 1) / vis.length) * 100);
    document.getElementById('eo-progress-bar').style.width = `${pct}%`;
    this.renderSidebarTrack();
    this.updateToolbar();
  }

  updateToolbar() {
    const bar = document.getElementById('eo-toolbar');
    if (!bar) return;
    bar.hidden = this.finalized;
    if (this.finalized) return;
    if (!this.toolbarBound) {
      document.getElementById('eo-save-btn')?.addEventListener('click', () => this.saveProgress(true));
      document.getElementById('eo-clear-btn')?.addEventListener('click', () => this.clearAllFields());
      this.toolbarBound = true;
    }
    this.updateSaveStatus();
  }

  updateSaveStatus() {
    const el = document.getElementById('eo-save-status');
    if (!el) return;
    if (this.lastSavedAt) {
      el.textContent = `Last saved ${formatSavedAt(this.lastSavedAt)}`;
    } else if (this.savedDraft?.savedAt) {
      el.textContent = `Saved progress available (${formatSavedAt(this.savedDraft.savedAt)})`;
    } else {
      el.textContent = 'Progress auto-saves as you go';
    }
  }

  saveProgress(showToast = false) {
    saveLocalDraft(this.answers, this.index);
    this.lastSavedAt = Date.now();
    saveDraftRemote(this.answers);
    this.updateSaveStatus();
    if (showToast) this.showToast(`Progress saved — ${formatSavedAt(this.lastSavedAt)}`);
  }

  showToast(message) {
    const el = document.getElementById('eo-toast');
    if (!el) return;
    if (this.toastTimer) clearTimeout(this.toastTimer);
    el.textContent = message;
    el.hidden = false;
    el.classList.remove('eo-toast-out');
    this.toastTimer = setTimeout(() => {
      el.classList.add('eo-toast-out');
      setTimeout(() => { el.hidden = true; }, 250);
    }, 3200);
  }

  clearAllFields() {
    if (!confirm('Clear all fields and saved progress? This cannot be undone.')) return;
    this.resetAnswers();
    clearLocalDraft(this.answers.game_id, this.answers.player_cell);
    clearAllEoDrafts();
    this.savedDraft = null;
    this.lastSavedAt = null;
    this.index = 0;
    this.editingFromReview = false;
    this.showToast('All fields cleared — starting fresh.');
    this.render();
  }

  resetAnswers() {
    const gameId = this.answers.game_id;
    const cell = this.answers.player_cell;
    this.answers = {
      game_id: gameId,
      player_cell: cell,
      deploy_mode: 'hosted',
      game_format: 'double-blind',
      factions: [],
    };
    if (gameId) {
      this.answers.campaign_base_url = defaultHostedUrl(this.data, gameId);
    }
  }

  resumeDraft() {
    if (!this.savedDraft) return;
    Object.assign(this.answers, this.savedDraft.answers);
    if (!this.answers.campaign_base_url && this.answers.game_id) {
      this.answers.campaign_base_url = defaultHostedUrl(this.data, this.answers.game_id);
    }
    const vis = this.visibleSteps();
    let idx = typeof this.savedDraft.index === 'number' ? this.savedDraft.index : 1;
    if (idx < 0 || idx >= vis.length) idx = 1;
    if (vis[idx] === 'welcome') idx = Math.min(1, vis.length - 1);
    this.index = idx;
    this.lastSavedAt = this.savedDraft.savedAt || Date.now();
    this.savedDraft = null;
    this.render();
  }

  startFresh() {
    if (!confirm('Start fresh and discard saved progress?')) return;
    clearLocalDraft(this.answers.game_id, this.answers.player_cell);
    clearAllEoDrafts();
    this.savedDraft = null;
    this.lastSavedAt = null;
    this.resetAnswers();
    this.index = 0;
    this.render();
  }

  renderSidebarTrack() {
    const el = document.getElementById('eo-sidebar-track');
    const label = document.getElementById('eo-track-label');
    if (!el) return;
    const rows = trackEntries(this.data, this.answers);
    if (label) label.hidden = !rows.length;
    if (!rows.length) {
      el.innerHTML = '<p class="eo-track-empty">Selections appear here as you proceed.</p>';
      return;
    }
    el.innerHTML = rows.map(([k, v]) => `<div class="eo-track-row"><span>${k}</span><strong>${escapeHtml(v)}</strong></div>`).join('');
  }

  render() {
    this.syncForceName();
    this.updateChrome();
    const panel = document.getElementById('eo-panel');
    const id = this.currentStepId();
    panel.innerHTML = `<h2>${titleFor(id, this.data, this.answers)}</h2>`;
    const body = document.createElement('div');

    switch (id) {
      case 'welcome': {
        const lobbyLine = this.lobbySummaryLine();
        const joinLine = this.joinMode && this.forcedCell
          ? `<p class="subtitle eo-join-banner">Joining as <strong>${cellDisplayName(this.forcedCell)}</strong>${this.answers.game_id ? ` on ${this.answers.game_id}` : ''}.</p>`
          : '';
        if (this.savedDraft) {
          const when = this.savedDraft.savedAt ? formatSavedAt(this.savedDraft.savedAt) : 'earlier';
          body.innerHTML = `${joinLine}<p class="subtitle">Saved progress found (${when}). Resume where you left off, or start fresh.</p>${lobbyLine ? `<p class="subtitle">${lobbyLine}</p>` : ''}`;
          body.appendChild(this.choiceBtn('resume', 'Resume stand-up', 'Restore your answers and continue.', () => this.resumeDraft()));
          body.appendChild(this.choiceBtn('fresh', 'Start fresh', 'Discard saved progress and begin again.', () => this.startFresh()));
        } else {
          body.innerHTML = `${joinLine}<p class="subtitle">When you are ready, Commander. Use <strong>Save progress</strong> anytime before closing the page.</p>${lobbyLine ? `<p class="subtitle">${lobbyLine}</p>` : ''}`;
          body.appendChild(this.continueBtn(this.joinMode ? `Begin ${cellDisplayName(this.forcedCell || 'stand-up')}` : 'Begin stand-up', () => this.advance()));
        }
        break;
      }

      case 'knowledge_level':
        body.appendChild(this.choiceBtn('tactician', 'Tactician', 'XO assists more hands off.', () => {
          this.answers.knowledge_level = 'tactician';
          this.advance();
        }));
        body.appendChild(this.choiceBtn('casual', 'Casual', 'XO is a hands on advisor.', () => {
          this.answers.knowledge_level = 'casual';
          this.advance();
        }));
        break;

      case 'faction_menu':
        this.renderFactionMenu(body);
        break;

      case 'commander_intro':
        body.appendChild(this.field('Name', 'commander_name', { required: true, placeholder: 'Your name' }));
        body.appendChild(this.field('Title (optional)', 'commander_title', {
          placeholder: 'Title',
          hint: '(Commander, General, Marshal, Acolyte, etc.)',
        }));
        body.appendChild(this.continueRow(() => {
          this.answers.commander_name = document.getElementById('fld-commander_name')?.value?.trim() || '';
          this.answers.commander_title = document.getElementById('fld-commander_title')?.value?.trim() || '';
          if (!this.answers.commander_name) { alert('Name is required.'); return; }
          this.advance();
        }));
        break;

      case 'warn_o':
        body.appendChild(this.textareaField('warn_o', 'Paste WarnO here (optional — deliver later if needed)', false));
        body.appendChild(this.continueRow(() => {
          this.answers.warn_o = document.getElementById('fld-warn_o')?.value?.trim() || null;
          this.advance();
        }));
        break;

      case 'theater':
        for (const t of this.data.theaters || []) {
          body.appendChild(this.choiceBtn(t.id, t.label, null, () => {
            this.answers.theater = t.id;
            this.advance();
          }));
        }
        break;

      case 'force_size':
        body.appendChild(this.forceSizeTable());
        for (const s of this.data.force_sizes || []) {
          const spec = this.data.force_specs?.[s];
          const hint = spec ? `~${spec.strength} PAX · ${spec.tier}` : '';
          body.appendChild(this.choiceBtn(s, s.charAt(0).toUpperCase() + s.slice(1), hint, () => {
            this.answers.force_size = s;
            this.advance();
          }));
        }
        break;

      case 'unit_identity':
        body.appendChild(this.field('Unit designator (optional)', 'unit_designator', {
          placeholder: 'e.g. 1st Plt, 2nd Bn, A Co, 223rd Strike Squadron',
        }));
        body.appendChild(this.field('Unit nickname (optional)', 'unit_nickname', {
          placeholder: 'e.g. The Vindicators, Tomb Breakers, Westfall\'s Pride',
        }));
        body.appendChild(this.para('If both are blank, default is faction and echelon.'));
        body.appendChild(this.continueRow(() => {
          this.answers.unit_designator = document.getElementById('fld-unit_designator')?.value?.trim() || '';
          this.answers.unit_nickname = document.getElementById('fld-unit_nickname')?.value?.trim() || '';
          this.syncForceName();
          this.advance();
        }));
        break;

      case 'opord_approach':
        if (this.answers.knowledge_level === 'tactician') {
          body.appendChild(this.choiceBtn('own', 'I can write my own OpOrd', null, () => {
            this.answers.opord_approach = 'own';
            this.advance();
          }));
          body.appendChild(this.choiceBtn('scribe', 'Scribe for me, XO', null, () => {
            this.answers.opord_approach = 'scribe';
            this.advance();
          }));
        } else {
          body.appendChild(this.choiceBtn('ai', 'Help me draft an OpOrd', null, () => {
            this.answers.opord_approach = 'ai';
            this.advance();
          }));
        }
        body.appendChild(this.choiceBtn('skip', 'Skip OpOrd for now', null, () => {
          this.answers.opord_approach = 'skip';
          this.advance();
        }));
        break;

      case 'opord_share':
        body.appendChild(this.para('Paste your OpOrd or a share link (Google Doc, etc.).'));
        body.appendChild(this.textareaField('opord_share', 'OpOrd text or link…', false));
        body.appendChild(this.continueRow(() => {
          this.answers.opord_share = document.getElementById('fld-opord_share')?.value?.trim() || '';
          this.answers.operation_order = this.answers.opord_share || null;
          this.advance();
        }));
        break;

      case 'opord_casual':
        body.appendChild(this.renderWarnoSplit(null));
        body.appendChild(this.para('Describe what the OpOrd should cover, or paste from Grok/Gemini/ChatGPT.'));
        body.appendChild(this.textareaField('casual_opord_prompt', 'Prompt for OpOrd basics…', false));
        body.appendChild(this.textareaField('operation_order', 'Paste completed OpOrd here (optional until you have one)', false));
        body.appendChild(this.textareaField('opord_share', 'Or paste a Google Doc link / external share', false));
        const msg = document.createElement('div');
        msg.className = 'eo-msg';
        msg.hidden = true;
        body.appendChild(msg);
        body.appendChild(this.actionRow([
          ['Ask XO to draft', async () => this.draftOpord(msg)],
          ['Continue', () => {
            const op = document.getElementById('fld-operation_order');
            const share = document.getElementById('fld-opord_share');
            this.answers.operation_order = op?.value?.trim() || share?.value?.trim() || null;
            this.advance();
          }],
        ]));
        break;

      case 'xo_briefing':
        body.appendChild(renderXoBriefing(
          this.data.briefings?.xo_briefing_web || this.data.briefings?.tutorial || '',
        ));
        body.appendChild(this.continueBtn('Acknowledge briefing', () => {
          this.answers.xo_briefing_seen = true;
          this.answers.tutorial_completed = 'yes';
          this.advance();
        }));
        break;

      case 'review_confirm':
        body.appendChild(this.renderReview());
        body.appendChild(this.continueBtn('Continue to admin setup', () => this.advance()));
        body.appendChild(this.choiceBtn('__edit__', 'Change a selection', null, () => this.showReviewEdit()));
        break;

      case 'game_format':
        for (const v of ['no-blind', 'single-blind', 'double-blind']) {
          body.appendChild(this.choiceBtn(v, v, null, () => {
            this.answers.game_format = v;
            this.advance();
          }));
        }
        break;

      case 'deploy_mode':
        body.appendChild(this.choiceBtn('local', 'Local — Discord KMZ packages', null, () => {
          this.answers.deploy_mode = 'local';
          this.answers.campaign_base_url = '';
          this.advance();
        }));
        body.appendChild(this.choiceBtn('hosted', 'Hosted — HTTPS campaign board', null, () => {
          this.answers.deploy_mode = 'hosted';
          if (!this.answers.campaign_base_url && this.answers.game_id) {
            this.answers.campaign_base_url = defaultHostedUrl(this.data, this.answers.game_id);
          }
          this.advance();
        }));
        break;

      case 'campaign_base_url': {
        const input = document.createElement('input');
        input.type = 'text';
        input.id = 'fld-campaign_base_url';
        input.value = this.answers.campaign_base_url || defaultHostedUrl(this.data, this.answers.game_id || 'table-01');
        body.appendChild(input);
        body.appendChild(this.continueRow(() => {
          this.answers.campaign_base_url = input.value.trim().replace(/\/$/, '');
          this.advance();
        }));
        break;
      }

      case 'player_cell': {
        const forced = this.forcedCell || (this.lobby?.open_cell && (this.lobby.blue || this.lobby.red) ? this.lobby.open_cell : null);
        if (forced) {
          this.answers.player_cell = forced;
          const opp = forced === 'blue-cell' ? this.lobby?.red : this.lobby?.blue;
          const hint = opp
            ? `${cellDisplayName(opp.cell)}: ${opp.faction_labels?.join(', ') || '—'} (${opp.commander_name})`
            : 'First player on this table — cell locked for join flow.';
          body.appendChild(this.para(`Your cell: <strong>${cellDisplayName(forced)}</strong> (locked).`));
          body.appendChild(this.para(hint));
          body.appendChild(this.continueRow(() => this.advance()));
          break;
        }
        const options = ['red-cell', 'blue-cell'].filter((c) => {
          if (c === 'blue-cell' && this.lobby?.blue) return false;
          if (c === 'red-cell' && this.lobby?.red) return false;
          return true;
        });
        if (!options.length) {
          body.appendChild(this.para('Both cells have completed stand-up on this table.'));
          break;
        }
        for (const c of options) {
          body.appendChild(this.choiceBtn(c, cellDisplayName(c), null, () => {
            this.answers.player_cell = c;
            this.advance();
          }));
        }
        break;
      }

      case 'game_id':
        if (this.answers.game_id) {
          const g = (this.data.games || []).find((x) => x.id === this.answers.game_id);
          body.appendChild(this.para(`Table: <strong>${g?.label || this.answers.game_id}</strong>${this.lobbySummaryLine() ? ` — ${this.lobbySummaryLine()}` : ''}`));
          body.appendChild(this.continueRow(() => this.advance()));
        } else {
          for (const g of this.data.games || []) {
            body.appendChild(this.choiceBtn(g.id, g.label, g.campaign_id, async () => {
              this.answers.game_id = g.id;
              this.answers.campaign_base_url = defaultHostedUrl(this.data, g.id);
              await this.loadLobby();
              this.advance();
            }));
          }
        }
        break;

      case 'finalize_setup':
        body.appendChild(this.renderReview());
        body.appendChild(this.continueBtn('Finalize campaign stand-up', () => this.finalize()));
        break;

      case 'review_edit': {
        const vis = this.visibleSteps();
        vis.forEach((sid, idx) => {
          if (sid === 'review_confirm') return;
          body.appendChild(this.choiceBtn(String(idx), `Change: ${titleFor(sid, this.data, this.answers)}`, null, () => {
            this.index = idx;
            this.editingFromReview = true;
            this.render();
          }));
        });
        body.appendChild(this.choiceBtn('back', 'Back to review', null, () => {
          this.index = vis.indexOf('review_confirm');
          this.render();
        }));
        break;
      }

      default:
        if (OSMEAC_IDS.includes(id)) {
          body.appendChild(this.renderOsmeacStep(id, body));
        }
    }

    if (!['welcome', 'review_confirm', 'review_edit', 'finalize_setup', 'xo_briefing'].includes(id) && !this.finalized && !OSMEAC_IDS.includes(id)) {
      this.prependBack(body);
    }
    if (OSMEAC_IDS.includes(id)) this.prependBack(body);

    panel.appendChild(body);
    if (id !== 'welcome' || !this.savedDraft) {
      saveLocalDraft(this.answers, this.index);
      if (!this.lastSavedAt) this.lastSavedAt = Date.now();
      saveDraftRemote(this.answers);
    }
  }

  renderOsmeacStep(stepId, body) {
    const wrap = document.createElement('div');
    wrap.className = 'eo-opord-split';
    wrap.appendChild(this.renderWarnoSplit(stepId));
    const right = document.createElement('div');
    right.className = 'eo-opord-draft';
    const sec = (this.data.tactician_sections || []).find((s) => s.step_id === stepId);
    right.innerHTML = `<h3>${OSMEAC_LABELS[stepId]}</h3>`;
    const ta = document.createElement('textarea');
    ta.id = `fld-${stepId}`;
    ta.rows = 14;
    ta.value = this.answers[stepId] || sec?.skeleton || '';
    ta.className = 'eo-skeleton-input';
    right.appendChild(ta);
    wrap.appendChild(right);
    body.appendChild(wrap);
    body.appendChild(this.continueRow(() => {
      this.answers[stepId] = ta.value.trim() || null;
      this.advance();
    }));
    return wrap;
  }

  renderWarnoSplit(stepId) {
    const left = document.createElement('div');
    left.className = 'eo-opord-ref';
    const warn = document.createElement('div');
    warn.className = 'eo-warn-ref';
    warn.innerHTML = '<strong>WarnO reference</strong><br>' + (this.answers.warn_o ? escapeHtml(this.answers.warn_o) : '<em>No WarnO uploaded yet.</em>');
    left.appendChild(warn);
    if (stepId && OSMEAC_IDS.includes(stepId)) {
      const sec = (this.data.tactician_sections || []).find((s) => s.step_id === stepId);
      const ex = document.createElement('pre');
      ex.className = 'eo-skeleton-example';
      ex.textContent = sec?.skeleton || '';
      left.appendChild(ex);
    }
    return left;
  }

  renderFactionMenu(body) {
    if (this.answers.factions?.length) {
      const pills = document.createElement('div');
      pills.className = 'eo-faction-pills';
      for (const f of this.answers.factions) {
        const pill = document.createElement('span');
        pill.className = 'eo-pill';
        pill.innerHTML = `${escapeHtml(factionLabel(this.data, f))} <button type="button" class="eo-pill-x" data-fid="${f}" title="Remove">×</button>`;
        pill.querySelector('.eo-pill-x').addEventListener('click', (ev) => {
          ev.stopPropagation();
          const fid = ev.target.getAttribute('data-fid');
          this.answers.factions = this.answers.factions.filter((x) => x !== fid);
          delete this.answers.executive_officer;
          this.render();
        });
        pills.appendChild(pill);
      }
      body.appendChild(pills);
      body.appendChild(this.choiceBtn('reset', 'Reset all faction choices', null, () => {
        this.answers.factions = [];
        delete this.answers.executive_officer;
        this.render();
      }));
    }
    for (const cat of ['Alliance', 'Horde', 'Antagonist', 'Neutral']) {
      body.appendChild(this.choiceBtn(cat, `Browse ${cat}`, null, () => this.showFactionPick(cat)));
    }
    const done = this.continueBtn('Done picking your factions', () => {
      if (!this.answers.factions?.length) { alert('Pick at least one faction.'); return; }
      this.answers.executive_officer = this.data.executive_officers?.[this.answers.factions[0]];
      this.advance();
    });
    body.appendChild(done);
  }

  renderReview() {
    const frag = document.createDocumentFragment();
    const dl = document.createElement('dl');
    dl.className = 'eo-review';
    const rows = [
      ['XO style', this.answers.knowledge_level === 'tactician' ? 'Hands off (Tactician)' : 'Hands on (Casual)'],
      ['Factions', (this.answers.factions || []).map((f) => factionLabel(this.data, f)).join(', ')],
      ['XO', xoName(this.data, this.answers)],
      ['Commander', commanderAddress(this.answers)],
      ['Area of operations', (this.data.theaters || []).find((t) => t.id === this.answers.theater)?.label],
      ['Echelon', this.answers.force_size],
      ['Unit', resolvedForceName(this.data, this.answers)],
      ['OpOrd approach', this.answers.opord_approach],
      ['Blind mode', this.answers.game_format],
      ['Sync', this.answers.deploy_mode],
      ['Cell', this.answers.player_cell],
      ['Table', (this.data.games || []).find((g) => g.id === this.answers.game_id)?.label],
    ];
    for (const [k, v] of rows) {
      if (!v) continue;
      const dt = document.createElement('dt'); dt.textContent = k;
      const dd = document.createElement('dd'); dd.textContent = v;
      dl.appendChild(dt); dl.appendChild(dd);
    }
    frag.appendChild(dl);

    const opordText = this.buildOpordPreview();
    if (opordText) {
      const det = document.createElement('details');
      det.className = 'eo-collapse';
      det.open = true;
      det.innerHTML = `<summary>Operation Order</summary><pre>${escapeHtml(opordText)}</pre>`;
      frag.appendChild(det);
    }
    if (this.answers.warn_o) {
      const det = document.createElement('details');
      det.className = 'eo-collapse';
      det.innerHTML = `<summary>Warning Order (WarnO)</summary><pre>${escapeHtml(this.answers.warn_o)}</pre>`;
      frag.appendChild(det);
    }
    return frag;
  }

  buildOpordPreview() {
    if (this.answers.opord_approach === 'skip') return null;
    if (this.answers.operation_order) return this.answers.operation_order;
    if (this.answers.opord_share) return this.answers.opord_share;
    const parts = OSMEAC_IDS.map((id) => this.answers[id]).filter(Boolean);
    return parts.length ? parts.join('\n\n') : null;
  }

  forceSizeTable() {
    const table = document.createElement('table');
    table.className = 'eo-force-table';
    table.innerHTML = '<thead><tr><th>Echelon</th><th>Doctrinal PAX</th><th>Tier</th></tr></thead>';
    const tb = document.createElement('tbody');
    for (const s of this.data.force_sizes || []) {
      const spec = this.data.force_specs?.[s];
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${s.charAt(0).toUpperCase() + s.slice(1)}</td><td>${spec?.strength ?? '—'}</td><td>${spec?.tier ?? '—'}</td>`;
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    return table;
  }

  async draftOpord(msgEl) {
    try {
      const promptEl = document.getElementById('fld-casual_opord_prompt');
      const outEl = document.getElementById('fld-operation_order');
      const res = await apiPost('/api/executive-officer/draft', {
        ...this.answers,
        faction_label: factionLabel(this.data, this.answers.factions?.[0]),
        message: promptEl?.value || '',
      });
      if (res.draft && outEl) {
        outEl.value = res.draft;
        showMsg(msgEl, 'Draft received from XO.', 'ok');
      } else {
        showMsg(msgEl, res.error || 'Draft unavailable', 'err');
      }
    } catch (e) {
      showMsg(msgEl, e.message, 'err');
    }
  }

  showFactionPick(category) {
    const panel = document.getElementById('eo-panel');
    panel.innerHTML = `<h2>Faction — ${category}</h2>`;
    const body = document.createElement('div');
    for (const f of this.data.factions_by_category?.[category] || []) {
      const picked = this.answers.factions.includes(f.id);
      body.appendChild(this.choiceBtn(f.id, picked ? `${f.label} ✓` : f.label, null, () => {
        if (picked) {
          this.answers.factions = this.answers.factions.filter((x) => x !== f.id);
        } else {
          this.answers.factions.push(f.id);
        }
        this.render();
      }));
    }
    body.appendChild(this.choiceBtn('__back__', '← Back to factions', null, () => this.render()));
    this.prependBack(body);
    panel.appendChild(body);
    document.getElementById('eo-briefing').textContent = `Select or de-select a ${category} faction.`;
  }

  field(label, key, opts = {}) {
    const wrap = document.createElement('label');
    wrap.className = 'eo-field';
    wrap.innerHTML = `<span>${label}</span>`;
    if (opts.hint) wrap.innerHTML += `<span class="eo-hint">${opts.hint}</span>`;
    const input = document.createElement('input');
    input.type = 'text';
    input.id = `fld-${key}`;
    input.value = this.answers[key] || '';
    input.placeholder = opts.placeholder || '';
    input.addEventListener('input', () => { this.answers[key] = input.value; this.renderSidebarTrack(); });
    wrap.appendChild(input);
    return wrap;
  }

  textareaField(key, placeholder, required) {
    const ta = document.createElement('textarea');
    ta.id = `fld-${key}`;
    ta.placeholder = placeholder;
    ta.value = this.answers[key] || '';
    ta.addEventListener('input', () => {
      this.answers[key] = ta.value;
      if (key === 'warn_o' || key === 'operation_order') this.renderSidebarTrack();
    });
    return ta;
  }

  para(text) {
    const p = document.createElement('p');
    p.className = 'subtitle';
    p.innerHTML = text;
    return p;
  }

  choiceBtn(value, label, hint, onClick) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'eo-choice';
    btn.innerHTML = hint ? `${label}<small>${hint}</small>` : label;
    btn.addEventListener('click', onClick);
    const wrap = document.createElement('div');
    wrap.className = 'eo-choices';
    wrap.appendChild(btn);
    return wrap.firstChild;
  }

  continueBtn(label, onClick) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'eo-btn-continue';
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    const wrap = document.createElement('div');
    wrap.className = 'eo-actions';
    wrap.appendChild(btn);
    return wrap;
  }

  continueRow(onContinue) {
    return this.actionRow([['Continue', onContinue]]);
  }

  actionRow(pairs) {
    const div = document.createElement('div');
    div.className = 'eo-actions';
    for (const [label, fn] of pairs) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = label;
      btn.className = label === 'Continue' || label.includes('Done') || label.includes('Finalize') || label.includes('Acknowledge')
        ? 'eo-btn-continue' : (label.includes('Ask') ? 'secondary' : 'eo-choice');
      if (btn.className === 'eo-choice') btn.classList.remove('eo-choice');
      if (label === 'Continue' || label.includes('Done') || label.includes('Finalize') || label.includes('Acknowledge')) {
        btn.className = 'eo-btn-continue';
      } else if (label.includes('Ask')) {
        btn.className = 'secondary';
      }
      btn.addEventListener('click', fn);
      div.appendChild(btn);
    }
    return div;
  }

  prependBack(body) {
    const back = document.createElement('button');
    back.type = 'button';
    back.className = 'secondary';
    back.textContent = 'Back';
    back.addEventListener('click', () => this.goBack());
    const actions = body.querySelector('.eo-actions') || (() => {
      const d = document.createElement('div');
      d.className = 'eo-actions';
      body.appendChild(d);
      return d;
    })();
    actions.prepend(back);
  }

  showReviewEdit() {
    const vis = this.visibleSteps();
    const panel = document.getElementById('eo-panel');
    panel.innerHTML = '<h2>Change a selection</h2>';
    const body = document.createElement('div');
    vis.forEach((sid, idx) => {
      if (sid === 'review_confirm' || sid === 'finalize_setup') return;
      body.appendChild(this.choiceBtn(String(idx), titleFor(sid, this.data, this.answers), null, () => {
        this.index = idx;
        this.editingFromReview = true;
        this.render();
      }));
    });
    body.appendChild(this.choiceBtn('back', 'Back to review', null, () => {
      this.index = vis.indexOf('review_confirm');
      this.render();
    }));
    panel.appendChild(body);
  }

  advance() {
    const vis = this.visibleSteps();
    if (this.editingFromReview) {
      this.editingFromReview = false;
      this.index = vis.indexOf('review_confirm');
      if (this.index < 0) this.index = vis.length - 1;
    } else if (this.index < vis.length - 1) {
      this.index += 1;
    }
    this.render();
  }

  goBack() {
    if (this.index > 0) {
      this.index -= 1;
      this.render();
    }
  }

  async finalize() {
    this.syncForceName();
    try {
      const res = await apiPost('/api/executive-officer/finalize', {
        ...this.answers,
        eo_data: { games: this.data.games },
        faction_labels: (this.answers.factions || []).map((f) => factionLabel(this.data, f)),
      });
      this.finalized = true;
      const panel = document.getElementById('eo-panel');
      const blob = new Blob([JSON.stringify(res.session, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const gameId = this.answers.game_id || 'table-01';
      const cell = res.player_cell || this.answers.player_cell || 'blue-cell';
      const uploadToken = res.upload_token || '';
      let statusHtml = '';
      if (res.initiated) {
        statusHtml = `<p class="msg ok">Wargame initiated — both cells are ready. Turn 1 is open on the hosted board.</p>`;
      } else if (res.waiting_for) {
        const joinUrl = `/executive-officer/?game=${encodeURIComponent(gameId)}&cell=${encodeURIComponent(res.waiting_for)}&join=1`;
        statusHtml = `<p class="msg ok">Waiting for ${cellDisplayName(res.waiting_for)}. Share this link with your opponent:</p>
          <p><a href="${joinUrl}">${location.origin}${joinUrl}</a></p>`;
      }
      const tokenHtml = uploadToken
        ? `<div class="eo-handoff">
            <h4>Your upload token (${cellDisplayName(cell)})</h4>
            <p class="eo-token"><code id="eo-upload-token">${escapeHtml(uploadToken)}</code></p>
            <p class="subtitle">Save this token — you need it to upload turn KMZ files on the game table.</p>
            <button type="button" class="eo-btn-continue" id="eo-open-game">Open game table</button>
            <button type="button" class="secondary" id="eo-copy-token">Copy token</button>
          </div>`
        : '<p class="subtitle">Ask white-cell for your upload token on the admin page.</p>';
      panel.innerHTML = `<h2>Stand-up complete</h2><div class="eo-complete">
        <h3>Campaign stand-up complete</h3>
        ${statusHtml}
        ${tokenHtml}
        <p>Download your session file for local Google Earth setup (optional if using hosted board).</p>
        <p><a class="btn eo-btn-continue" href="${url}" download="game_session.json">Download game_session.json</a></p>
      </div>`;
      document.getElementById('eo-open-game')?.addEventListener('click', () => {
        if (typeof openGameTableWithToken === 'function') {
          openGameTableWithToken(gameId, cell, uploadToken);
        } else {
          localStorage.setItem(`wowc_role_${gameId}`, cell);
          localStorage.setItem(`wowc_token_${gameId}_${cell}`, uploadToken);
          location.href = res.game_page_url || `/games/${gameId}/`;
        }
      });
      document.getElementById('eo-copy-token')?.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(uploadToken);
          this.showToast('Upload token copied.');
        } catch {
          this.showToast('Copy the token manually from the box above.');
        }
      });
      document.getElementById('eo-briefing').textContent = res.initiated
        ? 'Both cells stood to — wargame initiated.'
        : 'Well done, Commander. Orders logged.';
    } catch (e) {
      alert(e.message);
    }
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderXoBriefing(text) {
  const normalized = String(text || '')
    .replace(/EXECUTIVE OFFICER/g, 'XO')
    .replace(/Executive Officer/g, 'XO');
  const wrap = document.createElement('div');
  wrap.className = 'eo-briefing-doc';
  const blocks = normalized.split(/\n\n+/).map((b) => b.trim()).filter(Boolean);

  blocks.forEach((block, i) => {
    const lines = block.split('\n').map((l) => l.trim()).filter((l, idx) => idx > 0 || l.length);
    const first = lines[0] || '';
    if (i === 0 && /^XO BRIEFING/i.test(first)) {
      const h = document.createElement('h3');
      h.textContent = 'XO Briefing';
      wrap.appendChild(h);
      return;
    }
    const numbered = first.match(/^(\d+)\.\s+(.+)$/);
    if (numbered) {
      const sec = document.createElement('section');
      sec.className = 'eo-briefing-section';
      const h = document.createElement('h4');
      h.textContent = `${numbered[1]}. ${numbered[2]}`;
      sec.appendChild(h);
      const body = document.createElement('div');
      body.className = 'eo-briefing-body';
      body.innerHTML = lines.slice(1).map((l) => escapeHtml(l)).join('<br>');
      sec.appendChild(body);
      wrap.appendChild(sec);
      return;
    }
    const p = document.createElement('p');
    p.className = 'eo-briefing-footer';
    p.innerHTML = lines.map((l) => escapeHtml(l)).join('<br>');
    wrap.appendChild(p);
  });
  return wrap;
}

async function initEoWizard() {
  try {
    const res = await fetch('/data/eo-wizard.json');
    if (!res.ok) throw new Error('Failed to load wizard data');
    const data = await res.json();
    const wizard = new EoWizard(data);
    await wizard.loadLobby();
    wizard.render();
  } catch (e) {
    document.getElementById('eo-panel').innerHTML = `<p class="msg err">${e.message}</p>`;
  }
}

document.addEventListener('DOMContentLoaded', initEoWizard);