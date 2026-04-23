// ═══════════════════════════════════════════════════════════════════
//  Lead Agent System – Frontend JS
// ═══════════════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────
let ws = null;
let wsRetries = 0;
let leadsPage = 1;
let leadsTotal = 0;
let selectedIds = new Set();
let promptHistory = [];
let historyIdx = -1;
let currentView = 'browser';
let frameImg = null;
let frameNaturalW = 1280;
let frameNaturalH = 800;

const AGENTS = {
  ceo:          { label: 'CEO Agent',     icon: '⚡' },
  scraper:      { label: 'Scraper',       icon: '🌐' },
  outreach:     { label: 'Outreach',      icon: '✍️' },
  email_sender: { label: 'Email Sender',  icon: '📧' },
  qa:           { label: 'QA Agent',      icon: '✅' },
};

// ── WebSocket ──────────────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    wsRetries = 0;
    setWsDot(true);
  };
  ws.onclose = () => {
    setWsDot(false);
    const delay = Math.min(1000 * 2 ** wsRetries, 15000);
    wsRetries++;
    setTimeout(connectWS, delay);
  };
  ws.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    handleEvent(ev);
  };
}

function setWsDot(live) {
  const dot = document.getElementById('ws-dot');
  dot.className = 'ws-dot' + (live ? ' live' : '');
}

function handleEvent(ev) {
  switch (ev.type) {
    case 'init':
      renderAgentCards(ev.data.agents || {});
      updateStats(ev.data.stats || {});
      if (ev.data.last_frame && ev.data.last_frame.screenshot) {
        showFrame(ev.data.last_frame);
      }
      break;
    case 'agent_event':
      updateAgentCard(ev.data);
      pushLog(ev.data);
      pushSidebarHistory(ev.data);
      break;
    case 'browser_frame':
      showFrame(ev.data);
      if (currentView !== 'browser') flashTab('browser');
      break;
    case 'stats':
      updateStats(ev.data);
      break;
    case 'chat_message':
      appendChat(ev.data.role, ev.data.content, ev.data.msg_type, ev.data.ts);
      break;
  }
}

// ── Agent Cards ────────────────────────────────────────────────────
function renderAgentCards(agents) {
  const container = document.getElementById('agent-cards');
  container.innerHTML = Object.keys(AGENTS).map(key => agentCardHTML(key, agents[key])).join('');
}

function agentCardHTML(key, a) {
  a = a || { agent: key, status: 'idle', score: 0, detail: 'Venter...' };
  const cfg = AGENTS[key] || { label: key, icon: '•' };
  const dotClass = `dot-${a.status || 'idle'}`;
  const score = Math.round((a.score || 0) * 100);
  const scoreColor = score >= 90 ? '#10b981' : score >= 70 ? '#f59e0b' : score > 0 ? '#ef4444' : '#334155';
  const isActive = ['running'].includes(a.status);
  return `<div class="agent-card${isActive ? ' active' : ''}" id="ac-${key}">
    <div class="agent-header">
      <span class="agent-name">${cfg.icon} ${cfg.label}</span>
      <span class="agent-dot ${dotClass}"></span>
    </div>
    <div class="agent-detail" title="${s(a.detail || '')}">${s(a.detail || 'Idle')}</div>
    <div class="score-track">
      <div class="score-bar" style="width:${score}%;background:${scoreColor}"></div>
    </div>
  </div>`;
}

function updateAgentCard(a) {
  const el = document.getElementById(`ac-${a.agent}`);
  if (el) el.outerHTML = agentCardHTML(a.agent, a);
}

// ── Logs ───────────────────────────────────────────────────────────
function pushLog(a) {
  const container = document.getElementById('logs-container');
  const time = fmtTime(a.updated_at);
  const detail = s(a.detail || '');
  const status = a.status || 'idle';
  const agentLabel = (AGENTS[a.agent] || {}).label || a.agent;
  const line = document.createElement('div');
  line.className = `log-line ls-${status}`;
  line.innerHTML = `<span class="log-time">${time}</span><span class="log-agent">${agentLabel}</span><span class="log-detail">${detail}</span>`;
  container.appendChild(line);
  container.scrollTop = container.scrollHeight;
  // Cap at 500 lines
  while (container.children.length > 500) container.removeChild(container.firstChild);
}

function clearLogs() {
  document.getElementById('logs-container').innerHTML = '';
}

// ── Sidebar history ────────────────────────────────────────────────
function pushSidebarHistory(a) {
  const feed = document.getElementById('history-feed');
  const time = fmtTime(a.updated_at);
  const status = a.status || 'idle';
  const entry = document.createElement('div');
  entry.className = 'history-entry';
  entry.innerHTML = `<span class="he-time">${time}</span><span class="he-agent he-${status}">[${(a.agent||'').toUpperCase()}]</span><span>${s((a.detail||'').slice(0,50))}</span>`;
  feed.appendChild(entry);
  feed.scrollTop = feed.scrollHeight;
  while (feed.children.length > 150) feed.removeChild(feed.firstChild);
}

// ── Browser Frame ──────────────────────────────────────────────────
function showFrame(frame) {
  const screenshot = document.getElementById('browser-screenshot');
  const idle = document.getElementById('browser-idle');
  const cursor = document.getElementById('cursor-dot');
  const urlEl = document.getElementById('browser-url');
  const labelEl = document.getElementById('browser-label');
  const wrap = document.getElementById('browser-frame-wrap');

  if (!frame.screenshot) return;

  idle.style.display = 'none';
  screenshot.style.display = 'block';
  screenshot.src = 'data:image/jpeg;base64,' + frame.screenshot;

  if (frame.page_url) urlEl.textContent = frame.page_url.slice(0, 80);
  if (frame.label) labelEl.textContent = frame.label;

  // Position cursor overlay
  if (frame.cursor_x || frame.cursor_y) {
    screenshot.onload = () => {
      frameNaturalW = screenshot.naturalWidth || 1280;
      frameNaturalH = screenshot.naturalHeight || 800;
      positionCursor(cursor, wrap, screenshot, frame.cursor_x, frame.cursor_y);
    };
    if (screenshot.complete) {
      positionCursor(cursor, wrap, screenshot, frame.cursor_x, frame.cursor_y);
    }
    cursor.style.display = 'block';
  }
}

function positionCursor(cursor, wrap, img, cx, cy) {
  const rect = img.getBoundingClientRect();
  const wrapRect = wrap.getBoundingClientRect();
  const scaleX = rect.width / frameNaturalW;
  const scaleY = rect.height / frameNaturalH;
  const offsetX = rect.left - wrapRect.left;
  const offsetY = rect.top - wrapRect.top;
  cursor.style.left = (offsetX + cx * scaleX) + 'px';
  cursor.style.top = (offsetY + cy * scaleY) + 'px';
}

// ── Stats ──────────────────────────────────────────────────────────
function updateStats(stats) {
  if (stats.total_leads !== undefined) document.getElementById('h-leads').textContent = stats.total_leads;
  if (stats.emails_sent !== undefined) document.getElementById('h-sent').textContent = stats.emails_sent;
  if (stats.campaigns_active !== undefined) document.getElementById('h-campaigns').textContent = stats.campaigns_active;
}

// ── Chat ───────────────────────────────────────────────────────────
function appendChat(role, content, msgType, ts) {
  const container = document.getElementById('chat-messages');
  const isUser = role === 'user';
  const bubbleClass = isUser ? 'chat-bubble-user' : (
    msgType === 'result' ? 'chat-bubble-result' :
    msgType === 'error' ? 'chat-bubble-error' :
    'chat-bubble-agent'
  );
  const time = ts ? fmtTime(ts) : fmtTime(new Date().toISOString());
  const html = renderMarkdown(s(content));

  const div = document.createElement('div');
  div.className = `chat-msg chat-msg-${isUser ? 'user' : 'agent'}`;
  div.innerHTML = `<div class="chat-bubble ${bubbleClass}">${html}</div><div class="chat-time">${time}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function renderMarkdown(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

async function clearChat() {
  await fetch('/api/history', { method: 'DELETE' });
  document.getElementById('chat-messages').innerHTML = '';
}

// ── Prompt ─────────────────────────────────────────────────────────
async function sendPrompt() {
  const input = document.getElementById('prompt-input');
  const msg = input.value.trim();
  if (!msg) return;

  // History
  promptHistory.unshift(msg);
  if (promptHistory.length > 50) promptHistory.pop();
  historyIdx = -1;

  // Show in chat
  appendChat('user', msg, 'text', new Date().toISOString());
  input.value = '';

  // Show thinking
  const thinkId = 'think_' + Date.now();
  const container = document.getElementById('chat-messages');
  const thinkEl = document.createElement('div');
  thinkEl.id = thinkId;
  thinkEl.className = 'chat-msg chat-msg-agent';
  thinkEl.innerHTML = `<div class="chat-bubble chat-bubble-agent"><span class="spinner"></span> Behandler...</div>`;
  container.appendChild(thinkEl);
  container.scrollTop = container.scrollHeight;

  try {
    await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    });
  } catch (e) {
    appendChat('agent', 'Fejl: Kunne ikke forbinde til server.', 'error');
  } finally {
    const el = document.getElementById(thinkId);
    if (el) el.remove();
  }
}

// ── Keyboard shortcuts ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('prompt-input');

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendPrompt();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (historyIdx < promptHistory.length - 1) {
        historyIdx++;
        input.value = promptHistory[historyIdx] || '';
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIdx > 0) {
        historyIdx--;
        input.value = promptHistory[historyIdx] || '';
      } else {
        historyIdx = -1;
        input.value = '';
      }
    }
  });

  // Focus prompt on Cmd/Ctrl+K
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      input.focus();
    }
  });
});

// ── View switching ─────────────────────────────────────────────────
function switchView(name) {
  currentView = name;
  ['browser', 'logs', 'leads', 'campaigns'].forEach(v => {
    document.getElementById(`view-${v}`).classList.toggle('active', v === name);
    document.getElementById(`vtab-${v}`).classList.toggle('active', v === name);
  });
  document.querySelectorAll('.ttab').forEach(btn => {
    btn.classList.toggle('active', btn.textContent.toLowerCase().includes(name) ||
      (name === 'browser' && btn.textContent === 'Browser') ||
      (name === 'logs' && btn.textContent === 'Logs') ||
      (name === 'leads' && btn.textContent === 'Leads') ||
      (name === 'campaigns' && btn.textContent === 'Kampagner'));
  });
  if (name === 'leads') loadLeads();
  if (name === 'campaigns') loadCampaigns();
}

function flashTab(viewName) {
  const tab = document.getElementById(`vtab-${viewName}`);
  if (tab && !tab.classList.contains('active')) {
    tab.style.color = '#6366f1';
    setTimeout(() => { tab.style.color = ''; }, 800);
  }
}

// ── Leads ──────────────────────────────────────────────────────────
async function loadLeads() {
  const search = document.getElementById('lead-search').value;
  const status = document.getElementById('lead-status').value;
  const r = await fetch(`/api/leads?page=${leadsPage}&limit=50&search=${encodeURIComponent(search)}&status=${status}`);
  const data = await r.json();
  leadsTotal = data.total;
  document.getElementById('leads-count').textContent = `${data.total} leads`;
  document.getElementById('leads-page-info').textContent = `Side ${leadsPage} · ${data.total} total`;

  const tbody = document.getElementById('leads-tbody');
  tbody.innerHTML = data.leads.map(l => {
    const conf = Math.round((l.email_confidence || 0) * 100);
    const confColor = conf >= 80 ? '#10b981' : conf >= 40 ? '#f59e0b' : '#ef4444';
    return `<tr>
      <td><input type="checkbox" class="lead-cb" value="${l.id}" ${selectedIds.has(l.id)?'checked':''} onchange="toggleLead(${l.id},this.checked)"></td>
      <td class="td-company">${s(l.company||'—')}</td>
      <td class="td-email">${s(l.email||'—')}</td>
      <td class="td-phone">${s(l.phone||'—')}</td>
      <td style="color:var(--muted);font-size:11px">${s(l.niche||'—')}</td>
      <td>
        <div class="conf-bar">
          <div class="conf-track"><div class="conf-fill" style="width:${conf}%;background:${confColor}"></div></div>
          <span style="font-size:10px;color:var(--muted)">${conf}%</span>
        </div>
      </td>
      <td><span class="badge badge-${l.status||'new'}">${l.status||'new'}</span></td>
      <td><button class="btn-danger-sm" onclick="deleteLead(${l.id})">×</button></td>
    </tr>`;
  }).join('');
}

const debouncedLeads = debounce(loadLeads, 300);

function toggleLead(id, checked) {
  if (checked) selectedIds.add(id); else selectedIds.delete(id);
  updateLaunchBtn();
}
function toggleAll(cb) {
  document.querySelectorAll('.lead-cb').forEach(c => { c.checked = cb.checked; toggleLead(parseInt(c.value), cb.checked); });
  updateLaunchBtn();
}
function updateLaunchBtn() {
  const btn = document.getElementById('launch-btn');
  if (btn) btn.textContent = selectedIds.size > 0 ? `Launch kampagne (${selectedIds.size})` : 'Launch kampagne';
}

async function deleteLead(id) {
  if (!confirm('Slet dette lead?')) return;
  await fetch(`/api/leads/${id}`, { method: 'DELETE' });
  selectedIds.delete(id);
  loadLeads();
}
function prevPage() { if (leadsPage > 1) { leadsPage--; loadLeads(); } }
function nextPage() { if (leadsPage * 50 < leadsTotal) { leadsPage++; loadLeads(); } }
function exportLeads() { window.open('/api/leads?limit=10000', '_blank'); }

// ── Campaigns ──────────────────────────────────────────────────────
async function loadCampaigns() {
  const r = await fetch('/api/campaigns');
  const camps = await r.json();
  const list = document.getElementById('camp-list');

  if (!camps.length) {
    list.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:16px">Ingen kampagner endnu.<br>Opret en til venstre.</div>';
    return;
  }

  list.innerHTML = camps.map(c => {
    const statusColors = { idle:'var(--muted)', running:'var(--accent)', done:'var(--accent2)', paused:'var(--warn)' };
    return `<div class="camp-card">
      <div class="camp-card-header">
        <div>
          <span class="camp-card-name">${s(c.name)}</span>
          <span class="badge" style="margin-left:8px;background:rgba(99,102,241,.1);color:${statusColors[c.status]||'var(--muted)'}">${c.status}</span>
        </div>
        <button class="btn btn-ghost" style="padding:3px 8px;font-size:11px" onclick="viewCampLogs(${c.id})">Logs</button>
      </div>
      <div class="camp-stats">
        <div class="camp-stat"><div class="camp-stat-val" style="color:#818cf8">${c.leads_total}</div><div class="camp-stat-label">Leads</div></div>
        <div class="camp-stat"><div class="camp-stat-val" style="color:var(--accent2)">${c.sent_count}</div><div class="camp-stat-label">Sendt</div></div>
        <div class="camp-stat"><div class="camp-stat-val" style="color:var(--warn)">${c.reply_count}</div><div class="camp-stat-label">Svar</div></div>
        <div class="camp-stat"><div class="camp-stat-val" style="color:var(--danger)">${c.failed_count}</div><div class="camp-stat-label">Fejl</div></div>
      </div>
    </div>`;
  }).join('');

  // Populate modal dropdown
  const sel = document.getElementById('modal-camp-select');
  sel.innerHTML = '<option value="">Vælg kampagne...</option>' +
    camps.map(c => `<option value="${c.id}">${s(c.name)}</option>`).join('');
}

async function createCampaign() {
  const name = document.getElementById('camp-name').value.trim();
  const niche = document.getElementById('camp-niche').value.trim();
  if (!name) { alert('Kampagnenavn er påkrævet'); return; }
  await fetch('/api/campaigns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, niche }),
  });
  document.getElementById('camp-name').value = '';
  document.getElementById('camp-niche').value = '';
  loadCampaigns();
}

async function viewCampLogs(id) {
  const r = await fetch(`/api/campaigns/${id}/logs`);
  const logs = await r.json();
  if (!logs.length) { alert('Ingen emails sendt endnu'); return; }
  const text = logs.slice(0, 20).map(l => `[${l.status}] ${l.lead_company} <${l.lead_email}>\n  Emne: ${l.subject||'—'}\n  Fejl: ${l.error||'ingen'}`).join('\n\n');
  alert(text);
}

// ── Modal ──────────────────────────────────────────────────────────
function openLaunchModal() {
  if (!selectedIds.size) { alert('Vælg mindst ét lead'); return; }
  document.getElementById('modal-lead-count').textContent = `${selectedIds.size} leads valgt`;
  document.getElementById('launch-modal').classList.add('open');
  loadCampaigns();
}
function closeModal() { document.getElementById('launch-modal').classList.remove('open'); }

async function launchCampaign() {
  const campaign_id = parseInt(document.getElementById('modal-camp-select').value);
  const from_name = document.getElementById('modal-from').value.trim() || 'Lead System';
  const context = document.getElementById('modal-context').value.trim();
  if (!campaign_id) { alert('Vælg en kampagne'); return; }

  closeModal();
  await fetch('/api/campaigns/launch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ campaign_id, lead_ids: [...selectedIds], context, from_name }),
  });
  selectedIds.clear();
  switchView('campaigns');
}

// ── History loading ────────────────────────────────────────────────
async function loadHistory() {
  const r = await fetch('/api/history?limit=100');
  const msgs = await r.json();
  const container = document.getElementById('chat-messages');
  // Keep welcome msg, add history after
  const welcome = container.firstChild;
  container.innerHTML = '';
  if (welcome) container.appendChild(welcome);
  msgs.forEach(m => appendChat(m.role, m.content, m.msg_type, m.created_at));
}

async function loadStats() {
  const r = await fetch('/api/stats');
  const data = await r.json();
  updateStats(data);
}

// ── Utils ──────────────────────────────────────────────────────────
function s(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function fmtTime(iso) {
  try { return new Date(iso).toLocaleTimeString('da-DK', {hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
  catch { return ''; }
}
function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ── Boot ───────────────────────────────────────────────────────────
connectWS();
loadStats();
loadHistory();
setInterval(loadStats, 20000);
