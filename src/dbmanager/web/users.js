import { get, post, patch } from "./api.js";
import { confirmModal, formModal, showError } from "./app.js";

// Render the Users management panel.
export async function renderUsers() {
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = "Users";
  panel.append(h);

  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";
  toolbar.append(mkBtn("+ User", addUserDialog, ""));
  panel.append(toolbar);

  const [users, me] = await Promise.all([get("/api/users"), get("/api/me")]);
  const table = document.createElement("table");
  table.className = "grid";
  table.innerHTML =
    "<thead><tr><th>Email</th><th>Status</th><th>Must change pw</th>" +
    "<th>Last login</th><th></th></tr></thead>";
  const body = document.createElement("tbody");
  for (const u of users) {
    const locked = u.locked_until && new Date(u.locked_until) > new Date();
    const status = !u.is_active ? "inactive" : locked ? "locked" : "active";
    const tr = document.createElement("tr");
    for (const text of [
      u.email, status, u.must_change_password ? "yes" : "no",
      u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "—",
    ]) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.append(td);
    }
    const actions = document.createElement("td");
    actions.append(
      mkBtn(u.is_active ? "Deactivate" : "Activate",
            () => setActive(u.id, !u.is_active), "ghost"),
      mkBtn("Reset password", () => resetPassword(u.id, u.email), "ghost"));
    if (locked) {
      actions.append(mkBtn("Unlock", () => unlockUser(u.id), "ghost"));
    }
    if (me.is_admin === true) {
      const adminBtn = document.createElement("button");
      adminBtn.className = "ghost";
      adminBtn.textContent = u.is_admin ? "Revoke admin" : "Make admin";
      adminBtn.style.marginRight = "4px";
      adminBtn.onclick = async () => {
        const verb = u.is_admin ? "revoke" : "grant";
        const ok = await confirmModal(
          `${verb === "grant" ? "Make" : "Revoke"} admin for ${u.email}`,
          `Type the email to confirm you want to ${verb} admin.`,
          u.email);
        if (!ok) return;
        try {
          await patch(`/api/users/${u.id}/admin`, { is_admin: !u.is_admin });
          await renderUsers();
        } catch (e) { showError(e.message); }
      };
      actions.append(adminBtn);
    }
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

async function addUserDialog() {
  const v = await formModal("Add user", [
    { name: "email", label: "Email", type: "text" },
    { name: "password", label: "Temp password", type: "text" },
  ]);
  if (!v) return;
  try {
    await post("/api/users", { email: v.email, password: v.password });
    await renderUsers();
  } catch (e) { showError(e.message); }
}

async function setActive(id, active) {
  try {
    await patch(`/api/users/${id}`, { is_active: active });
    await renderUsers();
  } catch (e) { showError(e.message); }
}

async function resetPassword(id, email) {
  const v = await formModal(`Reset password for ${email}`, [
    { name: "password", label: "New temp password", type: "text" },
  ]);
  if (!v) return;
  try {
    await patch(`/api/users/${id}`, { password: v.password });
    await renderUsers();
  } catch (e) { showError(e.message); }
}

async function unlockUser(id) {
  try {
    await patch(`/api/users/${id}`, { unlock: true });
    await renderUsers();
  } catch (e) { showError(e.message); }
}
