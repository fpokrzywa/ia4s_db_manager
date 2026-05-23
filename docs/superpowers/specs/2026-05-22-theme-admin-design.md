# Theme Administration — Design

**Date:** 2026-05-22
**Status:** Approved for planning
**Builds on:** multi-user auth (`2026-05-21-multi-user-auth-design.md`); the
foundry-console theme already in `src/dbmanager/web/app.css`.

A new admin-only page lets the app's first user (and any user they promote)
edit the app's theme — pick from a small set of built-in presets and override
individual colors. The chosen theme is global to the app and applied from the
first paint (including the login screen).

## Goals

- Introduce a real admin role to the app for the first time, gated minimally
  so it does not creep into other features.
- Let an admin pick a built-in preset (Foundry / Slate / Daylight) as the base
  theme and override a curated set of high-impact colors on top.
- Persist the theme globally so every user sees the same look. New tabs and
  the login screen apply the theme on first paint, not after a flash of
  default.

## Admin role (new)

- New column on `users`: `is_admin BOOLEAN NOT NULL DEFAULT false`.
  `authdb.apply_schema` adds it via `ALTER TABLE users ADD COLUMN IF NOT
  EXISTS …`.
- `dbmanager init-auth`: ensures the app always has at least one admin.
  Specifically: after applying the auth schema, if the `users` table has no
  admins (`select count(*) from users where is_admin`), it sets
  `is_admin = true` on the user with `min(id)` (the first user, whether just
  created on this run or already present from a prior run). If at least one
  admin already exists, it does nothing to existing rows. This handles both
  fresh installs and migrations to a deployment that pre-dates this feature.
- New FastAPI dependency `require_admin` (in `src/dbmanager/auth.py`). Extends
  `require_session` and additionally checks `is_admin` for the resolved user;
  returns **403** for non-admins.
- `/api/me` (existing) includes `is_admin` in the response so the frontend can
  show/hide admin-only UI.
- `tests/conftest.py`: the seeded test user (`test@example.com`) is flagged
  `is_admin = true`, so the existing `client` fixture is an admin TestClient.
  A small fixture `non_admin_client` (or a per-test monkeypatch) creates a
  second user without admin to verify 403 paths.

### Promotion / demotion from the Users page

- New route `PATCH /api/users/{id}/admin` (in `routes/users.py`), body
  `{is_admin: bool}`, gated by `require_admin`.
- Last-admin protection: demoting a user that is the only admin returns 400
  with a clear message. This is enforced in the route (count admins, refuse).
- The Users page (`src/dbmanager/web/users.js`) gains a small "Make admin" /
  "Revoke admin" action on each row, rendered only when `/api/me` returns
  `is_admin = true`.

## Theme storage

- New table `app_settings` in `common_data`:

  ```sql
  CREATE TABLE IF NOT EXISTS app_settings (
      key         text PRIMARY KEY,
      value       jsonb NOT NULL,
      updated_at  timestamptz NOT NULL DEFAULT now()
  );
  ```

  Generic global key/value store for future settings; the theme lives at
  `key = 'theme'`. `authdb.apply_schema` creates it.

- Theme JSON shape:

  ```json
  {
    "preset": "foundry",
    "overrides": { "--soot": "#15110c", "--iron": "#ff5a1f" }
  }
  ```

  - `preset`: one of `"foundry"`, `"slate"`, `"daylight"` (validated on save).
  - `overrides`: partial map from CSS-var name to a `#RRGGBB` hex string
    (validated on save). Empty `{}` means the theme is just the preset.

## Built-in presets (immutable, in code)

In a new module `src/dbmanager/themes.py`:

- `PRESETS` — a dict mapping preset name to its full color map (the 7 curated
  vars below).
- `default_theme()` returns `{"preset": "foundry", "overrides": {}}`.
- `validate(theme: dict) -> None` raises `ValueError` for an unknown preset
  name or any override whose name is not in the curated set or whose value
  fails the `#[0-9a-fA-F]{6}` regex. Used by the PATCH route.

Initial presets:

- **Foundry** (default) — the current foundry-console palette (soot + hot
  iron). Same hex values currently in `app.css`.
- **Slate** — a cool dark theme; neutral grays for background and text, a
  muted blue accent. No orange.
- **Daylight** — a light theme; cream background, dark text, restrained
  orange accent that nods to Foundry without dominating.

Exact hex values for Slate and Daylight are fixed in the plan, not here.

## Curated color set surfaced in the pickers

Seven of the existing CSS vars — the most visible ones:

| Picker label | CSS var | Foundry default |
|---|---|---|
| Background | `--soot` | `#15110c` |
| Accent (primary) | `--iron` | `#ff5a1f` |
| Accent (warm) | `--ember` | `#ffae3d` |
| Primary text | `--bone` | `#f4ecdb` |
| Secondary text | `--ash` | `#ab9d85` |
| Success | `--patina` | `#5fb295` |
| Error | `--rust` | `#c2412a` |

The remaining vars (`--soot-1`/`--soot-2`/`--soot-3`, `--edge`/`--edge-hi`,
`--dim`, `--spark`, `--steel`) keep their preset defaults — they're not
exposed for override in v1. Fonts (`--display`, `--mono`) are out of scope.

## API

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /api/theme` | **public** | Return the saved theme, or `default_theme()` if none. The login screen needs this before login, so it must not require a session. |
| `PATCH /api/theme` | admin | Validate and save `{preset, overrides}`. Returns the saved theme. |
| `PATCH /api/users/{id}/admin` | admin | Promote or demote. Returns 400 when demoting the last admin. |

`GET /api/theme` deliberately returns no sensitive data — only the chosen
preset name and the override colors, both already public-ish (they paint the
UI).

## Frontend

### Theme admin page — `src/dbmanager/web/theme.js`

A new page module exporting `renderTheme()`:

- Preset dropdown at the top, defaulting to the current `preset`.
- Seven color pickers — one per row from the table above. Each row shows:
  - the picker, prefilled with the current effective value (override if set,
    else preset default);
  - a small "Reset to preset" link, shown only when the var is overridden;
  - the CSS var name in dim text for context.
- At the bottom: "Reset all overrides" + "Cancel" + "Save".

**Live preview:** every change to the preset dropdown OR any color picker
immediately mutates a `<style id="theme-live">` element to override the
`:root` vars accordingly. Cancel or navigating away removes the live element,
falling back to the saved theme. Save persists via `PATCH /api/theme` and
swaps `theme-live` into the saved `theme-saved` element.

### App boot — `src/dbmanager/web/app.js`

- On initial load (before the auth check), `fetch('/api/theme')` and inject
  a `<style id="theme-saved">` with rules that override `:root` vars in
  `overrides`. The login screen and the post-login app both render themed
  from the first paint.
- Sidebar gets a `▸ Theme` entry, **only rendered when `/api/me` says
  `is_admin = true`**.
- The "Make admin" / "Revoke admin" action on each Users-page row is shown
  only when the current user is admin (the Users page already fetches the
  user list; it just needs the toggle UI + the new PATCH call).

### Login page

The login page is served by the same SPA shell, so the boot-time
`/api/theme` fetch already covers it — no additional change.

## Tests

Backend:

- `tests/test_settings_store.py` — round-trip set/get; missing key returns
  `None`.
- `tests/test_themes.py` — `default_theme()` shape; `validate()` accepts a
  good payload, rejects unknown preset, rejects bad var name, rejects bad
  color string.
- `tests/test_theme_routes.py` — GET as anonymous returns the default; PATCH
  as admin saves; PATCH as non-admin returns 403; PATCH with invalid preset
  returns 400; PATCH with invalid color returns 400; GET after PATCH returns
  the saved theme.
- `tests/test_users.py` (additions) — PATCH /admin promotes a non-admin;
  demoting the last admin returns 400; promoting/demoting as a non-admin
  returns 403.
- `tests/test_init_auth.py` (additions) — first run flags the seeded user
  `is_admin = true`; re-running against a populated table with at least one
  admin does not toggle existing users; re-running against a populated table
  with zero admins (simulated by clearing the flag) re-flags `min(id)`.

Frontend: no automated tests (consistent with the rest of the frontend).
Verify with `node --check` and a manual run.

## Migration

Re-run `dbmanager init-auth` against the live `common_data`. It:

1. Adds `is_admin` to the existing `users` table (no-op if already present).
2. Creates the `app_settings` table (no-op if already present).
3. If the table has zero admins, sets `is_admin = true` on the user with
   `min(id)`. Existing users beyond the first stay non-admin until promoted
   via the Users page.

After re-running, the dev server on `:8962` needs a restart for the new
routes to be reachable (same pattern as prior backend changes).

## Out of scope

- Per-user themes (a user choosing their own look). The theme is global.
- Multiple named saved themes (a library of admin-made themes to switch
  between). v1 has one "current theme".
- Font customization. Adds asset loading complexity for low value here.
- Real-time theme push to all active sessions (websockets). Other users see
  the new theme on their next page load.
