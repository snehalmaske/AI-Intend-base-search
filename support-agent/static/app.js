"use strict";

// ---------------------------------------------------------------- helpers
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => "$" + Number(n || 0).toFixed(2);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = text; }
  if (!res.ok) {
    const err = new Error(typeof data === "object" ? JSON.stringify(data.detail ?? data) : text);
    err.data = data;
    throw err;
  }
  return data;
}

function decisionPill(decision) {
  const cls = { allow: "ok", deny: "deny", escalate: "warn", error: "deny" }[decision] || "";
  return `<span class="pill ${cls}">${esc(decision)}</span>`;
}

function statusPill(status) {
  const cls = {
    processed: "ok", approved: "ok", approved_by_supervisor: "ok",
    denied: "deny", denied_by_supervisor: "deny", supervisor_review: "warn",
  }[status] || "";
  return `<span class="pill ${cls}">${esc(status)}</span>`;
}

let CONFIG = null;
let SELECTED_CASE = null;
let ACT_AGENT = "records_agent";
const STEP_LOG = {}; // case_id -> [step results], newest first

// ---------------------------------------------------------------- header
async function loadConfig() {
  CONFIG = await api("/api/config");
  const off = Object.entries(CONFIG.guardrails).filter(([, on]) => !on).map(([g]) => g);
  const revoked = CONFIG.revocation === "revoked";
  $("#status-pills").innerHTML = [
    `<span class="pill">LLM: ${esc(CONFIG.llm === "mock" ? "mock" : CONFIG.model)}</span>`,
    `<span class="pill">RAG: ${esc(CONFIG.rag_backend)}</span>`,
    `<span class="pill ${revoked ? "deny" : "ok"}">authority: ${esc(CONFIG.revocation)}</span>`,
    `<span class="pill ${off.length ? "warn" : "ok"}">guardrails: ${off.length ? off.length + " off" : "all on"}</span>`,
  ].join("");
  const banner = $("#banner");
  if (revoked) {
    banner.className = "banner deny";
    banner.textContent = "Agent authority REVOKED - all consequential actions are being refused.";
  } else if (off.length) {
    banner.className = "banner warn";
    banner.textContent = "LAB MODE - guardrails disabled: " + off.join(", ");
  } else {
    banner.className = "banner hidden";
  }
}

// ---------------------------------------------------------------- tabs
const LOADERS = {
  queue: loadQueue, newcase: loadNewCase, customers: loadCustomers, reporting: loadReporting,
  evidence: loadAudit, policies: loadPolicies, controls: loadControls,
};

function showTab(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  try { localStorage.setItem("tab", name); } catch { /* storage unavailable */ }
  LOADERS[name]().catch(showError);
}

function showError(err) {
  console.error(err);
  alert(err.message || String(err));
}

// ---------------------------------------------------------------- queue
async function loadQueue() {
  const status = $("#queue-filter").value;
  const cases = await api("/api/cases" + (status ? "?status=" + encodeURIComponent(status) : ""));
  $("#case-table tbody").innerHTML = cases.map((c) => `
    <tr data-id="${c.id}" class="${c.id === SELECTED_CASE ? "selected" : ""}">
      <td>${c.id}</td><td>${esc(c.customer_name)}</td><td class="num">${money(c.amount_requested)}</td>
      <td>${statusPill(c.status)}${c.duplicate_of ? ' <span class="pill warn">dup</span>' : ""}</td>
      <td class="muted">${esc(c.next_step || "-")}</td>
    </tr>`).join("") || `<tr><td colspan="5" class="muted">No cases.</td></tr>`;
  $$("#case-table tbody tr[data-id]").forEach((tr) =>
    tr.addEventListener("click", () => openCase(Number(tr.dataset.id))));
  if (SELECTED_CASE) await openCase(SELECTED_CASE, false);
}

async function openCase(id, refreshList = true) {
  SELECTED_CASE = id;
  if (refreshList) $$("#case-table tbody tr").forEach((tr) => tr.classList.toggle("selected", Number(tr.dataset.id) === id));
  const c = await api(`/api/cases/${id}`);
  const steps = CONFIG.steps;
  const refund = c.refund;
  $("#case-detail").innerHTML = `
    <div class="row between wrap gap">
      <h2>Case #${c.id} · ${esc(c.customer_name)}</h2>
      <div>${statusPill(c.status)}</div>
    </div>
    <dl class="kv">
      <dt>Amount</dt><dd>${money(c.amount_requested)}</dd>
      <dt>Description</dt><dd>${esc(c.description)}</dd>
      <dt>Assigned</dt><dd>${esc(c.assigned_agent || "-")}</dd>
      ${c.duplicate_of ? `<dt>Duplicate of</dt><dd>case #${c.duplicate_of}</dd>` : ""}
      ${refund ? `<dt>Decision</dt><dd>${statusPill(refund.decision)} by ${esc(refund.decided_by)}
        ${refund.processed ? '<span class="pill ok">issued</span>' : ""}<br>${esc(refund.reason)}
        <br><span class="muted">cites: ${esc(refund.policy_refs.join(", ") || "-")}</span></dd>` : ""}
    </dl>

    <h3>Workflow</h3>
    <div class="pipeline">
      ${steps.map((s) => `<button data-step="${s.step}" class="${s.step === c.next_step ? "next" : ""}">
        ${esc(s.step)}<small>${esc(s.agent)}</small></button>`).join("")}
    </div>
    <div class="row gap wrap">
      <button class="primary" id="run-next" ${c.next_step ? "" : "disabled"}>Run next step${c.next_step ? ` (${esc(c.next_step)})` : ""}</button>
      <button id="run-all" ${c.next_step ? "" : "disabled"}>Run full workflow</button>
    </div>
    <p class="muted">Any step can be clicked out of order; the policy engine decides whether it may run.</p>

    ${c.status === "supervisor_review" ? `
      <h3>Supervisor review (human)</h3>
      <div class="row gap wrap">
        <input id="sup-reason" placeholder="reason" style="flex:1;min-width:160px">
        <button class="safe" id="sup-approve">Approve</button>
        <button class="danger" id="sup-deny">Deny</button>
      </div>` : ""}

    <h3>Agent console</h3>
    <div class="row gap wrap">
      <select id="act-agent">${Object.keys(CONFIG.agents).filter((a) => a.endsWith("_agent"))
        .map((a) => `<option ${a === ACT_AGENT ? "selected" : ""}>${a}</option>`).join("")}</select>
      <input id="act-instruction" placeholder='instruction, or JSON {"tool": "...", "params": {...}}' style="flex:1;min-width:200px">
      <button id="act-send">Send</button>
    </div>

    <h3>Live agent activity</h3>
    <div class="log" id="step-log">${renderLog(STEP_LOG[id] || [])}</div>

    <h3>Emails</h3>
    ${c.emails.map((e) => `<div class="email ${e.direction}">
        <strong>${e.direction === "out" ? "→ to" : "← from"} ${esc(e.address)}</strong> · ${esc(e.subject)}
        <span class="muted">${esc(e.created_at.replace("T", " ").slice(0, 19))}</span><pre>${esc(e.body)}</pre></div>`).join("")
      || '<p class="muted">none</p>'}

    <h3>Audit trail for this case</h3>
    <div class="table-wrap"><table class="table">
      <thead><tr><th>#</th><th>Actor</th><th>Action</th><th>Decision</th><th>Rule</th><th>Reason</th></tr></thead>
      <tbody>${c.audit.map((a) => `<tr><td>${a.id}</td><td>${esc(a.actor_agent)}</td><td>${esc(a.action)}</td>
        <td>${decisionPill(a.decision)}</td><td>${esc(a.rule)}</td><td>${esc(a.reason)}</td></tr>`).join("")}</tbody>
    </table></div>`;

  $$("#case-detail .pipeline button").forEach((b) => b.addEventListener("click", () => runStep(id, b.dataset.step)));
  $("#run-next")?.addEventListener("click", () => runStep(id, c.next_step));
  $("#run-all")?.addEventListener("click", () => runAll(id));
  $("#sup-approve")?.addEventListener("click", () => supervisor(id, "approve"));
  $("#sup-deny")?.addEventListener("click", () => supervisor(id, "deny"));
  $("#act-send").addEventListener("click", () => agentAct(id));
}

function renderLog(results) {
  if (!results.length) return '<p class="muted">Run a step to see each agent\'s tool calls and the policy engine verdicts.</p>';
  return results.map((r) => `
    <div class="step">
      <div class="head">${r.ok ? '<span class="pill ok">ok</span>' : '<span class="pill deny">stopped</span>'}
        ${r.halted ? '<span class="pill deny">halted by kill switch</span>' : ""}
        <span>${esc(r.step)}</span><span class="muted">${esc(r.agent)}</span></div>
      <div>${esc(r.summary)}</div>
      ${r.calls.map((call) => `<div class="call">
        <span><code>${esc(call.tool)}</code></span>
        <span>${decisionPill(call.verdict.decision)} <code>${esc(call.verdict.rule)}</code></span>
        <span>${esc(call.verdict.reason)}${call.verdict.policy_refs.length ? ` <span class="muted">[${esc(call.verdict.policy_refs.join(", "))}]</span>` : ""}
          ${call.verdict.guardrails_off.length ? ` <span class="pill warn">guardrail off: ${esc(call.verdict.guardrails_off.join(", "))}</span>` : ""}</span>
      </div>`).join("")}
    </div>`).join("");
}

function pushLog(id, results) {
  STEP_LOG[id] = [...results.slice().reverse(), ...(STEP_LOG[id] || [])].slice(0, 40);
}

async function runStep(id, step) {
  try {
    pushLog(id, [await api(`/api/cases/${id}/steps/${step}`, { method: "POST" })]);
  } catch (e) { showError(e); }
  await refreshAfterAction();
}

async function runAll(id) {
  try {
    const run = await api(`/api/cases/${id}/run`, { method: "POST" });
    pushLog(id, run.steps);
  } catch (e) { showError(e); }
  await refreshAfterAction();
}

async function supervisor(id, decision) {
  const reason = $("#sup-reason").value.trim() || `Supervisor ${decision}d after review`;
  try {
    const res = await api(`/api/cases/${id}/supervisor`, { method: "POST", body: { decision, reason } });
    pushLog(id, [{ step: "supervisor", agent: "supervisor", ok: res.ok, halted: false,
      summary: `supervisor ${decision}`, calls: [res] }]);
  } catch (e) {
    const d = e.data?.detail;
    if (d?.verdict) pushLog(id, [{ step: "supervisor", agent: "supervisor", ok: false, halted: d.verdict.rule === "revocation", summary: "refused", calls: [d] }]);
    else showError(e);
  }
  await refreshAfterAction();
}

async function agentAct(id) {
  const agent = ACT_AGENT = $("#act-agent").value;
  const raw = $("#act-instruction").value.trim();
  const body = { case_id: id, instruction: raw };
  try {
    const parsed = JSON.parse(raw);
    if (parsed && parsed.tool) { body.tool = parsed.tool; body.params = parsed.params || {}; }
  } catch { /* plain-language instruction */ }
  try {
    pushLog(id, [await api(`/api/agents/${agent}/act`, { method: "POST", body })]);
  } catch (e) { showError(e); }
  await refreshAfterAction();
}

async function refreshAfterAction() {
  await loadConfig();
  await loadQueue();
}

// ---------------------------------------------------------------- new case
async function loadNewCase() {
  const customers = await api("/api/customers");
  $("#newcase-customer").innerHTML = customers.map((c) =>
    `<option value="${c.id}">#${c.id} ${esc(c.name)}</option>`).join("");
}

$("#newcase-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  const out = $("#newcase-result");
  out.classList.remove("hidden");
  try {
    const res = await api("/api/cases", { method: "POST", body: {
      customer_id: Number(f.get("customer_id")),
      amount_requested: Number(f.get("amount_requested")),
      description: f.get("description"),
    } });
    out.textContent = res.summary + "\n\n" + JSON.stringify(res.calls[0].verdict, null, 2);
    SELECTED_CASE = res.data.case_id;
    ev.target.reset();
  } catch (e) {
    out.textContent = "Refused: " + e.message;
  }
});

// ---------------------------------------------------------------- customers
async function loadCustomers() {
  const customers = await api("/api/customers");
  $("#customer-table tbody").innerHTML = customers.map((c) => `
    <tr><td>${c.id}</td><td>${esc(c.name)}</td><td>${esc(c.email)}</td><td><code>${esc(c.bank_account)}</code></td>
    <td class="num">${money(c.balance)}</td><td class="num">${money(c.weekly_approved_total)}</td></tr>`).join("");
}

// ---------------------------------------------------------------- reporting
async function loadReporting() {
  const [sum, weekly] = await Promise.all([api("/api/reports/summary"), api("/api/reports/weekly")]);
  const tiles = [
    ["Approved refunds", sum.refunds_by_decision.approved || 0],
    ["Denied refunds", sum.refunds_by_decision.denied || 0],
    ["Awaiting supervisor", sum.cases_by_status.supervisor_review || 0],
    ["Approved amount", money(sum.approved_amount)],
    ["Issued to balances", money(sum.issued_amount)],
  ];
  $("#report-tiles").innerHTML = tiles.map(([l, v]) =>
    `<div class="tile"><div class="label">${esc(l)}</div><div class="value">${esc(v)}</div></div>`).join("");
  $("#weekly-table tbody").innerHTML = weekly.customers.map((c) => {
    const pct = Math.min(100, (c.rolling_7d_total / c.cap) * 100);
    return `<tr><td>${esc(c.name)}</td><td class="num">${money(c.rolling_7d_total)}</td>
      <td><div class="meter ${pct >= 80 ? "hot" : ""}"><span style="width:${pct}%"></span></div></td>
      <td class="num">${money(c.headroom)}</td></tr>`;
  }).join("");
  $("#reasons-table tbody").innerHTML = Object.entries(sum.denial_reasons).map(([k, v]) =>
    `<tr><td>${esc(k)}</td><td class="num">${v}</td></tr>`).join("") || '<tr><td colspan="2" class="muted">none</td></tr>';
  $("#entries-table tbody").innerHTML = sum.entries.map((e) => `<tr><td>#${e.case_id}</td><td>#${e.customer_id}</td>
    <td>${statusPill(e.outcome)}</td><td class="num">${money(e.amount)}</td><td>${esc(e.reason)}</td>
    <td class="muted">${esc(e.created_at.replace("T", " ").slice(0, 16))}</td></tr>`).join("");
}

// ---------------------------------------------------------------- evidence
async function loadAudit() {
  const params = new URLSearchParams();
  new FormData($("#audit-filter")).forEach((v, k) => { if (v) params.set(k, v); });
  const [rows, chain] = await Promise.all([api("/api/audit?" + params), api("/api/audit/verify")]);
  const actorSel = $("#audit-filter select[name=actor]");
  if (actorSel.options.length === 1) {
    [...Object.keys(CONFIG.agents), "operator", "seed"].forEach((a) => actorSel.add(new Option(a, a)));
  }
  $("#chain-status").className = "pill " + (chain.ok ? "ok" : "deny");
  $("#chain-status").textContent = chain.ok ? `hash chain verified (${chain.rows} rows)` : `chain BROKEN at row ${chain.first_bad_id}`;
  $("#export-csv").href = "/api/audit/export?format=csv&" + params;
  $("#export-json").href = "/api/audit/export?format=json&" + params;
  $("#audit-table tbody").innerHTML = rows.map((a) => `<tr>
    <td>${a.id}</td><td class="muted">${esc(a.ts.replace("T", " ").slice(0, 19))}</td><td>${esc(a.actor_agent)}</td>
    <td><code>${esc(a.action)}</code></td><td>${esc(a.target)}</td><td>${decisionPill(a.decision)}</td>
    <td><code>${esc(a.rule)}</code></td><td>${esc(a.reason)}${a.guardrails_off.length ? ` <span class="pill warn">off: ${esc(a.guardrails_off.join(", "))}</span>` : ""}</td>
    <td>${esc(a.policy_refs.join(", "))}</td><td>${esc(a.revocation_state)}</td></tr>`).join("");
}

$("#audit-filter").addEventListener("submit", (ev) => { ev.preventDefault(); loadAudit().catch(showError); });

// ---------------------------------------------------------------- policies
async function loadPolicies() {
  const chunks = await api("/api/policies/chunks");
  $("#policy-chunks").innerHTML = chunks.map((c) => `<div class="chunk"><strong>${esc(c.id)}</strong>
    <span class="muted">${esc(c.metadata.source)}</span><pre>${esc(c.text)}</pre></div>`).join("")
    || '<p class="muted">No policy indexed.</p>';
}

$("#policy-file").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  $("#policy-form textarea").value = await file.text();
  $("#policy-form input[name=name]").value = file.name;
});

$("#policy-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  const out = $("#policy-result");
  out.classList.remove("hidden");
  try {
    const res = await api("/api/policies", { method: "POST", body: { name: f.get("name"), content: f.get("content") } });
    out.textContent = `Indexed ${res.data.chunks.length} chunks: ${res.data.chunks.join(", ")}`;
    await loadPolicies();
  } catch (e) { out.textContent = "Refused: " + e.message; }
});

$("#policy-search").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const q = new FormData(ev.target).get("q");
  const hits = await api("/api/policies/search?q=" + encodeURIComponent(q));
  $("#policy-search-results").innerHTML = hits.map((h) => `<div class="chunk"><strong>${esc(h.id)}</strong>
    <span class="muted">score ${h.score}</span><pre>${esc(h.text)}</pre></div>`).join("");
});

// ---------------------------------------------------------------- controls
async function loadControls() {
  await loadConfig();
  const revoked = CONFIG.revocation === "revoked";
  $("#kill-state").className = "kill-state " + CONFIG.revocation;
  $("#kill-state").textContent = revoked ? "Authority REVOKED" : "Authority active";
  const btn = $("#kill-toggle");
  btn.textContent = revoked ? "Restore authority" : "Revoke authority";
  btn.className = revoked ? "safe" : "danger";
  $("#guardrail-table tbody").innerHTML = Object.entries(CONFIG.guardrails).map(([g, on]) =>
    `<tr><td><code>${esc(g)}</code></td><td>${esc(CONFIG.policy_sections[g] || "")}</td>
     <td>${on ? '<span class="pill ok">on</span>' : '<span class="pill warn">OFF (lab)</span>'}</td></tr>`).join("");
  $("#grants-table tbody").innerHTML = Object.entries(CONFIG.agents).map(([a, tools]) =>
    `<tr><td><code>${esc(a)}</code></td><td>${tools.map((t) => `<code>${esc(t)}</code>`).join(", ")}</td></tr>`).join("");
}

$("#kill-toggle").addEventListener("click", async () => {
  const revoke = CONFIG.revocation !== "revoked";
  try {
    await api("/api/controls/revocation", { method: "POST",
      body: { revoked: revoke, reason: $("#kill-reason").value.trim() } });
    $("#kill-reason").value = "";
    await loadControls();
  } catch (e) { showError(e); }
});

// ---------------------------------------------------------------- boot
$$("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
$("#queue-filter").addEventListener("change", () => loadQueue().catch(showError));

(async () => {
  await loadConfig();
  let tab = "queue";
  try { tab = localStorage.getItem("tab") || "queue"; } catch { /* storage unavailable */ }
  showTab(LOADERS[tab] ? tab : "queue");
})().catch(showError);
