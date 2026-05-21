# UI Capability Follow-ups — Design

**Date:** 2026-05-21
**Status:** Approved for planning
**Builds on:** `2026-05-21-postgres-database-manager-design.md`

## Purpose

The v1 frontend exposes less than the backend supports. This addendum closes
four gaps so the UI matches the backend's full capability.

## Changes

1. **Connected-server label.** New session-guarded `GET /api/server-info`
   returning `{host, port}` parsed from `DATABASE_URL` via
   `psycopg.conninfo.conninfo_to_dict` — the password is never returned. The
   frontend fills the existing top-bar `#server-label` with `host:port`.

2. **Ordered multi-column picker.** A reusable `columnPicker(options)`
   component in `app.js`: a dropdown plus an "Add" button that builds an
   ordered list of chosen columns, each removable. Column order is preserved
   (it matters for composite keys/indexes). `formModal` gains a `"columns"`
   field type backed by this component. `modalShell` is exported so custom
   dialogs can be built.

3. **Constraint dialog — foreign keys + multi-column.** The "+ Constraint"
   dialog becomes a custom dialog offering UNIQUE / PRIMARY KEY / FOREIGN KEY.
   Local columns use the ordered multi-column picker. For FOREIGN KEY a
   referenced-table select appears; changing it loads that table's columns
   into a second ordered picker for the referenced columns.

4. **Index dialog — multi-column.** The "+ Index" dialog's single-column
   select becomes the ordered multi-column picker.

5. **Edit-column dialog — nullable + default.** `editColumnDialog` gains a
   Nullable checkbox (pre-filled from `is_nullable`) and a Default field
   (pre-filled from `column_default`). On save it sends only what changed:
   `nullable` when toggled, `default` when set to a new value, and
   `drop_default: true` when a previously-set default is cleared.

## Out of scope

No backend route changes beyond the new `/api/server-info` endpoint — all DDL
capability already exists in `routes/tables.py` and `sqlbuild.py`.

## Delivery

Branch `feature/ui-followups`; full test suite stays green (a new test covers
`/api/server-info`); merge to `main` and push to GitHub.
