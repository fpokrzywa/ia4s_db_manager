import { get, post, patch, del } from "./api.js";
import { confirmModal, formModal, showError } from "./app.js";

let current = { db: null, table: null, tab: "data" };

// Entry point called by the sidebar. `refresh` reloads the sidebar tree.
export async function renderTableView(db, table, refresh) {
  current = { db, table, tab: current.tab || "data" };
  const panel = document.getElementById("panel");
  panel.innerHTML = "";

  const h = document.createElement("h2");
  h.textContent = `${db} · ${table}`;
  panel.append(h);

  const tabs = document.createElement("div");
  tabs.className = "tabs";
  for (const name of ["data", "structure"]) {
    const b = document.createElement("button");
    b.textContent = name[0].toUpperCase() + name.slice(1);
    if (current.tab === name) b.classList.add("active");
    b.onclick = () => { current.tab = name; renderTableView(db, table, refresh); };
    tabs.append(b);
  }
  panel.append(tabs);

  const content = document.createElement("div");
  panel.append(content);
  if (current.tab === "structure") await renderStructure(content, db, table, refresh);
  else await renderDataTab(content, db, table);
}

// renderDataTab is provided by rows.js (Task 13). Bound at load time.
let renderDataTab = async (el) => { el.textContent = "Data tab — Phase 4."; };
export function bindDataTab(fn) { renderDataTab = fn; }

async function renderStructure(el, db, table, refresh) {
  const base = `/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}`;
  const struct = await get(base);

  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";
  const addCol = mkBtn("+ Column", () => addColumnDialog(db, table, refresh));
  const addIdx = mkBtn("+ Index", () =>
    addIndexDialog(db, table, struct.columns.map((c) => c.name), refresh));
  const addFk = mkBtn("+ Constraint", () =>
    addConstraintDialog(db, table, struct.columns.map((c) => c.name), refresh));
  const dropTbl = mkBtn("Drop table", async () => {
    if (await confirmModal(`Drop table "${table}"`,
        "This permanently deletes the table and its data.", table)) {
      await del(base); await refresh();
    }
  }, "danger");
  toolbar.append(addCol, addIdx, addFk, dropTbl);
  el.append(toolbar);

  el.append(mkSection("Columns", ["Name", "Type", "Nullable", "Default", ""],
    struct.columns.map((c) => [
      c.name, c.data_type, c.is_nullable, c.column_default ?? "",
      rowActions([
        ["Edit", () => editColumnDialog(db, table, c, refresh)],
        ["Drop", async () => {
          if (await confirmModal(`Drop column "${c.name}"`,
              "This permanently deletes the column and its data.", c.name)) {
            await del(`${base}/columns/${encodeURIComponent(c.name)}`);
            await renderTableView(db, table, refresh);
          }
        }],
      ]),
    ])));

  el.append(mkSection("Constraints", ["Name", "Type", "Definition", ""],
    struct.constraints.map((c) => [
      c.name, c.type, c.definition,
      rowActions([["Drop", async () => {
        await del(`${base}/constraints/${encodeURIComponent(c.name)}`);
        await renderTableView(db, table, refresh);
      }]]),
    ])));

  el.append(mkSection("Indexes", ["Name", "Definition", ""],
    struct.indexes.map((i) => [
      i.name, i.definition,
      rowActions([["Drop", async () => {
        await del(`${base}/indexes/${encodeURIComponent(i.name)}`);
        await renderTableView(db, table, refresh);
      }]]),
    ])));
}

// --- dialogs ----------------------------------------------------------------

async function addColumnDialog(db, table, refresh) {
  const v = await formModal("Add column", [
    { name: "name", label: "Name", type: "text" },
    { name: "type", label: "Type", type: "text" },
    { name: "nullable", label: "Nullable", type: "checkbox" },
    { name: "default", label: "Default", type: "text" },
  ]);
  if (!v) return;
  try {
    await post(`/api/databases/${db}/tables/${table}/columns`, {
      name: v.name, type: v.type, nullable: v.nullable,
      default: v.default || null,
    });
    await renderTableView(db, table, refresh); await refresh();
  } catch (e) { showError(e.message); }
}

async function editColumnDialog(db, table, col, refresh) {
  const v = await formModal(`Edit column "${col.name}"`, [
    { name: "new_name", label: "Rename to", type: "text" },
    { name: "type", label: "New type", type: "text" },
  ]);
  if (!v) return;
  try {
    await patch(
      `/api/databases/${db}/tables/${table}/columns/${encodeURIComponent(col.name)}`,
      { new_name: v.new_name || null, type: v.type || null });
    await renderTableView(db, table, refresh); await refresh();
  } catch (e) { showError(e.message); }
}

async function addIndexDialog(db, table, columns, refresh) {
  const v = await formModal("Create index", [
    { name: "name", label: "Index name", type: "text" },
    { name: "column", label: "Column", type: "select", options: columns },
    { name: "unique", label: "Unique", type: "checkbox" },
  ]);
  if (!v) return;
  try {
    await post(`/api/databases/${db}/tables/${table}/indexes`,
      { name: v.name, columns: [v.column], unique: v.unique });
    await renderTableView(db, table, refresh);
  } catch (e) { showError(e.message); }
}

async function addConstraintDialog(db, table, columns, refresh) {
  const v = await formModal("Add constraint", [
    { name: "type", label: "Type", type: "select",
      options: ["UNIQUE", "PRIMARY KEY"] },
    { name: "column", label: "Column", type: "select", options: columns },
    { name: "name", label: "Name (optional)", type: "text" },
  ]);
  if (!v) return;
  try {
    await post(`/api/databases/${db}/tables/${table}/constraints`,
      { type: v.type, columns: [v.column], name: v.name || null });
    await renderTableView(db, table, refresh);
  } catch (e) { showError(e.message); }
}

// --- small DOM helpers ------------------------------------------------------

function mkBtn(text, onClick, cls) {
  const b = document.createElement("button");
  b.textContent = text;
  if (cls) b.className = cls;
  b.onclick = onClick;
  return b;
}

function rowActions(actions) {
  const span = document.createElement("span");
  for (const [label, fn] of actions) {
    const b = mkBtn(label, fn, "ghost");
    b.style.marginRight = "4px";
    span.append(b);
  }
  return span;
}

function mkSection(title, headers, rows) {
  const wrap = document.createElement("div");
  const h = document.createElement("h3");
  h.textContent = title;
  wrap.append(h);
  const table = document.createElement("table");
  table.className = "grid";
  table.innerHTML =
    `<thead><tr>${headers.map((x) => `<th>${x}</th>`).join("")}</tr></thead>`;
  const body = document.createElement("tbody");
  for (const cells of rows) {
    const tr = document.createElement("tr");
    for (const c of cells) {
      const td = document.createElement("td");
      if (c instanceof Node) td.append(c);
      else td.textContent = c;
      tr.append(td);
    }
    body.append(tr);
  }
  table.append(body);
  wrap.append(table);
  return wrap;
}

// Used by the create-table flow from the sidebar.
export async function newTableDialog(db, refresh) {
  const v = await formModal(`New table in "${db}"`, [
    { name: "name", label: "Table name", type: "text" },
    { name: "col", label: "First column", type: "text" },
    { name: "type", label: "Column type", type: "text" },
  ]);
  if (!v) return;
  try {
    await post(`/api/databases/${db}/tables`, {
      name: v.name,
      columns: [{ name: v.col, type: v.type, primary_key: true,
                  nullable: false }],
    });
    await refresh();
  } catch (e) { showError(e.message); }
}
