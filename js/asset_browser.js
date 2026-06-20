import { app } from "../../scripts/app.js";

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

function cabRenderPanel(parent, embedded = false) {
  cabStyles();
  const existing = parent.querySelector?.(".cab-panel");
  if (existing) existing.remove();

  const panel = document.createElement("section");
  panel.id = embedded ? "cab-sidebar-panel" : "cab-panel";
  panel.className = `cab-panel ${embedded ? "cab-sidebar cab-open" : ""} cab-size-medium`;
  panel.innerHTML = `
    <div class="cab-header">
      <strong>Assets</strong>
      <div class="cab-actions">
        <button data-action="scan">Scan</button>
        <button data-action="close" ${embedded ? "hidden" : ""}>x</button>
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
  parent.appendChild(panel);
  CAB_STATE.panel = panel;

  panel.querySelector('[data-action="close"]')?.addEventListener("click", () => {
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
  if (embedded) cabLoadAssets(true);
  return panel;
}

function cabMountFallback() {
  if (document.getElementById("cab-launcher")) return;
  if (!document.body) {
    window.addEventListener("DOMContentLoaded", cabMountFallback, { once: true });
    return;
  }
  const launcher = document.createElement("button");
  launcher.id = "cab-launcher";
  launcher.className = "cab-toggle";
  launcher.textContent = "Assets";
  launcher.title = "Open asset browser";
  document.body.appendChild(launcher);
  const panel = cabRenderPanel(document.body, false);
  launcher.addEventListener("click", () => {
    CAB_STATE.open = !CAB_STATE.open;
    panel.classList.toggle("cab-open", CAB_STATE.open);
    if (CAB_STATE.open && !CAB_STATE.assets.length) cabLoadAssets(true);
  });
}

function cabRegisterSidebar() {
  if (app?.extensionManager?.registerSidebarTab) {
    app.extensionManager.registerSidebarTab({
      id: "jonmsales.asset-browser",
      icon: "pi pi-images",
      title: "Assets",
      tooltip: "Asset Browser",
      type: "custom",
      render: (el) => {
        el.style.height = "100%";
        cabRenderPanel(el, true);
      },
    });
    return true;
  }
  return false;
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
    const summary = cabBuildAssetSummary(asset);
    const backdrop = document.createElement("div");
    backdrop.className = "cab-backdrop";
    backdrop.innerHTML = `
      <div class="cab-dialog cab-detail-dialog">
        <div class="cab-preview-pane">
          <img src="${cabEscape(asset.view_url)}" alt="">
        </div>
        <div class="cab-detail-pane">
          <header class="cab-detail-header">
            <div>
              <h3>${cabEscape(asset.filename)}</h3>
              <p>${cabEscape(summary.subtitle)}</p>
            </div>
            <button data-action="close-detail">Close</button>
          </header>
          <section class="cab-section">
            <h4>File</h4>
            <div class="cab-field-grid">${cabFieldsHtml(summary.file)}</div>
          </section>
          <section class="cab-section">
            <h4>Generation</h4>
            <div class="cab-field-grid">${cabFieldsHtml(summary.generation)}</div>
          </section>
          <section class="cab-section">
            <h4>Workflow</h4>
            <div class="cab-field-grid">${cabFieldsHtml(summary.workflow)}</div>
          </section>
          ${summary.loras.length ? `<section class="cab-section"><h4>LoRAs</h4><div class="cab-chip-list">${summary.loras.map((lora) => `<span>${cabEscape(lora)}</span>`).join("")}</div></section>` : ""}
          ${summary.prompts.positive || summary.prompts.negative ? `<section class="cab-section"><h4>Prompts</h4>${summary.prompts.positive ? `<label>Positive</label><pre class="cab-prompt-text">${cabEscape(summary.prompts.positive)}</pre>` : ""}${summary.prompts.negative ? `<label>Negative</label><pre class="cab-prompt-text">${cabEscape(summary.prompts.negative)}</pre>` : ""}</section>` : ""}
          <details class="cab-raw-json">
            <summary>Raw metadata JSON</summary>
            <pre>${cabEscape(JSON.stringify({ metadata: asset.metadata || {}, prompt: asset.prompt || null }, null, 2))}</pre>
          </details>
        </div>
      </div>`;
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop || event.target.dataset.action === "close-detail") backdrop.remove();
    });
    document.body.appendChild(backdrop);
  } catch (error) {
    cabStatus(error.message || String(error));
  }
}

function cabBuildAssetSummary(asset) {
  const promptGraph = cabPromptGraph(asset.prompt);
  const promptTexts = cabExtractPrompts(promptGraph);
  const dimensions = asset.width && asset.height ? `${asset.width} x ${asset.height}` : "-";
  const batchSize = cabFindInput(promptGraph, ["batch_size"]) || "-";
  return {
    subtitle: asset.model_name || asset.format || "Generated asset",
    file: [
      ["Filename", asset.filename],
      ["Folder", asset.subfolder || "output root"],
      ["Format", asset.format ? String(asset.format).toUpperCase() : "-"],
      ["Dimensions", dimensions],
      ["Size", cabFormatBytes(asset.size)],
      ["Modified", cabFormatNsDate(asset.modified)],
    ],
    generation: [
      ["Model", asset.model_name || cabFindInput(promptGraph, ["ckpt_name", "model_name", "unet_name"]) || "-"],
      ["Sampler", asset.sampler_name || cabFindInput(promptGraph, ["sampler_name"]) || "-"],
      ["Scheduler", cabFindInput(promptGraph, ["scheduler"]) || "-"],
      ["Steps", asset.steps ?? cabFindInput(promptGraph, ["steps"]) ?? "-"],
      ["CFG", asset.cfg ?? cabFindInput(promptGraph, ["cfg"]) ?? "-"],
      ["Seed", asset.seed ?? cabFindInput(promptGraph, ["seed", "noise_seed"]) ?? "-"],
      ["Batch Size", batchSize],
      ["Duration", asset.duration_sec ? `${Number(asset.duration_sec).toFixed(1)}s` : "Not embedded"],
    ],
    workflow: [
      ["Workflow Embedded", asset.has_workflow ? "Yes" : "No"],
      ["Prompt Embedded", asset.has_prompt ? "Yes" : "No"],
      ["Workflow Hash", asset.workflow_hash ? String(asset.workflow_hash).slice(0, 16) : "-"],
      ["Node Count", promptGraph ? Object.keys(promptGraph).length : "-"],
    ],
    loras: Array.isArray(asset.lora_names) ? asset.lora_names : [],
    prompts: promptTexts,
  };
}

function cabFieldsHtml(rows) {
  return rows.map(([label, value]) => `
    <div class="cab-field">
      <span>${cabEscape(label)}</span>
      <strong title="${cabEscape(value)}">${cabEscape(value ?? "-")}</strong>
    </div>
  `).join("");
}

function cabPromptGraph(prompt) {
  if (!prompt) return null;
  if (prompt.prompt && typeof prompt.prompt === "object") return prompt.prompt;
  return typeof prompt === "object" ? prompt : null;
}

function cabExtractPrompts(graph) {
  const out = { positive: "", negative: "" };
  if (!graph) return out;
  for (const node of Object.values(graph)) {
    if (!node || typeof node !== "object") continue;
    const inputs = node.inputs || {};
    const text = inputs.text || inputs.positive || inputs.negative || inputs.prompt;
    if (typeof text !== "string" || !text.trim()) continue;
    const title = String(node?._meta?.title || node.class_type || "").toLowerCase();
    if (!out.negative && title.includes("negative")) out.negative = text;
    else if (!out.positive && (title.includes("positive") || node.class_type === "CLIPTextEncode")) out.positive = text;
  }
  return out;
}

function cabFindInput(graph, keys) {
  if (!graph) return null;
  for (const node of Object.values(graph)) {
    if (!node || typeof node !== "object") continue;
    const inputs = node.inputs || {};
    for (const key of keys) {
      const value = inputs[key];
      if (value !== undefined && value !== null && !Array.isArray(value)) return value;
    }
  }
  return null;
}

function cabFormatBytes(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) return "-";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function cabFormatNsDate(ns) {
  const value = Number(ns);
  if (!Number.isFinite(value) || value <= 0) return "-";
  return new Date(value / 1_000_000).toLocaleString();
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
    .cab-panel.cab-open{transform:translateX(0)}.cab-panel.cab-sidebar{position:relative;inset:auto;z-index:auto;width:100%;height:100%;transform:none;transition:none;box-shadow:none;border-right:0;background:transparent}.cab-sidebar .cab-header{padding-top:12px}.cab-size-small{--cab-cols:3;--cab-h:86px}.cab-size-medium{--cab-cols:2;--cab-h:132px}.cab-size-large{--cab-cols:1;--cab-h:260px}
    .cab-header,.cab-footer{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.1)}.cab-footer{border-top:1px solid rgba(255,255,255,.1);border-bottom:0;color:#aeb7c4}
    .cab-actions, .cab-footer div{display:flex;gap:6px}.cab-panel button,.cab-panel select,.cab-panel input{border:1px solid rgba(255,255,255,.14);border-radius:6px;background:#101318;color:#f4f7fb;min-height:30px}.cab-panel button{background:#262b33;cursor:pointer;padding:0 10px}
    .cab-filters{display:grid;gap:8px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.08)}.cab-filters input{box-sizing:border-box;width:100%;padding:0 9px}.cab-filter-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.cab-filter-row select{min-width:0;width:100%}
    .cab-grid{min-height:0;overflow-y:auto;overflow-x:hidden;padding:10px 12px 14px;display:grid;grid-template-columns:repeat(var(--cab-cols),minmax(0,1fr));grid-auto-rows:var(--cab-h);gap:10px;align-content:start}.cab-card{height:var(--cab-h)!important;padding:0;overflow:hidden;background:#05070a;border:1px solid rgba(255,255,255,.12);border-radius:7px}.cab-card img{display:block;width:100%;height:100%;object-fit:contain}.cab-empty{grid-column:1/-1;color:#aeb7c4;padding:30px 8px;text-align:center}
    .cab-backdrop{position:fixed;inset:0;z-index:300001;background:rgba(0,0,0,.55);display:grid;place-items:center;padding:22px}.cab-dialog{width:min(1120px,96vw);max-height:92vh;display:grid;grid-template-columns:minmax(300px,44%) 1fr;background:#191c21;color:#e8edf4;border:1px solid rgba(255,255,255,.16);border-radius:8px;overflow:hidden}.cab-preview-pane{min-height:0;background:#05070a;display:grid;place-items:center}.cab-dialog img{width:100%;height:100%;max-height:92vh;object-fit:contain;background:#05070a}.cab-detail-pane{padding:14px 16px;overflow:auto}.cab-detail-header{display:flex;justify-content:space-between;align-items:start;gap:12px;margin-bottom:12px}.cab-detail-header h3{margin:0 0 4px;font-size:18px}.cab-detail-header p{margin:0;color:#aeb7c4}.cab-section{border-top:1px solid rgba(255,255,255,.1);padding:12px 0}.cab-section h4{margin:0 0 10px;font-size:13px;color:#d6dde8}.cab-field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.cab-field{min-width:0;border:1px solid rgba(255,255,255,.1);border-radius:6px;background:#11151b;padding:8px}.cab-field span{display:block;color:#95a0af;font-size:11px;margin-bottom:3px}.cab-field strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}.cab-chip-list{display:flex;flex-wrap:wrap;gap:6px}.cab-chip-list span{border:1px solid rgba(255,255,255,.14);border-radius:999px;background:#11151b;padding:4px 8px}.cab-section label{display:block;color:#95a0af;font-size:11px;margin:8px 0 4px}.cab-prompt-text,.cab-raw-json pre{max-height:210px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:#05070a;padding:10px;border-radius:6px;border:1px solid rgba(255,255,255,.08)}.cab-raw-json{border-top:1px solid rgba(255,255,255,.1);padding:12px 0}.cab-raw-json summary{cursor:pointer;color:#c8d1df}.cab-raw-json pre{max-height:320px}.cab-detail-header button{border:1px solid rgba(255,255,255,.14);border-radius:6px;background:#262b33;color:#f4f7fb;min-height:30px;padding:0 10px;cursor:pointer}@media(max-width:820px){.cab-dialog{grid-template-columns:1fr}.cab-preview-pane{max-height:45vh}.cab-field-grid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);
}

app.registerExtension({
  name: "JonMSales.AssetBrowser",
  async init() {
    if (!cabRegisterSidebar()) cabMountFallback();
  },
});

