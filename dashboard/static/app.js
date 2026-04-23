// ─── State ────────────────────────────────────────────────────────────────────
let leadsPage = 1;
let leadsTotal = 0;
let selectedLeadIds = new Set();
let pipelineChart = null;
let ws = null;

const AGENTS = ["ceo", "scraper", "outreach", "email_sender", "qa"];
const AGENT_LABELS = {
  ceo: "CEO Agent",
  scraper: "Scraper",
  outreach: "Outreach",
  email_sender: "Email Sender",
  qa: "QA Agent",
};
const STATUS_COLOR = {
  idle: "pulse-gray",
  running: "pulse-green",
  success: "pulse-green",
  warning: "pulse-yellow",
  error: "pulse-red",
};

// ─── WebSocket ────────────────────────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    document.getElementById("ws-status").textContent = "LIVE";
    document.getElementById("ws-status").className = "badge badge-green ml-2";
  };

  ws.onclose = () => {
    document.getElementById("ws-status").textContent = "OFFLINE";
    document.getElementById("ws-status").className = "badge badge-red ml-2";
    setTimeout(connectWS, 3000);
  };

  ws.onmessage = (e) => {
    const event = JSON.parse(e.data);
    if (event.type === "init") {
      renderAgentGrid(event.data.agents);
      updateHeaderStats(event.data.stats);
    } else if (event.type === "agent_event") {
      updateAgentCard(event.data);
      pushActivityLog(event.data);
    } else if (event.type === "stats") {
      updateHeaderStats(event.data);
    }
  };
}

// ─── Agent Grid ───────────────────────────────────────────────────────────────
function renderAgentGrid(agents) {
  const grid = document.getElementById("agent-grid");
  grid.innerHTML = AGENTS.map(key => {
    const a = agents[key] || { agent: key, action: AGENT_LABELS[key], detail: "Idle", status: "idle", score: 0 };
    return agentCard(a);
  }).join("");
}

function agentCard(a) {
  const pulseClass = STATUS_COLOR[a.status] || "pulse-gray";
  const scoreColor = a.score >= 0.9 ? "#10b981" : a.score >= 0.7 ? "#f59e0b" : "#ef4444";
  const score = Math.round((a.score || 0) * 100);
  return `
    <div class="glass rounded-xl p-4 space-y-3" id="agent-card-${a.agent}">
      <div class="flex items-center justify-between">
        <span class="text-sm font-semibold">${AGENT_LABELS[a.agent] || a.agent}</span>
        <span class="pulse-dot ${pulseClass}"></span>
      </div>
      <div class="text-xs text-slate-400 truncate" title="${a.detail}">${a.detail || "Waiting..."}</div>
      <div class="score-bar">
        <div class="score-fill" style="width:${score}%;background:${scoreColor}"></div>
      </div>
      <div class="flex justify-between text-xs">
        <span class="text-slate-500">${a.status}</span>
        <span style="color:${scoreColor}">${score}%</span>
      </div>
    </div>`;
}

function updateAgentCard(a) {
  const el = document.getElementById(`agent-card-${a.agent}`);
  if (el) {
    el.outerHTML = agentCard(a);
  } else {
    // card doesn't exist yet, re-render grid
    const grid = document.getElementById("agent-grid");
    const existing = {};
    AGENTS.forEach(k => { existing[k] = { agent: k, status: "idle", score: 0, detail: "Idle" }; });
    existing[a.agent] = a;
    renderAgentGrid(existing);
  }
}

// ─── Activity Feed ────────────────────────────────────────────────────────────
const feedColors = { success: "#10b981", running: "#6366f1", warning: "#f59e0b", error: "#ef4444", idle: "#475569" };

function pushActivityLog(a) {
  const feed = document.getElementById("activity-feed");
  const color = feedColors[a.status] || "#94a3b8";
  const time = new Date(a.updated_at || Date.now()).toLocaleTimeString();
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.innerHTML = `<span style="color:#475569">${time}</span>
    <span style="color:${color};margin:0 6px">[${(a.agent||"").toUpperCase()}]</span>
    <span style="color:#94a3b8">${sanitize(a.detail || "")}</span>`;
  feed.prepend(entry);
  // Keep only last 100 entries
  while (feed.children.length > 100) feed.removeChild(feed.lastChild);
}

// ─── Header Stats ─────────────────────────────────────────────────────────────
function updateHeaderStats(stats) {
  if (!stats) return;
  if (stats.total_leads !== undefined) document.getElementById("h-leads").textContent = stats.total_leads;
  if (stats.emails_sent !== undefined) document.getElementById("h-sent").textContent = stats.emails_sent;
  if (stats.campaigns_active !== undefined) document.getElementById("h-campaigns").textContent = stats.campaigns_active;
}

async function loadStats() {
  const r = await fetch("/api/stats");
  const data = await r.json();
  updateHeaderStats(data);
  updatePipelineChart(data);
}

function updatePipelineChart(data) {
  const ctx = document.getElementById("pipeline-chart");
  if (!ctx) return;
  if (pipelineChart) pipelineChart.destroy();
  pipelineChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Total Leads", "Emails Sent", "Active Campaigns"],
      datasets: [{
        data: [data.total_leads || 0, data.emails_sent || 0, data.campaigns_active || 0],
        backgroundColor: ["#6366f1", "#10b981", "#f59e0b"],
        borderWidth: 0,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: "#94a3b8", font: { size: 12 } } } },
      cutout: "65%",
    },
  });
}

// ─── Leads ────────────────────────────────────────────────────────────────────
async function loadLeads() {
  const search = document.getElementById("lead-search").value;
  const status = document.getElementById("lead-status").value;
  const r = await fetch(`/api/leads?page=${leadsPage}&limit=50&search=${encodeURIComponent(search)}&status=${status}`);
  const data = await r.json();
  leadsTotal = data.total;

  document.getElementById("leads-count").textContent = `${data.total} leads total`;
  const tbody = document.getElementById("leads-table");
  tbody.innerHTML = data.leads.map(l => `
    <tr class="border-b border-white/4 hover:bg-white/2 transition-colors">
      <td class="px-4 py-3"><input type="checkbox" class="lead-cb" value="${l.id}" ${selectedLeadIds.has(l.id) ? "checked" : ""} onchange="toggleLead(${l.id},this.checked)"></td>
      <td class="px-4 py-3 font-medium text-sm">${sanitize(l.company || "-")}</td>
      <td class="px-4 py-3 text-xs text-indigo-300">${sanitize(l.email || "—")}</td>
      <td class="px-4 py-3 text-xs text-slate-400">${sanitize(l.phone || "—")}</td>
      <td class="px-4 py-3 text-xs text-slate-400">${sanitize(l.niche || "—")}</td>
      <td class="px-4 py-3">
        <div class="flex items-center gap-2">
          <div class="score-bar w-12"><div class="score-fill" style="width:${Math.round((l.email_confidence||0)*100)}%;background:#6366f1"></div></div>
          <span class="text-xs text-slate-400">${Math.round((l.email_confidence||0)*100)}%</span>
        </div>
      </td>
      <td class="px-4 py-3">
        <span class="badge ${statusBadge(l.status)}">${l.status}</span>
      </td>
      <td class="px-4 py-3">
        <button class="btn-danger text-xs px-2 py-1" onclick="deleteLead(${l.id})">Del</button>
      </td>
    </tr>`).join("");
}

function statusBadge(s) {
  return { new: "badge-gray", contacted: "badge-blue", replied: "badge-green", unsubscribed: "badge-red" }[s] || "badge-gray";
}

function toggleLead(id, checked) {
  if (checked) selectedLeadIds.add(id);
  else selectedLeadIds.delete(id);
}

function toggleAll(cb) {
  document.querySelectorAll(".lead-cb").forEach(c => {
    c.checked = cb.checked;
    toggleLead(parseInt(c.value), cb.checked);
  });
}

async function deleteLead(id) {
  if (!confirm("Delete this lead?")) return;
  await fetch(`/api/leads/${id}`, { method: "DELETE" });
  loadLeads();
}

function prevPage() { if (leadsPage > 1) { leadsPage--; loadLeads(); } }
function nextPage() { if (leadsPage * 50 < leadsTotal) { leadsPage++; loadLeads(); } }

function exportLeads() {
  window.open("/api/leads?limit=10000", "_blank");
}

// ─── Scrape ───────────────────────────────────────────────────────────────────
async function startScrape() {
  const query = document.getElementById("sc-query").value.trim();
  const location = document.getElementById("sc-location").value.trim();
  const count = parseInt(document.getElementById("sc-count").value) || 50;
  const niche = document.getElementById("sc-niche").value.trim() || query;

  if (!query || !location) { alert("Query and location are required"); return; }

  const btn = document.getElementById("scrape-btn");
  btn.disabled = true;
  btn.textContent = "Scraping...";
  document.getElementById("scrape-status").textContent = "Starting scrape – watch the Agent Monitor for live updates...";

  const r = await fetch("/api/scrape", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, location, count, niche }),
  });
  const data = await r.json();

  // Poll for completion
  const pollInterval = setInterval(async () => {
    const tr = await fetch(`/api/tasks/${data.task_id}`);
    const task = await tr.json();
    if (task.status === "done") {
      clearInterval(pollInterval);
      btn.disabled = false;
      btn.textContent = "Start Scraping";
      const leads = task.result?.scrape?.leads_found || 0;
      document.getElementById("scrape-status").textContent = `Done! ${leads} leads saved.`;
      loadLeads();
      loadStats();
    }
  }, 2000);
}

// ─── Campaigns ────────────────────────────────────────────────────────────────
async function loadCampaigns() {
  const r = await fetch("/api/campaigns");
  const camps = await r.json();
  const container = document.getElementById("campaigns-list");
  if (!camps.length) { container.innerHTML = '<p class="text-slate-500 text-sm">No campaigns yet.</p>'; return; }

  container.innerHTML = camps.map(c => `
    <div class="glass rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between">
        <div>
          <span class="font-semibold">${sanitize(c.name)}</span>
          <span class="badge ml-2 ${campaignBadge(c.status)}">${c.status}</span>
        </div>
        <span class="text-xs text-slate-400">${c.niche || "—"}</span>
      </div>
      <div class="grid grid-cols-4 gap-3 text-center">
        <div><div class="font-bold text-indigo-400">${c.leads_total}</div><div class="text-xs text-slate-500">Leads</div></div>
        <div><div class="font-bold text-emerald-400">${c.sent_count}</div><div class="text-xs text-slate-500">Sent</div></div>
        <div><div class="font-bold text-amber-400">${c.reply_count}</div><div class="text-xs text-slate-500">Replies</div></div>
        <div><div class="font-bold text-red-400">${c.failed_count}</div><div class="text-xs text-slate-500">Failed</div></div>
      </div>
      <button class="btn-primary text-xs w-full" onclick="viewCampaignLogs(${c.id})">View Logs</button>
    </div>`).join("");

  // Populate modal dropdown
  const sel = document.getElementById("modal-campaign");
  sel.innerHTML = '<option value="">Select campaign...</option>' +
    camps.filter(c => c.status !== "done").map(c => `<option value="${c.id}">${c.name}</option>`).join("");
}

function campaignBadge(s) {
  return { idle: "badge-gray", running: "badge-blue", done: "badge-green", paused: "badge-yellow" }[s] || "badge-gray";
}

async function createCampaign() {
  const name = document.getElementById("camp-name").value.trim();
  const niche = document.getElementById("camp-niche").value.trim();
  const from = document.getElementById("camp-from").value.trim();
  if (!name) { alert("Campaign name is required"); return; }

  await fetch("/api/campaigns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, niche }),
  });
  document.getElementById("camp-name").value = "";
  document.getElementById("camp-niche").value = "";
  loadCampaigns();
}

async function viewCampaignLogs(id) {
  const r = await fetch(`/api/campaigns/${id}/logs`);
  const logs = await r.json();
  const text = logs.map(l => `[${l.status}] ${l.lead_company} <${l.lead_email}>\n${l.subject}\n`).join("\n---\n");
  alert(text || "No emails sent yet");
}

// ─── Launch Campaign Modal ────────────────────────────────────────────────────
function openSelectModal() {
  if (!selectedLeadIds.size) { alert("Select at least one lead"); return; }
  document.getElementById("selected-count").textContent = selectedLeadIds.size;
  document.getElementById("launch-modal").classList.add("open");
  loadCampaigns();
}

function closeModal() {
  document.getElementById("launch-modal").classList.remove("open");
}

async function launchCampaign() {
  const campaign_id = parseInt(document.getElementById("modal-campaign").value);
  const from_name = document.getElementById("modal-from").value.trim() || "Lead System";
  const context = document.getElementById("modal-context").value.trim();

  if (!campaign_id) { alert("Select a campaign"); return; }
  if (!selectedLeadIds.size) { alert("No leads selected"); return; }

  closeModal();

  await fetch("/api/campaigns/launch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      campaign_id,
      lead_ids: [...selectedLeadIds],
      context,
      from_name,
    }),
  });

  selectedLeadIds.clear();
  showTab("campaigns");
  loadCampaigns();
}

// ─── Tab Navigation ───────────────────────────────────────────────────────────
function showTab(name) {
  ["dashboard", "leads", "campaigns", "scrape"].forEach(t => {
    document.getElementById(`tab-${t}`).classList.toggle("hidden", t !== name);
  });
  document.querySelectorAll(".tab-btn").forEach((btn, i) => {
    const names = ["dashboard", "leads", "campaigns", "scrape"];
    btn.classList.toggle("active", names[i] === name);
    btn.classList.toggle("text-slate-400", names[i] !== name);
  });

  if (name === "leads") loadLeads();
  if (name === "campaigns") loadCampaigns();
  if (name === "dashboard") loadStats();
}

// ─── Utils ────────────────────────────────────────────────────────────────────
function sanitize(str) {
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function debounce(fn, delay) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

// ─── Boot ─────────────────────────────────────────────────────────────────────
connectWS();
loadStats();
setInterval(loadStats, 30000);
