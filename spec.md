# spec.md — Meals.Chat-style Telegram Calorie Tracker Bot (UPDATED)

You are an expert senior Python engineer. Implement this specification 1:1. Do not invent extra features beyond this spec.

========================================================
0) SUMMARY
========================================================
Build a Telegram bot that logs meals from ANY text or photo, estimates nutrition (kcal + P/C/F) and likely ingredients using OpenAI, stores everything in PostgreSQL, and shows:
- Today's totals after every saved meal
- Reports: Today, last 7 days (incl today), last 4 weeks (last 28 days grouped Mon–Sun, weekly averages)

Target stack:
- Python 3.12.x + Poetry
- aiogram 3
- FastAPI (webhook)
- PostgreSQL
- SQLAlchemy 2 (async) + Alembic
- Railway deploy
- Docker support (Dockerfile + optional compose for local)

Key product rules:
- Goal is a label only: maintenance / deficit / bulk
- Timezone is mandatory for correct day boundaries, selectable via city list (IANA) and UTC offsets
- The bot accepts ANY text/photo as a meal logging attempt (in addition to commands and buttons)
- Edit/Delete flows must exist as per UX requirements
- OpenAI must return strict structured JSON; bot must validate it
- Pre-API filtering must be simple and non-aggressive (avoid false rejects)
- Add ChatAction “typing…” while OpenAI is processing
- Add rate limiting and per-user concurrency guard before calling OpenAI
- Add raw_ai_response persistence for observability
- Add Pydantic Settings for config validation
- Add structured logging (JSON logs)
- Implement soft delete (is_deleted) so deleted meals disappear from reports/history but stay in DB

========================================================
1) IN SCOPE (MVP GOALS)
========================================================
1.1 User can:
- Set goal label: maintenance / deficit / bulk
- Set timezone (city list + UTC offset)
- Add meals via:
  - pressing “✏️ Add Meal” and typing
  - sending any text at any time
  - sending a photo (with optional caption)
- View:
  - Today’s Stats
  - Weekly report (last 7 days incl today)
  - 4-week report (last 28 days grouped Mon–Sun, averages)
  - History list of recent meals
- Edit and Delete both draft (before saving) and saved meals

1.2 Bot must:
- Analyze meal from text and/or photo via OpenAI and produce:
  - meal_name
  - calories_kcal
  - macros: protein_g, carbs_g, fat_g
  - weight_g or volume_ml (estimate if missing; trust if user provides)
  - likely_ingredients list
- Always print Today’s Stats after each saved meal
- If unrecognized: reply EXACTLY:
  "I couldn't recognize the food. Please try sending it again."
- If input is non-food/no-calories/insufficient detail: do not save and reply with a friendly English message (see examples)

========================================================
2) OUT OF SCOPE / NON-GOALS
========================================================
- No payments/subscriptions implementation (commands can exist as stubs)
- No admin panel
- No calorie target calculations (goal is label only)
- No historical re-bucketing when timezone changes
- No storing raw image bytes in DB
- No heavy analytics pipeline (but keep deleted records for future analysis)

========================================================
3) UX REQUIREMENTS (MATCH SCREENSHOTS)
========================================================
3.1 Persistent reply keyboard (5 buttons):
- "📊 Stats"
- "🎯 Goals"
- "☁️ Help"
- "🕘 History"
- "✏️ Add Meal"

3.2 Commands must exist:
- /start
- /help
- /add
- /stats
- /goals
- /history
- /feedback  (stub OK)
- /subscription (stub OK)

3.3 /help output (English, close to this):
Hi. Every time you eat, send me a 📸 pic of your meal (or drink). I'll guess the macros, calories, caffeine and ingredients to help you keep track of your diet.
Tip: Pin this chat so it stays at the top for easy access.
Tip: You can write stuff like yesterday or two days ago when logging meals that you forgot to add before.
Commands
ℹ️ /help — What you're looking at now
✍️ /add — Manually write any meal or drink without a photo
📊 /stats — See your daily, weekly or monthly stats
🎯 /goals — Set your calorie and macro goals
🕘 /history — See your meal history and delete meals
🗣️ /feedback — Send feedback to my maker
🧾 /subscription — Manage your subscription
🌍 Remember to change your time zone if you moved countries.

Include inline button: "🕒 Change Time Zone"

3.4 Meal saved message template (after saving):
✅ Saved. You added: <MealName>

Calories
<NNN>kcal

Macros
• Protein: <Pg>
• Carbs: <Cg>
• Fat: <Fg>

Likely Ingredients
• <Ingredient 1> (<amount>, <kcal>kcal)
• <Ingredient 2> (<amount>, <kcal>kcal)

Then always show Today’s Stats block:
📊 Today's Stats
⚪ Calories: <total>kcal
⚪ Carbs: <total>g
⚪ Protein: <total>g
⚪ Fat: <total>g

3.5 Draft vs saved inline actions:
After analysis BEFORE saving (draft):
- "✅ Save"
- "✏️ Edit"
- "🛑 Delete"

After saving:
- "✏️ Edit"
- "🛑 Delete"

3.6 Deleting:
- Draft delete: discard draft -> reply "🗑️ Deleted."
- Saved delete: soft delete record (is_deleted=true) and show updated Today’s Stats

3.7 Editing:
- Edit triggers “send corrected text” flow
- After correction, re-run OpenAI (still required because ingredients must be generated) and show draft with Save/Edit/Delete
- Save updates the existing MealEntry record (do not create a new row) and shows Today’s Stats

3.8 ChatAction:
While OpenAI is processing (text or photo analysis), bot must display ChatAction "typing..." as a heartbeat (e.g., every ~4 seconds) until it replies.

========================================================
4) TIMEZONE & DAY BOUNDARIES
========================================================
- Day boundaries are 00:00–23:59 in the user's local time.
- Each meal is stored with:
  - consumed_at_utc (timestamptz)
  - local_date (date computed at save time using current user timezone)
  - tz snapshot used for that computation:
    - tz_name_snapshot (nullable) or tz_offset_minutes_snapshot (nullable)
- User can change timezone later, but existing meals keep their stored local_date and tz snapshot (no re-bucketing).

Timezone selection:
- City list (IANA tz like "Asia/Almaty", "Europe/Prague")
- UTC offsets from UTC-12 to UTC+14 (store as minutes)

========================================================
5) INPUT RULES & PRE-API FILTERING (SIMPLE, NON-AGGRESSIVE)
========================================================
Goal: reduce obvious non-food/spam and protect budget BEFORE calling OpenAI, without rejecting real food.

IMPORTANT: Even if user provides kcal/macros/weight, still call OpenAI because we must produce Likely Ingredients and meal naming.

5.1 Message type gate (no OpenAI):
Reject and reply:
"Please ✏️ write a food or drink or send me a 📸 photo."
for updates that are not text or photo:
- sticker, animation/gif, voice, video, document, contact, location, etc.

5.2 Empty/junk text gate (no OpenAI):
If normalized text is empty or only emojis/punctuation -> reply:
"Please ✏️ write a food or drink or send me a 📸 photo."

5.3 Water-only quick reject (no OpenAI):
If the text is clearly water-only (keep list short):
- вода, water, стакан воды, попил воды
Reply exactly:
"I can't analyse that because it seems to just say 'вода', which means 'water'. Water doesn't contain calories or macros. 😀"

5.4 Medicine quick reject (no OpenAI):
If text contains obvious medicine keywords (keep list short):
- лекарство, таблетка, ibuprofen, paracetamol
Reply:
"Please ✏️ write a food or drink or send me a 📸 photo."

5.5 Optional conservative “vague text-only” reject (no OpenAI):
Apply ONLY for a small curated list of vague placeholders (do NOT do language-based rejection):
Examples: "вкусняшка", "еда", "поел", "ням", "что-то"
Only if:
- text-only (no photo)
- no numbers/units
- matches curated vague words
Reply:
"I can't analyse that because the text is not in English and lacks sufficient detail about the food item to make an estimation 😀"
NOTE: Do NOT reject valid short foods like "pizza", "burger", "плов", "шаурма".

5.6 Photo size guard (no OpenAI):
- choose a reasonable photo size variant to download (not necessarily largest)
- if bytes exceed MAX_PHOTO_BYTES -> ask user to resend a clearer/smaller photo and do not call OpenAI

5.7 Rate limiting + concurrency guard (no OpenAI if exceeded):
- per-user rate limit (e.g., 6 requests per minute)
- per-user concurrency limit: 1 in-flight OpenAI analysis
If exceeded: reply:
"Too many requests. Please wait a bit and try again 🙂"

5.8 Duplicate protection:
- Idempotency by (tg_chat_id, tg_message_id) for saving
- For photos: if file_unique_id was analyzed recently for same user, optionally reuse result or treat as duplicate (either acceptable), but must not call OpenAI again unnecessarily.

5.9 Unrecognized food after OpenAI:
If OpenAI returns reject_unrecognized OR any OpenAI transient error happens:
Reply EXACTLY:
"I couldn't recognize the food. Please try sending it again."

========================================================
6) OPENAI INTEGRATION (STRICT STRUCTURED OUTPUTS)
========================================================
Use OpenAI API with:
- Vision for photos
- Structured outputs returning strict JSON validated by Pydantic.

The bot must:
- validate outputs
- reject if uncertain
- never hallucinate numbers if the input is unrelated

6.1 Schema (Pydantic model)
Fields:
- action: one of
  save
  reject_no_calories
  reject_not_food
  reject_insufficient_detail
  reject_unrecognized
- meal_name: string | null
- calories_kcal: int | null
- protein_g: float | null
- carbs_g: float | null
- fat_g: float | null
- weight_g: int | null
- volume_ml: int | null
- caffeine_mg: int | null (optional)
- likely_ingredients: list of objects:
  - name: str
  - amount: str
  - calories_kcal: int
- user_message: string | null (English, for reject cases except reject_unrecognized which uses the fixed phrase)
- confidence: float 0..1

6.2 Rules
- Prefer rejection over guessing when uncertain.
- If input is unrelated/non-food/no-calories/insufficient detail -> reject_* with user_message.
- If unrecognized -> reject_unrecognized and bot responds with the fixed phrase.
- Numeric sanity: non-negative; absurd values -> reject_insufficient_detail or reject_unrecognized.
- If user provides explicit numbers (kcal/macros/weight/volume), the bot must trust them (pass through) and instruct OpenAI to not overwrite them, but still generate ingredients and meal name.

6.3 raw AI response retention
Persist raw OpenAI structured result (and optionally the raw JSON string) into MealEntry.raw_ai_response for debugging.

========================================================
7) DATA MODEL (POSTGRES + SQLALCHEMY2 + ALEMBIC) + SOFT DELETE
========================================================
All queries for stats/history must ignore soft-deleted meals.

7.1 User table
- id (pk)
- tg_user_id (unique)
- goal (string enum)
- tz_mode ("city"|"offset")
- tz_name (nullable string)
- tz_offset_minutes (nullable int)
- created_at, updated_at

7.2 MealEntry table
- id (pk)
- user_id (fk)
- tg_chat_id
- tg_message_id
- source ("text"|"photo")
- original_text (nullable)
- photo_file_id (nullable)
- consumed_at_utc (timestamptz)
- local_date (date)
- tz_name_snapshot (nullable)
- tz_offset_minutes_snapshot (nullable)
- meal_name (string)
- calories_kcal (int)
- protein_g, carbs_g, fat_g (numeric)
- weight_g (nullable int)
- volume_ml (nullable int)
- caffeine_mg (nullable int)
- likely_ingredients_json (jsonb)
- raw_ai_response (jsonb or text; store parsed JSON + metadata)
- is_deleted (bool default false)
- deleted_at (nullable timestamptz) [recommended]
- created_at, updated_at

7.3 Constraints & indexes
- Unique constraint on (tg_chat_id, tg_message_id) for idempotency
- Index on (user_id, local_date) where is_deleted=false (or just index with filter if available)
- (Optional) Index on (user_id, created_at)

========================================================
8) REPORTS
========================================================
8.1 Today's Stats
- Sum calories/protein/carbs/fat for user’s local_date “today” in user timezone.
- Always show zeros if none.
- Must exclude is_deleted=true meals.

8.2 Weekly (Last 7 days incl today)
- Dates: today, today-1, ... today-6 (based on user's timezone)
- Show totals per day, zeros if none
- Must exclude deleted meals

8.3 4 Weeks (Last 28 days grouped Mon–Sun)
- Consider the last 28 days including today.
- Group into Mon–Sun weeks (4 weeks).
- For each week show AVERAGE per day (divide totals by 7; include zeros).
- Must exclude deleted meals.

========================================================
9) HISTORY
========================================================
- Show last N non-deleted meals (e.g. 20), with local date/time and macros summary.
- Provide inline delete.
- After delete, refresh history and/or show updated Today’s Stats.

========================================================
10) WEBHOOK + INFRASTRUCTURE
========================================================
10.1 Web structure separation
- Put FastAPI app code under web/ (e.g., app/web/main.py) to keep it clean from bot modules.
- Bot modules under app/bot/...
- Shared code under app/core, app/services, app/db, app/reports

10.2 FastAPI requirements
- POST /webhook/{secret}
- GET /health -> {"status":"ok"}
- On startup, set webhook to PUBLIC_URL + /webhook/{secret}
- Webhook secret required (validate path param)

10.3 Docker requirements
- Provide Dockerfile that runs uvicorn web app
- Provide .dockerignore
- Optional: docker-compose.yml for local Postgres + app

10.4 Railway
- README instructions for Railway
- Support PORT env

========================================================
11) CONFIGURATION (PYDANTIC SETTINGS) + VALIDATION
========================================================
Use Pydantic Settings (pydantic-settings) to define and validate env vars.
Required:
- BOT_TOKEN
- DATABASE_URL
- OPENAI_API_KEY
- PUBLIC_URL
- WEBHOOK_SECRET
Optional:
- OPENAI_MODEL
- LOG_LEVEL
- OPENAI_TIMEOUT_SECONDS
- MAX_PHOTO_BYTES
- RATE_LIMIT_PER_MINUTE
- MAX_CONCURRENT_PER_USER

Validation examples:
- PUBLIC_URL must be https and must not end with "/"
- WEBHOOK_SECRET minimum length
- numeric limits must be positive

Provide .env.example

========================================================
12) LOGGING & OBSERVABILITY
========================================================
Implement structured logging (JSON logs).
Log fields should include:
- tg_user_id, chat_id, message_id, update_id
- request_id/trace_id in FastAPI
- event names: precheck_reject, openai_call_start, openai_call_done, save_meal, edit_meal, delete_meal, stats_generated
- openai latency ms, model name, and optionally openai request id (if available)

========================================================
13) RATE LIMITING (SECURITY / BUDGET PROTECTION)
========================================================
Implement per-user rate limiting before calling OpenAI:
- default: 6 requests/minute/user
- respond with friendly throttle message
Implementation must work at least for single instance; document that multi-instance should use shared store (optional future).

Also implement per-user concurrency guard:
- allow only 1 in-flight OpenAI analysis per user
- if another arrives -> throttle message

========================================================
14) TESTING STRATEGY
========================================================
14.1 Unit tests (pytest)
- core/time:
  - local_date computation for tz_name and tz_offset
  - midnight boundary cases
  - week grouping Mon–Sun
  - last-28-days bucketing for 4 weeks
- reports/aggregations:
  - today totals include zeros
  - weekly includes zeros
  - 4-week averages divide by 7 and include zeros
  - excludes deleted meals
- services/precheck:
  - water/medicine/vague text logic
  - rate limit triggers
  - message type gate
- services/nutrition_ai:
  - schema validation (mocked)
  - reject_unrecognized -> fixed phrase behavior

14.2 Integration tests (DB)
- Use test Postgres (testcontainers recommended if feasible)
- Verify:
  - idempotency unique constraint
  - soft delete hides from stats/history
  - edit updates record fields and stats

14.3 Contract tests (AI layer)
- Never call real OpenAI in tests.
- Mock AI results to cover all action values:
  save, reject_no_calories, reject_not_food, reject_insufficient_detail, reject_unrecognized

========================================================
15) ACCEPTANCE CHECKLIST
========================================================
MVP accepted when:
- New user can set goal + timezone.
- Any text/photo triggers meal analysis attempt (unless precheck rejects).
- Bot shows ChatAction typing while OpenAI works.
- Meals can be saved/edited/soft-deleted.
- After each saved meal: saved summary + Today’s Stats always shown.
- Stats: Today / Weekly / 4 Weeks work, include zeros, exclude deleted meals.
- Non-food/no-calories/insufficient detail are rejected and not saved.
- Unrecognized returns EXACT fixed phrase.
- Rate limiting and concurrency guard prevent spamming OpenAI.
- raw_ai_response is stored for saved meals.
- Pydantic Settings validate env.
- Structured logging exists.
- Webhook works and Railway deploy is documented.
- Tests pass locally.

========================================================
END OF SPEC
========================================================