# UI Capability Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Database Manager frontend expose the backend's full capability — foreign keys, multi-column constraints/indexes, column nullable/default editing, and a connected-server label.

**Architecture:** Six tasks on branch `feature/ui-followups`. One new backend endpoint (`/api/server-info`); the rest are frontend changes to `app.js` and `tables.js`. The existing DDL routes already support everything else.

**Tech Stack:** FastAPI, psycopg 3, vanilla-JS ES modules, pytest.

**Spec:** `docs/superpowers/specs/2026-05-21-ui-followups-design.md`

---

## Task 1: `/api/server-info` endpoint

**Files:**
- Modify: `src/dbmanager/webapp.py`
- Test: `tests/test_webapp.py`

- [ ] **Step 1: Create the branch**

```bash
cd s:/Development_2026/ia4service/database_manager
git checkout -b feature/ui-followups
```

- [ ] **Step 2: Add failing tests to `tests/test_webapp.py`** (append, keep existing tests)

```python
def test_server_info_returns_host_port():
    c = TestClient(app)
    c.post("/api/login", json={"password": "test-password"})
    resp = c.get("/api/server-info")
    assert resp.status_code == 200
    data = resp.json()
    assert "host" in data and "port" in data


def test_server_info_requires_auth():
    resp = TestClient(app).get("/api/server-info")
    assert resp.status_code == 401
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_webapp.py -v`
Expected: FAIL — 404 on `/api/server-info`

- [ ] **Step 4: Add the endpoint to `src/dbmanager/webapp.py`**

Add this import to the top import block (after `from dbmanager.config import Settings`):

```python
from psycopg.conninfo import conninfo_to_dict
```

Then, at the END of the file (after the existing `app.include_router(query.router, ...)` line — `Depends` and `require_session` are already imported above), add:

```python


@app.get("/api/server-info", dependencies=[Depends(require_session)])
def server_info() -> dict:
    """Host and port of the configured Postgres server — no credentials."""
    info = conninfo_to_dict(Settings.from_env().database_url)
    return {"host": info.get("host") or "", "port": info.get("port") or ""}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_webapp.py -v`
Expected: PASS (all webapp tests, including the 2 new ones)

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/webapp.py tests/test_webapp.py
git commit -m "feat: server-info endpoint"
```

---

## Task 2: Ordered multi-column picker

**Files:**
- Modify: `src/dbmanager/web/app.js`

No automated test (frontend). Verify the file is served and parses.

- [ ] **Step 1: Export `modalShell`**

In `src/dbmanager/web/app.js`, the function is currently declared:

```js
function modalShell() {
```

Change that line to:

```js
export function modalShell() {
```

- [ ] **Step 2: Add the `columnPicker` component**

In `src/dbmanager/web/app.js`, immediately AFTER the `modalShell` function (after its closing `}` on the line `return { bg, box };` block) and BEFORE the `confirmModal` function, insert:

```js

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
```

- [ ] **Step 3: Add a `"columns"` field type to `formModal`**

In `formModal`, the field-building loop currently has this `if/else if/else`
chain:

```js
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
```

Replace that entire block with:

```js
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
```

- [ ] **Step 4: Collect `"columns"` values in `formModal`**

In `formModal`'s `ok.onclick` handler, the collection loop is currently:

```js
      const out = {};
      for (const f of fields) {
        out[f.name] = f.type === "checkbox"
          ? inputs[f.name].checked : inputs[f.name].value.trim();
      }
```

Replace it with:

```js
      const out = {};
      for (const f of fields) {
        if (f.type === "checkbox") out[f.name] = inputs[f.name].checked;
        else if (f.type === "columns") out[f.name] = inputs[f.name].__picker.get();
        else out[f.name] = inputs[f.name].value.trim();
      }
```

- [ ] **Step 5: Verify**

Start the server (or use `TestClient`) and confirm `GET /static/app.js`
returns 200 and the file contains `export function columnPicker` and
`export function modalShell`. Run `pytest -q` to confirm the backend suite is
unaffected.

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/web/app.js
git commit -m "feat: ordered multi-column picker and modalShell export"
```

---

## Task 3: Constraint dialog — foreign keys + multi-column

**Files:**
- Modify: `src/dbmanager/web/tables.js`

- [ ] **Step 1: Update the import from `app.js`**

In `src/dbmanager/web/tables.js`, line 2 is currently:

```js
import { confirmModal, formModal, showError } from "./app.js";
```

Change it to:

```js
import { confirmModal, formModal, showError, modalShell, columnPicker } from "./app.js";
```

- [ ] **Step 2: Replace `addConstraintDialog`**

In `src/dbmanager/web/tables.js`, replace the entire current `addConstraintDialog`
function (the `async function addConstraintDialog(db, table, columns, refresh) { ... }`
block) with:

```js
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

  const tables = await get(`/api/databases/${encodeURIComponent(db)}/tables`);
  for (const t of tables) {
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
```

- [ ] **Step 3: Verify**

Confirm `GET /static/tables.js` returns 200 and contains
`import { confirmModal, formModal, showError, modalShell, columnPicker }` and
`FOREIGN KEY`. Run `pytest -q` — backend suite unaffected.

- [ ] **Step 4: Commit**

```bash
git add src/dbmanager/web/tables.js
git commit -m "feat: constraint dialog with foreign keys and multi-column"
```

---

## Task 4: Index dialog — multi-column

**Files:**
- Modify: `src/dbmanager/web/tables.js`

- [ ] **Step 1: Replace `addIndexDialog`**

In `src/dbmanager/web/tables.js`, replace the entire current `addIndexDialog`
function with:

```js
async function addIndexDialog(db, table, columns, refresh) {
  const v = await formModal("Create index", [
    { name: "name", label: "Index name", type: "text" },
    { name: "columns", label: "Columns", type: "columns", options: columns },
    { name: "unique", label: "Unique", type: "checkbox" },
  ]);
  if (!v) return;
  if (!v.columns.length) { showError("select at least one column"); return; }
  try {
    await post(
      `/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}/indexes`,
      { name: v.name, columns: v.columns, unique: v.unique });
    await renderTableView(db, table, refresh);
  } catch (e) { showError(e.message); }
}
```

- [ ] **Step 2: Verify**

Confirm `GET /static/tables.js` returns 200 and the new `addIndexDialog` uses
`type: "columns"`. Run `pytest -q`.

- [ ] **Step 3: Commit**

```bash
git add src/dbmanager/web/tables.js
git commit -m "feat: multi-column index dialog"
```

---

## Task 5: Edit-column dialog — nullable + default

**Files:**
- Modify: `src/dbmanager/web/tables.js`

- [ ] **Step 1: Replace `editColumnDialog`**

In `src/dbmanager/web/tables.js`, replace the entire current `editColumnDialog`
function with:

```js
async function editColumnDialog(db, table, col, refresh) {
  const wasNullable = col.is_nullable === "YES";
  const currentDefault = col.column_default ?? "";
  const v = await formModal(`Edit column "${col.name}"`, [
    { name: "new_name", label: "Rename to", type: "text" },
    { name: "type", label: "New type", type: "text" },
    { name: "nullable", label: "Nullable", type: "checkbox", value: wasNullable },
    { name: "default", label: "Default", type: "text", value: currentDefault },
  ]);
  if (!v) return;
  const body = { new_name: v.new_name || null, type: v.type || null };
  if (v.nullable !== wasNullable) body.nullable = v.nullable;
  if (v.default !== currentDefault) {
    if (v.default === "") body.drop_default = true;
    else body.default = v.default;
  }
  try {
    await patch(
      `/api/databases/${encodeURIComponent(db)}/tables/${encodeURIComponent(table)}/columns/${encodeURIComponent(col.name)}`,
      body);
    await renderTableView(db, table, refresh); await refresh();
  } catch (e) { showError(e.message); }
}
```

- [ ] **Step 2: Verify**

Confirm `GET /static/tables.js` returns 200 and the new `editColumnDialog`
includes the `nullable` and `default` fields. Run `pytest -q`.

- [ ] **Step 3: Commit**

```bash
git add src/dbmanager/web/tables.js
git commit -m "feat: nullable and default editing in edit-column dialog"
```

---

## Task 6: Connected-server label

**Files:**
- Modify: `src/dbmanager/web/app.js`

- [ ] **Step 1: Populate the server label in `showApp`**

In `src/dbmanager/web/app.js`, the `showApp` function is currently:

```js
async function showApp() {
  loginEl.classList.add("hidden");
  appEl.classList.remove("hidden");
  await loadSidebar();
}
```

Replace it with:

```js
async function showApp() {
  loginEl.classList.add("hidden");
  appEl.classList.remove("hidden");
  await loadSidebar();
  try {
    const info = await get("/api/server-info");
    document.getElementById("server-label").textContent =
      info.host ? `${info.host}:${info.port}` : "";
  } catch { /* label is cosmetic — ignore failures */ }
}
```

- [ ] **Step 2: Verify**

Confirm `GET /static/app.js` returns 200 and `showApp` now fetches
`/api/server-info`. Run `pytest -q`.

- [ ] **Step 3: Commit**

```bash
git add src/dbmanager/web/app.js
git commit -m "feat: show connected server in the top bar"
```

---

# Self-Review Notes

- **Spec coverage:** server-info endpoint + label (Tasks 1, 6); multi-column
  picker (Task 2); FK + multi-column constraints (Task 3); multi-column
  indexes (Task 4); nullable/default column editing (Task 5).
- **Type consistency:** `columnPicker` returns `{el, get}`; `formModal`'s
  `"columns"` field type stores the picker on `el.__picker` and `get()`
  returns an array; the constraint/index dialogs send `columns` (and
  `ref_columns`) as arrays, matching `ConstraintBody`/`IndexBody` in
  `routes/tables.py`.
- **Backend:** only `/api/server-info` is new; all DDL routes already exist.
