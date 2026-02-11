# AGENTS.md — Project Operating Rules for Agents (Codex/CLI/IDE)

## Goals
- Make small, safe changes with minimal diff.
- Prefer reliability and clarity over cleverness.
- Always preserve existing behavior unless explicitly requested.

## Working style
- Produce a unified diff (or `git diff`) first.
- Do NOT run commands unless explicitly asked.
- If uncertain, propose 2 options with trade-offs, then wait.

## Project layout

```
app/
  core/config.py        Pydantic Settings (env vars)
  core/logging.py       JSON structured logging
  db/models.py          SQLAlchemy 2 models (User, MealEntry)
  db/repos.py           UserRepo, MealRepo (async)
  db/engine.py          Engine + session factory
  services/nutrition_ai.py  OpenAI structured output (text + vision)
  services/precheck.py  Pre-API filtering (water, medicine, vague text)
  services/rate_limit.py    Per-user rate limiter + concurrency guard
  reports/stats.py      Stats aggregation (today, weekly, 4-week)
  bot/handlers/         Aiogram routers (start, meal, goals, stats, etc.)
  bot/keyboards.py      Reply + inline keyboard builders
  bot/formatters.py     Message templates
  bot/middlewares.py    DB session + logging context middleware
  bot/factory.py        Bot + dispatcher wiring
  web/main.py           FastAPI app (webhook + polling modes)
tests/                  pytest (aiosqlite, no external deps)
alembic/                DB migrations
```

## Setup (Python)
- Python 3.12, Poetry 2.x
- Virtualenv should be in-project: `.venv/`
- Install: `poetry install`

## Common commands
- **Local dev (polling):** `make dev` — no PUBLIC_URL needed, no ngrok
- **Production (webhook):** `make serve` or `docker compose up` — set PUBLIC_URL + WEBHOOK_SECRET
- **Docker:** `docker compose up --build` — PostgreSQL + app, migrations auto-run
- **Tests:** `poetry run pytest -v` or `make test`
- **Lint:** `poetry run ruff check .` or `make lint`
- **Format:** `poetry run ruff format .` or `make fmt`
- **Health:** `curl http://127.0.0.1:8000/health`
- **Migrations:** auto on startup; manual: `poetry run alembic upgrade head`

## Key patterns
- **Async everywhere:** SQLAlchemy async sessions, aiogram async handlers.
- **Soft delete:** `MealEntry.is_deleted` + `deleted_at`. All queries filter `is_deleted=False`.
- **Draft flow:** User sends text/photo → AI analysis → draft preview → Save/Edit/Delete buttons.
- **Draft token:** Each draft has a `draft_id`; callbacks validate it to prevent stale button actions.
- **One draft per user:** `draft_store: dict[int, DraftData]` keyed by `tg_user_id`.
- **Photo size selection:** Iterate from largest to smallest PhotoSize, pick first ≤ `MAX_PHOTO_BYTES`.
- **Middleware order:** DBSessionMiddleware (outer) → LoggingMiddleware (outer) → handlers.
- **Router order:** Command routers first, meal router last (catch-all text/photo).
- **Two run modes:** `PUBLIC_URL` set → webhook; empty → polling (local dev). Auto-detected in lifespan.
- **Auto-migrations:** `alembic upgrade head` runs via subprocess on every startup.

## Secrets rules (critical)
- NEVER commit `.env`, `.venv/`, `__pycache__/`, keys, tokens, credentials.
- Use `.env.example` with placeholders only.
- Runtime secrets: `.env` locally, platform env vars in production.

## Pitfalls (avoid)
- Do not create/rename local modules that shadow Python stdlib modules.
- SQLite tests: JSONB not supported — conftest.py patches it to JSON.
- `cast(column, Date)` breaks on SQLite — use `.label()` directly.

## Change policy
- One commit = one logical change.
- Keep PRs small: prefer multiple small commits over one huge.
- Always run `ruff format . && ruff check . && pytest` before committing.
