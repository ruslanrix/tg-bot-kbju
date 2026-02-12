"""English locale strings.

Keys are grouped by functional area matching the handler/module structure.
All user-facing UI strings are catalogued here for centralized translation.
"""

STRINGS: dict[str, str] = {
    # ---------------------------------------------------------------------------
    # Onboarding (middlewares.py — TimezoneGateMiddleware)
    # ---------------------------------------------------------------------------
    "onboarding_a": (
        "Hi. Every time you eat, send me a 📸 pic of your meal (or drink). "
        "I'll guess the macros, calories, caffeine and ingredients to help you "
        "keep track of your diet."
    ),
    "onboarding_b": (
        "🌍 First I need to know your time zone so I can divide up your meals "
        "into days correctly. You can change it later."
    ),
    "onboarding_tz_alert": "Please set your timezone first.",

    # ---------------------------------------------------------------------------
    # /start
    # ---------------------------------------------------------------------------
    "welcome_back": "Welcome back! 🍽 Send me a photo or description of your food.",

    # ---------------------------------------------------------------------------
    # /help
    # ---------------------------------------------------------------------------
    "help_text": (
        "Hi. Every time you eat, send me a 📸 pic of your meal (or drink). "
        "I'll guess the macros, calories, caffeine and ingredients to help you "
        "keep track of your diet.\n\n"
        "Tip: Pin this chat so it stays at the top for easy access.\n"
        "Tip: You can write stuff like yesterday or two days ago when logging "
        "meals that you forgot to add before.\n\n"
        "Commands\n"
        "ℹ️ /help — What you're looking at now\n"
        "✍️ /add — Manually write any meal or drink without a photo\n"
        "📊 /stats — See your daily, weekly or monthly stats\n"
        "🎯 /goals — Set your calorie and macro goals\n"
        "🕘 /history — See your meal history and delete meals\n"
        "🗣️ /feedback — Send feedback to my maker\n"
        "🧾 /subscription — Manage your subscription\n\n"
        "🌍 Remember to change your time zone if you moved countries."
    ),

    # ---------------------------------------------------------------------------
    # /add
    # ---------------------------------------------------------------------------
    "add_prompt": "What did you eat? Send me a text description or a 📸 photo.",

    # ---------------------------------------------------------------------------
    # Meal processing (meal.py)
    # ---------------------------------------------------------------------------
    "msg_unrecognized": "I couldn't recognize the food. Please try sending it again.",
    "msg_throttle": "Too many requests. Please wait a bit and try again 🙂",
    "msg_sanity_fail": "⚠️ The values look unrealistic. Please double-check and try again.",
    "msg_edit_window_expired": "⏳ This meal can no longer be edited (older than {hours}h).",
    "msg_delete_window_expired": "⏳ This meal can no longer be deleted (older than {hours}h).",
    "msg_processing_new": "🔄 Combobulating...",
    "msg_processing_edit": "🔄 Analysing again with your feedback...",
    "meal_not_found": "Meal not found.",
    "edit_send_corrected": "Send corrected text for this meal:",
    "already_saved": "Already saved.",
    "deleted_label": "🗑️ Deleted.",
    "draft_expired": "This draft has expired. Please send your meal again.",

    # ---------------------------------------------------------------------------
    # Formatters (formatters.py)
    # ---------------------------------------------------------------------------
    "fmt_saved_prefix": "✅ Saved. You added: ",
    "fmt_draft_prefix": "🍽 Draft: ",
    "fmt_calories": "Calories",
    "fmt_macros": "Macros",
    "fmt_protein": "Protein",
    "fmt_carbs": "Carbs",
    "fmt_fat": "Fat",
    "fmt_totals": "Totals",
    "fmt_weight": "Weight",
    "fmt_volume": "Volume",
    "fmt_caffeine": "Caffeine",
    "fmt_likely_ingredients": "Likely Ingredients",
    "fmt_today_stats_header": "📊 Today's Stats",
    "fmt_weekly_stats_header": "📊 Weekly Stats (Last 7 Days)",
    "fmt_4week_stats_header": "📊 4-Week Stats (Daily Averages)",
    "fmt_week_label": "Week",
    "fmt_no_meals": "No meals recorded yet.",

    # ---------------------------------------------------------------------------
    # Reply keyboard buttons (keyboards.py)
    # ---------------------------------------------------------------------------
    "kb_stats": "📊 Stats",
    "kb_goals": "🎯 Goals",
    "kb_help": "☁️ Help",
    "kb_history": "🕘 History",
    "kb_add_meal": "✏️ Add Meal",

    # ---------------------------------------------------------------------------
    # Inline keyboard buttons (keyboards.py)
    # ---------------------------------------------------------------------------
    "kb_save": "✅ Save",
    "kb_edit": "✏️ Edit",
    "kb_delete": "🛑 Delete",
    "kb_today": "Today",
    "kb_weekly": "Weekly",
    "kb_4weeks": "4 Weeks",
    "kb_change_tz": "🕒 Change Time Zone",
    "kb_choose_offset": "⏱ Choose UTC offset instead",
    "kb_choose_city": "🏙 Choose city instead",

    # ---------------------------------------------------------------------------
    # Goals (goals.py)
    # ---------------------------------------------------------------------------
    "goals_prompt": "Choose your goal:",
    "goal_maintenance": "🏋️ Maintenance",
    "goal_deficit": "📉 Deficit",
    "goal_bulk": "💪 Bulk",
    "goal_set_confirmation": "Goal set to {label} ✅",

    # ---------------------------------------------------------------------------
    # Timezone (timezone.py)
    # ---------------------------------------------------------------------------
    "tz_choose_city": "🌍 Choose your city:",
    "tz_choose_offset": "⏱ Choose your UTC offset:",
    "tz_saved": "✅ Time zone saved: {tz}. You can change it later.",

    # ---------------------------------------------------------------------------
    # Stats (stats.py)
    # ---------------------------------------------------------------------------
    "stats_choose_period": "Choose a stats period:",

    # ---------------------------------------------------------------------------
    # Stubs (stubs.py)
    # ---------------------------------------------------------------------------
    "stub_feedback": "Thanks! Feedback feature coming soon. 🗣️",
    "stub_subscription": "Subscription management coming soon. 🧾",

    # ---------------------------------------------------------------------------
    # Reminder (web/main.py)
    # ---------------------------------------------------------------------------
    "reminder_text": (
        "Hey! You haven't logged any meals in a while. "
        "Send me a photo or describe what you ate 🍽️"
    ),

    # ---------------------------------------------------------------------------
    # Language selection (language.py)
    # ---------------------------------------------------------------------------
    "lang_unknown": "Unknown language.",
    "lang_set_confirmation": "Language set to {label} ✅",

    # ---------------------------------------------------------------------------
    # Precheck (precheck.py)
    # ---------------------------------------------------------------------------
    "precheck_not_text_or_photo": "Please ✏️ write a food or drink or send me a 📸 photo.",
    "precheck_water": (
        "I can't analyse that because it seems to just say 'вода', "
        "which means 'water'. Water doesn't contain calories or macros. 😀"
    ),
    "precheck_vague": (
        "I can't analyse that because the text is not in English and "
        "lacks sufficient detail about the food item to make an estimation 😀"
    ),
    "precheck_photo_too_large": "The photo is too large. Please resend a clearer or smaller photo 📸",

    # ---------------------------------------------------------------------------
    # Navigation
    # ---------------------------------------------------------------------------
    "nav_arrow": "👇",
}
