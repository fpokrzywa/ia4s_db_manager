# Server UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a connection Test button to the server Add/Edit modal, and make the sidebar's database tree collapsible (default collapsed).

**Architecture:** A new `POST /api/servers/test-connection` endpoint connection-tests raw form values. `formModal` gains an optional `actions` parameter so the server dialog can host a Test button with an in-modal status line. The sidebar groups each database's tables in a container div toggled by a themed `+`/`−` control, with expanded state held in a module-level `Set`.

**Tech Stack:** FastAPI, psycopg 3, vanilla-JS ES modules, pytest.

**Spec:** `docs/superpowers/specs/2026-05-22-server-ux-improvements-design.md`

**Branch:** `feature/server-ux-improvements` (already created off `main`).

---

## File Structure

| File | Responsibility |
|---|---|
| `src/dbmanager/serverdb.py` | MODIFY — add `conninfo_from_fields`; `conninfo_for` delegates to it. |
| `src/dbmanager/routes/servers.py` | MODIFY — `TestConnectionBody` + `POST /api/servers/test-connection`. |
| `tests/test_serverdb.py` | MODIFY — test `conninfo_from_fields`. |
| `tests/test_servers.py` | MODIFY — test the test-connection endpoint. |
| `src/dbmanager/web/app.js` | MODIFY — `formModal` gains `opts.actions` + status line; `loadSidebar` collapsible tree. |
| `src/dbmanager/web/servers.js` | MODIFY — Test button in the server dialog. |
| `src/dbmanager/web/app.css` | MODIFY — `.modal-status` and `.tree-toggle` styling. |

The full test suite currently passes at **95**. Task 1 adds 4 tests → **99**. Tasks 2 and 3 touch no backend code, so the suite stays at 99.

Test environment: tests run against a live Postgres via `DATABASE_URL` in `.env` (pytest-postgresql noproc mode). Always run `pytest -q` as a SINGLE foreground invocation — overlapping runs collide on the template database and produce spurious `dbm_pytest`/`InvalidCatalogName` errors. If you see those, re-run once cleanly.

---

## Task 1: Backend — `test-connection` endpoint

**Files:**
- Modify: `src/dbmanager/serverdb.py`, `src/dbmanager/routes/servers.py`
- Test: `tests/test_serverdb.py`, `tests/test_servers.py`

- [ ] **Step 1: Write the failing test for `conninfo_from_fields`**

Append to `tests/test_serverdb.py`:

```python
def test_conninfo_from_fields_builds_libpq_string():
    info = serverdb.conninfo_from_fields(
        host="h.example", port=6000, username="bob", password="topsecret",
        sslmode="require", dbname="mydb")
    assert "host=h.example" in info
    assert "port=6000" in info
    assert "user=bob" in info
    assert "password=topsecret" in info
    assert "dbname=mydb" in info


def test_conninfo_from_fields_defaults_dbname_to_maintenance_db():
    info = serverdb.conninfo_from_fields(
        host="h", port=5432, username="u", password="p",
        maintenance_db="admin_db")
    assert "dbname=admin_db" in info
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_serverdb.py::test_conninfo_from_fields_builds_libpq_string -v`
Expected: FAIL — `AttributeError: module 'dbmanager.serverdb' has no attribute 'conninfo_from_fields'`.

- [ ] **Step 3: Add `conninfo_from_fields` and refactor `conninfo_for`**

In `src/dbmanager/serverdb.py`, replace the existing `conninfo_for` function (the last function in the file) with these two functions:

```python
def conninfo_from_fields(*, host, port, username, password,
                         maintenance_db="postgres", sslmode="prefer",
                         dbname=None) -> str:
    """Build a libpq conninfo string from raw connection fields. `dbname`
    overrides `maintenance_db`."""
    return make_conninfo(
        "",
        host=host,
        port=str(port),
        user=username,
        password=password,
        dbname=dbname or maintenance_db,
        sslmode=sslmode,
    )


def conninfo_for(server: dict, dbname: str | None = None) -> str:
    """Build a libpq conninfo string for a server record. `dbname` overrides
    the server's maintenance database."""
    return conninfo_from_fields(
        host=server["host"],
        port=server["port"],
        username=server["username"],
        password=decrypt(server["password_enc"]),
        maintenance_db=server["maintenance_db"],
        sslmode=server["sslmode"],
        dbname=dbname,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_serverdb.py -v`
Expected: PASS — 9 tests (the 7 existing + 2 new). The existing `test_conninfo_for_decrypts_password` must still pass, confirming the refactor preserved `conninfo_for`'s behavior.

- [ ] **Step 5: Write the failing tests for the endpoint**

Append to `tests/test_servers.py`:

```python
def test_test_connection_ok(client, server_url):
    from psycopg.conninfo import conninfo_to_dict
    p = conninfo_to_dict(server_url)
    resp = client.post("/api/servers/test-connection", json={
        "host": p.get("host"), "port": int(p.get("port") or 5432),
        "username": p.get("user"), "password": p.get("password") or "",
        "maintenance_db": "postgres"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_test_connection_reports_failure(client):
    resp = client.post("/api/servers/test-connection", json={
        "host": "nonexistent-host.invalid", "port": 5432,
        "username": "u", "password": "pw"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_test_connection_does_not_leak_password(client):
    secret = "p@ss-no-leak-testconn-551"
    resp = client.post("/api/servers/test-connection", json={
        "host": "nonexistent-host.invalid", "port": 5432,
        "username": "u", "password": secret})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert secret not in (body.get("error") or "")
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `pytest tests/test_servers.py::test_test_connection_ok -v`
Expected: FAIL — 404, because `/api/servers/test-connection` is not yet a route.

- [ ] **Step 7: Add `TestConnectionBody` and the endpoint**

In `src/dbmanager/routes/servers.py`, add this model immediately after the existing `ActiveServerBody` class:

```python
class TestConnectionBody(BaseModel):
    host: str
    port: int = 5432
    username: str
    password: str
    maintenance_db: str = "postgres"
    sslmode: str = "prefer"
```

Then add this endpoint immediately after the existing `test_server` function (the `@router.post("/servers/{server_id}/test")` one):

```python
@router.post("/servers/test-connection")
def test_connection(body: TestConnectionBody) -> dict:
    """Try to connect using raw connection fields (before a server is saved);
    report success or the scrubbed error message. Never raises."""
    conninfo = serverdb.conninfo_from_fields(
        host=body.host, port=body.port, username=body.username,
        password=body.password, maintenance_db=body.maintenance_db,
        sslmode=body.sslmode)
    try:
        with psycopg.connect(conninfo, connect_timeout=8) as probe:
            probe.execute("SELECT 1")
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": _scrub(str(exc))}
```

(`psycopg`, `serverdb`, `_scrub`, and `BaseModel` are already imported in this file.)

- [ ] **Step 8: Run the endpoint tests to verify they pass**

Run: `pytest tests/test_servers.py -v`
Expected: PASS — 13 tests (the 10 existing + 3 new).

- [ ] **Step 9: Run the full suite**

Run: `pytest -q`
Expected: PASS — **99 passed**.

- [ ] **Step 10: Commit**

```bash
git add src/dbmanager/serverdb.py src/dbmanager/routes/servers.py tests/test_serverdb.py tests/test_servers.py
git commit -m "feat: /api/servers/test-connection endpoint"
```
End the commit message with the trailer:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

> **Note:** the running dev server on `:8962` must be restarted after this task before the new endpoint is reachable in the browser — the Python process does not hot-reload. This is an operational step, not part of the commit.

---

## Task 2: Frontend — Test button on the server modal

**Files:**
- Modify: `src/dbmanager/web/app.js` (the `formModal` function), `src/dbmanager/web/servers.js` (`serverDialog`), `src/dbmanager/web/app.css`

No automated frontend test — verify with `node --check` and that the backend suite is unaffected.

- [ ] **Step 1: Extend `formModal` in `src/dbmanager/web/app.js`**

Replace the entire `formModal` function with this version (adds the optional `opts` parameter, a `collectValues` helper, an in-modal status line, and extra action buttons; all existing field rendering is unchanged):

```js
export function formModal(title, fields, opts = {}) {
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

    const collectValues = () => {
      const out = {};
      for (const f of fields) {
        if (f.type === "checkbox") out[f.name] = inputs[f.name].checked;
        else if (f.type === "columns") out[f.name] = inputs[f.name].__picker.get();
        else out[f.name] = inputs[f.name].value.trim();
      }
      return out;
    };

    const status = document.createElement("div");
    status.className = "modal-status";
    const setStatus = (msg, kind) => {
      status.textContent = msg;
      status.className = "modal-status" + (kind ? " " + kind : "");
    };

    const actions = document.createElement("div");
    actions.className = "row";
    for (const a of opts.actions || []) {
      const btn = document.createElement("button");
      btn.className = "ghost";
      btn.textContent = a.label;
      btn.onclick = () => a.onClick(collectValues(), setStatus);
      actions.append(btn);
    }
    const cancel = document.createElement("button");
    cancel.className = "ghost"; cancel.textContent = "Cancel";
    const ok = document.createElement("button");
    ok.textContent = "Save";
    cancel.onclick = () => { bg.remove(); resolve(null); };
    ok.onclick = () => { bg.remove(); resolve(collectValues()); };
    actions.append(cancel, ok);
    box.append(status, actions);
  });
}
```

- [ ] **Step 2: Add `.modal-status` styling to `src/dbmanager/web/app.css`**

Immediately after the `.modal .row:last-child { ... }` line (the end of the modal section, before the `/* ---- keyframes ---- */` comment), add:

```css
.modal-status {
  min-height: 1.15em;
  margin-top: .45rem;
  font-family: var(--mono);
  font-size: 12px;
  color: var(--dim);
}
.modal-status.ok { color: var(--patina); }
.modal-status.error { color: var(--rust); }
```

- [ ] **Step 3: Add the Test button to `serverDialog` in `src/dbmanager/web/servers.js`**

In `serverDialog`, the `formModal(...)` call currently takes two arguments (the title and the fields array). Add a third argument — an `opts` object with a Test action. Change the call from:

```js
  ]);
  if (!v) return;
```

to:

```js
  ], {
    actions: [{
      label: "Test",
      onClick: async (vals, setStatus) => {
        setStatus("Testing connection…", "");
        let r;
        try {
          if (editing && !vals.password) {
            r = await post(`/api/servers/${server.id}/test`);
          } else {
            r = await post("/api/servers/test-connection", {
              host: vals.host, port: Number(vals.port) || 5432,
              username: vals.username, password: vals.password,
              maintenance_db: vals.maintenance_db || "postgres",
              sslmode: vals.sslmode,
            });
          }
        } catch (e) { setStatus(e.message, "error"); return; }
        if (r.ok) setStatus("Connection succeeded.", "ok");
        else setStatus("Connection failed: " + r.error, "error");
      },
    }],
  });
  if (!v) return;
```

(`post` is already imported in `servers.js`; `editing` and `server` are in scope inside `serverDialog`.)

- [ ] **Step 4: Syntax-check the changed JS**

Run: `node --check src/dbmanager/web/app.js` then `node --check src/dbmanager/web/servers.js`
Expected: no output, exit 0 for both.

- [ ] **Step 5: Run the full suite to confirm no backend regression**

Run: `pytest -q`
Expected: PASS — **99 passed** (Task 2 changes no backend code).

- [ ] **Step 6: Commit**

```bash
git add src/dbmanager/web/app.js src/dbmanager/web/servers.js src/dbmanager/web/app.css
git commit -m "feat: Test button on the server add/edit modal"
```
End the commit message with the trailer:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

---

## Task 3: Frontend — collapsible database tree in the sidebar

**Files:**
- Modify: `src/dbmanager/web/app.js` (the `loadSidebar` function + a new module-level `Set`), `src/dbmanager/web/app.css`

No automated frontend test — verify with `node --check` and that the backend suite is unaffected.

- [ ] **Step 1: Replace `loadSidebar` in `src/dbmanager/web/app.js`**

The `loadSidebar` function is preceded by the comment line `// --- sidebar ----...`. Replace from that comment through the end of the `loadSidebar` function with:

```js
// --- sidebar ----------------------------------------------------------------

// Names of databases whose table list is expanded. Empty at page load, so
// every database starts collapsed; toggling updates this set, and it survives
// sidebar rebuilds (navigation) within the session.
const expandedDbs = new Set();

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

  const serversBtn = document.createElement("div");
  serversBtn.className = "tree-item";
  serversBtn.textContent = "▸ Servers";
  serversBtn.onclick = () => renderServers();
  sidebar.append(serversBtn);

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

    const tablesEl = document.createElement("div");
    sidebar.append(tablesEl);
    for (const t of tables) {
      const tEl = document.createElement("div");
      tEl.className = "tree-item tree-table";
      tEl.textContent = t.name;
      tEl.onclick = () => selectTable(db.name, t.name);
      tablesEl.append(tEl);
    }

    if (tables.length) {
      const toggle = document.createElement("span");
      toggle.className = "tree-toggle";
      const expanded = expandedDbs.has(db.name);
      tablesEl.hidden = !expanded;
      toggle.textContent = expanded ? "−" : "+";
      toggle.onclick = (e) => {
        e.stopPropagation();
        const willExpand = tablesEl.hidden;
        tablesEl.hidden = !willExpand;
        toggle.textContent = willExpand ? "−" : "+";
        if (willExpand) expandedDbs.add(db.name);
        else expandedDbs.delete(db.name);
      };
      dbEl.append(toggle);
    }
  }
}
```

Note: the `−` in `toggle.textContent` is the MINUS SIGN character `−` (U+2212), paired with the plus sign `+`. Keep it exactly as written.

- [ ] **Step 2: Add `.tree-toggle` styling to `src/dbmanager/web/app.css`**

The `.tree-db` rule currently reads:

```css
.tree-db {
  font-family: var(--display);
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: .02em;
  color: var(--bone);
  text-transform: uppercase;
}
```

Add a `padding-right` line to it so a long database name never runs under the toggle:

```css
.tree-db {
  font-family: var(--display);
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: .02em;
  color: var(--bone);
  text-transform: uppercase;
  padding-right: 1.7rem;
}
```

Then, immediately after the `.tree-table:hover { ... }` line (the end of the tree section), add:

```css
.tree-toggle {
  position: absolute;
  right: .55rem;
  top: 50%;
  transform: translateY(-50%);
  font-family: var(--mono);
  font-size: 14px;
  line-height: 1;
  color: var(--dim);
  cursor: pointer;
  user-select: none;
}
.tree-toggle:hover { color: var(--ember); }
```

- [ ] **Step 3: Syntax-check the changed JS**

Run: `node --check src/dbmanager/web/app.js`
Expected: no output, exit 0.

- [ ] **Step 4: Run the full suite to confirm no backend regression**

Run: `pytest -q`
Expected: PASS — **99 passed** (Task 3 changes no backend code).

- [ ] **Step 5: Commit**

```bash
git add src/dbmanager/web/app.js src/dbmanager/web/app.css
git commit -m "feat: collapsible database tree in the sidebar"
```
End the commit message with the trailer:
`Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

---

# Self-Review Notes

- **Spec coverage:** `test-connection` endpoint + `conninfo_from_fields` refactor (Task 1); `formModal` `opts.actions` + in-modal status line + `servers.js` Test button with the Edit-blank-password branch (Task 2); collapsible tree with right-edge `+`/`−` toggle, container-grouped tables, `expandedDbs` session set, default collapsed, no toggle for empty databases, `.tree-toggle` theme styling (Task 3). All spec requirements map to a task.
- **Test coverage:** `conninfo_from_fields` (2 tests, Task 1 Step 1); test-connection ok/failure/no-leak (3 tests, Task 1 Step 5). The existing `test_conninfo_for_decrypts_password` guards the `conninfo_for` refactor. Frontend has no automated tests, consistent with the rest of the frontend; verified via `node --check`.
- **Type consistency:** `conninfo_from_fields` is keyword-only and used with keywords by both `conninfo_for` and the endpoint. `formModal(title, fields, opts)` — `opts.actions` is `[{label, onClick}]`; `onClick(values, setStatus)`; `setStatus(msg, kind)` with `kind` in `""|"ok"|"error"` matching the `.modal-status` / `.modal-status.ok` / `.modal-status.error` CSS classes. The Test handler calls `post` (already imported in `servers.js`).
- **Green between tasks:** Task 1 is additive (suite 95 → 99). Tasks 2 and 3 touch no backend code (suite stays 99). `formModal`'s new `opts` parameter defaults to `{}`, so every existing caller is unaffected.
