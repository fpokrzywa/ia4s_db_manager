import { get, post, patch, del } from "./api.js";
import { confirmModal, formModal, showError } from "./app.js";

let state = { db: null, table: null, page: 1, filterCol: "", filterVal: "" };

// Bound into tables.js via bindDataTab(). Renders the Data tab.
export async function renderDataTab(el, db, table) {
  if (state.db !== db || state.table !== table) {
    state = { db, table, page: 1, filterCol: "", filterVal: "" };
  }
  await draw(el, db, table);
}

async function draw(el, db, table) {
  const base = `/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}/rows`;
  const qs = new URLSearchParams({ page: state.page, page_size: 50 });
  if (state.filterCol && state.filterVal) {
    qs.set("filter_column", state.filterCol);
    qs.set("filter_value", state.filterVal);
  }
  const data = await get(`${base}?${qs}`);
  el.innerHTML = "";

  // toolbar
  const toolbar = document.createElement("div");
  toolbar.className = "toolbar";
  const addBtn = mkBtn("+ Row", () => addRowDialog(el, db, table, data.columns));
  addBtn.disabled = !data.editable;
  const filterCol = document.createElement("select");
  for (const c of ["", ...data.columns]) {
    const o = document.createElement("option");
    o.value = c; o.textContent = c || "(filter column)";
    filterCol.append(o);
  }
  filterCol.value = state.filterCol;
  const filterVal = document.createElement("input");
  filterVal.placeholder = "filter value";
  filterVal.value = state.filterVal;
  const applyBtn = mkBtn("Filter", () => {
    state.filterCol = filterCol.value;
    state.filterVal = filterVal.value;
    state.page = 1;
    draw(el, db, table);
  });
  toolbar.append(addBtn, filterCol, filterVal, applyBtn);
  el.append(toolbar);

  if (!data.editable) {
    const note = document.createElement("p");
    note.className = "notice";
    note.textContent =
      "This table has no primary key — rows are read-only. Add a primary key, or use the SQL Console.";
    el.append(note);
  }

  // grid
  const table_ = document.createElement("table");
  table_.className = "grid";
  const headCells = data.columns.map((c) => `<th>${c}</th>`).join("");
  table_.innerHTML =
    `<thead><tr>${headCells}${data.editable ? "<th></th>" : ""}</tr></thead>`;
  const body = document.createElement("tbody");
  for (const row of data.rows) {
    const tr = document.createElement("tr");
    for (const c of data.columns) {
      const td = document.createElement("td");
      td.textContent = row[c] === null ? "∅" : String(row[c]);
      tr.append(td);
    }
    if (data.editable) {
      const td = document.createElement("td");
      const pk = Object.fromEntries(data.primary_key.map((k) => [k, row[k]]));
      td.append(
        mkBtn("Edit", () => editRowDialog(el, db, table, data.columns, pk, row), "ghost"),
        mkBtn("Delete", async () => {
          if (await confirmModal("Delete row",
              "This permanently deletes the row.",
              "delete")) {
            try {
              await del(`${base}`, { pk });
              await draw(el, db, table);
            } catch (e) { showError(e.message); }
          }
        }, "ghost"));
      tr.append(td);
    }
    body.append(tr);
  }
  table_.append(body);
  el.append(table_);

  // pager
  const pager = document.createElement("div");
  pager.className = "toolbar";
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  const prev = mkBtn("‹ Prev", () => { state.page--; draw(el, db, table); }, "ghost");
  const next = mkBtn("Next ›", () => { state.page++; draw(el, db, table); }, "ghost");
  prev.disabled = state.page <= 1;
  next.disabled = state.page >= pages;
  const label = document.createElement("span");
  label.textContent = `Page ${data.page} of ${pages} · ${data.total} row(s)`;
  pager.append(prev, next, label);
  el.append(pager);
}

async function addRowDialog(el, db, table, columns) {
  const v = await formModal("Insert row",
    columns.map((c) => ({ name: c, label: c, type: "text" })));
  if (!v) return;
  const values = {};
  for (const c of columns) if (v[c] !== "") values[c] = v[c];
  try {
    await post(`/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}/rows`, { values });
    await draw(el, db, table);
  } catch (e) { showError(e.message); }
}

async function editRowDialog(el, db, table, columns, pk, row) {
  const fields = columns.map((c) => ({
    name: c, label: c, type: "text",
    value: row[c] === null ? "" : String(row[c]),
  }));
  const v = await formModal("Edit row", fields);
  if (!v) return;
  // Send only the columns whose value changed.
  const values = {};
  for (const c of columns) {
    const before = row[c] === null ? "" : String(row[c]);
    if (v[c] !== before) values[c] = v[c];
  }
  if (Object.keys(values).length === 0) return;
  try {
    await patch(`/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}/rows`, { pk, values });
    await draw(el, db, table);
  } catch (e) { showError(e.message); }
}

function mkBtn(text, onClick, cls) {
  const b = document.createElement("button");
  b.textContent = text;
  if (cls) b.className = cls;
  b.onclick = onClick;
  return b;
}
