const CAB_STATE = {
  open: false,
  offset: 0,
  limit: 36,
  query: "",
  workflow: "",
  format: "",
  model: "",
  exclude_model: "",
  lora: "",
  exclude_lora: "",
  workflow_hash: "",
  sort: "modified",
  order: "desc",
  thumbSize: "medium",
  loading: false,
  hasMore: false,
  total: 0,
  assets: [],
};

function cabApi(path, options) {
  return fetch(path, options).then(async (response) => {
    if (response.status === 404 && !path.startsWith("/api/")) return fetch(`/api${path}`, options);
    return response;
  }).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data?.error?.message || `Request failed: ${response.status}`);
    return data;
  });
}

function cabMount() {
  if (document.getElementById("cab-launcher")) return;
  if (!document.body) {
    window.addEventListener("DOMContentLoaded", cabMount, { once: true });
    return;
  }
  cabStyles();

  const launcher = document.createElement("button");
  launcher.id = "cab-launcher";
  launcher.className = "cab-toggle";
  launcher.textContent = "Assets";
  launcher.title = "Open asset browser";
  document.body.appendChild(launcher);

  const panel = document.createElement("section");
  panel.id = "cab-panel";
  panel.className = "cab-panel cab-size-medium";
  panel.innerHTML = `
    <div class="cab-header">
      <strong>Assets</strong>
      <div class="cab-actions">
        <button data-action="scan">Scan</button>
        <button data-action="close">x</button>
      </div>
    </div>
    <div class="cab-filters">
      <input data-field="query" type="search" placeholder="Search filename, model, metadata" />
      <div class="cab-filter-row">
        <select data-field="workflow"><option value="">All</option><option value="1">Workflow</option><option value="0">No workflow</option></select>
        <select data-field="format"><option value="">Any format</option><option value="png">PNG</option><option value="webp">WebP</option><option value="jpeg">JPEG</option><option value="jpg">JPG</option></select>
        <select data-field="model" data-filter="models"><option value="">Any model</option></select>
        <select data-field="exclude_model" data-filter="models"><option value="">Hide no model</option></select>
        <select data-field="lora" data-filter="loras"><option value="">Any LoRA</option></select>
        <select data-field="exclude_lora" data-filter="loras"><option value="">Hide no LoRA</option></select>
        <select data-field="workflow_hash" data-filter="workflows"><option value="">Any workflow graph</option></select>
        <select data-field="sort"><option value="modified">Modified</option><option value="filename">Name</option><option value="size">Size</option><option value="model">Model</option></select>
        <select data-field="thumbSize"><option value="small">Small thumbs</option><option value="medium" selected>Medium thumbs</option><option value="large">Large thumbs</option></select>
      </div>
    </div>
    <div class="cab-grid"></div>
    <div class="cab-footer"><span class="cab-status">Ready</span><div><button data-action="less">Less</button><button data-action="more">More</button></div></div>
  `;
  document.body.appendChild(panel);
  CAB_STATE.panel = panel;

  launcher.addEventListener("click", () => {
    CAB_STATE.open = !CAB_STATE.open;
    panel.classList.toggle("cab-open", CAB_STATE.open);
    if (CAB_STATE.open && !CAB_STATE.assets.length) cabLoadAssets(true);
  });
  panel.querySelector('[data-action="close"]').addEventListener("click", () => {
    CAB_STATE.open = false;
    panel.classList.remove("cab-open");
  });
  panel.querySelector('[data-action="scan"]').addEventListener("click", cabScan);
  panel.querySelector('[data-action="more"]').addEventListener("click", () => cabLoadAssets(false));
  panel.querySelector('[data-action="less"]').addEventListener("click", cabLess);
  panel.querySelector('[data-field="query"]').addEventListener("input", cabDebounce((event) => {
    CAB_STATE.query = event.target.value.trim();
    cabLoadAssets(true);
  }, 250));
  for (const select of panel.querySelectorAll("select")) {
    select.addEventListener("change", () => {
      CAB_STATE[select.dataset.field] = select.value;
      if (select.dataset.field === "thumbSize") cabApplySize();
      else cabLoadAssets(true);
    });
  }
  cabApplySize();
}

function cabParams(includePaging = true) {
  const params = new URLSearchParams();
  if (includePaging) {
    params.set("limit", String(CAB_STATE.limit));
    params.set("offset", String(CAB_STATE.offset));
    params.set("sort", CAB_STATE.sort);
    params.set("order", CAB_STATE.order);
  }
  const map = { query: "q", workflow: "workflow", format: "format", model: "model", exclude_model: "exclude_model", lora: "lora", exclude_lora: "exclude_lora", workflow_hash: "workflow_hash" };
  for (const [stateKey, paramKey] of Object.entries(map)) if (CAB_STATE[stateKey]) params.set(paramKey, CAB_STATE[stateKey]);
  return params;
}

async function cabLoadAssets(reset) {
  if (CAB_STATE.loading) return;
  CAB_STATE.loading = true;
  if (reset) { CAB_STATE.offset = 0; CAB_STATE.assets = []; }
  cabStatus("Loading...");
  try {
    const data = await cabApi(`/asset-browser/assets?${cabParams(true)}`);
    CAB_STATE.assets = reset ? data.assets : CAB_STATE.assets.concat(data.assets);
    CAB_STATE.offset += data.assets.length;
    CAB_STATE.hasMore = data.has_more;
    CAB_STATE.total = data.total;
    cabRender();
    cabStatus(`${CAB_STATE.assets.length} of ${CAB_STATE.total}`);
    cabLoadFilters();
  } catch (error) {
    cabStatus(error.message || String(error));
  } finally {
    CAB_STATE.loading = false;
  }
}

async function cabLoadFilters() {
  try {
    const data = await cabApi(`/asset-browser/filters?${cabParams(false)}`);
    cabFillSelect("model", data.models || [], "Any model", CAB_STATE.model);
    cabFillSelect("exclude_model", data.models || [], "Hide no model", CAB_STATE.exclude_model);
    cabFillSelect("lora", data.loras || [], "Any LoRA", CAB_STATE.lora);
    cabFillSelect("exclude_lora", data.loras || [], "Hide no LoRA", CAB_STATE.exclude_lora);
    cabFillWorkflow(data.workflows || []);
  } catch (error) {
    console.debug("Asset Browser filters failed", error);
  }
}

function cabFillSelect(field, rows, empty, selected) {
  const select = CAB_STATE.panel.querySelector(`[data-field="${field}"]`);
  if (!select) return;
  const seen = new Set([""]);
  const options = [`<option value="">${cabEscape(empty)}</option>`];
  for (const row of rows) {
    const value = row.value || "";
    if (!value || seen.has(value)) continue;
    seen.add(value);
    options.push(`<option value="${cabEscape(value)}">${cabEscape(`${value} (${row.count})`)}</option>`);
  }
  if (selected && !seen.has(selected)) options.push(`<option value="${cabEscape(selected)}">${cabEscape(`${selected} (active)`)}</option>`);
  select.innerHTML = options.join("");
  select.value = selected || "";
}

function cabFillWorkflow(rows) {
  const select = CAB_STATE.panel.querySelector('[data-field="workflow_hash"]');
  const options = ['<option value="">Any workflow graph</option>'];
  for (const row of rows) {
    const model = row.model ? ` - ${row.model}` : "";
    options.push(`<option value="${cabEscape(row.value)}">${cabEscape(`${String(row.value).slice(0, 10)}${model} (${row.count})`)}</option>`);
  }
  select.innerHTML = options.join("");
  select.value = CAB_STATE.workflow_hash || "";
}

function cabRender() {
  const grid = CAB_STATE.panel.querySelector(".cab-grid");
  grid.innerHTML = "";
  if (!CAB_STATE.assets.length) {
    grid.innerHTML = '<div class="cab-empty">No assets found. Run Scan after generating images.</div>';
    return;
  }
  for (const asset of CAB_STATE.assets) {
    const card = document.createElement("button");
    card.className = "cab-card";
    card.title = asset.filename || "";
    card.innerHTML = `<img loading="lazy" src="${cabEscape(asset.view_url)}" alt="">`;
    card.addEventListener("click", () => cabDetail(asset.id));
    grid.appendChild(card);
  }
  CAB_STATE.panel.querySelector('[data-action="more"]').disabled = !CAB_STATE.hasMore;
  CAB_STATE.panel.querySelector('[data-action="less"]').disabled = CAB_STATE.assets.length <= CAB_STATE.limit;
}

async function cabDetail(id) {
  try {
    const asset = await cabApi(`/asset-browser/assets/${encodeURIComponent(id)}`);
    const backdrop = document.createElement("div");
    backdrop.className = "cab-backdrop";
    backdrop.innerHTML = `<div class="cab-dialog"><img src="${cabEscape(asset.view_url)}" alt=""><div><h3>${cabEscape(asset.filename)}</h3><p>${cabEscape(asset.model_name || "")}</p><pre>${cabEscape(JSON.stringify(asset.metadata || {}, null, 2))}</pre><button>Close</button></div></div>`;
    backdrop.addEventListener("click", (event) => { if (event.target === backdrop || event.target.tagName === "BUTTON") backdrop.remove(); });
    document.body.appendChild(backdrop);
  } catch (error) { cabStatus(error.message || String(error)); }
}

async function cabScan() {
  try { await cabApi("/asset-browser/scan", { method: "POST" }); cabStatus("Scan started"); }
  catch (error) { cabStatus(error.message || String(error)); }
}

function cabLess() {
  CAB_STATE.assets = CAB_STATE.assets.slice(0, Math.max(CAB_STATE.limit, CAB_STATE.assets.length - CAB_STATE.limit));
  CAB_STATE.offset = CAB_STATE.assets.length;
  CAB_STATE.hasMore = CAB_STATE.assets.length < CAB_STATE.total;
  cabRender();
  cabStatus(`${CAB_STATE.assets.length} of ${CAB_STATE.total}`);
}

function cabApplySize() {
  CAB_STATE.panel.classList.remove("cab-size-small", "cab-size-medium", "cab-size-large");
  CAB_STATE.panel.classList.add(`cab-size-${CAB_STATE.thumbSize || "medium"}`);
}
function cabStatus(text) { CAB_STATE.panel.querySelector(".cab-status").textContent = text; }
function cabEscape(value) { return String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function cabDebounce(fn, delay) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); }; }

function cabStyles() {
  if (document.getElementById("cab-styles")) return;
  const style = document.createElement("style");
  style.id = "cab-styles";
  style.textContent = `
    .cab-toggle{position:fixed;left:48px;top:45%;z-index:300000;width:38px;height:108px;border:1px solid #3a414c;border-radius:6px;background:#20242b;color:#e8edf4;writing-mode:vertical-rl;cursor:pointer;font:12px system-ui,sans-serif;letter-spacing:0}
    .cab-panel{position:fixed;z-index:299999;top:0;left:0;bottom:0;width:min(430px,calc(100vw - 48px));display:grid;grid-template-rows:auto auto 1fr auto;transform:translateX(-105%);transition:transform .16s ease;background:#191c21;color:#e8edf4;border-right:1px solid rgba(255,255,255,.12);box-shadow:10px 0 34px rgba(0,0,0,.36);font:13px/1.35 system-ui,sans-serif;--cab-cols:2;--cab-h:132px}
    .cab-panel.cab-open{transform:translateX(0)}.cab-size-small{--cab-cols:3;--cab-h:86px}.cab-size-medium{--cab-cols:2;--cab-h:132px}.cab-size-large{--cab-cols:1;--cab-h:260px}
    .cab-header,.cab-footer{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.1)}.cab-footer{border-top:1px solid rgba(255,255,255,.1);border-bottom:0;color:#aeb7c4}
    .cab-actions, .cab-footer div{display:flex;gap:6px}.cab-panel button,.cab-panel select,.cab-panel input{border:1px solid rgba(255,255,255,.14);border-radius:6px;background:#101318;color:#f4f7fb;min-height:30px}.cab-panel button{background:#262b33;cursor:pointer;padding:0 10px}
    .cab-filters{display:grid;gap:8px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.08)}.cab-filters input{box-sizing:border-box;width:100%;padding:0 9px}.cab-filter-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.cab-filter-row select{min-width:0;width:100%}
    .cab-grid{min-height:0;overflow-y:auto;overflow-x:hidden;padding:10px 12px 14px;display:grid;grid-template-columns:repeat(var(--cab-cols),minmax(0,1fr));grid-auto-rows:var(--cab-h);gap:10px;align-content:start}.cab-card{height:var(--cab-h)!important;padding:0;overflow:hidden;background:#05070a;border:1px solid rgba(255,255,255,.12);border-radius:7px}.cab-card img{display:block;width:100%;height:100%;object-fit:contain}.cab-empty{grid-column:1/-1;color:#aeb7c4;padding:30px 8px;text-align:center}
    .cab-backdrop{position:fixed;inset:0;z-index:300001;background:rgba(0,0,0,.5);display:grid;place-items:center;padding:22px}.cab-dialog{width:min(920px,96vw);max-height:92vh;display:grid;grid-template-columns:minmax(260px,42%) 1fr;background:#191c21;color:#e8edf4;border:1px solid rgba(255,255,255,.16);border-radius:8px;overflow:hidden}.cab-dialog img{width:100%;max-height:88vh;object-fit:contain;background:#05070a}.cab-dialog div{padding:12px;overflow:auto}.cab-dialog pre{max-height:55vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:#05070a;padding:8px;border-radius:6px}
  `;
  document.head.appendChild(style);
}

cabMount();