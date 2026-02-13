# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.3] - 2026-02-13

### Fixed
- **4-week stats:** always exactly 4 calendar weeks (Mon–Sun), replacing
  the old helper that could produce 4–5 blocks depending on weekday.
- **Integer rounding:** `round()` instead of `int()` in weekly and 4-week
  formatters — no more truncation (e.g. 65.7 → 66, not 65).

### Changed
- **Weekly stats template:** locale-aware compact format
  `Mon 17.06: 1850 kcal | P/C/F 120/200/65` (EN) /
  `Пн 17.06: 1850 ккал | Б/У/Ж 120/200/65` (RU).
- **4-week stats template:** 2-line blocks per week
  (`Week 1 (DD.MM-DD.MM)` + `1850 kcal | P/C/F …`).
- **Date format:** `DD.MM` in weekly and 4-week stats (both locales),
  no more English-only `strftime` weekdays.
- **Bold headers:** stats messages use `<b>` HTML headers via opt-in
  `bold_header_html=True`; `parse_mode="HTML"` in all stats callbacks.

## [1.1.2] - 2026-02-13

### Fixed
- Removed standalone "👇" emoji messages sent after goals, stats, language,
  and delete callbacks.
- **Ingredient formatting:** each ingredient line now shows only grams and
  kcal (e.g. "Chicken (120g, 165kcal)"); no more ml, cups, or extra
  descriptors. Localized units: `g/kcal` (EN), `г/ккал` (RU).
- **Removed "Totals/Итого" block** from meal output; caffeine repositioned
  to appear after calories and before macros.

### Added
- **Edit flow redesign:** tapping "Edit" now sends a new prompt message
  asking what looks wrong, with "✅ It looks OK" and "🛑 Delete it" buttons.
  User feedback (any text) triggers re-analysis with original meal context.
  5-minute timeout, per-user session control, photo rejection during edit.

## [1.1.0] - 2026-02-12

### Added
- **i18n support (EN/RU):** `/language` command to switch UI language;
  main user-facing flows (meal, stats, goals, history, help, timezone,
  onboarding, precheck) are localized via `t(key, lang)` helper.
  Admin and `/version` commands remain English-only.
- **OpenAI language control:** AI responses (meal names, ingredients, user
  messages) follow the user's language preference.
- **Edit window:** meals older than 48 h (configurable) cannot be edited.
- **Delete window:** meals older than 48 h (configurable) cannot be deleted.
- **Processing UX:** "Combobulating..." / "Analysing again..." messages shown
  during OpenAI calls, edited in-place with the result.
- **Per-ingredient weights/volumes:** `weight_g` and `volume_ml` on each
  ingredient in `likely_ingredients`.
- **Sanity checks:** reject absurd nutrition values before saving.
- **Auto-save:** meals are saved immediately after analysis (no draft step).
- **Reply keyboard:** persistent main keyboard with Stats, Goals, Help,
  History, and Add Meal buttons.
- **Timezone onboarding gate:** new users must set timezone before logging meals.
- **Activity tracking middleware:** records `last_activity_at` on every update.
- **Scheduled purge:** `/tasks/purge` endpoint permanently removes
  soft-deleted records older than the configured retention period.
- **Reminder system:** `/tasks/remind` endpoint nudges inactive users.
- **Admin commands:** `/admin_ping`, `/admin_stats`, `/admin_limits` for
  bot operators.
- **`/version` command:** returns current SemVer from `pyproject.toml`.
- **`/history` command:** last 20 meals with inline delete buttons.
- **Stats periods:** today, weekly (7 days), and 4-week views.
- **Rate limiting and concurrency guard** for OpenAI calls.

### Changed
- Version bumped from `0.1.0` to `1.1.0`.
- Precheck reject messages now return i18n keys instead of hardcoded strings.
- `SYSTEM_PROMPT` is now built dynamically with language instruction (rule 13).

### Fixed
- `date.today()` replaced with `datetime.now(timezone.utc).date()` in admin
  stats to avoid local-timezone drift.
- Admin commands added to timezone gate bypass list.

## [0.1.0] - 2025-12-01

### Added
- Initial release: text and photo meal logging via OpenAI, `/start`, `/help`,
  `/goals`, `/timezone`, `/stats`, `/feedback` (stub), `/subscription` (stub).
- FastAPI webhook receiver with health endpoint.
- SQLAlchemy async models, Alembic migrations.
- Docker and docker-compose setup.
- Railway deployment support.
