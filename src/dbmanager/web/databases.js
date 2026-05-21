import { get, post, del } from "./api.js";
import { confirmModal, formModal, fmtBytes, showError } from "./app.js";

// Render the database overview panel.
export async function renderDatabaseOverview(dbName) {
  const panel = document.getElementById("panel");
  const databases = await get("/api/databases");
  const db = databases.find((d) => d.name === dbName);
  const tables = await get(`/api/databases/${encodeURIComponent(dbName)}/tables`);
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = dbName;
  panel.append(h);

  const meta = document.createElement("p");
  meta.className = "notice";
  meta.textContent = db
    ? `owner ${db.owner} · ${db.encoding} · ${fmtBytes(db.size_bytes)} · ${tables.length} table(s)`
    : `${tables.length} table(s)`;
  panel.append(meta);

  const grid = document.createElement("table");
  grid.className = "grid";
  grid.innerHTML =
    "<thead><tr><th>Table</th><th>Approx rows</th><th>Size</th></tr></thead>";
  const body = document.createElement("tbody");
  for (const t of tables) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${t.name}</td><td>${t.approx_rows}</td><td>${fmtBytes(t.size_bytes)}</td>`;
    body.append(tr);
  }
  grid.append(body);
  panel.append(grid);
}

// "New database" dialog.
export async function newDatabaseDialog(reload) {
  const values = await formModal("Create database", [
    { name: "name", label: "Name", type: "text" },
    { name: "owner", label: "Owner (optional)", type: "text" },
  ]);
  if (!values) return;
  try {
    await post("/api/databases", { name: values.name, owner: values.owner || null });
    await reload();
  } catch (err) { showError(err.message); }
}

// Drop-database confirmation.
export async function dropDatabaseDialog(name, reload) {
  const ok = await confirmModal(
    `Drop database "${name}"`,
    `This permanently deletes the database and all its data. Type the name to confirm.`,
    name);
  if (!ok) return;
  try {
    await del(`/api/databases/${encodeURIComponent(name)}?force=true`);
    await reload();
  } catch (err) { showError(err.message); }
}
