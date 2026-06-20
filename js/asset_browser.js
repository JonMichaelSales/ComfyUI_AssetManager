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
  favorite: "",
  archived: "",
  rating: "",
  tag: "",
  collection: "",
  min_width: "",
  min_height: "",
  date_from: "",
  date_to: "",
  sampler: "",
  seed: "",
  duration: "",
  sort: "modified",
  order: "desc",
  thumbSize: "medium",
  loading: false,
  hasMore: false,
  total: 0,
  assets: [],
  selected: new Set(),
  modelAliases: new Map(),
  hideModelExtensions: true,
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
        <select data-field="tag" data-filter="tags"><option value="">Any tag</option></select>
        <select data-field="collection" data-filter="collections"><option value="">Any collection</option></select>
        <select data-field="favorite"><option value="">Any favorite</option><option value="1">Favorites</option><option value="0">Not favorites</option></select>
        <select data-field="archived"><option value="">Active assets</option><option value="1">Archived only</option><option value="all">Active + archived</option></select>
        <select data-field="rating"><option value="">Any rating</option><option value="5">5 stars</option><option value="4">4+ stars</option><option value="3">3+ stars</option><option value="2">2+ stars</option><option value="1">1+ stars</option></select>
        <select data-field="duration"><option value="">Any duration</option><option value="1">Has duration</option><option value="0">No duration</option></select>
        <select data-field="sampler" data-filter="samplers"><option value="">Any sampler</option></select>
        <select data-field="sort"><option value="modified">Modified</option><option value="filename">Name</option><option value="size">Size</option><option value="model">Model</option></select>
        <select data-field="thumbSize"><option value="small">Small thumbs</option><option value="medium" selected>Medium thumbs</option><option value="large">Large thumbs</option></select>
      </div>
      <div class="cab-filter-row cab-text-filters">
        <input data-field="seed" data-filter-input type="search" placeholder="Seed" />
        <input data-field="min_width" data-filter-input type="number" min="1" placeholder="Min width" />
        <input data-field="min_height" data-filter-input type="number" min="1" placeholder="Min height" />
        <input data-field="date_from" data-filter-input type="date" title="Modified from" />
        <input data-field="date_to" data-filter-input type="date" title="Modified to" />
      </div>
      <div class="cab-bulk">
        <span data-role="selection-count">0 selected</span>
        <button data-action="bulk-favorite">Favorite</button>
        <button data-action="bulk-archive">Archive</button>
        <button data-action="bulk-tag">Tag</button>
        <button data-action="clear-selection">Clear</button>
      </div>
    </div>
    <div class="cab-grid"></div>
    <div class="cab-footer"><span class="cab-status">Ready</span><div><button data-action="less">Less</button><button data-action="more">More</button></div></div>
  `;
  parent.appendChild(panel);
  CAB_STATE.panel = panel;
  window.ComfyAssetBrowser = {
    ...(window.ComfyAssetBrowser || {}),
    openAsset: (id) => cabDetail(id),
    openByOutput: (filename) => cabOpenByOutput(filename),
  };

  panel.querySelector('[data-action="close"]')?.addEventListener("click", () => {
    CAB_STATE.open = false;
    panel.classList.remove("cab-open");
  });
  panel.querySelector('[data-action="scan"]').addEventListener("click", cabScan);
  panel.querySelector('[data-action="more"]').addEventListener("click", () => cabLoadAssets(false));
  panel.querySelector('[data-action="less"]').addEventListener("click", cabLess);
  panel.querySelector('[data-action="bulk-favorite"]').addEventListener("click", () => cabBulkAnnotation({ favorite: true }));
  panel.querySelector('[data-action="bulk-archive"]').addEventListener("click", () => cabBulkAnnotation({ archived: true }));
  panel.querySelector('[data-action="bulk-tag"]').addEventListener("click", cabBulkTag);
  panel.querySelector('[data-action="clear-selection"]').addEventListener("click", cabClearSelection);
  panel.querySelector('[data-field="query"]').addEventListener("input", cabDebounce((event) => {
    CAB_STATE.query = event.target.value.trim();
    cabLoadAssets(true);
  }, 250));
  for (const input of panel.querySelectorAll("[data-filter-input]")) {
    input.addEventListener("input", cabDebounce(() => {
      CAB_STATE[input.dataset.field] = input.value.trim();
      cabLoadAssets(true);
    }, 300));
  }
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

async function cabOpenByOutput(filename) {
  const data = await cabApi(`/asset-browser/assets?limit=1&offset=0&q=${encodeURIComponent(filename)}`);
  const asset = (data.assets || []).find((row) => row.filename === filename) || data.assets?.[0];
  if (asset) cabDetail(asset.id);
  return asset || null;
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
  const map = { query: "q", workflow: "workflow", format: "format", model: "model", exclude_model: "exclude_model", lora: "lora", exclude_lora: "exclude_lora", workflow_hash: "workflow_hash", favorite: "favorite", archived: "archived", rating: "rating", tag: "tag", collection: "collection", min_width: "min_width", min_height: "min_height", sampler: "sampler", seed: "seed", duration: "duration" };
  for (const [stateKey, paramKey] of Object.entries(map)) if (CAB_STATE[stateKey]) params.set(paramKey, CAB_STATE[stateKey]);
  if (CAB_STATE.date_from) params.set("date_from", String(Date.parse(CAB_STATE.date_from) * 1_000_000));
  if (CAB_STATE.date_to) params.set("date_to", String((Date.parse(CAB_STATE.date_to) + 86_399_999) * 1_000_000));
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
    if (reset) CAB_STATE.selected.clear();
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
    await cabLoadPerformanceSettings();
    const data = await cabApi(`/asset-browser/filters?${cabParams(false)}`);
    cabFillSelect("model", data.models || [], "Any model", CAB_STATE.model);
    cabFillSelect("exclude_model", data.models || [], "Hide no model", CAB_STATE.exclude_model);
    cabFillSelect("lora", data.loras || [], "Any LoRA", CAB_STATE.lora);
    cabFillSelect("exclude_lora", data.loras || [], "Hide no LoRA", CAB_STATE.exclude_lora);
    cabFillSelect("tag", data.tags || [], "Any tag", CAB_STATE.tag);
    cabFillSelect("sampler", data.samplers || [], "Any sampler", CAB_STATE.sampler);
    cabFillCollection(data.collections || []);
    cabFillWorkflow(data.workflows || []);
  } catch (error) {
    console.debug("Asset Browser filters failed", error);
  }
}

async function cabLoadPerformanceSettings() {
  try {
    const data = await cabApi("/performance-tracker/settings");
    CAB_STATE.modelAliases = new Map((data.aliases || []).map((row) => [row.model_name, row.friendly_name]));
    CAB_STATE.hideModelExtensions = data.settings?.hide_file_extensions !== false;
  } catch (_) {
    CAB_STATE.modelAliases = new Map();
  }
}

function cabModelLabel(name) {
  if (!name) return "";
  if (CAB_STATE.modelAliases.has(name)) return CAB_STATE.modelAliases.get(name);
  if (!CAB_STATE.hideModelExtensions) return name;
  return String(name).replace(/\.(safetensors|ckpt|pt|pth|bin)$/i, "");
}

function cabFillCollection(rows) {
  const select = CAB_STATE.panel.querySelector('[data-field="collection"]');
  const options = ['<option value="">Any collection</option>'];
  for (const row of rows) {
    options.push(`<option value="${cabEscape(row.value)}">${cabEscape(`${row.label || row.value} (${row.count})`)}</option>`);
  }
  select.innerHTML = options.join("");
  select.value = CAB_STATE.collection || "";
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
    const label = field.includes("model") ? cabModelLabel(value) : value;
    options.push(`<option value="${cabEscape(value)}">${cabEscape(`${label} (${row.count})`)}</option>`);
  }
  if (selected && !seen.has(selected)) options.push(`<option value="${cabEscape(selected)}">${cabEscape(`${selected} (active)`)}</option>`);
  select.innerHTML = options.join("");
  select.value = selected || "";
}

function cabFillWorkflow(rows) {
  const select = CAB_STATE.panel.querySelector('[data-field="workflow_hash"]');
  const options = ['<option value="">Any workflow graph</option>'];
  for (const row of rows) {
    const model = row.model ? ` - ${cabModelLabel(row.model)}` : "";
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
    const card = document.createElement("div");
    card.className = "cab-card";
    card.classList.toggle("is-selected", CAB_STATE.selected.has(asset.id));
    card.title = asset.filename || "";
    card.innerHTML = `
      <button class="cab-thumb" type="button"><img loading="lazy" src="${cabEscape(asset.view_url)}" alt=""></button>
      <label class="cab-select"><input type="checkbox" ${CAB_STATE.selected.has(asset.id) ? "checked" : ""}></label>
      <div class="cab-badges">${asset.favorite ? "<span>Fav</span>" : ""}${asset.rating ? `<span>${Number(asset.rating)}/5</span>` : ""}${asset.archived ? "<span>Archived</span>" : ""}${asset.duration_sec ? `<span>${Number(asset.duration_sec).toFixed(1)}s</span>` : ""}</div>`;
    card.querySelector(".cab-thumb").addEventListener("click", () => cabDetail(asset.id));
    card.querySelector("input").addEventListener("change", (event) => {
      if (event.target.checked) CAB_STATE.selected.add(asset.id);
      else CAB_STATE.selected.delete(asset.id);
      cabRender();
    });
    grid.appendChild(card);
  }
  CAB_STATE.panel.querySelector('[data-action="more"]').disabled = !CAB_STATE.hasMore;
  CAB_STATE.panel.querySelector('[data-action="less"]').disabled = CAB_STATE.assets.length <= CAB_STATE.limit;
  cabUpdateSelection();
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
          <section class="cab-section cab-curation">
            <h4>Curation</h4>
            <div class="cab-curation-row">
              <label><input type="checkbox" data-curation="favorite" ${asset.favorite ? "checked" : ""}> Favorite</label>
              <label><input type="checkbox" data-curation="archived" ${asset.archived ? "checked" : ""}> Archived</label>
              <label>Rating <select data-curation="rating">${[0,1,2,3,4,5].map((n) => `<option value="${n}" ${Number(asset.rating || 0) === n ? "selected" : ""}>${n || "None"}</option>`).join("")}</select></label>
            </div>
            <div class="cab-chip-list">${(asset.tags || []).map((tag) => `<span>${cabEscape(tag.name)} <button data-remove-tag="${cabEscape(tag.name)}">x</button></span>`).join("") || "<em>No tags</em>"}</div>
            <div class="cab-inline-form"><input data-role="new-tag" placeholder="Add tag"><button data-action="add-tag">Add Tag</button></div>
            <div class="cab-chip-list">${(asset.collections || []).map((collection) => `<span>${cabEscape(collection.name)} <button data-remove-collection="${collection.id}">x</button></span>`).join("") || "<em>No collections</em>"}</div>
            <div class="cab-inline-form"><input data-role="new-collection" placeholder="Add to collection"><button data-action="add-collection">Add Collection</button></div>
            <label>Note</label><textarea data-curation="note" placeholder="Notes for this asset">${cabEscape(asset.note || "")}</textarea>
            <button data-action="save-curation">Save Curation</button>
          </section>
          <section class="cab-section cab-performance-section">
            <h4>Performance</h4>
            <div data-role="performance-content" class="cab-subtle">Looking for linked run...</div>
          </section>
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
          <section class="cab-section">
            <h4>Related Assets</h4>
            <div data-role="related-content" class="cab-subtle">Loading related assets...</div>
          </section>
          <details class="cab-raw-json">
            <summary>Raw metadata JSON</summary>
            <pre>${cabEscape(JSON.stringify({ metadata: asset.metadata || {}, prompt: asset.prompt || null }, null, 2))}</pre>
          </details>
        </div>
      </div>`;
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop || event.target.dataset.action === "close-detail") backdrop.remove();
    });
    backdrop.querySelector('[data-action="save-curation"]').addEventListener("click", async () => {
      await cabSaveCuration(asset.id, backdrop);
      backdrop.remove();
      await cabLoadAssets(true);
    });
    backdrop.querySelector('[data-action="add-tag"]').addEventListener("click", async () => {
      const input = backdrop.querySelector('[data-role="new-tag"]');
      const name = input.value.trim();
      if (!name) return;
      await cabApi(`/asset-browser/assets/${encodeURIComponent(asset.id)}/tags/${encodeURIComponent(name)}`, { method: "POST" });
      backdrop.remove();
      cabDetail(asset.id);
    });
    backdrop.querySelector('[data-action="add-collection"]').addEventListener("click", async () => {
      const input = backdrop.querySelector('[data-role="new-collection"]');
      const name = input.value.trim();
      if (!name) return;
      const collection = await cabApi("/asset-browser/collections", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
      await cabApi(`/asset-browser/collections/${collection.id}/assets/${encodeURIComponent(asset.id)}`, { method: "POST" });
      backdrop.remove();
      cabDetail(asset.id);
    });
    for (const button of backdrop.querySelectorAll("[data-remove-tag]")) {
      button.addEventListener("click", async () => {
        await cabApi(`/asset-browser/assets/${encodeURIComponent(asset.id)}/tags/${encodeURIComponent(button.dataset.removeTag)}`, { method: "DELETE" });
        backdrop.remove();
        cabDetail(asset.id);
      });
    }
    for (const button of backdrop.querySelectorAll("[data-remove-collection]")) {
      button.addEventListener("click", async () => {
        await cabApi(`/asset-browser/collections/${encodeURIComponent(button.dataset.removeCollection)}/assets/${encodeURIComponent(asset.id)}`, { method: "DELETE" });
        backdrop.remove();
        cabDetail(asset.id);
      });
    }
    document.body.appendChild(backdrop);
    cabLoadPerformance(asset, backdrop);
    cabLoadRelated(asset.id, backdrop);
  } catch (error) {
    cabStatus(error.message || String(error));
  }
}

async function cabSaveCuration(assetId, root) {
  const body = {
    favorite: root.querySelector('[data-curation="favorite"]').checked,
    archived: root.querySelector('[data-curation="archived"]').checked,
    rating: Number(root.querySelector('[data-curation="rating"]').value) || null,
    note: root.querySelector('[data-curation="note"]').value,
  };
  await cabApi(`/asset-browser/assets/${encodeURIComponent(assetId)}/annotation`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function cabLoadPerformance(asset, root) {
  const target = root.querySelector('[data-role="performance-content"]');
  try {
    const params = new URLSearchParams({ filename: asset.filename, subfolder: asset.subfolder || "", type: asset.type || "output" });
    const data = await cabApi(`/performance-tracker/assets/by-output?${params}`);
    const run = data.run;
    const cache = run.total_node_count ? `${Math.round((Number(run.cached_node_count || 0) / Number(run.total_node_count)) * 100)}%` : "-";
    target.innerHTML = `
      <div class="cab-field-grid">${cabFieldsHtml([
        ["Duration", cabFormatDurationMs(run.duration_ms)],
        ["Model", run.primary_model_display || run.primary_model || "-"],
        ["Status", run.status || "-"],
        ["Cache", cache],
        ["Nodes", `${run.cached_node_count}/${run.executed_node_count}/${run.total_node_count}`],
        ["Averages", run.excluded_from_stats ? "Excluded" : "Included"],
      ])}</div>
      <button data-action="open-performance-run">Open Performance Run</button>`;
    target.querySelector('[data-action="open-performance-run"]').addEventListener("click", () => {
      if (window.ComfyPerformanceTracker?.openRun) window.ComfyPerformanceTracker.openRun(run.prompt_id);
      else alert(`Performance run: ${run.prompt_id}`);
    });
  } catch (_) {
    target.textContent = "No linked Performance Tracker run found.";
  }
}

async function cabLoadRelated(assetId, root) {
  const target = root.querySelector('[data-role="related-content"]');
  try {
    const data = await cabApi(`/asset-browser/assets/${encodeURIComponent(assetId)}/related?limit=8`);
    const related = data.related || {};
    const sections = Object.entries(related).filter(([, rows]) => rows?.length);
    if (!sections.length) {
      target.textContent = "No related assets found.";
      return;
    }
    target.innerHTML = sections.map(([label, rows]) => `
      <div class="cab-related-section"><strong>${cabEscape(label)}</strong><div class="cab-related-grid">
        ${rows.map((row) => `<button data-asset-id="${cabEscape(row.id)}"><img src="${cabEscape(row.view_url)}" alt=""><span>${cabEscape(row.filename)}</span></button>`).join("")}
      </div></div>
    `).join("");
    for (const button of target.querySelectorAll("[data-asset-id]")) {
      button.addEventListener("click", () => {
        root.remove();
        cabDetail(button.dataset.assetId);
      });
    }
  } catch (_) {
    target.textContent = "Related assets are unavailable.";
  }
}

function cabBuildAssetSummary(asset) {
  const promptGraph = cabPromptGraph(asset.prompt);
  const promptTexts = cabExtractPrompts(promptGraph);
  const dimensions = asset.width && asset.height ? `${asset.width} x ${asset.height}` : "-";
  const batchSize = cabFindInput(promptGraph, ["batch_size"]) || "-";
  return {
    subtitle: cabModelLabel(asset.model_name) || asset.format || "Generated asset",
    file: [
      ["Filename", asset.filename],
      ["Folder", asset.subfolder || "output root"],
      ["Format", asset.format ? String(asset.format).toUpperCase() : "-"],
      ["Dimensions", dimensions],
      ["Size", cabFormatBytes(asset.size)],
      ["Modified", cabFormatNsDate(asset.modified)],
    ],
    generation: [
      ["Model", cabModelLabel(asset.model_name || cabFindInput(promptGraph, ["ckpt_name", "model_name", "unet_name"])) || "-"],
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

function cabFormatDurationMs(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value)) return "-";
  if (value < 60_000) return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)}s`;
  return `${Math.floor(value / 60_000)}m ${Math.round((value % 60_000) / 1000)}s`;
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

async function cabBulkAnnotation(values) {
  const ids = [...CAB_STATE.selected];
  if (!ids.length) return;
  cabStatus("Updating selected assets...");
  try {
    for (const id of ids) {
      await cabApi(`/asset-browser/assets/${encodeURIComponent(id)}/annotation`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
    }
    CAB_STATE.selected.clear();
    await cabLoadAssets(true);
  } catch (error) {
    cabStatus(error.message || String(error));
  }
}

async function cabBulkTag() {
  const ids = [...CAB_STATE.selected];
  if (!ids.length) return;
  const tag = prompt("Tag selected assets");
  if (!tag?.trim()) return;
  cabStatus("Tagging selected assets...");
  try {
    for (const id of ids) {
      await cabApi(`/asset-browser/assets/${encodeURIComponent(id)}/tags/${encodeURIComponent(tag.trim())}`, { method: "POST" });
    }
    CAB_STATE.selected.clear();
    await cabLoadAssets(true);
  } catch (error) {
    cabStatus(error.message || String(error));
  }
}

function cabClearSelection() {
  CAB_STATE.selected.clear();
  cabRender();
}

function cabUpdateSelection() {
  const count = CAB_STATE.selected.size;
  const label = CAB_STATE.panel.querySelector('[data-role="selection-count"]');
  if (label) label.textContent = `${count} selected`;
  for (const action of ["bulk-favorite", "bulk-archive", "bulk-tag", "clear-selection"]) {
    const button = CAB_STATE.panel.querySelector(`[data-action="${action}"]`);
    if (button) button.disabled = count === 0;
  }
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
    .cab-filters{display:grid;gap:8px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.08);max-height:42vh;overflow:auto}.cab-filters input{box-sizing:border-box;width:100%;padding:0 9px}.cab-filter-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.cab-filter-row select{min-width:0;width:100%}.cab-text-filters{grid-template-columns:repeat(2,minmax(0,1fr))}.cab-bulk{display:flex;align-items:center;gap:6px;flex-wrap:wrap;color:#aeb7c4}.cab-bulk button:disabled{opacity:.45;cursor:not-allowed}
    .cab-grid{min-height:0;overflow-y:auto;overflow-x:hidden;padding:10px 12px 14px;display:grid;grid-template-columns:repeat(var(--cab-cols),minmax(0,1fr));grid-auto-rows:var(--cab-h);gap:10px;align-content:start}.cab-card{position:relative;height:var(--cab-h)!important;padding:0;overflow:hidden;background:#05070a;border:1px solid rgba(255,255,255,.12);border-radius:7px}.cab-card.is-selected{outline:2px solid #58a6ff}.cab-thumb{display:block;width:100%;height:100%;padding:0!important;border:0!important;background:#05070a!important}.cab-card img{display:block;width:100%;height:100%;object-fit:contain}.cab-select{position:absolute;top:5px;left:5px;margin:0!important}.cab-select input{min-height:auto;width:16px;height:16px}.cab-badges{position:absolute;left:5px;right:5px;bottom:5px;display:flex;gap:4px;flex-wrap:wrap;pointer-events:none}.cab-badges span{border-radius:4px;background:rgba(0,0,0,.72);color:#f4f7fb;padding:2px 4px;font-size:10px}.cab-empty{grid-column:1/-1;color:#aeb7c4;padding:30px 8px;text-align:center}
    .cab-backdrop{position:fixed;inset:0;z-index:300001;background:rgba(0,0,0,.55);display:grid;place-items:center;padding:22px}.cab-dialog{width:min(1120px,96vw);max-height:92vh;display:grid;grid-template-columns:minmax(300px,44%) 1fr;background:#191c21;color:#e8edf4;border:1px solid rgba(255,255,255,.16);border-radius:8px;overflow:hidden}.cab-preview-pane{min-height:0;background:#05070a;display:grid;place-items:center}.cab-dialog img{width:100%;height:100%;max-height:92vh;object-fit:contain;background:#05070a}.cab-detail-pane{padding:14px 16px;overflow:auto}.cab-detail-header{display:flex;justify-content:space-between;align-items:start;gap:12px;margin-bottom:12px}.cab-detail-header h3{margin:0 0 4px;font-size:18px}.cab-detail-header p{margin:0;color:#aeb7c4}.cab-section{border-top:1px solid rgba(255,255,255,.1);padding:12px 0}.cab-section h4{margin:0 0 10px;font-size:13px;color:#d6dde8}.cab-field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.cab-field{min-width:0;border:1px solid rgba(255,255,255,.1);border-radius:6px;background:#11151b;padding:8px}.cab-field span{display:block;color:#95a0af;font-size:11px;margin-bottom:3px}.cab-field strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}.cab-chip-list{display:flex;flex-wrap:wrap;gap:6px}.cab-chip-list span{border:1px solid rgba(255,255,255,.14);border-radius:999px;background:#11151b;padding:4px 8px}.cab-chip-list button{min-height:18px;padding:0 4px;margin-left:4px}.cab-section label{display:block;color:#95a0af;font-size:11px;margin:8px 0 4px}.cab-curation-row{display:flex;gap:12px;flex-wrap:wrap}.cab-curation-row label{display:flex;align-items:center;gap:6px}.cab-inline-form{display:grid;grid-template-columns:1fr auto;gap:6px;margin:8px 0}.cab-detail-pane textarea{box-sizing:border-box;width:100%;min-height:72px;border:1px solid rgba(255,255,255,.14);border-radius:6px;background:#101318;color:#f4f7fb;padding:8px;font:inherit}.cab-subtle{color:#aeb7c4}.cab-related-section{margin-top:10px}.cab-related-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:6px}.cab-related-grid button{min-height:0;padding:0;overflow:hidden}.cab-related-grid img{display:block;width:100%;height:74px;object-fit:contain}.cab-related-grid span{display:block;padding:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.cab-prompt-text,.cab-raw-json pre{max-height:210px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:#05070a;padding:10px;border-radius:6px;border:1px solid rgba(255,255,255,.08)}.cab-raw-json{border-top:1px solid rgba(255,255,255,.1);padding:12px 0}.cab-raw-json summary{cursor:pointer;color:#c8d1df}.cab-raw-json pre{max-height:320px}.cab-detail-header button{border:1px solid rgba(255,255,255,.14);border-radius:6px;background:#262b33;color:#f4f7fb;min-height:30px;padding:0 10px;cursor:pointer}@media(max-width:820px){.cab-dialog{grid-template-columns:1fr}.cab-preview-pane{max-height:45vh}.cab-field-grid,.cab-related-grid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);
}

app.registerExtension({
  name: "JonMSales.AssetBrowser",
  async init() {
    if (!cabRegisterSidebar()) cabMountFallback();
  },
});

