import { get, post, patch, del } from "./api.js";
import { confirmModal, formModal, showError, modalShell, columnPicker } from "./app.js";
import { renderDataTab as dataTab } from "./rows.js";

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

const renderDataTab = dataTab;

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
    await post(`/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}/columns`, {
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
      `/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}/columns/${encodeURIComponent(col.name)}`,
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
    await post(`/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}/indexes`,
      { name: v.name, columns: [v.column], unique: v.unique });
    await renderTableView(db, table, refresh);
  } catch (e) { showError(e.message); }
}

async function addConstraintDialog(db, table, columns, refresh) {
  const { bg, box } = modalShell();
  box.innerHTML = "<h2>Add constraint</h2>";

  const typeRow = document.createElement("div");
  typeRow.className = "row";
  const typeLabel = document.createElement("label");
  typeLabel.textContent = "Type";
  const typeSel = document.createElement("select");
  for (const t of ["UNIQUE", "PRIMARY KEY", "FOREIGN KEY"]) {
    const o = document.createElement("option");
    o.value = t; o.textContent = t;
    typeSel.append(o);
  }
  typeRow.append(typeLabel, typeSel);

  const colsLabel = document.createElement("p");
  colsLabel.className = "notice";
  colsLabel.textContent = "Columns";
  const localPicker = columnPicker(columns);

  const nameRow = document.createElement("div");
  nameRow.className = "row";
  const nameLabel = document.createElement("label");
  nameLabel.textContent = "Name (optional)";
  const nameInput = document.createElement("input");
  nameRow.append(nameLabel, nameInput);

  // Foreign-key-only section.
  const fkSection = document.createElement("div");
  fkSection.style.display = "none";
  const refTableRow = document.createElement("div");
  refTableRow.className = "row";
  const refTableLabel = document.createElement("label");
  refTableLabel.textContent = "References table";
  const refTableSel = document.createElement("select");
  refTableRow.append(refTableLabel, refTableSel);
  const refColsLabel = document.createElement("p");
  refColsLabel.className = "notice";
  refColsLabel.textContent = "Referenced columns";
  const refColsHolder = document.createElement("div");
  let refPicker = columnPicker([]);
  refColsHolder.append(refPicker.el);
  fkSection.append(refTableRow, refColsLabel, refColsHolder);

  const tableList = await get(`/api/databases/${encodeURIComponent(db)}/tables`);
  for (const t of tableList) {
    const o = document.createElement("option");
    o.value = t.name; o.textContent = t.name;
    refTableSel.append(o);
  }

  async function loadRefColumns() {
    if (!refTableSel.value) return;
    const struct = await get(
      `/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(refTableSel.value)}`);
    refPicker = columnPicker(struct.columns.map((c) => c.name));
    refColsHolder.innerHTML = "";
    refColsHolder.append(refPicker.el);
  }
  refTableSel.onchange = loadRefColumns;

  typeSel.onchange = () => {
    const isFk = typeSel.value === "FOREIGN KEY";
    fkSection.style.display = isFk ? "" : "none";
    if (isFk) loadRefColumns();
  };

  const actions = document.createElement("div");
  actions.className = "row";
  const cancel = document.createElement("button");
  cancel.className = "ghost"; cancel.textContent = "Cancel";
  cancel.onclick = () => bg.remove();
  const save = document.createElement("button");
  save.textContent = "Save";
  save.onclick = async () => {
    const body = {
      type: typeSel.value,
      columns: localPicker.get(),
      name: nameInput.value.trim() || null,
    };
    if (!body.columns.length) { showError("select at least one column"); return; }
    if (typeSel.value === "FOREIGN KEY") {
      body.ref_table = refTableSel.value;
      body.ref_columns = refPicker.get();
      if (!body.ref_columns.length) {
        showError("select at least one referenced column"); return;
      }
    }
    try {
      await post(
        `/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}/constraints`,
        body);
      bg.remove();
      await renderTableView(db, table, refresh);
    } catch (e) { showError(e.message); }
  };
  actions.append(cancel, save);

  box.append(typeRow, colsLabel, localPicker.el, nameRow, fkSection, actions);
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
    await post(`/api/databases/${encodeURIComponent(db)}/tables`, {
      name: v.name,
      columns: [{ name: v.col, type: v.type, primary_key: true,
                  nullable: false }],
    });
    await refresh();
  } catch (e) { showError(e.message); }
}
