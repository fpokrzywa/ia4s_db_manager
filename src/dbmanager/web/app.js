import { get, post } from "./api.js";
import { renderDatabaseOverview, newDatabaseDialog, dropDatabaseDialog }
  from "./databases.js";
import { renderTableView as tableView, newTableDialog } from "./tables.js";
import { renderConsole as consoleView } from "./query.js";
import { renderUsers } from "./users.js";

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

export function modalShell() {
  const bg = document.createElement("div");
  bg.className = "modal-bg";
  const box = document.createElement("div");
  box.className = "modal";
  bg.append(box);
  document.body.append(bg);
  return { bg, box };
}

// An ordered multi-column picker. Returns { el, get }: `el` is the DOM node to
// insert into a dialog; `get()` returns the chosen column names, in order.
export function columnPicker(options) {
  const chosen = [];
  const wrap = document.createElement("div");
  const ctl = document.createElement("div");
  ctl.className = "row";
  const picker = document.createElement("select");
  for (const o of options) {
    const opt = document.createElement("option");
    opt.value = o; opt.textContent = o;
    picker.append(opt);
  }
  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "ghost";
  addBtn.textContent = "Add";
  const list = document.createElement("div");
  list.style.marginTop = "4px";
  const render = () => {
    list.innerHTML = "";
    chosen.forEach((col, i) => {
      const tag = document.createElement("span");
      tag.textContent = `${i + 1}. ${col} `;
      tag.style.marginRight = "8px";
      const x = document.createElement("button");
      x.type = "button";
      x.className = "ghost";
      x.textContent = "✕";
      x.onclick = () => { chosen.splice(i, 1); render(); };
      tag.append(x);
      list.append(tag);
    });
  };
  addBtn.onclick = () => {
    if (picker.value && !chosen.includes(picker.value)) {
      chosen.push(picker.value);
      render();
    }
  };
  ctl.append(picker, addBtn);
  wrap.append(ctl, list);
  return { el: wrap, get: () => chosen.slice() };
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
      } else if (f.type === "columns") {
        const picker = columnPicker(f.options);
        el = picker.el;
        el.__picker = picker;
      } else {
        el = document.createElement("input");
        el.type = f.type || "text";
      }
      if (f.value !== undefined && f.type !== "columns") {
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
        if (f.type === "checkbox") out[f.name] = inputs[f.name].checked;
        else if (f.type === "columns") out[f.name] = inputs[f.name].__picker.get();
        else out[f.name] = inputs[f.name].value.trim();
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

  const usersBtn = document.createElement("div");
  usersBtn.className = "tree-item";
  usersBtn.textContent = "▸ Users";
  usersBtn.onclick = () => renderUsers();
  sidebar.append(usersBtn);

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
  await renderDatabaseOverview(db, loadSidebar);
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
  consoleView(db);
}

// --- auth / boot ------------------------------------------------------------

const changePwEl = document.getElementById("change-password");

async function showApp() {
  loginEl.classList.add("hidden");
  changePwEl.classList.add("hidden");
  appEl.classList.remove("hidden");
  await loadSidebar();
  try {
    const info = await get("/api/server-info");
    document.getElementById("server-label").textContent =
      info.host ? `${info.host}:${info.port}` : "";
  } catch { /* label is cosmetic — ignore failures */ }
}
function showLogin() {
  appEl.classList.add("hidden");
  changePwEl.classList.add("hidden");
  loginEl.classList.remove("hidden");
}
function showChangePassword() {
  appEl.classList.add("hidden");
  loginEl.classList.add("hidden");
  changePwEl.classList.remove("hidden");
}

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("login-error");
  errEl.textContent = "";
  try {
    const r = await post("/api/login", {
      email: document.getElementById("login-email").value,
      password: document.getElementById("login-password").value,
    });
    if (r.must_change_password) showChangePassword();
    else await showApp();
  } catch (err) { errEl.textContent = err.message; }
});

document.getElementById("change-password-form")
  .addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("cp-error");
    errEl.textContent = "";
    const current = document.getElementById("cp-current").value;
    const next = document.getElementById("cp-new").value;
    const confirm = document.getElementById("cp-confirm").value;
    if (next !== confirm) {
      errEl.textContent = "new passwords do not match";
      return;
    }
    try {
      await post("/api/change-password",
        { current_password: current, new_password: next });
      await showApp();
    } catch (err) { errEl.textContent = err.message; }
  });

document.getElementById("logout").addEventListener("click", async () => {
  await post("/api/logout");
  showLogin();
});

(async function init() {
  try {
    const me = await get("/api/me");
    if (me.must_change_password) showChangePassword();
    else await showApp();
  } catch { showLogin(); }
})();
