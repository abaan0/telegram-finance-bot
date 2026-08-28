import os
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from commands import command
from services.finance import (
    get_all_months_data,
    analyze_financial_data,
)
from services.gemini import GEMINI_MODEL


TIMEZONE = os.getenv(
    "TIMEZONE",
    "Asia/Kolkata",
)


def is_admin(update: Update) -> bool:
    """Check whether the Telegram user is the configured admin."""

    user = update.effective_user

    return (
        user is not None
        and user.id
        == int(os.environ["ADMIN_ID"])
    )


def format_currency(amount: float) -> str:
    """Format currency with Indian numbering system."""

    if amount >= 10000000:  # 1 crore
        return f"₹{amount / 10000000:.2f} Cr"

    elif amount >= 100000:  # 1 lakh
        return f"₹{amount / 100000:.2f} L"

    else:
        return f"₹{amount:,.2f}"


def format_percentage(value: float) -> str:
    """Format percentage with sign."""

    sign = "+" if value > 0 else ""

    return f"{sign}{value:.1f}%"


def build_budget_summary_message(
    analysis: dict,
) -> str:
    """Build the main budget summary message."""

    if (
        "error" in analysis
        and analysis.get("fallback")
    ):
        return build_fallback_message(
            analysis
        )

    km = analysis.get(
        "key_metrics",
        {},
    )

    budget_health = analysis.get(
        "budget_health",
        {},
    )

    comparisons = analysis.get(
        "comparisons",
        {},
    )

    forecast = analysis.get(
        "projected_forecast",
        {},
    )

    patterns = analysis.get(
        "spending_patterns",
        {},
    )

    # Use the actual model that generated
    # the analysis. Falls back to the configured
    # primary model if unavailable.
    model_used = analysis.get(
        "model_used",
        GEMINI_MODEL,
    )

    today = datetime.now(
        ZoneInfo(TIMEZONE)
    )

    month_name = today.strftime(
        "%B %Y"
    )

    lines = [
        f"💰 <b>{month_name} BUDGET SUMMARY</b>",
        "",
        "📊 <b>KEY METRICS</b>",
        f"├─ Total Spent: "
        f"<b>{format_currency(km.get('total_expenses', 0))}</b>",
        f"├─ Total Income: "
        f"<b>{format_currency(km.get('total_income', 0))}</b>",
        f"├─ Net Savings: "
        f"<b>{format_currency(km.get('net_savings', 0))}</b>",
        f"├─ Savings Rate: "
        f"<b>{km.get('savings_rate_percent', 0):.1f}%</b>",
        f"├─ Daily Average: "
        f"{format_currency(km.get('daily_average_spending', 0))}",
        f"└─ Days Remaining: "
        f"<b>{km.get('days_remaining_in_month', 0)}</b>",
        "",
    ]

    # Budget Health
    status_emoji = {
        "on_track": "✅",
        "attention_needed": "⚠️",
        "critical": "🚨",
    }

    status_text = {
        "on_track": "On Track",
        "attention_needed": "Attention Needed",
        "critical": "Over Budget",
    }

    status = budget_health.get(
        "overall_status",
        "on_track",
    )

    lines.extend(
        [
            f"{status_emoji.get(status, '✅')} "
            f"<b>BUDGET HEALTH: "
            f"{status_text.get(status, 'On Track')}</b>",
        ]
    )

    if budget_health.get(
        "categories_over_budget"
    ):
        lines.append(
            "🚨 <b>Over Budget:</b>"
        )

        for cat in budget_health[
            "categories_over_budget"
        ]:
            lines.append(
                f"   • {cat}"
            )

    if budget_health.get(
        "categories_near_limit"
    ):
        lines.append(
            "⚠️ <b>Near Limit (75%+):</b>"
        )

        for cat in budget_health[
            "categories_near_limit"
        ]:
            lines.append(
                f"   • {cat}"
            )

    if budget_health.get(
        "projected_over_budget"
    ):
        lines.append(
            "📈 <b>Projected to Exceed:</b>"
        )

        for cat in budget_health[
            "projected_over_budget"
        ]:
            lines.append(
                f"   • {cat}"
            )

    if not any(
        [
            budget_health.get(
                "categories_over_budget"
            ),
            budget_health.get(
                "categories_near_limit"
            ),
            budget_health.get(
                "projected_over_budget"
            ),
        ]
    ):
        lines.append(
            "   All categories within budget! 🎉"
        )

    lines.append("")

    # Category Analysis
    cat_analysis = analysis.get(
        "category_analysis",
        [],
    )

    if cat_analysis:
        lines.append(
            "📈 <b>CATEGORY BREAKDOWN</b>"
        )

        for cat in cat_analysis[:8]:
            cat_name = cat.get(
                "category",
                "",
            )

            current = cat.get(
                "current",
                0,
            )

            change = cat.get(
                "change_percent",
                0,
            )

            trend = cat.get(
                "trend",
                "stable",
            )

            insight = cat.get(
                "insight",
                "",
            )

            trend_emoji = {
                "up": "📈",
                "down": "📉",
                "stable": "➡️",
            }

            change_str = format_percentage(
                change
            )

            lines.append(
                f"├─ {cat_name}: "
                f"<b>{format_currency(current)}</b> "
                f"({change_str} "
                f"{trend_emoji.get(trend, '➡️')})"
            )

            if insight:
                lines.append(
                    f"│   <i>{insight}</i>"
                )

        lines[-1] = lines[-1].replace(
            "├─",
            "└─",
        )

        lines.append("")

    # Comparison with Last Month
    vs_last = comparisons.get(
        "vs_last_month",
        {},
    )

    if vs_last:
        exp_change = vs_last.get(
            "expense_change",
            0,
        )

        sav_change = vs_last.get(
            "savings_rate_change",
            0,
        )

        summary = vs_last.get(
            "summary",
            "",
        )

        change_emoji = (
            "📈"
            if exp_change > 0
            else "📉"
            if exp_change < 0
            else "➡️"
        )

        lines.extend(
            [
                f"📊 <b>vs LAST MONTH</b> "
                f"{change_emoji}",
                f"├─ Expenses: "
                f"{format_percentage(exp_change)}",
                f"├─ Savings Rate: "
                f"{format_percentage(sav_change)}",
                f"└─ {summary}",
                "",
            ]
        )

    # 6-Month Average Comparison
    vs_avg = comparisons.get(
        "vs_6month_average",
        {},
    )

    if vs_avg:
        diff = vs_avg.get(
            "difference_percent",
            0,
        )

        summary = vs_avg.get(
            "summary",
            "",
        )

        diff_emoji = (
            "📈"
            if diff > 0
            else "📉"
            if diff < 0
            else "➡️"
        )

        lines.extend(
            [
                f"📊 <b>vs 6-MONTH AVERAGE</b> "
                f"{diff_emoji}",
                f"└─ {format_percentage(diff)} "
                f"- {summary}",
                "",
            ]
        )

    # Forecast
    if forecast:
        proj_exp = forecast.get(
            "projected_total_expenses",
            0,
        )

        proj_sav = forecast.get(
            "projected_savings",
            0,
        )

        confidence = forecast.get(
            "confidence",
            "medium",
        )

        assumptions = forecast.get(
            "key_assumptions",
            [],
        )

        conf_emoji = {
            "high": "🎯",
            "medium": "📍",
            "low": "🔮",
        }

        lines.extend(
            [
                f"{conf_emoji.get(confidence, '🔮')} "
                f"<b>MONTH-END FORECAST</b>",
                f"├─ Projected Expenses: "
                f"<b>{format_currency(proj_exp)}</b>",
                f"├─ Projected Savings: "
                f"<b>{format_currency(proj_sav)}</b>",
                f"└─ Confidence: "
                f"{confidence.title()}",
            ]
        )

        if assumptions:
            for assumption in assumptions[:2]:
                lines.append(
                    f"   • {assumption}"
                )

        lines.append("")

    # Spending Patterns
    if patterns:
        lines.extend(
            [
                "🔍 <b>SPENDING PATTERNS</b>",
                f"├─ Peak Day: "
                f"{patterns.get('peak_spending_day', 'N/A')}",
                f"├─ Top Category: "
                f"{patterns.get('peak_spending_category', 'N/A')}",
                f"├─ Weekend/Weekday Ratio: "
                f"{patterns.get('weekend_vs_weekday_ratio', 0):.1f}x",
                f"└─ <i>"
                f"{patterns.get('pattern_insight', '')}"
                f"</i>",
                "",
            ]
        )

    # Wins
    wins = analysis.get(
        "wins",
        [],
    )

    if wins:
        lines.append(
            "🏆 <b>WINS THIS MONTH</b>"
        )

        for win in wins[:3]:
            lines.append(
                f"✅ {win}"
            )

        lines.append("")

    # Concerns
    concerns = analysis.get(
        "concerns",
        [],
    )

    if concerns:
        lines.append(
            "⚠️ <b>WATCH OUT</b>"
        )

        for concern in concerns[:3]:
            lines.append(
                f"⚠️ {concern}"
            )

        lines.append("")

    # Actionable Recommendations
    recommendations = analysis.get(
        "actionable_recommendations",
        [],
    )

    if recommendations:
        lines.append(
            "💡 <b>RECOMMENDATIONS</b>"
        )

        for rec in recommendations[:4]:
            priority = rec.get(
                "priority",
                "medium",
            )

            action = rec.get(
                "action",
                "",
            )

            impact = rec.get(
                "impact",
                "",
            )

            effort = rec.get(
                "effort",
                "medium",
            )

            priority_emoji = {
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢",
            }

            effort_emoji = {
                "easy": "⚡",
                "medium": "⚙️",
                "hard": "🔧",
            }

            lines.append(
                f"{priority_emoji.get(priority, '🟡')} "
                f"{action}"
            )

            if impact:
                lines.append(
                    f"   → Impact: {impact} | "
                    f"Effort: "
                    f"{effort_emoji.get(effort, '⚙️')}"
                )

        lines.append("")

    # Milestones
    milestones = analysis.get(
        "milestones",
        [],
    )

    if milestones:
        lines.append(
            "🎯 <b>MILESTONES</b>"
        )

        for milestone in milestones[:2]:
            lines.append(
                f"🎯 {milestone}"
            )

        lines.append("")

    # Motivational Note
    note = analysis.get(
        "motivational_note",
        "",
    )

    if note:
        lines.append(
            f"💪 <i>{note}</i>"
        )

    # Footer
    lines.extend(
        [
            "",
            f"🤖 Analysis by {model_used} | "
            f"{today.strftime('%d %b %Y, %I:%M %p')}",
        ]
    )

    return "\n".join(lines)


def build_fallback_message(
    analysis: dict,
) -> str:
    """Build a basic message when AI analysis fails."""

    km = analysis.get(
        "key_metrics",
        {},
    )

    today = datetime.now(
        ZoneInfo(TIMEZONE)
    )

    lines = [
        f"💰 <b>{today.strftime('%B %Y')} "
        f"BUDGET SUMMARY</b>",
        "",
        "📊 <b>KEY METRICS</b>",
        f"├─ Total Spent: "
        f"<b>{format_currency(km.get('total_expenses', 0))}</b>",
        f"├─ Total Income: "
        f"<b>{format_currency(km.get('total_income', 0))}</b>",
        f"├─ Net Savings: "
        f"<b>{format_currency(km.get('net_savings', 0))}</b>",
        f"├─ Savings Rate: "
        f"<b>{km.get('savings_rate_percent', 0):.1f}%</b>",
        f"├─ Daily Average: "
        f"{format_currency(km.get('daily_average_spending', 0))}",
        f"└─ Days Remaining: "
        f"<b>{km.get('days_remaining_in_month', 0)}</b>",
        "",
        "⚠️ <i>AI analysis temporarily "
        "unavailable. Showing basic metrics only.</i>",
        "",
        f"🤖 Powered by {GEMINI_MODEL} | "
        f"{today.strftime('%d %b %Y, %I:%M %p')}",
    ]

    return "\n".join(lines)


@command(
    "budgetsummary",
    "Get AI-powered financial summary and trends",
)
async def budgetsummary(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Comprehensive budget summary with AI insights."""

    message = update.effective_message

    # Protect all financial summary data.
    if not is_admin(update):
        await message.reply_text(
            "⛔ You are not authorized to use this command."
        )
        return

    # Send initial loading message.
    loading_msg = await message.reply_text(
        "🔍 Fetching your financial data..."
    )

    try:
        # Get all transaction data.
        await loading_msg.edit_text(
            "📊 Analyzing spending patterns..."
        )

        transactions = (
            get_all_months_data()
        )

        if not transactions:
            await loading_msg.edit_text(
                "📭 No expense data found yet.\n\n"
                "Start tracking with /expense "
                "or /income commands!"
            )
            return

        # Get AI analysis.
        await loading_msg.edit_text(
            "🧠 Generating AI insights..."
        )

        analysis = await analyze_financial_data(
            transactions
        )

        # Build and send response.
        await loading_msg.edit_text(
            "✨ Building your summary..."
        )

        response_text = (
            build_budget_summary_message(
                analysis
            )
        )

        await loading_msg.edit_text(
            response_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception as e:
        print(
            f"budgetsummary error: {e}"
        )

        await loading_msg.edit_text(
            f"⚠️ Couldn't generate budget summary.\n\n"
            f"Error: {str(e)[:200]}"
        )