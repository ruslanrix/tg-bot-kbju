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
  core/          config, logging, time, version
  db/            models, repos, engine
  i18n/          locales (EN, RU), t() helper
  services/      nutrition_ai, precheck, rate_limit
  reports/       stats aggregation
  bot/
    handlers/    start, meal, goals, stats, history, timezone,
                 language, version, admin, stubs
    keyboards.py
    formatters.py
    middlewares.py
    factory.py
  web/           FastAPI app (webhook + health + task endpoints)
tests/           pytest (483+ tests)
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

### 6. Railway Deploy

1. Create a project at [railway.app](https://railway.app).
2. Add the **PostgreSQL** plugin — Railway provisions the database automatically.
3. Connect your GitHub repository (branch `main`).
4. Open **Variables** in the service settings and add:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | Token from [@BotFather](https://t.me/BotFather) |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `DATABASE_URL` | `postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}` |
| `PUBLIC_URL` | Your Railway domain, e.g. `https://my-app.up.railway.app` |
| `WEBHOOK_SECRET` | Random string (min 8 chars): `openssl rand -hex 16` |

> **Note:** Railway's built-in `DATABASE_URL` uses the `postgresql://` scheme, but
> asyncpg requires `postgresql+asyncpg://`. The reference-variable formula above
> builds the correct URL automatically.

5. Generate a public domain: **Settings → Networking → Generate Domain**.
   Copy the `https://xxx.up.railway.app` URL into `PUBLIC_URL`.
6. Deploy triggers automatically on push to `main`.
7. Verify:

```bash
curl https://xxx.up.railway.app/health   # {"status":"ok"}
```

Then send a message to the bot in Telegram — it should respond.

Database migrations run automatically on every deploy.

### 7. Health check

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

| Command         | Description                        |
| --------------- | ---------------------------------- |
| `/start`        | Register and show main keyboard    |
| `/help`         | Usage instructions                 |
| `/add`          | Manually write a meal (no photo)   |
| `/goals`        | Set daily calorie goal             |
| `/timezone`     | Change timezone (city or UTC)      |
| `/stats`        | Today / weekly / 4-week stats      |
| `/history`      | Last 20 meals with delete          |
| `/language`     | Switch UI language (EN / RU)       |
| `/version`      | Show current bot version           |
| `/feedback`     | Stub (coming soon)                 |
| `/subscription` | Stub (coming soon)                 |

Send any **text** or **photo** of food to log a meal.

## Versioning and releases

The single source of truth for the version is `pyproject.toml` (`[project].version`).
The `/version` bot command reads it at runtime via `app.core.version.get_version()`.

To cut a new release:

```bash
# 1. Bump version in pyproject.toml
# 2. Add a new section to CHANGELOG.md
# 3. Commit and push to main
git add pyproject.toml CHANGELOG.md
git commit -m "release: vX.Y.Z"
git push

# 4. Tag the release
git tag vX.Y.Z
git push origin vX.Y.Z
```

See [CHANGELOG.md](CHANGELOG.md) for the full release history.

## Repo hygiene

- Do not commit `.env`, `.venv/`, `__pycache__/`, tokens/keys.
- Keep `.env.example` with placeholders only.
