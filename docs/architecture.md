# Архитектура

Техническая документация по архитектуре Telegram KBJU бота для разработчиков.

---

## Содержание

- [Высокоуровневая схема](#высокоуровневая-схема)
- [Технологический стек](#технологический-стек)
- [Структура модулей](#структура-модулей)
- [Жизненный цикл приложения](#жизненный-цикл-приложения)
- [Мидлвари](#мидлвари)
- [Роутеры](#роутеры)
- [Потоки данных](#потоки-данных)
- [Архитектурные паттерны](#архитектурные-паттерны)
- [Логирование](#логирование)

---

## Высокоуровневая схема

```
User
  │
  ▼
Telegram API
  │
  ▼
FastAPI (webhook POST /webhook/{secret}  или  aiogram polling)
  │
  ▼
aiogram Dispatcher
  │
  ▼
Outer Middlewares (DB Session → Logging → Activity → Timezone Gate)
  │
  ▼
Router (start, admin, version, language, goals, timezone, stats, history, stubs, meal)
  │
  ▼
Handler
  │
  ├──► NutritionAIService (OpenAI API)
  ├──► Precheck (фильтры до API)
  ├──► RateLimiter / ConcurrencyGuard
  └──► DB (SQLAlchemy async → PostgreSQL)

Внешние сервисы:
  • OpenAI API (gpt-4o-mini) — анализ текста и фото
  • cron-job.org — вызов /tasks/remind и /tasks/purge по расписанию
```

---

## Технологический стек

| Компонент | Технология | Версия |
|-----------|------------|--------|
| Язык | Python | 3.12 |
| Telegram фреймворк | aiogram | 3.6.0 |
| HTTP-сервер | FastAPI + uvicorn | FastAPI >=0.128, uvicorn >=0.40 |
| ORM | SQLAlchemy 2.0 async | >=2.0 |
| Драйвер БД | asyncpg | >=0.29 |
| Миграции | Alembic | >=1.13 |
| AI | OpenAI API (gpt-4o-mini) | openai 1.40.0 |
| Конфигурация | pydantic-settings v2 | >=2.4 |
| Валидация | Pydantic v2 | (через pydantic-settings) |
| HTTP-клиент | httpx | >=0.27 |
| Управление зависимостями | Poetry | 2.x |
| Линтер/форматтер | ruff | >=0.9 |

---

## Структура модулей

```
app/
├── __init__.py
├── core/                       # Ядро приложения
│   ├── config.py               # Settings (pydantic-settings), get_settings()
│   ├── logging.py              # JSONFormatter, setup_logging()
│   ├── time.py                 # Утилиты часовых поясов, границы дней, week_bounds
│   └── version.py              # get_version() — читает из pyproject.toml
│
├── db/                         # Слой данных
│   ├── models.py               # User, MealEntry (SQLAlchemy 2.0 declarative)
│   ├── repos.py                # UserRepo, MealRepo — CRUD операции
│   └── session.py              # Фабрика engine (create_async_engine)
│
├── services/                   # Бизнес-логика
│   ├── nutrition_ai.py         # NutritionAIService — OpenAI structured output + vision
│   ├── precheck.py             # Пре-API фильтры (вода, лекарства, пустой ввод)
│   └── rate_limit.py           # RateLimiter (sliding window) + ConcurrencyGuard (semaphore)
│
├── reports/                    # Отчёты
│   └── stats.py                # today_stats, weekly_stats, four_week_stats — агрегация
│
├── i18n/                       # Интернационализация
│   ├── __init__.py             # t(key, lang) — хелпер перевода
│   └── locales/
│       ├── en.py               # STRINGS: dict[str, str] — английские строки
│       └── ru.py               # STRINGS: dict[str, str] — русские строки
│
├── bot/                        # Telegram-бот
│   ├── factory.py              # create_bot(), create_dispatcher() — сборка компонентов
│   ├── middlewares.py          # DBSession, Logging, Activity, TimezoneGate
│   ├── keyboards.py            # Reply и inline клавиатуры
│   ├── formatters.py           # Форматирование ответов (meal, stats, history)
│   └── handlers/               # Обработчики
│       ├── start.py            # /start, /help
│       ├── admin.py            # /admin_ping, /admin_stats, /admin_limits
│       ├── version.py          # /version
│       ├── language.py         # /language, lang:* callbacks
│       ├── goals.py            # /goals, goal:* callbacks
│       ├── timezone.py         # tz_city:*, tz_offset:*, tz_*_menu callbacks
│       ├── stats.py            # /stats, stats:* callbacks, кнопка 📊 Stats
│       ├── history.py          # /history, hist_delete:* callbacks
│       ├── stubs.py            # /feedback, /subscription — заглушки
│       └── meal.py             # Catch-all: текст/фото → анализ → сохранение, edit/delete flow
│
└── web/                        # HTTP-слой
    └── main.py                 # FastAPI app, lifespan, /health, /webhook/{secret}, /tasks/*
```

---

## Жизненный цикл приложения

Приложение управляется через FastAPI lifespan context manager (`app/web/main.py`):

### Запуск (startup)

1. **setup_logging** — настройка JSON structured logging на stdout
2. **_run_migrations** — запуск `alembic upgrade head` через subprocess (отдельный процесс, т.к. alembic использует `asyncio.run()` внутри)
3. **create_async_engine** — создание SQLAlchemy async engine для task-эндпоинтов
4. **create_bot** — создание экземпляра `aiogram.Bot` с BOT_TOKEN
5. **create_dispatcher** — создание Dispatcher, регистрация мидлварей, роутеров, сервисов
6. **Режим работы**:
   - Если `PUBLIC_URL` задан → **webhook**: вызов `bot.set_webhook(url)`
   - Если `PUBLIC_URL` пуст → **polling**: запуск `dp.start_polling()` в asyncio task

### Завершение (shutdown)

1. Остановка polling (если был запущен)
2. Dispose task engine
3. Удаление webhook (если был установлен)
4. Закрытие bot session

---

## Мидлвари

Все мидлвари зарегистрированы как **outer middlewares** на уровне `dp.update`. Порядок регистрации определяет порядок выполнения:

### 1. DBSessionMiddleware

- Инжектирует `AsyncSession` в `data["session"]`
- Оборачивает handler в `try/except`: commit при успехе, rollback при ошибке
- Все последующие мидлвари и хендлеры имеют доступ к сессии

### 2. LoggingMiddleware

- Извлекает из `Update` идентификаторы: `tg_user_id`, `chat_id`, `message_id`
- Устанавливает значения в `ContextVar` (context variables)
- JSONFormatter автоматически подхватывает эти значения в логах
- Сбрасывает context vars в блоке `finally`

### 3. ActivityMiddleware

- Выполняется **после** handler (downstream-first)
- Обновляет `User.last_activity_at = now()` через `UserRepo.touch_activity()`
- Использует `SAVEPOINT` (`session.begin_nested()`) для изоляции — ошибка touch не откатывает основную транзакцию
- Ошибки логируются, но не пробрасываются (fire-and-forget)

### 4. TimezoneGateMiddleware

- Блокирует любой пользовательский ввод до установки часового пояса
- **Пропускает без проверки**:
  - Команды: `/start`, `/help`, `/language`, `/version`, `/admin_ping`, `/admin_stats`, `/admin_limits`
  - Callback-данные с префиксами: `tz_city:`, `tz_offset:`, `tz_city_menu`, `tz_offset_menu`, `lang:`
- **При отсутствии часового пояса**: отправляет онбординг-сообщение с клавиатурой выбора города/смещения
- Для callback-запросов: отвечает alert-уведомлением

---

## Роутеры

Роутеры регистрируются в `factory.py`. Порядок критически важен, т.к. meal router содержит catch-all обработчики для текста и фото:

1. `start.router` — `/start`, `/help`
2. `admin.router` — `/admin_ping`, `/admin_stats`, `/admin_limits`
3. `version.router` — `/version`
4. `language.router` — `/language`, `lang:*` callbacks
5. `goals.router` — `/goals`, `goal:*` callbacks
6. `timezone.router` — `tz_city:*`, `tz_offset:*`, menu callbacks
7. `stats.router` — `/stats`, `stats:*` callbacks, кнопка `📊 Stats`
8. `history.router` — `/history`, `hist_delete:*` callbacks
9. `stubs.router` — `/feedback`, `/subscription`
10. **`meal.router`** (последним) — catch-all для текста/фото, `saved_edit:*`, `saved_delete:*`, `draft_*:*`, `edit_ok:*`, `edit_delete:*`, FSM-обработчик `EditMealStates.waiting_for_text`

---

## Потоки данных

### Логирование приёма пищи

```
Message (текст или фото)
  │
  ├─ precheck: check_message_type → check_text / check_photo_size
  │  (отсекает воду, лекарства, пустой ввод, крупные фото)
  │
  ├─ RateLimiter.check(tg_user_id)
  │  (sliding window, 6 запросов/мин)
  │
  ├─ ConcurrencyGuard(tg_user_id)
  │  (максимум 1 одновременный анализ)
  │
  ├─ Typing heartbeat (индикатор "бот печатает...")
  │
  ├─ NutritionAIService.analyze_text() / analyze_photo()
  │  (OpenAI gpt-4o-mini → NutritionAnalysis)
  │
  ├─ sanity_check(analysis)
  │  (проверка на реалистичность значений)
  │
  ├─ MealRepo.exists_by_message() — idempotency check
  │
  ├─ MealRepo.create() — сохранение в БД
  │
  └─ Ответ: format_meal_saved() + saved_actions_keyboard (Edit / Delete)
```

### Редактирование записи

```
Callback "saved_edit:{meal_id}"
  │
  ├─ Проверка окна редактирования (48 часов)
  │
  ├─ FSM: переход в EditMealStates.waiting_for_text
  │
  ├─ Отправка: "Что не так?" + edit_feedback_keyboard (OK / Delete)
  │
  ├─ Таймаут: 5 минут (auto-cancel FSM)
  │
  ▼
Пользователь отправляет текст обратной связи
  │
  ├─ Повторный анализ: AI получает оригинал + обратную связь
  │
  ├─ sanity_check(analysis)
  │
  ├─ MealRepo.update() — обновление записи в БД
  │
  └─ Финализация: обновлённая карточка + новая клавиатура
```

### Удаление записи

```
Callback "saved_delete:{meal_id}"
  │
  ├─ Проверка окна удаления (48 часов)
  │
  ├─ MealRepo.soft_delete()
  │  (is_deleted=True, deleted_at=now())
  │
  └─ Ответ: подтверждение + обновлённая статистика за день
```

---

## Архитектурные паттерны

### Soft Delete (мягкое удаление)

- Записи не удаляются физически, а помечаются: `is_deleted=True`, `deleted_at=now()`
- Все запросы MealRepo фильтруют `is_deleted=False` (кроме `exists_by_message`)
- Физическое удаление: эндпоинт `POST /tasks/purge` удаляет записи старше `PURGE_DELETED_AFTER_DAYS` (30 дней по умолчанию)

### Idempotency (идемпотентность)

- Unique constraint: `(tg_chat_id, tg_message_id)` на таблице `meal_entries`
- Перед сохранением: `MealRepo.exists_by_message()` проверяет наличие записи (включая удалённые)
- Предотвращает дублирование при повторной обработке одного сообщения

### Rate Limiting (ограничение частоты)

- **Sliding window**: `RateLimiter` хранит timestamps последних запросов per user, окно 60 секунд, лимит по умолчанию 6 запросов
- **Concurrency guard**: `ConcurrencyGuard` — per-user semaphore, максимум 1 одновременный вызов OpenAI
- Оба механизма **in-memory only** — работают только для single-instance деплоя

### Sanity Checks (проверка на реалистичность)

Предельные значения для одного приёма пищи:

| Параметр | Максимум |
|----------|----------|
| `MAX_CALORIES_KCAL` | 5 000 |
| `MAX_PROTEIN_G` | 500.0 |
| `MAX_CARBS_G` | 800.0 |
| `MAX_FAT_G` | 400.0 |
| `MAX_WEIGHT_G` | 10 000 |
| `MAX_VOLUME_ML` | 5 000 |
| `MAX_CAFFEINE_MG` | 2 000 |

Проверяются как общие значения, так и значения по каждому ингредиенту.

### Timezone (часовые пояса)

- `local_date` вычисляется один раз при сохранении записи на основе текущего часового пояса пользователя
- При смене часового пояса существующие записи **не пересчитываются** (no re-bucketing)
- Два режима: `city` (IANA name, например `Europe/Moscow`) и `offset` (фиксированное смещение в минутах)

---

## Логирование

- **Формат**: JSON structured (один JSON-объект на строку)
- **Вывод**: stdout (через `logging.StreamHandler`)
- **Formatter**: `JSONFormatter` (`app/core/logging.py`)
- **Context vars**: `tg_user_id`, `chat_id`, `message_id` — устанавливаются `LoggingMiddleware` и автоматически включаются в каждую JSON-строку
- **Extra fields**: `event`, `latency_ms`, `model`, `request_id`, `trace_id` — передаются явно через `extra={}` в вызовах `logger.*`

Пример JSON-строки лога:

```json
{
  "timestamp": "2024-06-17T12:34:56.789000+00:00",
  "level": "INFO",
  "logger": "app.bot.handlers.meal",
  "message": "Meal saved",
  "tg_user_id": 123456789,
  "chat_id": 123456789,
  "event": "meal_saved",
  "latency_ms": 1250,
  "model": "gpt-4o-mini"
}
```

Шумные логгеры (`httpx`, `httpcore`) приглушены до уровня WARNING; `aiogram` — до INFO.
