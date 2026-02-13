# База данных

Документация по схеме базы данных, моделям, репозиториям и миграциям.

---

## Содержание

- [Обзор](#обзор)
- [Модель User](#модель-user)
- [Модель MealEntry](#модель-mealentry)
- [UserRepo](#userrepo)
- [MealRepo](#mealrepo)
- [Управление сессиями](#управление-сессиями)
- [Миграции Alembic](#миграции-alembic)
- [Агрегация и отчёты](#агрегация-и-отчёты)
- [Soft Delete](#soft-delete)

---

## Обзор

| Компонент | Технология |
|-----------|------------|
| СУБД (продакшн) | PostgreSQL 16 |
| СУБД (тесты) | SQLite (in-memory, через aiosqlite) |
| ORM | SQLAlchemy 2.0 (declarative, async) |
| Драйвер (продакшн) | asyncpg |
| Драйвер (тесты) | aiosqlite |
| Миграции | Alembic |

Строка подключения задаётся переменной окружения `DATABASE_URL`. Формат для PostgreSQL:

```
postgresql+asyncpg://user:password@host:5432/dbname
```

---

## Модель User

**Таблица**: `users`

**Файл**: `app/db/models.py`

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | `UUID` (PK) | Первичный ключ, генерируется через `uuid4()` |
| `tg_user_id` | `BigInteger` | Telegram user ID. Unique, indexed |
| `goal` | `String(32)`, nullable | Цель питания: `"maintenance"`, `"deficit"`, `"bulk"` или `NULL` |
| `tz_mode` | `String(16)`, nullable | Режим часового пояса: `"city"` или `"offset"` |
| `tz_name` | `String(64)`, nullable | IANA имя часового пояса (например, `Europe/Moscow`) |
| `tz_offset_minutes` | `Integer`, nullable | Смещение от UTC в минутах (например, `180` для UTC+3) |
| `language` | `String(2)`, default `"EN"` | Язык интерфейса: `"EN"` или `"RU"` |
| `last_activity_at` | `DateTime(tz)`, nullable | Время последней активности пользователя (UTC) |
| `last_reminder_at` | `DateTime(tz)`, nullable | Время последнего отправленного напоминания (UTC) |
| `created_at` | `DateTime(tz)` | Время создания записи (UTC), server_default `now()` |
| `updated_at` | `DateTime(tz)` | Время последнего обновления (UTC), автообновляется через `onupdate` |

**Связи**: `meals` — one-to-many к `MealEntry` (`back_populates="user"`, `lazy="selectin"`)

---

## Модель MealEntry

**Таблица**: `meal_entries`

**Файл**: `app/db/models.py`

### Поля

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | `UUID` (PK) | Первичный ключ, `uuid4()` |
| `user_id` | `UUID` (FK → `users.id`) | Владелец записи, indexed |
| `tg_chat_id` | `BigInteger` | Telegram chat ID |
| `tg_message_id` | `BigInteger` | Telegram message ID |
| `source` | `String(16)` | Тип источника: `"text"` или `"photo"` |
| `original_text` | `Text`, nullable | Оригинальный текст сообщения или подпись к фото |
| `photo_file_id` | `String(256)`, nullable | Telegram file ID фотографии |
| `consumed_at_utc` | `DateTime(tz)` | Время приёма пищи в UTC |
| `local_date` | `Date` | Локальная дата (вычислена при сохранении, не пересчитывается) |
| `tz_name_snapshot` | `String(64)`, nullable | Снимок IANA имени часового пояса на момент сохранения |
| `tz_offset_minutes_snapshot` | `Integer`, nullable | Снимок смещения UTC на момент сохранения |
| `meal_name` | `String(256)` | Название блюда (от AI) |
| `calories_kcal` | `Integer` | Калории (ккал) |
| `protein_g` | `Float` | Белки (г) |
| `carbs_g` | `Float` | Углеводы (г) |
| `fat_g` | `Float` | Жиры (г) |
| `weight_g` | `Integer`, nullable | Вес порции (г) |
| `volume_ml` | `Integer`, nullable | Объём (мл) |
| `caffeine_mg` | `Integer`, nullable | Кофеин (мг) |
| `likely_ingredients_json` | `JSONB`, nullable | Список ингредиентов (JSON) |
| `raw_ai_response` | `JSONB`, nullable | Полный ответ AI (JSON, для отладки) |
| `is_deleted` | `Boolean`, default `False` | Флаг мягкого удаления |
| `deleted_at` | `DateTime(tz)`, nullable | Время мягкого удаления |
| `created_at` | `DateTime(tz)` | Время создания, server_default `now()` |
| `updated_at` | `DateTime(tz)` | Время обновления, автообновление |

### Ограничения и индексы

- **Unique constraint**: `(tg_chat_id, tg_message_id)` — имя `uq_meal_chat_message`. Обеспечивает идемпотентность: одно сообщение Telegram порождает не более одной записи
- **Partial index**: `ix_meal_user_localdate_active` на `(user_id, local_date)` с условием `WHERE is_deleted = false`. Ускоряет запросы статистики по дате для активных записей

**Связи**: `user` — many-to-one к `User` (`back_populates="meals"`, `lazy="selectin"`)

---

## UserRepo

**Файл**: `app/db/repos.py`

Класс `UserRepo` предоставляет статические методы для работы с таблицей `users`:

### get_or_create(session, tg_user_id)

Возвращает существующего пользователя или создаёт нового. Используется при первом контакте с ботом и в мидлвари `TimezoneGateMiddleware`.

### update_goal(session, user_id, goal)

Устанавливает цель питания (`"maintenance"`, `"deficit"`, `"bulk"`). Использует `UPDATE ... RETURNING` для атомарного обновления.

### update_timezone(session, user_id, tz_mode, tz_name, tz_offset_minutes)

Обновляет настройки часового пояса. Принимает режим (`"city"` или `"offset"`), имя IANA и/или смещение в минутах.

### update_language(session, user_id, language)

Устанавливает язык интерфейса (`"EN"` или `"RU"`). Значение автоматически приводится к верхнему регистру.

### touch_activity(session, tg_user_id)

Обновляет `last_activity_at = now()` для пользователя. Вызывается из `ActivityMiddleware` после каждого взаимодействия. Если пользователь ещё не создан — операция игнорируется (no-op).

### claim_inactive_users(session, inactivity_cutoff, cooldown_cutoff)

Атомарно выбирает и помечает пользователей, подходящих для напоминания. Использует `UPDATE ... RETURNING` — конкурентные вызовы `/tasks/remind` не могут выбрать одних и тех же пользователей.

Критерии отбора:
- `tz_mode IS NOT NULL` — пользователь завершил онбординг
- `last_activity_at IS NOT NULL` и старше `inactivity_cutoff`
- `last_reminder_at IS NULL` или старше `cooldown_cutoff`

---

## MealRepo

**Файл**: `app/db/repos.py`

Класс `MealRepo` предоставляет статические методы для работы с таблицей `meal_entries`:

### create(session, **fields)

Создаёт новую запись о приёме пищи. Принимает любые атрибуты модели `MealEntry` через kwargs.

### get_by_id(session, meal_id, user_id)

Получает запись по первичному ключу. Возвращает только **неудалённые** записи. Проверяет принадлежность пользователю (`user_id`).

### update(session, meal_id, user_id, **fields)

Обновляет существующую запись (используется в процессе редактирования). Только неудалённые записи могут быть обновлены. Возвращает обновлённый `MealEntry` через `RETURNING`.

### soft_delete(session, meal_id, user_id)

Мягкое удаление: устанавливает `is_deleted=True` и `deleted_at=now()`. Возвращает `True`, если запись была обновлена; `False` — если не найдена или уже удалена.

### exists_by_message(session, tg_chat_id, tg_message_id)

Проверяет существование записи по идентификаторам сообщения Telegram. **Включает удалённые записи** — используется для проверки идемпотентности перед сохранением.

### list_recent(session, user_id, limit=20)

Возвращает последние неудалённые записи пользователя, отсортированные по `consumed_at_utc` (новые первыми). По умолчанию лимит 20 записей.

### hard_delete_deleted_before(session, cutoff)

Физически удаляет записи с `is_deleted=True` и `deleted_at < cutoff`. Используется эндпоинтом `/tasks/purge` для очистки старых удалённых данных.

---

## Управление сессиями

### Основные обработчики (bot handlers)

`DBSessionMiddleware` инжектирует `AsyncSession` в `data["session"]` для каждого входящего обновления Telegram. Мидлварь управляет жизненным циклом сессии:
- `commit()` при успешной обработке
- `rollback()` при исключении

### Task-эндпоинты (/tasks/*)

Эндпоинты `/tasks/purge` и `/tasks/remind` используют отдельный `_task_engine` и `_session_factory`, созданные в lifespan. Это обеспечивает независимость от сессий бота.

---

## Миграции Alembic

Файлы миграций хранятся в директории `alembic/`.

### Автоматический запуск

Миграции выполняются при каждом запуске приложения через `_run_migrations()` — subprocess-вызов `alembic upgrade head`.

### Ручные команды

```bash
# Применить все миграции
poetry run alembic upgrade head

# Создать новую миграцию (autogenerate из моделей)
poetry run alembic revision --autogenerate -m "описание изменения"

# Откатить последнюю миграцию
poetry run alembic downgrade -1

# Показать текущую ревизию
poetry run alembic current

# Показать историю миграций
poetry run alembic history
```

### Особенности тестов

В тестах используется SQLite (in-memory). Файл `conftest.py` содержит патч, заменяющий тип `JSONB` на `JSON` для совместимости с SQLite (SQLite не поддерживает JSONB).

---

## Агрегация и отчёты

**Файл**: `app/reports/stats.py`

Модуль содержит три функции агрегации для формирования статистики:

### today_stats(session, user_id, local_date) → DayStats

Суммирует калории и макронутриенты за указанный `local_date`. Возвращает нули при отсутствии данных. Используется для отображения статистики после сохранения записи и по запросу "Сегодня".

### weekly_stats(session, user_id, dates) → list[DayStats]

Возвращает суммы по каждому дню из списка дат (обычно последние 7 дней). Дни без записей получают нулевые значения. Результат упорядочен в том же порядке, что и входной список `dates`.

### four_week_stats(session, user_id, week_ranges) → list[WeekAvgStats]

Вычисляет средние дневные показатели для каждого Mon-Sun блока. Суммы за неделю делятся на 7 (включая дни без записей). Входной параметр `week_ranges` — список кортежей `(monday, sunday)`.

Все функции исключают записи с `is_deleted=True`.

---

## Soft Delete

Механизм мягкого удаления реализован на уровне модели `MealEntry`:

1. **Пометка**: `MealRepo.soft_delete()` устанавливает `is_deleted=True` и `deleted_at=now()`
2. **Фильтрация**: все запросы (кроме `exists_by_message`) фильтруют `is_deleted=False`
3. **Partial index**: `ix_meal_user_localdate_active` индексирует только активные записи
4. **Очистка**: эндпоинт `POST /tasks/purge` через `MealRepo.hard_delete_deleted_before()` физически удаляет записи старше `PURGE_DELETED_AFTER_DAYS` дней (по умолчанию 30)
5. **Идемпотентность**: `exists_by_message()` проверяет **все** записи (включая удалённые), чтобы предотвратить повторное сохранение из одного сообщения
