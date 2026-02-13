"""Message formatting helpers for the Telegram bot.

All output templates match the spec §3.4 / §8 requirements.
User-facing labels are resolved via ``t(key, lang)`` for i18n.
"""

from __future__ import annotations

from datetime import date

from app.i18n import t as tr
from app.reports.stats import DayStats, WeekAvgStats
from app.services.nutrition_ai import Ingredient, NutritionAnalysis


# ---------------------------------------------------------------------------
# Meal saved / draft message (spec §3.4, D5/FEAT-07)
# ---------------------------------------------------------------------------


def _format_ingredient_line(ing: Ingredient, lang: str = "EN") -> str:
    """Build a single ingredient bullet: name (Xg, Ykcal) or name (Ykcal).

    Display grams from ``weight_g``; if absent, convert ``volume_ml``
    at 1 ml ≈ 1 g; if both absent, omit grams entirely.
    """
    g_unit = tr("fmt_unit_g", lang)
    kcal_unit = tr("fmt_unit_kcal", lang)

    if ing.weight_g is not None:
        grams_part = f"{round(ing.weight_g)}{g_unit}, "
    elif ing.volume_ml is not None:
        grams_part = f"{round(ing.volume_ml)}{g_unit}, "  # 1 ml ≈ 1 g display-only
    else:
        grams_part = ""

    return f"• {ing.name} ({grams_part}{ing.calories_kcal}{kcal_unit})"


def _format_meal_body(analysis: NutritionAnalysis, lang: str = "EN") -> list[str]:
    """Shared body lines: calories, macros, totals, ingredients."""
    lines: list[str] = []
    lines.append("")
    lines.append(tr("fmt_calories", lang))
    lines.append(f"{analysis.calories_kcal}{tr('fmt_unit_kcal', lang)}")

    # Caffeine — shown only if present, placed after calories and before macros
    if analysis.caffeine_mg is not None:
        lines.append("")
        lines.append(f"☕ {tr('fmt_caffeine', lang)}: {analysis.caffeine_mg}mg")

    lines.append("")
    lines.append(tr("fmt_macros", lang))
    lines.append(
        f"• {tr('fmt_protein', lang)}: {analysis.protein_g}{tr('fmt_unit_g', lang)}"
    )
    lines.append(
        f"• {tr('fmt_carbs', lang)}: {analysis.carbs_g}{tr('fmt_unit_g', lang)}"
    )
    lines.append(
        f"• {tr('fmt_fat', lang)}: {analysis.fat_g}{tr('fmt_unit_g', lang)}"
    )

    if analysis.likely_ingredients:
        lines.append("")
        lines.append(tr("fmt_likely_ingredients", lang))
        for ing in analysis.likely_ingredients:
            lines.append(_format_ingredient_line(ing, lang))

    return lines


def format_meal_saved(analysis: NutritionAnalysis, lang: str = "EN") -> str:
    """Format the meal summary shown after saving (spec §3.4).

    Includes meal name, calories, macros, totals, and likely ingredients.
    """
    lines = [f"{tr('fmt_saved_prefix', lang)}{analysis.meal_name}"]
    lines.extend(_format_meal_body(analysis, lang))
    return "\n".join(lines)


def format_meal_draft(analysis: NutritionAnalysis, lang: str = "EN") -> str:
    """Format the draft preview (before saving).

    Same as saved but with a different header.
    """
    lines = [f"{tr('fmt_draft_prefix', lang)}{analysis.meal_name}"]
    lines.extend(_format_meal_body(analysis, lang))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stats formatting helpers
# ---------------------------------------------------------------------------


def _weekday_abbr(d: date, lang: str) -> str:
    """Locale-aware weekday abbreviation (Mon–Sun)."""
    names = tr("fmt_weekdays", lang).split(",")
    return names[d.weekday()]


def _format_date_short(d: date) -> str:
    """Format date as DD.MM."""
    return f"{d.day:02d}.{d.month:02d}"


# ---------------------------------------------------------------------------
# Today's Stats block (spec §3.4)
# ---------------------------------------------------------------------------


def format_today_stats(
    stats: DayStats,
    lang: str = "EN",
    *,
    bold_header_html: bool = False,
) -> str:
    """Format Today's Stats block shown after saving a meal."""
    header = tr("fmt_today_stats_header", lang)
    if bold_header_html:
        header = f"<b>{header}</b>"
    return (
        f"{header}\n"
        f"⚪ {tr('fmt_calories', lang)}: {stats['calories_kcal']}kcal\n"
        f"⚪ {tr('fmt_carbs', lang)}: {stats['carbs_g']}g\n"
        f"⚪ {tr('fmt_protein', lang)}: {stats['protein_g']}g\n"
        f"⚪ {tr('fmt_fat', lang)}: {stats['fat_g']}g"
    )


# ---------------------------------------------------------------------------
# Weekly stats (spec §8.2)
# ---------------------------------------------------------------------------


def format_weekly_stats(
    days: list[DayStats],
    lang: str = "EN",
    *,
    bold_header_html: bool = False,
) -> str:
    """Format per-day breakdown for the last 7 days.

    Template:
        EN: ``Mon 17.06: 1850 kcal | P/C/F 120/200/65``
        RU: ``Пн 17.06: 1850 ккал | Б/У/Ж 120/200/65``
    """
    kcal_unit = tr("fmt_unit_kcal", lang)
    macro_label = tr("fmt_macro_pcf", lang)
    header = tr("fmt_weekly_stats_header", lang)
    if bold_header_html:
        header = f"<b>{header}</b>"
    lines: list[str] = [header]
    lines.append("")
    for day in days:
        d: date = day["date"]
        dow = _weekday_abbr(d, lang)
        dd_mm = _format_date_short(d)
        cal = round(day["calories_kcal"])
        p = round(day["protein_g"])
        c = round(day["carbs_g"])
        f = round(day["fat_g"])
        lines.append(f"{dow} {dd_mm}: {cal} {kcal_unit} | {macro_label} {p}/{c}/{f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4-week stats (spec §8.3)
# ---------------------------------------------------------------------------


def format_four_week_stats(
    weeks: list[WeekAvgStats],
    lang: str = "EN",
    *,
    bold_header_html: bool = False,
) -> str:
    """Format weekly averages for the last 4 weeks (2-line blocks).

    Template (each week)::

        EN: Week 1 (17.06-23.06)
            1850 kcal | P/C/F 120/200/65

        RU: Неделя 1 (17.06-23.06)
            1850 ккал | Б/У/Ж 120/200/65
    """
    week_label = tr("fmt_week_label", lang)
    kcal_unit = tr("fmt_unit_kcal", lang)
    macro_label = tr("fmt_macro_pcf", lang)
    header = tr("fmt_4week_stats_header", lang)
    if bold_header_html:
        header = f"<b>{header}</b>"
    lines: list[str] = [header]
    for i, week in enumerate(weeks, 1):
        ws = _format_date_short(week["week_start"])
        we = _format_date_short(week["week_end"])
        cal = round(week["avg_calories_kcal"])
        p = round(week["avg_protein_g"])
        c = round(week["avg_carbs_g"])
        f = round(week["avg_fat_g"])
        lines.append("")
        lines.append(f"{week_label} {i} ({ws}-{we})")
        lines.append(f"{cal} {kcal_unit} | {macro_label} {p}/{c}/{f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# History list (spec §9)
# ---------------------------------------------------------------------------


def format_history_entry(
    meal_name: str,
    calories_kcal: int,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    local_date: date,
) -> str:
    """Format a single history list entry."""
    d = local_date.strftime("%b %d")
    return f"{d} — {meal_name}: {calories_kcal}kcal | P:{protein_g}g C:{carbs_g}g F:{fat_g}g"
