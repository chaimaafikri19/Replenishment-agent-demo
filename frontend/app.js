// Replenishment review dashboard.
// Loads the agent's drafts and stock levels from the API, lets a buyer
// approve / edit / dismiss each draft, and saves approved ones as requisitions.

const API = "http://127.0.0.1:8000";

// Demo mode: on any host other than this computer, load a saved snapshot
// (demo-data.json) instead of calling the API, and never save anything.
const DEMO = !["localhost", "127.0.0.1"].includes(location.hostname);
let snapshotDate = null;  // set in demo mode, e.g. "2026-11-16"

// ---------- State ----------
let drafts = [];          // from GET /agent/suggestions
let stockById = {};       // from GET /stock, keyed by product id
let suppliersById = {};   // from GET /suppliers (for supplier names and lead times)
let filter = "all";       // "all" | "high" | "medium"
let saving = false;

// One entry per draft: { status, quantity, editing, error, savedId }
// status is "draft" | "approved" | "dismissed" | "saved"
const review = {};

const URGENCY_RANK = { high: 1, medium: 2 };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// ---------- Small helpers ----------

// Escape text before putting it into HTML.
function esc(value) {
  return String(value).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const formatNumber = (n) => Number(n).toLocaleString("en-GB", { maximumFractionDigits: 1 });
const amount = (n, unit) => `${formatNumber(n)} ${unit}`;
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// "Mon 23 Nov" (optionally with the year)
function formatDate(date, withYear = false) {
  const text = `${WEEKDAYS[date.getDay()]} ${date.getDate()} ${MONTHS[date.getMonth()]}`;
  return withYear ? `${text} ${date.getFullYear()}` : text;
}

// Parse "2026-11-23" as a local date (not UTC, which can shift the day).
function parseIsoDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

async function getJson(path) {
  const response = await fetch(API + path);
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

function showMessage(type, title, text) {
  const box = document.getElementById("message");
  box.className = `message ${type}`;
  box.innerHTML = `<strong>${esc(title)}</strong>${text ? esc(text) : ""}`;
  box.hidden = false;
}

function hideMessage() {
  document.getElementById("message").hidden = true;
}

// ---------- Loading ----------

async function load() {
  hideMessage();
  try {
    const [suggestions, stock, suppliers] = DEMO ? await loadDemoData() : await Promise.all([
      getJson("/agent/suggestions"),
      getJson("/stock"),
      getJson("/suppliers").catch(() => []), // only used for nicer summary cards
    ]);

    drafts = [...suggestions].sort((a, b) => URGENCY_RANK[a.urgency] - URGENCY_RANK[b.urgency]);
    stockById = Object.fromEntries(stock.map((p) => [p.id, p]));
    suppliersById = Object.fromEntries(suppliers.map((s) => [s.id, s]));
    drafts.forEach((d) => {
      review[d.product_id] = { status: "draft", quantity: d.quantity, editing: false, error: "" };
    });

    const status = document.getElementById("agent-status");
    const run = DEMO
      ? `Snapshot ${formatDate(parseIsoDate(snapshotDate), true)}`
      : `Last run ${new Date().toTimeString().slice(0, 5)}`;
    status.textContent = `Replenishment agent · ${run} · ${stock.length} products checked`;
    status.hidden = false;

    renderAll();
  } catch (err) {
    console.error(err);
    renderLoadError();
  }
}

// Demo mode: read the snapshot file and show the banner and snapshot date.
async function loadDemoData() {
  const response = await fetch("demo-data.json");
  if (!response.ok) throw new Error(`demo-data.json returned ${response.status}`);
  const data = await response.json();
  snapshotDate = data.snapshot_date;

  const shown = formatDate(parseIsoDate(snapshotDate), true);
  const banner = document.getElementById("demo-banner");
  banner.textContent = `Demo mode: sample data from ${shown}. Nothing is saved.`;
  banner.hidden = false;
  showHeaderDate(parseIsoDate(snapshotDate));

  return [data.agent_suggestions, data.stock, data.suppliers];
}

// Friendly message instead of a blank page when the data can't be loaded.
function renderLoadError() {
  document.getElementById("subtitle").textContent = "We couldn't load the agent's suggestions.";
  if (DEMO) {
    showMessage("error", "The sample data couldn't be loaded.", " Please reload the page to try again.");
  } else {
    showMessage("error", "The replenishment service isn't reachable right now.",
      " Check that the API is running on http://127.0.0.1:8000, then try again.");
  }
  document.getElementById("list").innerHTML = `
    <div class="card empty">
      <strong>No suggestions to show</strong>
      <p>${DEMO ? "Reload this page to try again." : "Start the API and reload this page."}</p>
      <p style="margin-top:12px"><button type="button" class="btn btn-primary" id="retry">Try again</button></p>
    </div>`;
  document.getElementById("retry").addEventListener("click", load);
  renderPanel();
}

// ---------- Rendering ----------

function renderAll() {
  renderHeading();
  renderSummary();
  renderList();
  renderPanel();
}

function renderHeading() {
  const high = drafts.filter((d) => d.urgency === "high").length;
  document.getElementById("subtitle").textContent =
    `${high} high-urgency ${high === 1 ? "item needs" : "items need"} ordering today. The agent drafts, a buyer approves.`;
  document.getElementById("suggestions-title").textContent =
    `Agent suggestions (${plural(drafts.length, "draft")})`;
}

// Days of stock that would keep us above safety stock until a delivery arrives.
function daysNeeded(product, leadTime) {
  return leadTime + product.safety_stock / product.avg_daily_usage;
}

function renderSummary() {
  const products = Object.values(stockById);
  const leadTime = (p) => suppliersById[p.supplier_id]?.lead_time_days;
  const supplierName = (p) =>
    suppliersById[p.supplier_id]?.name ||
    drafts.find((d) => d.supplier_id === p.supplier_id)?.supplier_name || p.supplier_id;

  // Most urgent = fewest days of stock left.
  const mostUrgent = (urgency) =>
    drafts.filter((d) => d.urgency === urgency)
      .map((d) => stockById[d.product_id])
      .filter(Boolean)
      .sort((a, b) => a.days_of_stock_left - b.days_of_stock_left)[0];

  const cards = [
    { tone: "high", count: drafts.filter((d) => d.urgency === "high").length, label: "high urgency",
      badge: "High risk", example: mostUrgent("high") },
    { tone: "medium", count: drafts.filter((d) => d.urgency === "medium").length, label: "medium urgency",
      badge: "Medium risk", example: mostUrgent("medium") },
    { tone: "ok", count: products.filter((p) => p.risk_group === "ok").length, label: "products OK",
      badge: "Stock healthy", example: products.find((p) => p.risk_group === "ok") },
  ];

  document.getElementById("summary").innerHTML = cards.map((c) => {
    const p = c.example;
    let detail = `<p class="product">No products in this group</p>`;
    if (p) {
      const lead = leadTime(p);
      // Bar: how much of the stock we need to get safely to a delivery we actually have.
      const fill = lead ? Math.min(1, p.days_of_stock_left / daysNeeded(p, lead)) : 1;
      detail = `
        <div class="row">
          <p class="product">${esc(p.name)}</p>
          <p class="supplier">${esc(supplierName(p))}</p>
        </div>
        <div class="row">
          <p class="stock-left">${formatNumber(p.days_of_stock_left)} days of stock left</p>
          ${lead ? `<p class="delivery">${plural(lead, "day")} delivery</p>` : ""}
        </div>
        <div class="bar" role="img" aria-label="${Math.round(fill * 100)}% of the stock needed until delivery">
          <span style="width:${(fill * 100).toFixed(0)}%"></span>
        </div>`;
    }
    return `
      <article class="summary-card tone-${c.tone}">
        <div class="row">
          <h3>${c.count} ${c.label}</h3>
          <span class="badge">${c.badge}</span>
        </div>
        ${detail}
      </article>`;
  }).join("");
}

function renderList() {
  const visible = drafts.filter((d) => filter === "all" || d.urgency === filter);
  const list = document.getElementById("list");
  if (visible.length === 0) {
    list.innerHTML = `<div class="card empty"><strong>No ${filter === "all" ? "" : filter + "-urgency "}drafts</strong>
      <p>The agent has nothing to suggest here.</p></div>`;
    return;
  }
  list.innerHTML = visible.map(cardHtml).join("");
}

const SPARKLE = `<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor"
  d="M8 0c.4 3.9 2.1 5.6 6 6-3.9.4-5.6 2.1-6 6-.4-3.9-2.1-5.6-6-6 3.9-.4 5.6-2.1 6-6z" transform="translate(0 2)"/></svg>`;

function cardHtml(d) {
  const r = review[d.product_id];
  const name = esc(d.product_name);
  const id = esc(d.product_id);
  const min = stockById[d.product_id]?.min_order_quantity ?? 1;
  const delivery = formatDate(parseIsoDate(d.expected_delivery_date));

  // Quantity: a number, or an input while editing.
  const qty = r.editing
    ? `<label class="qty-label" for="qty-${id}">Quantity (${esc(d.unit)}, min ${formatNumber(min)})</label><br>
       <input id="qty-${id}" type="number" min="${min}" step="1" value="${esc(r.inputValue ?? r.quantity)}"
              data-id="${id}" aria-invalid="${r.error ? "true" : "false"}"
              ${r.error ? `aria-describedby="err-${id}"` : ""}>
       ${r.error ? `<p class="qty-error" id="err-${id}">${esc(r.error)}</p>` : ""}`
    : `<p class="qty-value">${esc(amount(r.quantity, d.unit))}</p>
       <p class="qty-label">${r.status === "saved" ? "Ordered" : "Suggested order"}</p>`;

  // Buttons depend on the card's status.
  let actions;
  if (r.status === "saved") {
    actions = `<span class="status-text">${DEMO ? "Saved (demo, not saved)" : `Saved as requisition ${esc(r.savedId)}`}</span>`;
  } else if (r.status === "dismissed") {
    actions = `<span class="status-text">Dismissed</span>
      <button type="button" class="btn btn-secondary" data-action="undo" data-id="${id}"
              aria-label="Undo dismiss for ${name}">Undo</button>`;
  } else {
    const approved = r.status === "approved";
    actions = `
      <button type="button" class="btn ${approved ? "btn-approved" : "btn-primary"}" data-action="approve"
              data-id="${id}" aria-pressed="${approved}" ${r.editing ? "disabled" : ""}
              aria-label="${approved ? `Approved: ${name}. Press to undo approval` : `Approve ${name}`}">${approved ? "Approved" : "Approve"}</button>
      <button type="button" class="btn btn-secondary" data-action="${r.editing ? "done" : "edit"}" data-id="${id}"
              aria-label="${r.editing ? `Save quantity for ${name}` : `Edit quantity for ${name}`}">${r.editing ? "Done" : "Edit quantity"}</button>
      <button type="button" class="btn btn-ghost" data-action="dismiss" data-id="${id}"
              aria-label="Dismiss ${name}">Dismiss</button>`;
  }

  return `
    <article class="card is-${r.status}" aria-label="${name}, ${d.urgency} urgency${r.status !== "draft" ? `, ${r.status}` : ""}">
      <div class="card-top">
        <div>
          <div class="card-title">
            <h3>${name}</h3>
            <span class="chip ${d.urgency}">${d.urgency}</span>
          </div>
          <p class="meta">${esc(d.supplier_name)}<span class="dot" aria-hidden="true">·</span>Delivery ${delivery}</p>
        </div>
        <div class="qty">${qty}</div>
      </div>
      <p class="reason">${esc(d.reason)}</p>
      <div class="card-bottom">
        <span class="agent-tag">${SPARKLE}Drafted by replenishment agent</span>
        <div class="actions">${actions}</div>
      </div>
    </article>`;
}

function renderPanel() {
  const approved = drafts.filter((d) => review[d.product_id]?.status === "approved");
  const suppliers = new Set(approved.map((d) => d.supplier_id)).size;
  const n = approved.length;

  document.getElementById("panel-count").textContent = plural(n, "item");
  const body = document.getElementById("panel-body");

  if (n === 0) {
    body.innerHTML = `
      <div class="empty">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.6"
          d="M4 4h16v16H4zM8 12l3 3 5-6"/></svg>
        <strong>Nothing approved yet</strong>
        <p>Approve a suggestion to add it here.</p>
      </div>`;
    return;
  }

  body.innerHTML = `
    <ul class="approved-list">
      ${approved.map((d) => `
        <li class="approved-item">
          <p class="approved-label">Approved by you</p>
          <p class="name">${esc(d.product_name)}</p>
          <p class="amount">${esc(amount(review[d.product_id].quantity, d.unit))}</p>
          <p class="detail">${esc(d.supplier_name)} · Delivery ${formatDate(parseIsoDate(d.expected_delivery_date))}</p>
        </li>`).join("")}
    </ul>
    <p class="panel-note">Review quantities and delivery dates before saving.</p>
    <p class="panel-summary">Requisition <strong>${plural(n, "item")} · ${plural(suppliers, "supplier")}</strong></p>
    <button type="button" class="btn btn-primary btn-wide" id="save" ${saving ? "disabled" : ""}>
      ${saving ? "Saving…" : `Save ${plural(n, "requisition")}`}
    </button>
    <p class="panel-note panel-footnote">Nothing is sent to suppliers.<br>You're saving an internal purchase requisition.</p>`;
  document.getElementById("save").addEventListener("click", save);
}

// Re-render, then put keyboard focus back on the same control.
function rerender(id, action) {
  renderSummary();
  renderList();
  renderPanel();
  const target =
    document.querySelector(`input[data-id="${id}"]`) ||
    document.querySelector(`[data-id="${id}"][data-action="${action}"]`) ||
    document.querySelector(`[data-id="${id}"][data-action]`);
  if (target) target.focus();
}

// ---------- Actions ----------

// Check an edited quantity. Returns true if it was accepted.
function commitQuantity(id) {
  const r = review[id];
  const input = document.querySelector(`input[data-id="${id}"]`);
  const value = Number(input?.value);
  const min = stockById[id]?.min_order_quantity ?? 1;
  const unit = drafts.find((d) => d.product_id === id).unit;

  if (!input || input.value.trim() === "" || !Number.isFinite(value)) {
    r.error = "Enter a number.";
  } else if (value < min) {
    r.error = `The minimum order is ${amount(min, unit)}.`;
  } else {
    r.quantity = value;
    r.editing = false;
    r.error = "";
    return true;
  }
  return false;
}

function handleAction(action, id) {
  const r = review[id];
  if (!r) return;
  hideMessage();

  if (action === "approve") {
    r.status = r.status === "approved" ? "draft" : "approved";
  } else if (action === "dismiss") {
    r.status = "dismissed";
    r.editing = false;
    r.error = "";
  } else if (action === "undo") {
    r.status = "draft";
    action = "dismiss";
  } else if (action === "edit") {
    r.editing = true;
    r.inputValue = undefined;
  } else if (action === "done") {
    if (commitQuantity(id)) action = "edit";
  } else if (action === "cancel") {
    r.editing = false;
    r.error = "";
    action = "edit";
  }
  rerender(id, action);
}

// One POST /requisitions per approved draft.
async function save() {
  const approved = drafts.filter((d) => review[d.product_id].status === "approved");
  if (approved.length === 0 || saving) return;
  saving = true;
  renderPanel();

  // Demo mode: never call the API, just mark the items as saved.
  if (DEMO) {
    approved.forEach((d) => { review[d.product_id].status = "saved"; });
    saving = false;
    showMessage("success", `Saved ${plural(approved.length, "requisition")} (demo, not saved).`,
      " Nothing has been sent to suppliers.");
    renderList();
    renderPanel();
    document.getElementById("message").scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }

  const savedIds = [];
  let failed = 0;
  for (const d of approved) {
    try {
      const response = await fetch(`${API}/requisitions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_id: d.product_id, quantity: review[d.product_id].quantity }),
      });
      if (!response.ok) throw new Error(`POST /requisitions returned ${response.status}`);
      const record = await response.json();
      review[d.product_id].status = "saved";
      review[d.product_id].savedId = record.id;
      savedIds.push(record.id);
    } catch (err) {
      console.error(err);
      failed += 1; // leave it approved so the buyer can try again
    }
  }
  saving = false;

  if (failed === 0) {
    showMessage("success", `Saved ${plural(savedIds.length, "requisition")} (${savedIds.join(", ")}).`,
      " Nothing has been sent to suppliers.");
  } else {
    showMessage("error",
      `${savedIds.length ? `Saved ${savedIds.length}, but ` : ""}${plural(failed, "requisition")} could not be saved.`,
      " The replenishment service may be unavailable. The unsaved items are still in the panel, so you can try again.");
  }
  renderList();
  renderPanel();
  document.getElementById("message").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ---------- Events ----------

// One click handler for every card button.
document.getElementById("list").addEventListener("click", (e) => {
  const button = e.target.closest("button[data-action]");
  if (button) handleAction(button.dataset.action, button.dataset.id);
});

// Remember what is typed, so a re-render doesn't lose it.
document.getElementById("list").addEventListener("input", (e) => {
  if (e.target.dataset.id) review[e.target.dataset.id].inputValue = e.target.value;
});

// Enter saves the edited quantity, Escape cancels.
document.getElementById("list").addEventListener("keydown", (e) => {
  if (e.target.tagName !== "INPUT") return;
  if (e.key === "Enter") handleAction("done", e.target.dataset.id);
  if (e.key === "Escape") handleAction("cancel", e.target.dataset.id);
});

document.querySelectorAll(".filter").forEach((button) => {
  button.addEventListener("click", () => {
    filter = button.dataset.filter;
    document.querySelectorAll(".filter").forEach((b) => {
      b.classList.toggle("is-active", b === button);
      b.setAttribute("aria-pressed", String(b === button));
    });
    renderList();
  });
});

// Header date: today, or the snapshot date in demo mode.
function showHeaderDate(date) {
  const el = document.getElementById("today");
  el.textContent = formatDate(date, true);
  el.dateTime = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

if (!DEMO) showHeaderDate(new Date());
load();
