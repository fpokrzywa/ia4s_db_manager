import { get, post } from "./api.js";
import { showError } from "./app.js";

// Render the SQL console. `preferredDb` is the database last selected.
export async function renderConsole(preferredDb) {
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = "SQL Console";
  panel.append(h);

  const databases = await get("/api/databases");
  const picker = document.createElement("select");
  for (const d of databases) {
    const o = document.createElement("option");
    o.value = d.name; o.textContent = d.name;
    picker.append(o);
  }
  if (preferredDb) picker.value = preferredDb;

  const banner = document.createElement("p");
  banner.className = "notice";
  const setBanner = () => {
    banner.textContent = `Statements run against "${picker.value}".`;
  };
  picker.onchange = setBanner;
  setBanner();

  const editor = document.createElement("textarea");
  editor.rows = 8;
  editor.style.width = "100%";
  editor.placeholder = "SELECT * FROM ...";

  const runBtn = document.createElement("button");
  runBtn.textContent = "Run";

  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";
  toolbar.append(picker, runBtn);

  const result = document.createElement("div");

  runBtn.onclick = async () => {
    result.innerHTML = "";
    try {
      const data = await post(
        `/api/databases/${encodeURIComponent(picker.value)}/query`,
        { sql: editor.value });
      const msg = document.createElement("p");
      msg.className = "notice";
      msg.textContent = data.message;
      result.append(msg);
      if (data.columns.length) result.append(resultGrid(data));
    } catch (e) { showError(e.message); }
  };

  panel.append(toolbar, banner, editor, result);
}

function resultGrid(data) {
  const table = document.createElement("table");
  table.className = "grid";
  table.innerHTML =
    `<thead><tr>${data.columns.map((c) => `<th>${c}</th>`).join("")}</tr></thead>`;
  const body = document.createElement("tbody");
  for (const row of data.rows) {
    const tr = document.createElement("tr");
    for (const c of data.columns) {
      const td = document.createElement("td");
      td.textContent = row[c] === null ? "∅" : String(row[c]);
      tr.append(td);
    }
    body.append(tr);
  }
  table.append(body);
  return table;
}
