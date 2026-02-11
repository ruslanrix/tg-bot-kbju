# tg-bot-kbju

Telegram bot for tracking meals and calories/macros (KBJU). Send a text
description or a photo of your meal and the bot uses OpenAI to estimate
calories, protein, carbs, and fat. View daily/weekly/monthly stats, set
personal goals, and manage timezone.

## Stack

- Python 3.12, Poetry 2.x
- **aiogram 3** (Telegram Bot API)
- **FastAPI** (webhook receiver)
- **SQLAlchemy 2** (async) + **Alembic** (migrations)
- **PostgreSQL** (production) / SQLite (tests)
- **OpenAI API** (GPT-4o-mini vision + text)
- Docker & docker-compose

## Project layout

```
app/
  core/          config, logging
  db/            models, repos, engine
  services/      nutrition_ai, precheck, rate_limit
  reports/       stats aggregation
  bot/
    handlers/    start, meal, goals, stats, history, timezone, stubs
    keyboards.py
    formatters.py
    middlewares.py
    factory.py
  web/           FastAPI app (webhook + health)
tests/           pytest (97 tests)
alembic/         DB migrations
```

## Quickstart

### 1. Requirements

- Python 3.12 (pyenv recommended)
- Poetry installed
- PostgreSQL (or use docker-compose)

### 2. Install

```bash
poetry install
```

### 3. Configure

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

Required variables: `BOT_TOKEN`, `DATABASE_URL`, `OPENAI_API_KEY`.

Optional (for webhook/production): `PUBLIC_URL`, `WEBHOOK_SECRET`.
Leave `PUBLIC_URL` empty for local dev (polling mode, no ngrok needed).

### 4. Run

The app supports two modes:

**Polling mode (local dev)** — `PUBLIC_URL` not set, bot fetches updates itself:

```bash
make dev
```

**Webhook mode (production)** — set `PUBLIC_URL` and `WEBHOOK_SECRET`:

```bash
make serve
```

Database migrations run automatically on startup.
To run manually: `poetry run alembic upgrade head`.

### 5. Docker

```bash
docker compose up --build
```

This starts PostgreSQL and the bot app together. Migrations run automatically.

### 6. Health check

```bash
make health
# or
curl -s http://127.0.0.1:8000/health
```

## Tests

```bash
make test
# or
poetry run pytest -v
```

Tests use in-memory SQLite (no PostgreSQL needed).

## Lint / Format

```bash
make fmt    # ruff format
make lint   # ruff check
```

## Bot commands

| Command         | Description                     |
| --------------- | ------------------------------- |
| `/start`        | Register and show main keyboard |
| `/help`         | Usage instructions              |
| `/goals`        | Set daily calorie goal          |
| `/timezone`     | Change timezone (city or UTC)   |
| `/stats`        | Today / weekly / 4-week stats   |
| `/history`      | Last 20 meals with delete       |
| `/feedback`     | Stub (coming soon)              |
| `/subscription` | Stub (coming soon)              |

Send any **text** or **photo** of food to log a meal.

## Repo hygiene

- Do not commit `.env`, `.venv/`, `__pycache__/`, tokens/keys.
- Keep `.env.example` with placeholders only.
