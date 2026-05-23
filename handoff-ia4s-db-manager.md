# Handoff — IA4S Database Manager

**Date:** 2026-05-22
**Workspace:** `s:\Development_2026\ia4service\database_manager`
**GitHub:** https://github.com/fpokrzywa/ia4s_db_manager

## What this project is

A self-hosted web app for full CRUD over Postgres servers (databases, tables,
full DDL, row editing, SQL console) with multi-user login. FastAPI backend +
vanilla-JS frontend + Docker. v1 and a UI-capability follow-up batch are on
`main`.

Reference artifacts — read these, do not re-summarise them:
- Specs/plans in `docs/superpowers/specs/` and `docs/superpowers/plans/`:
  v1, UI follow-ups, multi-user auth, and **multi-server support**
  (`2026-05-22-multi-server-support-*.md`).

## Current branch & status

Active branch: **`feature/multi-user-auth`** (NOT merged to `main`). It has
accumulated several bodies of work, all committed:
1. Multi-user auth feature — complete, reviewed, 70+ tests passing.
2. Frontend redesign — FORGE-style "industrial foundry console"
   (warm soot palette, hot-iron accent, Big Shoulders wordmark, atmosphere
   layers).
3. A visible "+ New table" button on the database overview panel.
4. **Multi-server support — IN PROGRESS** (see below).

## Multi-server support — in progress

Goal: replace the single hardwired `DATABASE_URL` with an in-app registry of
Postgres servers, a top-bar picker to choose the active server per session,
and Fernet-encrypted server passwords. Spec + 7-task plan are written and
committed (`docs/superpowers/specs|plans/2026-05-22-multi-server-support-*`).

Execution: subagent-driven (fresh subagent per task, two-stage spec +
code-quality review per task).

- **Task 1 (`crypto.py` — Fernet encryption): IMPLEMENTED and committed**
  (`feat: Fernet encryption for stored secrets`); full suite **73 passed**.
  Its two-stage review is **NOT yet done — that is the immediate next action.**
- Tasks 2–7 (serverdb + schema, init-auth migration, the active-server
  cutover, registry routes, Servers page, top-bar picker): not started.

## Immediate next steps

1. Run the **spec + code-quality review for multi-server Task 1**
   (`src/dbmanager/crypto.py`, `tests/test_crypto.py`, the `pyproject.toml`
   dependency).
2. Continue the plan, Tasks 2–7, each: implement → spec review → code-quality
   review. **Task 4 is the atomic cutover** — it changes `config.py`,
   `deps.py`, all four resource routers, `webapp.py`, and the `client` test
   fixture together; expect it to be large and keep it atomic.
3. When the whole multi-server feature is done and the suite is green, do a
   final whole-branch review.
4. Merge `feature/multi-user-auth` → `main` and push. The branch bundles auth,
   the redesign, the +New-table button, and multi-server — all merge together.

## Live state

A uvicorn dev server is running in the background on **http://127.0.0.1:8962**
(serves `feature/multi-user-auth`, connected to the live Postgres via `.env`).
Static files serve from disk, so frontend edits show on browser refresh.

`init-auth` has been run against the live `common_data` — `users` /
`user_sessions` tables exist, `freddie@3cpublish.com` is seeded (must change
password on first login). A generated `APP_SECRET` is in the local (gitignored)
`.env`. NOTE: once multi-server Task 3 ships, re-running `init-auth` will also
create the `servers` table and register the current `DATABASE_URL` server.

## Test environment notes

- Tests run against the live Postgres (`DATABASE_URL` in `.env`) via
  `pytest-postgresql` noproc mode — no local Postgres/Docker on this machine.
- `tests/conftest.py` auto-drops stale `dbm_pytest*` databases at import. Run
  `pytest -q` as a SINGLE run — overlapping runs collide on the template DB
  and produce spurious `dbm_pytest_tmpl` errors that are NOT real failures.
- Last confirmed clean full run: **73 passed**.

## Still outstanding (separate, pre-existing)

`https://dbm.agenticweaver.com` runs an OLD build. It updates only when its
container is redeployed from `main` — pushing to GitHub does not redeploy it.
How that host is deployed (VPS `docker compose` vs. a hosting platform) is
still unconfirmed — ask the user.

## Suggested skills for the next session

- **superpowers:subagent-driven-development** — continue executing the
  multi-server plan (Task 1 review, then Tasks 2–7).
- **superpowers:requesting-code-review** — the per-task two-stage review.
- **superpowers:finishing-a-development-branch** — to merge
  `feature/multi-user-auth` into `main` once the feature is complete.
- **superpowers:verification-before-completion** — confirm a clean single
  `pytest -q` run before merging.
