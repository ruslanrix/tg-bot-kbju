# Project Name

Short description.

## Stack
- Python
- Poetry
- (FastAPI / Aiogram / etc.)

## Quickstart

### 1) Requirements
- Python via pyenv (recommended)
- Poetry installed
- Git

### 2) Install
    poetry install

### 3) Configure
Create `.env` (never commit it). Example:

    # Required
    TELEGRAM_BOT_TOKEN=your_token
    OPENAI_API_KEY=your_key

    # Optional defaults
    OPENAI_MODEL=gpt-4o-mini
    OPENAI_TEMPERATURE=0.6
    OPENAI_MAX_OUTPUT_TOKENS=350
    OPENAI_TIMEOUT_SECONDS=30

    # Webhook mode (if used)
    PUBLIC_URL=https://your-app.up.railway.app
    WEBHOOK_SECRET=your_webhook_secret

### 4) Run

#### Bot (script entry)
    make start
    # or
    poetry run python app.py

#### FastAPI (local dev)
    make dev
    # or
    poetry run uvicorn app.main:app --reload --port 8000

### 5) Health check (if applicable)
    make health
    # or
    curl -s http://127.0.0.1:8000/health && echo

## Tests
    make test
    # or
    poetry run pytest -q

## Lint / Format (optional)
    make lint
    make fmt

## Deployment (Railway notes)

### Poetry install in build
If build fails with "current project could not be installed", use:
    poetry install --no-interaction --no-ansi --no-root

### Telegram Webhook mode (if used)
- Endpoint: POST /webhook
- Secret: header X-Telegram-Bot-Api-Secret-Token
- App sets webhook automatically on startup if PUBLIC_URL is set.

Telegram debug:
    curl -s "https://api.telegram.org/bot$TOKEN/getWebhookInfo"

## Repo hygiene
- Do not commit `.env`, `.venv/`, `__pycache__/`, tokens/keys.
- Keep `.env.example` with placeholders only.

## Canonical learning plan
- See: MODULES.md (source of truth)
- Rule: done modules never renamed; new topics appended as new letters.
- Goal: vibecoding with agents (Codex/Claude) safely via PR + small diffs.

