# Plan: Telegram Calorie Tracker Bot (tg-bot-kbju)

## Context

Проект — scaffold без исходного кода (ветка `main`, коммит `init: scaffold`). Есть pyproject.toml (aiogram 3.6, fastapi, openai 1.40, uvicorn, httpx), Makefile, AGENTS.md, тесты-заглушки. Нужно реализовать Telegram-бота для трекинга калорий по `spec.md`.

**Окружение:** macOS, Python 3.12.12, Poetry 2.2.1, git 2.52, gh 2.85.

**Golden path (how-to-ship.md):** branch → fmt/lint/test → PR → CI green → merge. Маленькие PR, минимальные диффы.

**Что делает бот:** принимает текст/фото еды → анализирует через OpenAI (structured JSON) → хранит в PostgreSQL → показывает статистику (Today/Weekly/4 Weeks) и историю. Поддерживает edit/delete (soft delete), pre-API фильтрацию, rate limiting, webhook через FastAPI.

---

## Структура проекта (целевая)

```
app/
  __init__.py
  core/           — config (Pydantic Settings), time utils, logging
  db/             — models (SQLAlchemy 2), session, repos
  services/       — precheck, nutrition_ai, rate_limit
  reports/        — stats aggregation
  bot/            — handlers, keyboards, formatters, middlewares, FSM
    handlers/     — start, goals, timezone, meal, stats, history, stubs
  web/            — FastAPI (webhook + health)
alembic/          — миграции
tests/            — unit + integration тесты
Dockerfile, docker-compose.yml, .dockerignore
.env.example
```

---

## Шаги реализации

### Шаг 1. Зависимости + скелет директорий

**Что делать:**
- Добавить в `pyproject.toml`: `sqlalchemy[asyncio]>=2.0,<2.1`, `asyncpg>=0.29,<0.31`, `alembic>=1.13,<2.0`, `pydantic-settings>=2.4,<3.0`
- `poetry lock && poetry install`
- Создать дерево `app/` с `__init__.py` во всех подпакетах: `core`, `db`, `services`, `reports`, `bot`, `bot/handlers`, `web`

**Зависимости:** нет (первый шаг)

**Критерий готовности:**
- `poetry install` без ошибок
- `python -c "from app import core, db, services, reports, bot, web"` работает
- `make test` — smoke test проходит
- `make fmt && make lint` — чисто

---

### Шаг 2. Pydantic Settings + .env.example

**Что делать:**
- Создать `app/core/config.py` с классом `Settings(BaseSettings)`:
  - Required: `BOT_TOKEN`, `DATABASE_URL`, `OPENAI_API_KEY`, `PUBLIC_URL`, `WEBHOOK_SECRET`
  - Optional: `OPENAI_MODEL` (gpt-4o-mini), `LOG_LEVEL` (INFO), `OPENAI_TIMEOUT_SECONDS` (30), `MAX_PHOTO_BYTES` (5*1024*1024), `RATE_LIMIT_PER_MINUTE` (6), `MAX_CONCURRENT_PER_USER` (1), `PORT` (8000)
  - Валидаторы: `PUBLIC_URL` — https, без `/` на конце; `WEBHOOK_SECRET` — минимум 8 символов; числовые — положительные
- `get_settings()` с `@lru_cache`
- Создать `.env.example` со всеми переменными и плейсхолдерами

**Зависимости:** Шаг 1

**Критерий готовности:**
- `Settings` с валидными значениями создаётся; с невалидными — `ValidationError`
- `.env.example` содержит все переменные

---

### Шаг 3. Structured JSON logging

**Что делать:**
- Создать `app/core/logging.py`:
  - Кастомный JSON-форматтер (без внешних зависимостей, через `json.dumps`)
  - `setup_logging(log_level)` — root logger на stdout
  - Extra-поля: `tg_user_id`, `chat_id`, `message_id`, `event`, `request_id`

**Зависимости:** Шаг 2

**Критерий готовности:**
- `logger.info("test", extra={"event": "x"})` выводит валидный JSON на stdout

---

### Шаг 4. Утилиты для таймзон и дат

**Что делать:**
- Создать `app/core/time.py`:
  - `user_timezone(tz_mode, tz_name, tz_offset_minutes)` → `timezone` / `ZoneInfo`
  - `now_local(tz)`, `today_local(tz)` — текущее время/дата в tz пользователя
  - `local_date_from_utc(utc_dt, tz)` — UTC → локальная дата
  - `week_bounds(date)` — Mon-Sun неделя, содержащая дату
  - `last_7_days(today)` — список из 7 дат (today..today-6)
  - `last_28_days_weeks(today)` — 4 пары (Mon, Sun) для последних 28 дней
- Использовать `zoneinfo` (stdlib 3.12) для IANA, `datetime.timezone(timedelta(minutes=...))` для offset

**Зависимости:** Шаг 1

**Критерий готовности:**
- Корректно обрабатывает граничные случаи (полночь, смена дня)

---

### Шаг 5. Тесты для утилит времени

**Что делать:**
- Создать `tests/test_time.py`:
  - `local_date_from_utc` с Asia/Almaty (UTC+5): 22:00 UTC → следующий день
  - Midnight boundary: 23:59 vs 00:01
  - `week_bounds` для среды → Mon-Sun
  - `last_7_days` — 7 дат по убыванию
  - `last_28_days_weeks` — ровно 4 недели Mon-Sun

**Зависимости:** Шаг 4

**Критерий готовности:** `make test` — все тесты зелёные

---

### Шаг 6. SQLAlchemy модели + DB session

**Что делать:**
- Создать `app/db/models.py`:
  - `User`: id (UUID pk), tg_user_id (BigInt, unique, indexed), goal, tz_mode, tz_name, tz_offset_minutes, created_at, updated_at
  - `MealEntry`: все поля из spec 7.2 — JSONB для likely_ingredients_json и raw_ai_response, is_deleted (default False), deleted_at
  - Unique constraint на `(tg_chat_id, tg_message_id)`
  - Partial index на `(user_id, local_date)` WHERE `is_deleted=false`
- Создать `app/db/session.py`:
  - `async_engine`, `async_session_factory` от `DATABASE_URL`
  - `get_session()` async context manager

**Зависимости:** Шаги 1, 2

**Критерий готовности:** `from app.db.models import User, MealEntry` работает, колонки соответствуют spec 7.1-7.3

---

### Шаг 7. Alembic + начальная миграция

**Что делать:**
- `alembic init alembic`
- Настроить `alembic/env.py`: async engine, `target_metadata = Base.metadata`, DATABASE_URL из config
- `alembic revision --autogenerate -m "initial_tables"`
- Проверить сгенерированную миграцию

**Зависимости:** Шаг 6

**Критерий готовности:** `alembic upgrade head` создаёт таблицы users и meal_entries с правильной схемой

---

### Шаг 8. Репозитории (CRUD)

**Что делать:**
- Создать `app/db/repos.py`:
  - `UserRepo`: get_or_create, update_goal, update_timezone
  - `MealRepo`: create, get_by_id, update, soft_delete, exists_by_message, list_recent (limit=20)
- Все запросы фильтруют `is_deleted=False`

**Зависимости:** Шаг 6

**Критерий готовности:** Методы импортируются, типизированы, soft_delete ставит is_deleted=True + deleted_at

---

### Шаг 9. Запросы для отчётов (stats)

**Что делать:**
- Создать `app/reports/stats.py`:
  - `today_stats(session, user_id, local_date)` — суммы kcal/P/C/F, нули если нет данных
  - `weekly_stats(session, user_id, dates)` — по-дневные суммы за 7 дат
  - `four_week_stats(session, user_id, week_ranges)` — суммы за Mon-Sun / 7 = средние за день
- `WHERE is_deleted = false`, `COALESCE(SUM(...), 0)`

**Зависимости:** Шаги 6, 4

**Критерий готовности:** Корректные SQL-запросы с фильтрацией удалённых записей

---

### Шаг 10. Тесты для отчётов + DB fixtures

**Что делать:**
- Добавить `aiosqlite`, `pytest-asyncio` в dev-зависимости
- Создать `tests/conftest.py` с фикстурами: in-memory SQLite, create_all, тестовый user
- Создать `tests/test_reports.py`:
  - today_stats: 2 записи → суммы; 0 записей → нули; удалённая → исключена
  - weekly_stats: дни с данными и без → нули на пустых днях
  - four_week_stats: деление на 7 для средних

**Зависимости:** Шаги 9, 5

**Критерий готовности:** `make test` — зелёные

---

### Шаг 11. Сервис предварительной фильтрации (precheck)

**Что делать:**
- Создать `app/services/precheck.py`:
  - `PrecheckResult(passed, reject_message)`
  - Проверки по порядку (spec 5.1–5.6):
    1. Тип сообщения (не текст/фото → reject)
    2. Пустой/junk текст (только emoji/пунктуация)
    3. Вода: exact match "вода", "water", "стакан воды", "попил воды"
    4. Лекарства: "лекарство", "таблетка", "ibuprofen", "paracetamol"
    5. Vague text (ТОЛЬКО text-only, без чисел): "вкусняшка", "еда", "поел", "ням", "что-то"
    6. Размер фото > MAX_PHOTO_BYTES (проверяем `PhotoSize.file_size` без скачивания)
  - Сообщения отказа строго по спеке
  - НЕ отклонять: "pizza", "burger", "плов", "шаурма", "водка"

**Зависимости:** Шаг 2

**Критерий готовности:** Правильные accept/reject для всех edge cases

---

### Шаг 12. Тесты для precheck

**Что делать:**
- Создать `tests/test_precheck.py`:
  - "вода" → rejected; "водка" → passed (не false-positive!)
  - "таблетка" → rejected; "pizza" → passed
  - "еда" (text-only, no numbers) → rejected; "еда" (с фото) → passed
  - "!!!???" → rejected; "" → rejected
  - photo 10MB > 5MB → rejected

**Зависимости:** Шаг 11

**Критерий готовности:** `make test` — зелёные

---

### Шаг 13. Rate limiting + concurrency guard

**Что делать:**
- Создать `app/services/rate_limit.py`:
  - `RateLimiter`: in-memory sliding window dict, `check(tg_user_id, max_per_minute) -> bool`
  - `ConcurrencyGuard`: in-memory set + asyncio, `acquire(tg_user_id) -> bool`, `release(tg_user_id)`, async context manager
- Docstring: single-instance only; multi-instance → Redis (future)

**Зависимости:** Шаг 2

**Критерий готовности:** 7-й запрос/мин отклоняется; 2-й параллельный запрос того же user отклоняется

---

### Шаг 14. Сервис OpenAI (nutrition_ai)

**Что делать:**
- Создать `app/services/nutrition_ai.py`:
  - Pydantic-модели: `Ingredient(name, amount, calories_kcal)`, `NutritionAnalysis` (все поля из spec 6.1)
  - `action`: Literal["save", "reject_no_calories", "reject_not_food", "reject_insufficient_detail", "reject_unrecognized"]
  - `NutritionAIService`:
    - `analyze_text(text) -> NutritionAnalysis`
    - `analyze_photo(photo_bytes, caption) -> NutritionAnalysis` — base64 image, vision API
  - System prompt: правила из spec 6.2 (trust user numbers, prefer rejection, sanity checks, generate ingredients always)
  - Structured outputs через OpenAI SDK
  - API errors → `reject_unrecognized`

**Зависимости:** Шаги 1, 2

**Критерий готовности:** Схема валидируется для всех action; ошибки API → reject_unrecognized

---

### Шаг 15. Тесты для nutrition_ai (мок)

**Что делать:**
- Создать `tests/test_nutrition_ai.py`:
  - Мок `openai.AsyncOpenAI`
  - Все action: save, reject_no_calories, reject_not_food, reject_insufficient_detail, reject_unrecognized
  - Таймаут API → reject_unrecognized
  - Невалидный JSON → graceful handling

**Зависимости:** Шаг 14

**Критерий готовности:** `make test` — зелёные, без реальных вызовов OpenAI

---

### Шаг 16. Бот: фабрика, клавиатуры, /start, /help

**Что делать:**
- `app/bot/keyboards.py`:
  - `main_keyboard()` — ReplyKeyboard с 5 кнопками: "📊 Stats", "🎯 Goals", "☁️ Help", "🕘 History", "✏️ Add Meal"
  - `draft_actions_keyboard(meal_id)` — InlineKeyboard: ✅ Save / ✏️ Edit / 🛑 Delete
  - `saved_actions_keyboard(meal_id)` — InlineKeyboard: ✏️ Edit / 🛑 Delete
  - `timezone_inline_keyboard()`, `goal_inline_keyboard()`
- `app/bot/handlers/start.py`:
  - `/start` → get_or_create user + main keyboard
  - `/help` → текст из spec 3.3 + inline кнопка "🕒 Change Time Zone"
- `app/bot/router.py`: главный роутер
- `app/bot/factory.py`: `create_bot(token)`, `create_dispatcher()`

**Зависимости:** Шаги 2, 6, 8

**Критерий готовности:** Импорт работает; текст /help точно соответствует spec 3.3

---

### Шаг 17. Бот: выбор goal и timezone

**Что делать:**
- `app/bot/handlers/goals.py`: /goals + "🎯 Goals" → inline keyboard (maintenance/deficit/bulk), callback → update_goal
- `app/bot/handlers/timezone.py`: flow выбора — ~15-20 популярных городов (IANA) + UTC offsets от UTC-12 до UTC+14, callback → update_timezone
- Регистрация в роутере

**Зависимости:** Шаги 8, 16

**Критерий готовности:** Goal и timezone сохраняются в БД, подтверждение пользователю

---

### Шаг 18. Бот: meal flow (текст/фото → draft → save)

**Что делать:**
- `app/bot/handlers/meal.py`:
  - "✏️ Add Meal" / `/add` → подсказка ввести текст или фото
  - Любой текст (не команда, не кнопка main keyboard) → meal input:
    1. precheck pipeline → reject_message или pass
    2. rate limit + concurrency guard → throttle message
    3. ChatAction.typing heartbeat (background task каждые ~4с)
    4. OpenAI analysis (text или photo)
    5. reject_* → сообщение (fixed phrase "I couldn't recognize the food..." для unrecognized; user_message для остальных)
    6. action=save → draft в памяти + показать с Save/Edit/Delete
  - Фото → аналогично через analyze_photo (берём `message.photo[-1]`, проверяем file_size)
  - **Дубликат фото** (spec 5.8): проверка `file_unique_id` за последние N минут → reuse result (показать как новый draft — пользователь мог съесть две порции)
  - Callback "✅ Save":
    - Idempotency check по (tg_chat_id, tg_message_id)
    - Compute local_date по user timezone + snapshot tz
    - MealRepo.create с raw_ai_response
    - Отправить saved message (spec 3.4) + Today's Stats
    - Заменить inline keyboard на saved_actions (Edit/Delete)
  - Callback "🛑 Delete" (draft): удалить из памяти → "🗑️ Deleted."
- `app/bot/formatters.py`: format_meal_saved, format_today_stats — шаблоны из spec 3.4
- Draft store: `dict[int, DraftData]` (tg_user_id → NutritionAnalysis + metadata)

**Зависимости:** Шаги 4, 8, 9, 11, 13, 14, 16

**Критерий готовности:**
- Текст → OpenAI → draft с кнопками Save/Edit/Delete
- Save → запись в БД + Today's Stats
- Draft delete → без записи в БД, "🗑️ Deleted."
- ChatAction typing отображается
- Дубликат фото → reuse result как новый draft

---

### Шаг 19. Бот: edit и delete сохранённых записей

**Что делать:**
- Расширить `app/bot/handlers/meal.py` (или отдельный `edit_delete.py`):
  - "✏️ Edit" на saved meal → "Send corrected text" → FSM state `EditingMeal(meal_id=X)` (aiogram StatesGroup)
  - Пользователь отправляет текст → precheck + OpenAI (обязательно, spec 3.7: ingredients must be generated) → новый draft с Save/Edit/Delete
  - Save → `MealRepo.update(session, meal_id, ...)` — UPDATE existing row (не INSERT new!) + Today's Stats
  - "🛑 Delete" на saved meal → `MealRepo.soft_delete` → "🗑️ Deleted." + обновлённый Today's Stats

**Зависимости:** Шаг 18

**Критерий готовности:**
- Edit обновляет существующую запись (тот же row ID)
- Delete ставит is_deleted=True, stats пересчитываются
- FSM корректно отслеживает состояние "editing"

---

### Шаг 20. Бот: stats, history, stubs

**Что делать:**
- `app/bot/handlers/stats.py`:
  - /stats + "📊 Stats" → inline keyboard: Today / Weekly / 4 Weeks
  - Callback Today → `today_stats` → формат из spec
  - Callback Weekly → `weekly_stats` с `last_7_days(today)` → per-day breakdown, нули для пустых дней
  - Callback 4 Weeks → `four_week_stats` с `last_28_days_weeks(today)` → weekly averages (/7)
- `app/bot/handlers/history.py`:
  - /history + "🕘 History" → `MealRepo.list_recent(limit=20)` → список с inline delete buttons
  - Callback delete → soft_delete + refresh list + Today's Stats
- `app/bot/handlers/stubs.py`:
  - /feedback → "Thanks! Feedback feature coming soon."
  - /subscription → "Subscription management coming soon."
- `app/bot/formatters.py` дополнить: format_weekly_stats, format_four_week_stats, format_history_list

**Зависимости:** Шаги 4, 8, 9, 16

**Критерий готовности:**
- Today stats → нули без данных
- Weekly → 7 дней с нулями
- 4 Weeks → 4 блока, средние (/7)
- History → до 20 записей с кнопкой удаления

---

### Шаг 21. Bot middleware (DB session + logging context)

**Что делать:**
- Создать `app/bot/middlewares.py`:
  - `DBSessionMiddleware` (outer middleware): инжектит async session в handler `data["session"]`, commit on success, rollback on error
  - `LoggingMiddleware`: извлекает tg_user_id, chat_id, message_id из update → в logging context (через contextvars)
- Зарегистрировать в `create_dispatcher()`

**Зависимости:** Шаги 3, 6, 16

**Критерий готовности:** Handlers получают session через data; log lines содержат tg_user_id, chat_id

---

### Шаг 22. FastAPI: webhook + health + startup

**Что делать:**
- Создать `app/web/main.py`:
  - `GET /health` → `{"status": "ok"}`
  - `POST /webhook/{secret}` → валидация secret == WEBHOOK_SECRET, feed update в aiogram dispatcher
  - Lifespan context manager:
    - startup: setup_logging, create bot + dispatcher, run alembic migrations (или verify DB), set webhook `{PUBLIC_URL}/webhook/{WEBHOOK_SECRET}`
    - shutdown: delete webhook, close bot session
- Обновить Makefile: `APP_MODULE = app.web.main:app`

**Зависимости:** Шаги 3, 6, 7, 16, 21

**Критерий готовности:**
- `curl /health` → `{"status":"ok"}`
- POST с неверным secret → 403/404
- При старте webhook регистрируется

---

### Шаг 23. Docker

**Что делать:**
- `Dockerfile`: python:3.12-slim, poetry install --no-dev --no-root, copy app/ + alembic/, CMD `uvicorn app.web.main:app --host 0.0.0.0 --port $PORT`
- `.dockerignore`: .venv, .git, __pycache__, .env, tests, .pytest_cache, .ruff_cache
- `docker-compose.yml`: postgres:16-alpine (volume, env) + app (build, depends_on, env_file, ports)

**Зависимости:** Шаг 22

**Критерий готовности:** `docker build` проходит; `docker-compose up` → postgres + app, /health доступен

---

### Шаг 24. Интеграционные тесты (БД)

**Что делать:**
- Обновить `tests/conftest.py`: фикстуры с aiosqlite (in-memory), auto create_all, test user
- Создать `tests/test_db_integration.py`:
  - Idempotency: дублирование (tg_chat_id, tg_message_id) → IntegrityError
  - Soft delete скрывает из list_recent и today_stats
  - Update меняет поля, тот же row ID
  - today_stats с mix of deleted + active

**Зависимости:** Шаги 6, 8, 9

**Критерий готовности:** `make test` — зелёные без внешнего Postgres

---

### Шаг 25. Документация + acceptance checklist

**Что делать:**
- Обновить `README.md`:
  - Описание проекта и его назначение
  - Стек технологий
  - Quickstart: install, configure .env, run migrations, start (polling + webhook)
  - Docker: build, docker-compose up, health check
  - Railway deployment: env vars, PORT, webhook auto-setup
  - Доступные команды бота (/start, /help, /add, /stats, /goals, /history, /feedback, /subscription)
  - Тестирование: `make test`, описание тестовых слоёв (unit, integration, contract)
  - Структура проекта: дерево директорий с кратким описанием каждого модуля
- Обновить `AGENTS.md`:
  - Актуализировать project layout (app/bot, app/web, app/core, app/db, app/services, app/reports)
  - Обновить common commands (alembic migrate, make dev, make test)
  - Добавить описание key modules и их ответственностей
- Убедиться что **docstrings** есть:
  - Каждый модуль (`__init__.py` или верхний уровень файла) — краткое описание
  - Каждый публичный класс и метод — что делает, какие параметры, что возвращает
  - Сложная бизнес-логика — inline-комментарии (precheck rules, report aggregation, timezone handling)
- Проверить `.env.example` — полнота и комментарии к каждой переменной
- `make fmt && make lint && make test` — всё чисто
- Ручная проверка по acceptance checklist (spec 15):
  - [ ] New user → set goal + timezone
  - [ ] Text/photo → meal analysis (unless precheck rejects)
  - [ ] ChatAction typing during OpenAI
  - [ ] Save/edit/soft-delete работают
  - [ ] After save → saved summary + Today's Stats
  - [ ] Stats: Today/Weekly/4 Weeks — нули, exclude deleted
  - [ ] Non-food rejected, unrecognized → fixed phrase
  - [ ] Rate limit + concurrency guard
  - [ ] raw_ai_response stored
  - [ ] Pydantic Settings validate env
  - [ ] Structured logging
  - [ ] Webhook works
  - [ ] Tests pass

**Зависимости:** все предыдущие шаги

**Критерий готовности:** Все тесты зелёные, README/AGENTS.md актуальны, docstrings на месте, checklist выполнен

---

## Правила документирования (применяются на каждом шаге)

На **каждом** шаге, а не только в финале:
- Каждый новый файл начинается с module-level docstring (1-2 предложения: что делает модуль)
- Каждый публичный класс — docstring с описанием назначения
- Каждый публичный метод/функция — docstring (что делает, параметры, возвращаемое значение)
- Сложная логика — inline comments на русском или английском
- Это часть критерия готовности каждого шага (не отдельный шаг)

---

## Граф зависимостей

```
Шаг 1 (deps + skeleton)
├── Шаг 2 (config) ──┬── Шаг 3 (logging)
│                     ├── Шаг 6 (models) ──┬── Шаг 7 (alembic)
│                     │                    ├── Шаг 8 (repos)
│                     │                    ├── Шаг 9 (reports) ── Шаг 10 (report tests)
│                     │                    └── Шаг 24 (integration tests)
│                     ├── Шаг 11 (precheck) ── Шаг 12 (precheck tests)
│                     ├── Шаг 13 (rate limit)
│                     └── Шаг 14 (nutrition AI) ── Шаг 15 (AI tests)
│
├── Шаг 4 (time utils) ── Шаг 5 (time tests)
│
├── Шаг 16 (bot setup) ←── Шаги 2, 6, 8
│   ├── Шаг 17 (goals/tz)
│   ├── Шаг 18 (meal flow) ←── Шаги 4, 9, 11, 13, 14
│   │   └── Шаг 19 (edit/delete)
│   ├── Шаг 20 (stats/history) ←── Шаги 4, 9
│   └── Шаг 21 (middlewares) ←── Шаг 3
│
├── Шаг 22 (FastAPI) ←── Шаги 3, 7, 16, 21
│   └── Шаг 23 (Docker)
│
└── Шаг 25 (final) ←── все
```

## Параллельные ветки работы

Можно делать параллельно (разные ветки, раздельные PR):
- **Ветка A:** Шаги 4-5 (time utils + tests)
- **Ветка B:** Шаги 11-12 (precheck + tests)
- **Ветка C:** Шаги 13 (rate limit)
- **Ветка D:** Шаги 14-15 (nutrition AI + tests)

Все четыре сходятся в Шаге 18 (meal flow).

---

## Принятые решения по неоднозначностям

1. **Draft storage:** in-memory `dict[tg_user_id, DraftData]`. Draft теряется при рестарте — приемлемо, пользователь отправит заново.

2. **Timezone city list:** ~15-20 популярных IANA зон (Moscow, Almaty, Prague, London, New York, Tokyo, Dubai, Bangkok и т.д.) + UTC offsets от UTC-12 до UTC+14.

3. **Photo size variant:** берём `message.photo[-1]` (наибольший, обычно ≤1280px), проверяем `PhotoSize.file_size` до скачивания. MAX_PHOTO_BYTES по умолчанию 5MB.

4. **Duplicate photo** (spec 5.8): проверка `file_unique_id` за последние N минут → **reuse result** (показать как новый draft — пользователь мог съесть две порции одного блюда). Не блокировать, не отвечать "already analyzed".

5. **4-week grouping:** берём 28 дней от today, группируем в Mon-Sun недели. Неполные недели на краях — нули, делим на 7.

6. **Edit flow FSM:** aiogram `StatesGroup` для tracking "editing meal_id=X".

---

## Действия от пользователя (вне кода)

Перед ручным тестированием (после шага 22):
1. Создать бота через @BotFather в Telegram → получить `BOT_TOKEN`
2. Создать `.env` в корне проекта с реальными секретами (по шаблону `.env.example`)
3. Запустить PostgreSQL (локально или через `docker-compose up db`)

Эти действия НЕ нужны для шагов 1-24 — всё проверяется через `make test`.

---

## Верификация (end-to-end)

1. `make fmt && make lint && make test` — всё чисто
2. `docker-compose up` → postgres + app стартуют
3. `curl http://localhost:8000/health` → `{"status":"ok"}`
4. В Telegram: /start → main keyboard, /help → help text с кнопкой Change Time Zone
5. Отправить "chicken breast 200g" → draft → Save → saved message + Today's Stats
6. Отправить фото еды → draft → Save
7. /stats → Today/Weekly/4 Weeks
8. /history → список с delete
9. Edit + Delete flows
10. "вода" → reject; "!!!" → reject; 7 запросов за минуту → throttle
