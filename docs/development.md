# Разработка

Руководство по локальной разработке, тестированию и рабочим процессам.

---

## Содержание

- [Требования](#требования)
- [Установка](#установка)
- [Запуск](#запуск)
- [Тестирование](#тестирование)
- [Линтинг и форматирование](#линтинг-и-форматирование)
- [Makefile](#makefile)
- [Git-воркфлоу](#git-воркфлоу)
- [Версионирование](#версионирование)
- [AGENTS.md](#agentsmd)

---

## Требования

| Компонент | Версия | Примечание |
|-----------|--------|------------|
| Python | 3.12+ | рекомендуется установка через pyenv |
| Poetry | 2.x | менеджер зависимостей |
| PostgreSQL | 16 | для продакшн-окружения; для локальной разработки можно использовать docker-compose |

Для запуска тестов PostgreSQL не требуется — тесты используют SQLite in-memory.

---

## Установка

```bash
# Клонировать репозиторий
git clone <repo-url>
cd tg-bot-kbju

# Установить зависимости (включая dev)
poetry install

# Скопировать пример конфигурации
cp .env.example .env
```

Заполните `.env` обязательными значениями:

- `BOT_TOKEN` — токен Telegram бота от @BotFather
- `OPENAI_API_KEY` — ключ API OpenAI
- `DATABASE_URL` — строка подключения к PostgreSQL

Полное описание переменных окружения: [configuration.md](configuration.md)

---

## Запуск

### Режим polling (локальная разработка)

```bash
make dev
```

Запускает uvicorn с `--reload` (автоперезагрузка при изменении файлов). Приложение работает в режиме polling (переменная `PUBLIC_URL` должна быть пустой).

### Docker Compose

```bash
docker compose up --build
```

Поднимает PostgreSQL 16 и приложение. Миграции выполняются автоматически при старте. `DATABASE_URL` переопределяется для Docker-сети.

---

## Тестирование

### Запуск тестов

```bash
make test
```

Эквивалентно `poetry run pytest -q`.

### Характеристики тестовой среды

- **Количество тестов**: 606
- **БД**: SQLite in-memory (через `aiosqlite`)
- **Асинхронность**: `asyncio_mode = "auto"` (pytest-asyncio автоматически оборачивает async-тесты)
- **Совместимость**: `conftest.py` содержит патч, заменяющий тип `JSONB` на `JSON` для SQLite

### Структура тестов

Тесты организованы по файлам `tests/test_*.py`, каждый покрывает определённую функциональность:

| Файл | Описание |
|------|----------|
| `test_smoke.py` | Базовые smoke-тесты |
| `test_config.py` | Валидация Settings |
| `test_nutrition_ai.py` | NutritionAIService, sanity checks |
| `test_precheck.py` | Пре-API фильтры |
| `test_rate_limit.py` | RateLimiter, ConcurrencyGuard |
| `test_db_integration.py` | Интеграционные тесты БД |
| `test_reports.py` | Агрегация статистики |
| `test_formatters.py` | Форматирование ответов |
| `test_i18n.py` | Интернационализация |
| `test_goals_stats_handlers.py` | Обработчики /goals и /stats |
| `test_auto_save.py` | Автосохранение записей |
| `test_edit_feedback_flow.py` | Процесс редактирования |
| `test_edit_feedback_keyboard.py` | Клавиатура редактирования |
| `test_edit_window.py` | Окно редактирования (48ч) |
| `test_edit_timeout_lifecycle.py` | Таймаут FSM (5 мин) |
| `test_delete_window.py` | Окно удаления (48ч) |
| `test_processing_messages.py` | Сообщения при обработке |
| `test_timezone_gate.py` | Мидлварь TimezoneGate |
| `test_tz_confirmation.py` | Подтверждение часового пояса |
| `test_time.py` | Утилиты времени |
| `test_activity.py` | Отслеживание активности |
| `test_remind.py` | Напоминания |
| `test_purge.py` | Очистка удалённых записей |
| `test_admin.py` | Админ-команды |
| `test_language.py` | Смена языка |
| `test_version.py` | Команда /version |
| `test_user_columns.py` | Поля модели User |

---

## Линтинг и форматирование

Проект использует **ruff** для форматирования и линтинга. Максимальная длина строки: **100 символов**.

```bash
# Форматирование
make fmt

# Проверка линтинга
make lint
```

Рекомендуется запускать `make fmt` и `make lint` перед каждым коммитом.

---

## Makefile

Доступные цели:

| Команда | Действие |
|---------|----------|
| `make install` | Установка зависимостей: `poetry install` |
| `make dev` | Запуск uvicorn с `--reload` (polling, локальная разработка) |
| `make serve` | Запуск uvicorn без reload (webhook, продакшн-подобный) |
| `make test` | Запуск тестов: `pytest -q` |
| `make fmt` | Форматирование кода: `ruff format .` |
| `make lint` | Проверка кода: `ruff check .` |
| `make health` | Проверка здоровья: `curl http://127.0.0.1:8000/health` |
| `make clean` | Очистка кэшей: `.pytest_cache`, `.ruff_cache`, `__pycache__` |

Дополнительные переменные (можно переопределить):

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `APP_MODULE` | `app.web.main:app` | Путь к FastAPI-приложению |
| `PORT` | `8000` | Порт сервера |
| `HOST` | `127.0.0.1` | Хост сервера |

---

## Git-воркфлоу

### Именование веток

- `step-XX/описание` — этапы разработки по плану
- `feat-XX/описание` — новые функции
- `fix-XX/описание` — исправления ошибок

### Процесс

1. Создать ветку от `main`
2. Работать малыми коммитами
3. Перед коммитом:
   - `make fmt` — форматирование
   - `make lint` — проверка линтинга
   - `make test` — прогон тестов
4. Создать Pull Request в `main`
5. Авто-деплой при мерже в `main` (Railway)

---

## Версионирование

### Единый источник версии

Версия определена в одном месте — файл `pyproject.toml`, поле `version`:

```toml
[project]
version = "1.1.3"
```

Функция `app.core.version.get_version()` читает версию из `pyproject.toml` и кэширует результат. Версия отображается по команде `/version`.

### Процесс релиза

1. Обновить версию в `pyproject.toml`
2. Обновить `CHANGELOG.md`
3. Создать коммит: `git commit -m "Release vX.Y.Z"`
4. Создать тег: `git tag vX.Y.Z`
5. Отправить в remote: `git push origin main --tags`

---

## AGENTS.md

Файл `AGENTS.md` в корне проекта содержит правила и инструкции для AI-агентов, работающих с кодовой базой. Он определяет:
- Стиль кода и соглашения
- Правила работы с тестами
- Структуру и организацию модулей
- Рекомендации по коммитам

Подробнее: [../AGENTS.md](../AGENTS.md)
