# Server UX Improvements — Design

**Date:** 2026-05-22
**Status:** Approved for planning
**Builds on:** the multi-server-support feature (`2026-05-22-multi-server-support-design.md`)

Two small frontend-focused UX improvements to the Database Manager, implemented
in order: (1) a connection Test button on the server Add/Edit modal, then
(2) a collapsible database tree in the sidebar.

---

## Feature 1: Connection Test button on the server Add/Edit modal

### Problem

On the Servers page, a failed Save (bad credentials, unreachable host, wrong
SSL mode) shows an error and closes the modal, discarding everything typed.
The user must re-enter the whole form.

### Solution

A **Test** button in the Add/Edit server modal that attempts a live connection
with the current form values, reports success/failure on an in-modal status
line, and leaves the modal open so nothing is lost.

### Backend

- New endpoint `POST /api/servers/test-connection` in `routes/servers.py`,
  auto-gated by the servers router's existing `require_session` dependency.
- Request body `TestConnectionBody`: `host: str`, `port: int = 5432`,
  `username: str`, `password: str`, `maintenance_db: str = "postgres"`,
  `sslmode: str = "prefer"`. No label/is_default/notes — not needed to test.
- Behavior: build a libpq conninfo from the raw fields, attempt
  `psycopg.connect(conninfo, connect_timeout=8)` then `SELECT 1`. Return
  `{"ok": true}` on success, `{"ok": false, "error": "<scrubbed>"}` on any
  failure. Never raises. Reuses the existing `_scrub()` helper to redact any
  `password=` token from the error text.
- `serverdb.py`: extract `conninfo_from_fields(*, host, port, username,
  password, maintenance_db="postgres", sslmode="prefer", dbname=None) -> str`
  that builds the conninfo via `make_conninfo`. The existing
  `conninfo_for(server, dbname)` is refactored to decrypt the stored password
  and delegate to it — one conninfo-building code path. The new endpoint calls
  `conninfo_from_fields` directly with the plaintext form password.

### Frontend

- `app.js` `formModal(title, fields, opts)` gains an optional third parameter
  `opts`. `opts.actions` is an optional array of `{label, onClick}` extra
  buttons rendered alongside Cancel/Save. `formModal` also renders an in-modal
  status line. Each extra-button handler is called with `(values, setStatus)`
  where `values` is the current form values and `setStatus(message, kind)`
  writes the status line (`kind`: `"ok"` | `"error"`). Extra buttons do NOT
  close the modal. Callers that pass no `opts` are unaffected.
- `servers.js` `serverDialog` passes one extra action — a **Test** button:
  - Editing AND password field blank → `POST /api/servers/{id}/test` (tests
    the stored password).
  - Otherwise (adding, or editing with a typed password) →
    `POST /api/servers/test-connection` with the current form values.
  - Reports via `setStatus("Connection succeeded", "ok")` or
    `setStatus("Connection failed: <error>", "error")`.

### Tests

`tests/test_servers.py`: `test-connection` success (against the test
Postgres), failure (unreachable host → `ok: false`), and password-not-leaked
(a distinctive password is absent from the error string).

---

## Feature 2: Collapsible database tree in the sidebar

### Problem

The sidebar lists every database with all of its tables always expanded; a
database with many tables dominates the sidebar and there is no way to
collapse it.

### Solution

A theme-styled `+` / `−` toggle on the right of each database row
collapses/expands that database's table list. Databases default to collapsed.

### Structure (`app.js` `loadSidebar`)

- Today database rows and table rows are flat siblings of `#sidebar`. Change:
  each database renders its row (`dbEl`) followed by a container `<div>`
  (`tablesEl`) holding that database's table rows. Collapsing toggles the
  container's visibility.
- Each `dbEl` gets a `.tree-toggle` element, absolutely positioned at the
  row's right edge (`.tree-item` is already `position: relative`). Text `+`
  when collapsed, `−` when expanded. Its click handler toggles state and
  `stopPropagation`s so it does not also trigger the database overview.
  Databases with zero tables render no toggle.
- Clicking the database **name** still calls `selectDatabase` (overview);
  double-click (new table) and right-click (drop) are unchanged.
- A module-level `Set` `expandedDbs` holds the names of expanded databases.
  `loadSidebar` renders a database expanded iff its name is in the set. The
  set starts empty → all databases collapsed on first load and after a page
  reload; the toggle adds/removes names; navigation (which rebuilds the
  sidebar) preserves the set, so an opened database stays open while the user
  works.

### Styling (`app.css`)

- `.tree-toggle`: monospace `+`/`−`, theme dim/ash color,
  `position: absolute; right: .5rem`, hover → ember accent — consistent with
  the foundry-console palette.

### Scope / non-goals

- Tables are still fetched for all databases when the sidebar builds
  (unchanged from today); collapsed simply hides them. Lazy-loading tables
  only on expand is a possible future optimization, explicitly out of scope.
- Frontend only — no backend change. No automated frontend tests, consistent
  with the rest of the frontend.

---

## Implementation order

Feature 1 (Test button) is implemented and reviewed first, then Feature 2
(collapsible tree).
