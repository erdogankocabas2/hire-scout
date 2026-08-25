const STATUS_ORDER = [
  "new",
  "researching",
  "to_contact",
  "contacted",
  "replied",
  "interview",
  "rejected",
  "offer",
];

const state = {
  meta: null,
  pipeline: [],
  companies: [],
  people: [],
  runs: [],
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3200);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

function setView(name) {
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  const titles = {
    pipeline: ["Pipeline", "Track outreach toward getting hired."],
    companies: ["Companies", "Scouted companies and hiring signals."],
    people: ["People", "Cofounders, HR, and GTM / Product / BD contacts."],
    scout: ["Scout", "Scheduled research runs and manual triggers."],
  };
  $("#viewTitle").textContent = titles[name][0];
  $("#viewSubtitle").textContent = titles[name][1];
}

function renderPipeline() {
  const filter = $("#pipelineStatusFilter").value;
  const board = $("#pipelineBoard");
  const items = filter ? state.pipeline.filter((p) => p.status === filter) : state.pipeline;
  const byStatus = Object.fromEntries(STATUS_ORDER.map((s) => [s, []]));
  for (const item of items) {
    if (!byStatus[item.status]) byStatus[item.status] = [];
    byStatus[item.status].push(item);
  }
  board.innerHTML = STATUS_ORDER.map((status) => {
    const cards = (byStatus[status] || [])
      .map((item) => {
        const c = item.company || {};
        return `<div class="card" data-company-id="${item.company_id}">
          <strong>${escapeHtml(c.name || "Company")}</strong>
          <div class="meta">${escapeHtml(c.domain || c.locations || "—")}</div>
          <div class="chips">
            <select class="status-select" data-company-id="${item.company_id}" onclick="event.stopPropagation()">
              ${STATUS_ORDER.map(
                (s) => `<option value="${s}" ${s === item.status ? "selected" : ""}>${s}</option>`
              ).join("")}
            </select>
          </div>
        </div>`;
      })
      .join("");
    return `<div class="column"><h3>${status.replace("_", " ")} · ${(byStatus[status] || []).length}</h3>${cards || '<p class="muted">Empty</p>'}</div>`;
  }).join("");

  board.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("click", () => openCompany(Number(card.dataset.companyId)));
  });
  board.querySelectorAll(".status-select").forEach((sel) => {
    sel.addEventListener("change", async (e) => {
      const companyId = Number(sel.dataset.companyId);
      try {
        await api(`/api/pipeline/${companyId}`, {
          method: "PATCH",
          body: JSON.stringify({ status: e.target.value }),
        });
        await loadPipeline();
        toast("Pipeline updated");
      } catch (err) {
        toast(err.message, true);
      }
    });
  });
}

function renderCompanies() {
  const q = ($("#companySearch").value || "").toLowerCase();
  const list = $("#companiesList");
  const rows = state.companies.filter((c) => {
    if (!q) return true;
    return `${c.name} ${c.domain || ""} ${c.description || ""}`.toLowerCase().includes(q);
  });
  list.innerHTML = rows
    .map(
      (c) => `<article class="row-item" data-company-id="${c.id}">
        <div>
          <h3>${escapeHtml(c.name)}</h3>
          <p>${escapeHtml(c.description || c.hiring_signals || "No description yet")}</p>
          <div class="chips">
            ${c.domain ? `<span class="chip">${escapeHtml(c.domain)}</span>` : ""}
            ${c.locations ? `<span class="chip">${escapeHtml(c.locations)}</span>` : ""}
            ${c.stage_hint ? `<span class="chip warn">${escapeHtml(c.stage_hint)}</span>` : ""}
          </div>
        </div>
        <button class="btn small" data-open="${c.id}">Open</button>
      </article>`
    )
    .join("") || `<p class="muted">No companies yet. Run the scout.</p>`;

  list.querySelectorAll("[data-open]").forEach((btn) => {
    btn.addEventListener("click", () => openCompany(Number(btn.dataset.open)));
  });
  list.querySelectorAll(".row-item").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      openCompany(Number(row.dataset.companyId));
    });
  });
}

function renderPeople() {
  const category = $("#peopleCategoryFilter").value;
  const list = $("#peopleList");
  const rows = state.people.filter((p) => !category || p.category === category);
  list.innerHTML = rows
    .map(
      (p) => `<article class="row-item">
        <div>
          <h3>${escapeHtml(p.name)}</h3>
          <p>${escapeHtml(p.title || "—")} · ${escapeHtml(p.company_name || "Company")}</p>
          <div class="chips">
            <span class="chip accent">${escapeHtml(p.category)}</span>
            ${p.email ? `<span class="chip">${escapeHtml(p.email)}</span>` : ""}
            ${p.confidence != null ? `<span class="chip">${Math.round(p.confidence * 100)}%</span>` : ""}
          </div>
        </div>
        <div>
          ${p.email ? `<button class="btn small" data-copy="${escapeHtml(p.email)}">Copy email</button>` : ""}
          ${p.profile_url ? `<a class="btn small" href="${escapeAttr(p.profile_url)}" target="_blank" rel="noopener">Profile</a>` : ""}
        </div>
      </article>`
    )
    .join("") || `<p class="muted">No people yet.</p>`;

  list.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await navigator.clipboard.writeText(btn.dataset.copy);
      toast("Email copied");
    });
  });
}

function renderRuns() {
  const list = $("#runsList");
  list.innerHTML = state.runs
    .map((r) => {
      let stats = "";
      try {
        const s = r.stats_json ? JSON.parse(r.stats_json) : null;
        if (s) {
          stats = ` · +${s.companies_created || 0} companies · +${s.people_added || 0} people`;
        }
      } catch (_) {}
      return `<article class="row-item">
        <div>
          <h3>#${r.id} · ${escapeHtml(r.status)}</h3>
          <p>${escapeHtml(formatDate(r.started_at))}${escapeHtml(stats)}</p>
          ${r.error ? `<p style="color:#8f2f2f">${escapeHtml(r.error)}</p>` : ""}
        </div>
      </article>`;
    })
    .join("") || `<p class="muted">No runs yet.</p>`;
}

async function openCompany(id) {
  const data = await api(`/api/companies/${id}`);
  const dialog = $("#companyDialog");
  $("#dialogTitle").textContent = data.name;
  $("#dialogBody").innerHTML = `
    <p>${escapeHtml(data.description || "No description")}</p>
    <div class="chips" style="margin-top:10px">
      ${data.domain ? `<span class="chip">${escapeHtml(data.domain)}</span>` : ""}
      ${data.locations ? `<span class="chip">${escapeHtml(data.locations)}</span>` : ""}
      ${data.pipeline_status ? `<span class="chip accent">${escapeHtml(data.pipeline_status)}</span>` : ""}
    </div>
    <p style="margin-top:12px">${escapeHtml(data.hiring_signals || "")}</p>
    <div class="row gap" style="margin-top:12px">
      ${data.website_url ? `<a class="btn small" href="${escapeAttr(data.website_url)}" target="_blank" rel="noopener">Website</a>` : ""}
      ${data.careers_url ? `<a class="btn small" href="${escapeAttr(data.careers_url)}" target="_blank" rel="noopener">Careers</a>` : ""}
    </div>
    <div class="dialog-section">
      <h3>People</h3>
      ${(data.people || [])
        .map(
          (p) => `<div class="row-item" style="box-shadow:none;margin-bottom:8px">
            <div><h3>${escapeHtml(p.name)}</h3><p>${escapeHtml(p.title || "")} · ${escapeHtml(p.category)}</p>
            ${p.email ? `<div class="chips"><span class="chip">${escapeHtml(p.email)}</span></div>` : ""}</div>
          </div>`
        )
        .join("") || "<p class='muted'>No people linked.</p>"}
    </div>
    <div class="dialog-section">
      <h3>Jobs</h3>
      ${(data.jobs || [])
        .map(
          (j) => `<div class="row-item" style="box-shadow:none;margin-bottom:8px">
            <div><h3>${escapeHtml(j.title)}</h3><p>${escapeHtml(j.role_family || "")} · ${escapeHtml(j.location || "")}</p></div>
            ${j.url ? `<a class="btn small" href="${escapeAttr(j.url)}" target="_blank" rel="noopener">Open</a>` : ""}
          </div>`
        )
        .join("") || "<p class='muted'>No jobs linked.</p>"}
    </div>
    <div class="dialog-section">
      <h3>Notes</h3>
      <textarea id="companyNotes" rows="3" style="width:100%;font:inherit;padding:10px;border-radius:10px;border:1px solid var(--line)">${escapeHtml(
        (state.pipeline.find((p) => p.company_id === id) || {}).notes || ""
      )}</textarea>
      <div style="margin-top:8px">
        <button class="btn primary small" id="saveNotesBtn">Save notes</button>
      </div>
    </div>
  `;
  dialog.showModal();
  $("#saveNotesBtn").addEventListener("click", async (e) => {
    e.preventDefault();
    await api(`/api/pipeline/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ notes: $("#companyNotes").value }),
    });
    await loadPipeline();
    toast("Notes saved");
  });
}

async function loadMeta() {
  state.meta = await api("/api/meta");
  $("#geoLabel").textContent = `${state.meta.geo} · GTM / Product / BD`;
  $("#scoutGeo").value = state.meta.geo;
  $("#scheduleInfo").textContent = `Runs daily at ${String(state.meta.cron_hour).padStart(2, "0")}:${String(
    state.meta.cron_minute
  ).padStart(2, "0")} local time · geo ${state.meta.geo}`;
  $("#keysStatus").innerHTML = [
    `openai: ${state.meta.has_openai ? "on" : "off"}`,
    `tavily: ${state.meta.has_tavily ? "on" : "off"}`,
    `hunter: ${state.meta.has_hunter ? "on" : "off"}`,
  ].join("<br/>");

  const sel = $("#pipelineStatusFilter");
  if (sel.options.length <= 1) {
    STATUS_ORDER.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      sel.appendChild(opt);
    });
  }
}

async function loadPipeline() {
  state.pipeline = await api("/api/pipeline");
  renderPipeline();
}

async function loadCompanies() {
  const q = $("#companySearch").value;
  state.companies = await api(`/api/companies${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  renderCompanies();
}

async function loadPeople() {
  const category = $("#peopleCategoryFilter").value;
  state.people = await api(`/api/people${category ? `?category=${encodeURIComponent(category)}` : ""}`);
  renderPeople();
}

async function loadRuns() {
  state.runs = await api("/api/scout/runs");
  renderRuns();
}

async function runScout() {
  const btn = $("#runScoutBtn");
  btn.disabled = true;
  btn.textContent = "Scouting…";
  toast("Scout started — this can take a few minutes");
  try {
    const body = {
      geo: $("#scoutGeo")?.value || "Turkey",
      max_companies: Number($("#scoutMax")?.value || 15),
    };
    const result = await api("/api/scout/run", { method: "POST", body: JSON.stringify(body) });
    if (result.status === "failed") {
      toast(result.error || "Scout failed", true);
    } else {
      const s = result.stats || {};
      toast(`Done: +${s.companies_created || 0} companies, +${s.people_added || 0} people`);
    }
    await Promise.all([loadPipeline(), loadCompanies(), loadPeople(), loadRuns()]);
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run scout now";
  }
}

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(str) {
  return escapeHtml(str).replaceAll("'", "&#39;");
}

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function wireEvents() {
  $$(".nav-btn").forEach((btn) => btn.addEventListener("click", () => setView(btn.dataset.view)));
  $("#runScoutBtn").addEventListener("click", runScout);
  $("#pipelineStatusFilter").addEventListener("change", renderPipeline);
  $("#companySearch").addEventListener("input", () => {
    clearTimeout(wireEvents._t);
    wireEvents._t = setTimeout(loadCompanies, 250);
  });
  $("#peopleCategoryFilter").addEventListener("change", loadPeople);
}

async function boot() {
  wireEvents();
  await loadMeta();
  await Promise.all([loadPipeline(), loadCompanies(), loadPeople(), loadRuns()]);
}

boot().catch((err) => toast(err.message, true));
