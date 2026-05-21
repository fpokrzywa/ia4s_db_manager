import { get, post } from "./api.js";
import { renderDatabaseOverview, newDatabaseDialog, dropDatabaseDialog }
  from "./databases.js";
import { renderTableView as tableView, newTableDialog } from "./tables.js";

const loginEl = document.getElementById("login");
const appEl = document.getElementById("app");
let selected = null;  // { db } or { db, table }

// --- shared helpers ---------------------------------------------------------

export function fmtBytes(n) {
  if (n == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = Number(n);
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i ? 1 : 0)} ${u[i]}`;
}

export function showError(msg) { alert(msg); }

function modalShell() {
  const bg = document.createElement("div");
  bg.className = "modal-bg";
  const box = document.createElement("div");
  box.className = "modal";
  bg.append(box);
  document.body.append(bg);
  return { bg, box };
}

// Typed-confirmation modal. Resolves true only if the user types `phrase`.
export function confirmModal(title, message, phrase) {
  return new Promise((resolve) => {
    const { bg, box } = modalShell();
    box.innerHTML = `<h2>${title}</h2><p>${message}</p>`;
    const input = document.createElement("input");
    input.placeholder = phrase;
    const actions = document.createElement("div");
    actions.className = "row";
    const cancel = document.createElement("button");
    cancel.className = "ghost"; cancel.textContent = "Cancel";
    const ok = document.createElement("button");
    ok.className = "danger"; ok.textContent = "Confirm"; ok.disabled = true;
    input.addEventListener("input", () => { ok.disabled = input.value !== phrase; });
    cancel.onclick = () => { bg.remove(); resolve(false); };
    ok.onclick = () => { bg.remove(); resolve(true); };
    actions.append(cancel, ok);
    box.append(input, actions);
    input.focus();
  });
}

// Generic form modal. `fields` = [{name,label,type,options?}]. Resolves an
// object of values, or null if cancelled.
export function formModal(title, fields) {
  return new Promise((resolve) => {
    const { bg, box } = modalShell();
    box.innerHTML = `<h2>${title}</h2>`;
    const inputs = {};
    for (const f of fields) {
      const row = document.createElement("div");
      row.className = "row";
      const label = document.createElement("label");
      label.textContent = f.label;
      let el;
      if (f.type === "select") {
        el = document.createElement("select");
        for (const o of f.options) {
          const opt = document.createElement("option");
          opt.value = o; opt.textContent = o;
          el.append(opt);
        }
      } else if (f.type === "checkbox") {
        el = document.createElement("input");
        el.type = "checkbox";
      } else {
        el = document.createElement("input");
        el.type = f.type || "text";
      }
      if (f.value !== undefined) {
        if (f.type === "checkbox") el.checked = Boolean(f.value);
        else el.value = f.value;
      }
      inputs[f.name] = el;
      row.append(label, el);
      box.append(row);
    }
    const actions = document.createElement("div");
    actions.className = "row";
    const cancel = document.createElement("button");
    cancel.className = "ghost"; cancel.textContent = "Cancel";
    const ok = document.createElement("button");
    ok.textContent = "Save";
    cancel.onclick = () => { bg.remove(); resolve(null); };
    ok.onclick = () => {
      const out = {};
      for (const f of fields) {
        out[f.name] = f.type === "checkbox"
          ? inputs[f.name].checked : inputs[f.name].value.trim();
      }
      bg.remove(); resolve(out);
    };
    actions.append(cancel, ok);
    box.append(actions);
  });
}

// --- sidebar ----------------------------------------------------------------

async function loadSidebar() {
  const sidebar = document.getElementById("sidebar");
  sidebar.innerHTML = "";

  const newBtn = document.createElement("button");
  newBtn.textContent = "+ New database";
  newBtn.style.width = "100%";
  newBtn.onclick = () => newDatabaseDialog(loadSidebar);
  sidebar.append(newBtn);

  const consoleBtn = document.createElement("div");
  consoleBtn.className = "tree-item";
  consoleBtn.textContent = "▸ SQL Console";
  consoleBtn.onclick = () => openConsole();
  sidebar.append(consoleBtn);

  const databases = await get("/api/databases");
  for (const db of databases) {
    const dbEl = document.createElement("div");
    dbEl.className = "tree-item tree-db";
    dbEl.textContent = db.name;
    dbEl.oncontextmenu = (e) => {
      e.preventDefault();
      dropDatabaseDialog(db.name, loadSidebar);
    };
    dbEl.onclick = () => selectDatabase(db.name);
    dbEl.ondblclick = () => newTableDialog(db.name, loadSidebar);
    sidebar.append(dbEl);

    let tables;
    try {
      tables = await get(`/api/databases/${encodeURIComponent(db.name)}/tables`);
    } catch { tables = []; }
    for (const t of tables) {
      const tEl = document.createElement("div");
      tEl.className = "tree-item tree-table";
      tEl.textContent = t.name;
      tEl.onclick = () => selectTable(db.name, t.name);
      sidebar.append(tEl);
    }
  }
}

async function selectDatabase(db) {
  selected = { db };
  await renderDatabaseOverview(db);
}

async function selectTable(db, table) {
  selected = { db, table };
  await renderTableView(db, table);  // from tables.js (Task 12)
}

function openConsole() {
  renderConsole(selected?.db);  // from query.js (Task 14)
}

// Placeholders replaced in later phases.
async function renderTableView(db, table) {
  await tableView(db, table, loadSidebar);
}
function renderConsole(db) {
  document.getElementById("panel").textContent = "SQL Console";
}

// --- auth / boot ------------------------------------------------------------

async function showApp() {
  loginEl.classList.add("hidden");
  appEl.classList.remove("hidden");
  await loadSidebar();
}
function showLogin() {
  appEl.classList.add("hidden");
  loginEl.classList.remove("hidden");
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("login-error");
  errEl.textContent = "";
  try {
    await post("/api/login", {
      password: document.getElementById("login-password").value,
    });
    await showApp();
  } catch (err) { errEl.textContent = err.message; }
});

document.getElementById("logout").addEventListener("click", async () => {
  await post("/api/logout");
  showLogin();
});

(async function init() {
  try { await get("/api/databases"); await showApp(); }
  catch { showLogin(); }
})();
