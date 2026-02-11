"""Message formatting helpers for the Telegram bot.

All output templates match the spec §3.4 / §8 requirements.
"""

from __future__ import annotations

from datetime import date

from app.reports.stats import DayStats, WeekAvgStats
from app.services.nutrition_ai import NutritionAnalysis


# ---------------------------------------------------------------------------
# Meal saved / draft message (spec §3.4)
# ---------------------------------------------------------------------------


def format_meal_saved(analysis: NutritionAnalysis) -> str:
    """Format the meal summary shown after saving (spec §3.4).

    Includes meal name, calories, macros, and likely ingredients.
    """
    lines: list[str] = [f"✅ Saved. You added: {analysis.meal_name}"]
    lines.append("")
    lines.append("Calories")
    lines.append(f"{analysis.calories_kcal}kcal")
    lines.append("")
    lines.append("Macros")
    lines.append(f"• Protein: {analysis.protein_g}g")
    lines.append(f"• Carbs: {analysis.carbs_g}g")
    lines.append(f"• Fat: {analysis.fat_g}g")

    if analysis.likely_ingredients:
        lines.append("")
        lines.append("Likely Ingredients")
        for ing in analysis.likely_ingredients:
            lines.append(f"• {ing.name} ({ing.amount}, {ing.calories_kcal}kcal)")

    return "\n".join(lines)


def format_meal_draft(analysis: NutritionAnalysis) -> str:
    """Format the draft preview (before saving).

    Same as saved but with a different header.
    """
    lines: list[str] = [f"🍽 Draft: {analysis.meal_name}"]
    lines.append("")
    lines.append("Calories")
    lines.append(f"{analysis.calories_kcal}kcal")
    lines.append("")
    lines.append("Macros")
    lines.append(f"• Protein: {analysis.protein_g}g")
    lines.append(f"• Carbs: {analysis.carbs_g}g")
    lines.append(f"• Fat: {analysis.fat_g}g")

    if analysis.likely_ingredients:
        lines.append("")
        lines.append("Likely Ingredients")
        for ing in analysis.likely_ingredients:
            lines.append(f"• {ing.name} ({ing.amount}, {ing.calories_kcal}kcal)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Today's Stats block (spec §3.4)
# ---------------------------------------------------------------------------


def format_today_stats(stats: DayStats) -> str:
    """Format Today's Stats block shown after saving a meal."""
    return (
        "📊 Today's Stats\n"
        f"⚪ Calories: {stats['calories_kcal']}kcal\n"
        f"⚪ Carbs: {stats['carbs_g']}g\n"
        f"⚪ Protein: {stats['protein_g']}g\n"
        f"⚪ Fat: {stats['fat_g']}g"
    )


# ---------------------------------------------------------------------------
# Weekly stats (spec §8.2)
# ---------------------------------------------------------------------------


def format_weekly_stats(days: list[DayStats]) -> str:
    """Format per-day breakdown for the last 7 days."""
    lines: list[str] = ["📊 Weekly Stats (Last 7 Days)"]
    lines.append("")
    for day in days:
        d: date = day["date"]
        cal = day["calories_kcal"]
        p = day["protein_g"]
        c = day["carbs_g"]
        f = day["fat_g"]
        label = d.strftime("%a %b %d")
        lines.append(f"{label}: {cal}kcal | P:{p}g C:{c}g F:{f}g")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4-week stats (spec §8.3)
# ---------------------------------------------------------------------------


def format_four_week_stats(weeks: list[WeekAvgStats]) -> str:
    """Format weekly averages for the last 4 weeks."""
    lines: list[str] = ["📊 4-Week Stats (Daily Averages)"]
    lines.append("")
    for i, week in enumerate(weeks, 1):
        ws = week["week_start"].strftime("%b %d")
        we = week["week_end"].strftime("%b %d")
        cal = week["avg_calories_kcal"]
        p = week["avg_protein_g"]
        c = week["avg_carbs_g"]
        f = week["avg_fat_g"]
        lines.append(f"Week {i} ({ws}–{we}): {cal}kcal | P:{p}g C:{c}g F:{f}g")
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
