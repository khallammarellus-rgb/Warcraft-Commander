/** XO Advisor — focused OPORD + getting-started helper (not general chat) */

const MISSIONS = {
  getting_started: {
    title: 'Getting started briefing',
    desc: 'One-time walkthrough: Google Earth Pro, player pack, portal, turn loop.',
    placeholder: 'Request your stand-to briefing (e.g. "Walk me through getting started on Table 01").',
    opener: 'Commander, I will cover portal setup and your first turn workflow. Ask one focused question if something is unclear after the briefing.',
  },
  opord: {
    title: 'Draft operation order',
    desc: 'Five-paragraph OPORD for your force — paste Warn O context if you have it.',
    placeholder: 'Describe your force, theater, and mission. Paste Warn O above your request if issued.',
    opener: 'Provide force size, faction, theater, and mission intent. I will draft a five-paragraph OPORD.',
  },
  tactical_tasks: {
    title: 'Tactical tasks helper',
    desc: 'Mission verbs and subordinate tasks for your OPORD execution paragraph.',
    placeholder: 'List your units/echelons and commander\'s intent…',
    opener: 'Name your subordinate units and intent; I will suggest tactical tasks.',
  },
  order_polish: {
    title: 'Polish orders',
    desc: 'Clarify wording on an OPORD paragraph you already drafted — paste the text.',
    placeholder: 'Paste the OPORD paragraph to polish…',
    opener: 'Paste the paragraph you want clarified. I will tighten language without changing intent.',
  },
};

const MIN_SEND_INTERVAL_MS = 12000; // ~5 RPM project-wide — pace requests
let lastSendAt = 0;
let session = null;
let activeMission = 'getting_started';

function cooldownRemaining() {
  const left = MIN_SEND_INTERVAL_MS - (Date.now() - lastSendAt);
  return left > 0 ? left : 0;
}

function updateCooldownUI() {
  const el = document.getElementById('eo-cooldown');
  if (!el) return;
  const left = cooldownRemaining();
  if (left > 0) {
    el.textContent = `Shared quota — wait ${Math.ceil(left / 1000)}s before next request`;
    el.className = 'eo-cooldown warn';
    document.getElementById('chat-send')?.setAttribute('disabled', 'disabled');
  } else {
    el.textContent = 'Shared table quota — one request at a time, please';
    el.className = 'eo-cooldown';
    document.getElementById('chat-send')?.removeAttribute('disabled');
  }
}

function selectMission(id) {
  activeMission = id;
  const m = MISSIONS[id];
  document.querySelectorAll('.eo-mission').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.mission === id);
  });
  document.getElementById('workspace-title').textContent = m.title;
  document.getElementById('chat-input').placeholder = m.placeholder;
  const log = document.getElementById('chat-log');
  log.innerHTML = `<div class="assistant"><strong>XO:</strong> ${m.opener}</div>`;
}

function initAdvisorPage() {
  const params = new URLSearchParams(location.search);
  document.getElementById('auth-game').value = params.get('game') || 'table-01';

  document.querySelectorAll('.eo-mission').forEach((btn) => {
    btn.addEventListener('click', () => selectMission(btn.dataset.mission));
  });

  document.getElementById('auth-btn')?.addEventListener('click', async () => {
    const game_id = document.getElementById('auth-game').value;
    const cell = document.getElementById('auth-cell').value;
    const token = document.getElementById('auth-secret').value.trim();
    try {
      await apiPost('/api/assistant/auth', { game_id, cell, token, password: token });
      session = { game_id, cell, token };
      document.getElementById('login-gate').hidden = true;
      document.getElementById('advisor-app').hidden = false;
      selectMission('getting_started');
      setInterval(updateCooldownUI, 500);
      updateCooldownUI();
    } catch (e) {
      showMsg(document.getElementById('auth-msg'), e.message, 'err');
    }
  });

  async function sendMessage() {
    const msg = document.getElementById('chat-input').value.trim();
    if (!msg || !session) return;
    if (cooldownRemaining() > 0) {
      showMsg(document.getElementById('workspace-msg'), 'Please wait — shared API quota for all players at this table.', 'err');
      return;
    }
    const log = document.getElementById('chat-log');
    log.innerHTML += `<div class="user"><strong>You:</strong> ${escapeHtml(msg)}</div>`;
    document.getElementById('chat-input').value = '';
    document.getElementById('chat-send')?.setAttribute('disabled', 'disabled');
    try {
      const data = await apiPost('/api/assistant/chat', {
        game_id: session.game_id,
        cell: session.cell,
        token: session.token,
        mode: activeMission,
        message: msg,
      });
      log.innerHTML += `<div class="assistant"><strong>XO:</strong> ${escapeHtml(data.reply)}</div>`;
      log.scrollTop = log.scrollHeight;
      lastSendAt = Date.now();
      showMsg(document.getElementById('workspace-msg'), '', 'info');
    } catch (e) {
      let text = e.message;
      if (text.includes('429') || text.includes('limit')) {
        text += ' Use Grok, Gemini, or another AI for extended questions — see sidebar.';
      }
      log.innerHTML += `<div class="assistant" style="color:var(--err)">${escapeHtml(text)}</div>`;
      showMsg(document.getElementById('workspace-msg'), text, 'err');
    } finally {
      updateCooldownUI();
    }
  }

  document.getElementById('chat-send')?.addEventListener('click', sendMessage);
  document.getElementById('chat-input')?.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' && !ev.shiftKey) { ev.preventDefault(); sendMessage(); }
  });
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

document.addEventListener('DOMContentLoaded', initAdvisorPage);