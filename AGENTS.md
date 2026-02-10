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
- Source: `app/` or project root (see repo structure).
- Tests: `tests/`
- Config/secrets: ENV + optional encrypted secrets file.

## Setup (Python)
- Dependency manager: Poetry.
- Virtualenv should be in-project: `.venv/`
- Install:
  - `poetry install --no-interaction --no-ansi` (local)
  - On Railway-like builds, prefer: `poetry install --no-interaction --no-ansi --no-root`

## Common commands
- Run locally:
  - `make start` (preferred) OR `poetry run python app.py`
- Run FastAPI:
  - `poetry run uvicorn webhook_app:app --reload --port 8000`
- Tests:
  - `poetry run pytest -q`

## Secrets rules (critical)
- NEVER commit `.env`, `.venv/`, `__pycache__/`, keys, tokens, credentials.
- Use `.env.example` with placeholders only.
- Runtime secrets come from:
  - Local: `.env` (not committed)
  - Production: platform Variables (Railway, etc.)
- If encrypted secrets exist, keep encryption tooling unchanged unless asked.

## Pitfalls (avoid)
- Do not create/rename local modules that shadow Python stdlib modules
  (e.g., secrets.py, json.py, typing.py, email.py, asyncio.py, dataclasses.py).
  If a name conflict exists, rename the local file/package (e.g., secrets_store.py).

## Telegram bot specific
- Polling mode: only one instance can run at a time.
- Webhook mode:
  - Endpoint: `/webhook`
  - Validate header: `X-Telegram-Bot-Api-Secret-Token`
  - Health check: `/health`
  - Auto webhook registration on startup if `PUBLIC_URL` is set.

## Change policy
- One commit = one logical change.
- Keep PRs small: prefer multiple small commits over one huge.
- When changing config/loading behavior: do not break priority order or defaults.

## Output requirements
- When asked to implement something: return
  1) `git diff` / unified diff
  2) short explanation of what changed
  3) next command(s) to run (only if user asked)