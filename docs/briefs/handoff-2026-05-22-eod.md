# Handoff — IA4S Database Manager

**Date:** 2026-05-22 (end of session)
**Workspace:** `s:\Development_2026\ia4service\database_manager`
**GitHub:** https://github.com/fpokrzywa/ia4s_db_manager
**Prior handoff (archived):** [docs/briefs/handoff-2026-05-22-prior.md](docs/briefs/handoff-2026-05-22-prior.md) — the snapshot that bootstrapped *this* session.

## What this project is

A self-hosted FastAPI + vanilla-JS web app for full CRUD over **multiple** Postgres servers: in-app server registry with a top-bar picker, Fernet-encrypted credentials at rest, multi-user auth, databases / tables / rows / SQL console. Foundry-console UI theme.

## Current branch & status

Working on **`main`**, in sync with `origin/main` (0 ahead, 0 behind). Suite: **105 passed** (`pytest -q`, ~9–10 min wall-clock).

Three feature-batches landed this session, each with its own spec + plan:

| Feature | Spec | Plan |
|---|---|---|
| Multi-server support | [docs/superpowers/specs/2026-05-22-multi-server-support-design.md](docs/superpowers/specs/2026-05-22-multi-server-support-design.md) | [docs/superpowers/plans/2026-05-22-multi-server-support.md](docs/superpowers/plans/2026-05-22-multi-server-support.md) |
| Server UX (Test button + collapsible sidebar) | [docs/superpowers/specs/2026-05-22-server-ux-improvements-design.md](docs/superpowers/specs/2026-05-22-server-ux-improvements-design.md) | [docs/superpowers/plans/2026-05-22-server-ux-improvements.md](docs/superpowers/plans/2026-05-22-server-ux-improvements.md) |
| Performance (lazy-load + pooling) | [docs/superpowers/specs/2026-05-22-lazy-load-and-pool-design.md](docs/superpowers/specs/2026-05-22-lazy-load-and-pool-design.md) | [docs/superpowers/plans/2026-05-22-lazy-load-and-pool.md](docs/superpowers/plans/2026-05-22-lazy-load-and-pool.md) |

Mid-session there was also a debug-and-fix on "no server found" — which turned out to be environmental (stale dev server + missing `servers` table). Resolved by re-running `dbmanager init-auth` and restarting uvicorn; no code change required.

See `git log --oneline main` for the full commit trail; each feature lands as several reviewed commits (per-task spec + code-quality reviews caught real issues that were fixed before merge — see commit messages for the "refactor:" / "fix:" entries on top of each "feat:").

## Live state

A uvicorn dev server runs in the background on **http://127.0.0.1:8962** against the live Postgres in `.env`. It does **not** auto-reload — static files in `src/dbmanager/web/` serve from disk and update on browser refresh, but Python changes (anything in `src/dbmanager/*.py`) require an explicit restart.

**Restart procedure** (PowerShell on this Windows machine):

```powershell
$pid_ = (Get-NetTCPConnection -LocalPort 8962 -State Listen).OwningProcess
Stop-Process -Id $pid_ -Force
```

then from the workspace root:

```
python -m uvicorn dbmanager.webapp:app --host 127.0.0.1 --port 8962
```

(or `run_in_background: true` via the Bash tool to detach).

**Quick route-liveness probe** (no login required):

```
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:8962/api/<route>
```

`401` = route registered (auth-gated, working as expected). `404` = stale process, restart.

`common_data` already has the `users`, `user_sessions`, and `servers` tables. Multiple users seeded; at least two servers in the registry with one marked `is_default = true`. The exact rows are visible via the running app's Servers page or by querying the `servers` table directly.

## Test environment

- Tests run against the live Postgres via `DATABASE_URL` in `.env` (pytest-postgresql noproc mode — no local Postgres needed on this machine).
- `tests/conftest.py` auto-drops stale `dbm_pytest*` databases on import.
- An autouse fixture in `conftest.py` calls `pools.close_all()` after each test so the URL-keyed connection pools don't leak across the throwaway-DB tests.
- Run `pytest -q` as a **SINGLE FOREGROUND** invocation; overlapping pytest processes collide on the template database and produce spurious `dbm_pytest` / `InvalidCatalogName` errors.
- Per-test runtime is bounded by remote-Postgres `CREATE DATABASE` / `DROP DATABASE` overhead; pooling gave a modest test-suite win (~10 min → ~9 min), but the production app gets the full pooling benefit (~1.4 s of cold-connect handshake per request → ~50 ms once warm).

## Open items

1. **Deploy `dbm.agenticweaver.com`.** That host runs an OLD build and updates only on container redeploy from `main`. How it actually deploys (VPS `docker compose`, a hosting platform, a CI hook on push, …) is **still unconfirmed**. Pushing to GitHub does *not* redeploy it. Ask the user before assuming.
2. **Token-cost dashboard.** Working brief at [docs/briefs/token-usage-dashboard.md](docs/briefs/token-usage-dashboard.md) — an interview-driven design for live LLM-API token/cost tracking surfaced as a UI indicator. Not started. The brief explicitly says "Don't write any code yet. Start with an interview." — follow that.

## Light maintenance carry-overs (from per-task reviews, none blocking)

These were flagged during reviews and deemed non-blocking. Worth knowing about if any of these come up:

- The single-`is_default` invariant on `servers` is app-enforced (`_clear_default` + INSERT under autocommit), not DB-constrained. Low risk for a single-admin tool; a partial unique index would make it self-enforcing if ever desired.
- `init-auth` seeds an empty password if `DATABASE_URL` uses peer / `.pgpass` auth. Doesn't bite this deployment but would for someone migrating from passwordless local auth.
- Double-clicking the sidebar's `+` / `−` toggle also fires the row's `ondblclick` (which opens "new table"). Cosmetic UX wart; one-line fix (`toggle.ondblclick = e => e.stopPropagation()`) if it ever bothers anyone.
- pytest-postgresql per-test `CREATE / DROP DATABASE` against a remote VPS is the dominant test-suite cost. The structural fix would be a session-scoped DB plus per-test `TRUNCATE` — out of scope but worth flagging if test friction grows.

## Suggested skills for the next session

- **superpowers:using-superpowers** — read at the start of every session; reinforces the "invoke the relevant skill before responding" discipline.
- **superpowers:brainstorming → superpowers:writing-plans → superpowers:subagent-driven-development** — the design-then-execute cycle that worked end-to-end for every feature this session. Each task gets a fresh subagent with a two-stage (spec + code-quality) review.
- **superpowers:systematic-debugging** — for any "feels slow" / "this is broken" report. Measure before proposing fixes; this session, measuring ~700 ms per fresh Postgres connection drove the entire performance pass.
- **superpowers:verification-before-completion** — confirm `pytest -q` is green before claiming a feature is done.
- **superpowers:finishing-a-development-branch** — to merge feature branches and clean up at the end.
- **handoff** (this one) — to update this file again at the end of the next session.

## Project conventions (enforced by [CLAUDE.md](CLAUDE.md))

- Karpathy-style guidelines: think before coding, simplicity first, surgical changes, goal-driven execution. For trivial tasks use judgment.
- Commits end with the `Co-Authored-By: Claude …` trailer.
- Specs go in `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`; plans in `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`. Working briefs (future-feature material) go in `docs/briefs/`.
