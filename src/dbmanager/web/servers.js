import { get, post, patch, del } from "./api.js";
import { confirmModal, formModal, showError } from "./app.js";

const SSLMODES = ["prefer", "require", "disable", "allow",
                  "verify-ca", "verify-full"];

// Render the Servers management panel.
export async function renderServers() {
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = "Servers";
  panel.append(h);

  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";
  toolbar.append(mkBtn("+ Server", () => serverDialog(null), ""));
  panel.append(toolbar);

  const servers = await get("/api/servers");
  const table = document.createElement("table");
  table.className = "grid";
  table.innerHTML =
    "<thead><tr><th>Label</th><th>Host</th><th>Port</th><th>User</th>" +
    "<th>SSL</th><th>Default</th><th></th></tr></thead>";
  const body = document.createElement("tbody");
  for (const s of servers) {
    const tr = document.createElement("tr");
    for (const text of [s.label, s.host, s.port, s.username, s.sslmode,
                        s.is_default ? "yes" : "no"]) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.append(td);
    }
    const actions = document.createElement("td");
    actions.append(
      mkBtn("Test", () => testServer(s.id), "ghost"),
      mkBtn("Edit", () => serverDialog(s), "ghost"),
      mkBtn("Delete", () => deleteServer(s), "ghost"));
    tr.append(actions);
    body.append(tr);
  }
  table.append(body);
  panel.append(table);
}

function mkBtn(text, onClick, cls) {
  const b = document.createElement("button");
  b.textContent = text;
  if (cls) b.className = cls;
  b.style.marginRight = "4px";
  b.onclick = onClick;
  return b;
}

// Add (server=null) or edit a server.
async function serverDialog(server) {
  const editing = server !== null;
  const v = await formModal(editing ? `Edit "${server.label}"` : "Add server", [
    { name: "label", label: "Label", type: "text",
      value: editing ? server.label : "" },
    { name: "host", label: "Host", type: "text",
      value: editing ? server.host : "" },
    { name: "port", label: "Port", type: "number",
      value: editing ? String(server.port) : "5432" },
    { name: "username", label: "Username", type: "text",
      value: editing ? server.username : "" },
    { name: "password", label: editing ? "Password (blank = keep)" : "Password",
      type: "password" },
    { name: "maintenance_db", label: "Maint. DB", type: "text",
      value: editing ? server.maintenance_db : "postgres" },
    { name: "sslmode", label: "SSL mode", type: "select", options: SSLMODES,
      value: editing ? server.sslmode : "prefer" },
    { name: "is_default", label: "Default", type: "checkbox",
      value: editing ? server.is_default : false },
    { name: "notes", label: "Notes", type: "text",
      value: editing ? (server.notes || "") : "" },
  ]);
  if (!v) return;
  if (!editing && !v.password) { showError("A password is required."); return; }
  const payload = {
    label: v.label, host: v.host, port: Number(v.port) || 5432,
    username: v.username, maintenance_db: v.maintenance_db,
    sslmode: v.sslmode, is_default: v.is_default, notes: v.notes || null,
    password: v.password || null,
  };
  try {
    if (editing) await patch(`/api/servers/${server.id}`, payload);
    else await post("/api/servers", payload);
    await renderServers();
  } catch (e) { showError(e.message); }
}

async function testServer(id) {
  try {
    const r = await post(`/api/servers/${id}/test`);
    showError(r.ok ? "Connection succeeded." : `Connection failed: ${r.error}`);
  } catch (e) { showError(e.message); }
}

async function deleteServer(server) {
  const ok = await confirmModal(`Delete server "${server.label}"`,
    "This removes the server from the registry. Type the label to confirm.",
    server.label);
  if (!ok) return;
  try {
    await del(`/api/servers/${server.id}`);
    await renderServers();
  } catch (e) { showError(e.message); }
}
