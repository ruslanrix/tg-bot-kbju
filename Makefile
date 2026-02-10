# Makefile — universal helper for Poetry-based Python projects

# ---- Config (edit per project) ----
APP_MODULE ?= app.main:app        # FastAPI module: "package.module:app"
PY_ENTRY   ?= app.py              # Script entrypoint for bots/CLI apps
PORT       ?= 8000
HOST       ?= 127.0.0.1

# If your project is a bot (script entry), use `make start`.
# If your project is FastAPI, use `make dev` / `make serve`.

# ---- Internals ----
POETRY ?= poetry

.PHONY: help install install-ci update lock \
        start dev serve health test fmt lint clean \
        env python

help:
	@echo "Targets:"
	@echo "  install     - install deps (local)"
	@echo "  install-ci  - install deps for CI/Railway (no-root)"
	@echo "  start       - run script entry (bots): poetry run python $(PY_ENTRY)"
	@echo "  dev         - run FastAPI with reload"
	@echo "  serve       - run FastAPI without reload"
	@echo "  health      - curl http://$(HOST):$(PORT)/health"
	@echo "  test        - run pytest"
	@echo "  fmt         - format (ruff if installed)"
	@echo "  lint        - lint (ruff if installed)"
	@echo "  env         - show poetry env path"
	@echo "  python      - show python used by poetry"

install:
	$(POETRY) install --no-interaction --no-ansi

install-ci:
	$(POETRY) install --no-interaction --no-ansi --no-root

update:
	$(POETRY) update

lock:
	$(POETRY) lock --no-interaction

start:
	$(POETRY) run python $(PY_ENTRY)

dev:
	$(POETRY) run uvicorn $(APP_MODULE) --reload --host $(HOST) --port $(PORT)

serve:
	$(POETRY) run uvicorn $(APP_MODULE) --host 0.0.0.0 --port $(PORT)

health:
	curl -s http://$(HOST):$(PORT)/health && echo

test:
	$(POETRY) run pytest -q

fmt:
	@$(POETRY) run ruff format . 2>/dev/null || echo "ruff not installed (skip)"

lint:
	@$(POETRY) run ruff check . 2>/dev/null || echo "ruff not installed (skip)"

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ */__pycache__

# --- Project scaffolding (newproj.sh) ---
# Usage examples:
#   make new-fastapi NAME=hello-api CATEGORY=web
#   make new-tgbot   NAME=aristocrate CATEGORY=tg
#   make new-fastapi NAME=hello-api DIR=/tmp/hello-api

.PHONY: new-fastapi new-tgbot
new-fastapi:
	./newproj.sh -t fastapi -n $(NAME) $(if $(CATEGORY),-c $(CATEGORY),) $(if $(DIR),-d $(DIR),)

new-tgbot:
	./newproj.sh -t tgbot -n $(NAME) $(if $(CATEGORY),-c $(CATEGORY),) $(if $(DIR),-d $(DIR),)

.PHONY: inventory
inventory:
	$(HOME)/vibecode/bin/gen-local-inventory.sh