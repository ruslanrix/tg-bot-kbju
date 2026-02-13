# Деплой

Инструкция по развёртыванию Telegram KBJU бота. Поддерживаются два режима работы и несколько вариантов деплоя.

---

## Содержание

- [Режимы работы](#режимы-работы)
- [Docker](#docker)
- [Railway.app](#railwayapp)
- [Миграции базы данных](#миграции-базы-данных)
- [Health Check](#health-check)
- [Запланированные задачи](#запланированные-задачи)
- [Связанные документы](#связанные-документы)

---

## Режимы работы

Приложение поддерживает два режима, определяемых переменной окружения `PUBLIC_URL`:

### Polling (локальная разработка)

- `PUBLIC_URL` **не задан** (пустая строка)
- aiogram запускает long polling в фоновом asyncio task
- Не требует публичного IP, ngrok или туннеля
- Запуск: `make dev`

### Webhook (продакшн)

- `PUBLIC_URL` **задан** (например, `https://myapp.up.railway.app`)
- FastAPI принимает POST-запросы на `/webhook/{WEBHOOK_SECRET}`
- Telegram отправляет обновления на указанный URL
- Требует валидный HTTPS-сертификат (обеспечивается хостингом)
- Требует `WEBHOOK_SECRET` (минимум 8 символов)

---

## Docker

### Dockerfile

Приложение использует многослойную сборку на основе `python:3.12-slim`:

```dockerfile
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Установка Poetry
RUN pip install "poetry>=2.2,<3.0"

# Копирование файлов зависимостей для кэширования слоёв
COPY pyproject.toml poetry.lock ./

# Установка только production-зависимостей
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main

# Копирование кода приложения
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Порт по умолчанию (Railway задаёт PORT через env)
ENV PORT=8000
EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn app.web.main:app --host 0.0.0.0 --port ${PORT}"]
```

### docker-compose.yml

Файл `docker-compose.yml` поднимает PostgreSQL и приложение:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: bot
      POSTGRES_PASSWORD: bot
      POSTGRES_DB: kbju
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bot -d kbju"]
      interval: 2s
      timeout: 5s
      retries: 10

  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://bot:bot@db:5432/kbju
    ports:
      - "${PORT:-8000}:${PORT:-8000}"

volumes:
  pgdata:
```

Ключевые моменты:
- Сервис `db` использует `postgres:16-alpine` с healthcheck через `pg_isready`
- Сервис `app` ждёт готовности БД (`service_healthy`) перед запуском
- `DATABASE_URL` переопределяется в environment для Docker-сети (host `db` вместо `localhost`)
- Данные PostgreSQL сохраняются в Docker volume `pgdata`

### Запуск через Docker Compose

```bash
# Создать .env файл с обязательными переменными
cp .env.example .env
# Заполнить BOT_TOKEN, OPENAI_API_KEY и другие значения

# Собрать и запустить
docker compose up --build

# Запуск в фоне
docker compose up --build -d

# Просмотр логов
docker compose logs -f app
```

Миграции БД выполняются автоматически при старте приложения.

---

## Railway.app

### Создание проекта

1. Создайте новый проект на [railway.app](https://railway.app)
2. Добавьте **PostgreSQL** плагин в проект
3. Подключите GitHub-репозиторий к проекту

### Переменные окружения

Настройте следующие переменные в сервисе приложения:

| Переменная | Значение | Описание |
|------------|----------|----------|
| `BOT_TOKEN` | `123456:ABC...` | Токен бота от @BotFather |
| `OPENAI_API_KEY` | `sk-...` | Ключ API OpenAI |
| `DATABASE_URL` | формула (см. ниже) | Строка подключения к БД |
| `PUBLIC_URL` | `https://xxx.up.railway.app` | Публичный URL для webhook |
| `WEBHOOK_SECRET` | случайная строка (8+ символов) | Секрет для webhook URL |
| `TASKS_SECRET` | случайная строка (8+ символов) | Секрет для /tasks/* эндпоинтов |
| `ADMIN_IDS` | `123456789,987654321` | Telegram ID администраторов |

**Формула для DATABASE_URL** (используется для ссылки на PostgreSQL-плагин Railway):

```
postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
```

### Конфигурация Railway

Файл `railway.toml` в корне проекта:

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

### Настройка домена

1. Перейдите в **Settings** вашего сервиса на Railway
2. Раздел **Networking** → **Generate Domain**
3. Скопируйте сгенерированный URL (формат: `https://xxx.up.railway.app`)
4. Установите его как `PUBLIC_URL` в переменных окружения

### Автодеплой

Railway автоматически деплоит при push в ветку `main`. Каждый push запускает:
1. Сборку Docker-образа
2. Запуск нового контейнера
3. Health check
4. Переключение трафика

### Проверка деплоя

```bash
curl https://xxx.up.railway.app/health
# Ожидаемый ответ: {"status":"ok"}
```

---

## Миграции базы данных

### Автоматический запуск

Миграции выполняются автоматически при каждом запуске приложения через функцию `_run_migrations()` в `app/web/main.py`. Функция запускает `alembic upgrade head` в subprocess.

### Ручной запуск

```bash
# Через Poetry
poetry run alembic upgrade head

# Через Python
python -m alembic upgrade head
```

### Создание новой миграции

```bash
poetry run alembic revision --autogenerate -m "описание изменения"
```

Файлы миграций хранятся в директории `alembic/`.

---

## Health Check

Эндпоинт: `GET /health`

Ответ:

```json
{"status": "ok"}
```

- Используется Railway для проверки работоспособности (таймаут 30 сек)
- Можно использовать для внешнего мониторинга (uptime services)
- Доступен без авторизации

---

## Запланированные задачи

Приложение предоставляет два HTTP-эндпоинта для периодических задач, защищённых заголовком `X-Tasks-Secret`:

### POST /tasks/remind

Отправляет напоминания неактивным пользователям.

```bash
curl -X POST https://xxx.up.railway.app/tasks/remind \
  -H "X-Tasks-Secret: your-tasks-secret"
```

Рекомендуемый интервал: каждые 30-60 минут через cron-job.org или аналог.

### POST /tasks/purge

Физически удаляет записи, помеченные как удалённые более `PURGE_DELETED_AFTER_DAYS` дней назад (по умолчанию 30).

```bash
curl -X POST https://xxx.up.railway.app/tasks/purge \
  -H "X-Tasks-Secret: your-tasks-secret"
```

Рекомендуемый интервал: раз в сутки.

### Настройка через cron-job.org

1. Зарегистрируйтесь на [cron-job.org](https://cron-job.org)
2. Создайте задачу для каждого эндпоинта
3. Метод: POST
4. Заголовок: `X-Tasks-Secret: <значение TASKS_SECRET>`
5. Расписание: по рекомендациям выше

---

## Связанные документы

- [Конфигурация](configuration.md) — описание всех переменных окружения
- [База данных](database.md) — модели данных и миграции
- [Разработка](development.md) — локальная разработка и тестирование
