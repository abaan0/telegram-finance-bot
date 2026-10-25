import os
import json
import asyncio
from datetime import datetime, date, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo
from collections import defaultdict

from services.gemini import client, GEMINI_MODEL
from google.genai import types

from services.google_sheets import get_all_months_data

# Timezone for date calculations
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")

from services.categories import infer_category

async def analyze_financial_data(transactions: list[dict]) -> dict:
    """Analyze financial data using Gemini AI for insights."""

    if not transactions:
        return {"error": "No transactions found"}

    # Use the same configured timezone as transaction parsing and worksheet routing.
    today = datetime.now(ZoneInfo(TIMEZONE))
    current_month = today.month
    current_year = today.year
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month_start = (month_start + timedelta(days=32)).replace(day=1)
    days_in_month = (next_month_start - timedelta(days=1)).day
    days_remaining = days_in_month - today.day

    # Filter current month transactions
    current_month_transactions = [
        t for t in transactions
        if t["date"].month == current_month and t["date"].year == current_year
    ]

    # Calculate totals
    total_expense = sum(t["expense"] for t in current_month_transactions)
    total_income = sum(t["income"] for t in current_month_transactions)

    # Category breakdown
    category_totals = defaultdict(float)
    for t in current_month_transactions:
        if t["expense"] > 0:
            category_totals[t["category"]] += t["expense"]

    # Daily spending pattern for the last 30 days
    thirty_days_ago = today - timedelta(days=30)

    daily_totals = defaultdict(float)

    for t in transactions:
        transaction_date = t["date"].replace(
            tzinfo=ZoneInfo(TIMEZONE)
        )

        if (
            transaction_date >= thirty_days_ago
            and t["expense"] > 0
        ):
            day_key = transaction_date.strftime("%Y-%m-%d")
            daily_totals[day_key] += t["expense"]

    # Day of week pattern
    dow_totals = defaultdict(float)
    for t in current_month_transactions:
        if t["expense"] > 0:
            dow = t["date"].strftime("%A")
            dow_totals[dow] += t["expense"]

    # Previous month comparison
    prev_month = current_month - 1 if current_month > 1 else 12
    prev_year = current_year if current_month > 1 else current_year - 1
    prev_month_transactions = [
        t for t in transactions
        if t["date"].month == prev_month and t["date"].year == prev_year
    ]
    prev_month_expense = sum(t["expense"] for t in prev_month_transactions)
    prev_month_income = sum(t["income"] for t in prev_month_transactions)

    # Category comparison
    prev_category_totals = defaultdict(float)
    for t in prev_month_transactions:
        if t["expense"] > 0:
            prev_category_totals[t["category"]] += t["expense"]

    # Calculate this even when the previous month has no expenses. Previously
    # this was nested inside the loop and could leave six_month_avg undefined.
    six_months_ago = today - timedelta(days=180)
    six_month_transactions = [
        transaction for transaction in transactions
        if transaction["date"].replace(tzinfo=ZoneInfo(TIMEZONE)) >= six_months_ago
    ]
    six_month_expense = sum(
        transaction["expense"] for transaction in six_month_transactions
    )
    months_with_data = len({
        (transaction["date"].year, transaction["date"].month)
        for transaction in six_month_transactions
    })
    six_month_avg = six_month_expense / months_with_data if months_with_data else 0

    # Top expenses
    sorted_expenses = sorted(
        [t for t in current_month_transactions if t["expense"] > 0],
        key=lambda x: x["expense"],
        reverse=True
    )[:10]

    # Build prompt for Gemini
    prompt = f"""
You are a personal financial advisor analyzing the user's spending data for {today.strftime('%B %Y')}.

CURRENT MONTH DATA ({today.strftime('%B %Y')}):
- Total Expenses: ₹{total_expense:,.2f}
- Total Income: ₹{total_income:,.2f}
- Net Savings: ₹{total_income - total_expense:,.2f}
- Savings Rate: {((total_income - total_expense) / total_income * 100) if total_income > 0 else 0:.1f}%
- Days Elapsed: {today.day}
- Days Remaining in Month: {days_remaining}

CATEGORY BREAKDOWN (Current Month):
{json.dumps(dict(category_totals), indent=2)}

PREVIOUS MONTH COMPARISON ({datetime(prev_year, prev_month, 1).strftime('%B %Y')}):
- Total Expenses: ₹{prev_month_expense:,.2f}
- Total Income: ₹{prev_month_income:,.2f}
- Change: ₹{total_expense - prev_month_expense:+,.2f} ({(total_expense - prev_month_expense) / prev_month_expense * 100 if prev_month_expense > 0 else 0:+.1f}%)

CATEGORY COMPARISON:
{json.dumps(dict(prev_category_totals), indent=2)}

6-MONTH AVERAGE MONTHLY EXPENSE: ₹{six_month_avg:,.2f}
Current vs Average: {((total_expense - six_month_avg) / six_month_avg * 100) if six_month_avg > 0 else 0:+.1f}%

DAILY SPENDING PATTERN (Last 30 days):
{json.dumps(dict(daily_totals), indent=2)}

DAY OF WEEK PATTERN:
{json.dumps(dict(dow_totals), indent=2)}

TOP 10 EXPENSES THIS MONTH:
{json.dumps([{"item": t["item"], "amount": t["expense"], "category": t["category"], "date": t["date"].strftime("%d %b")} for t in sorted_expenses], indent=2)}

YOUR TASK:
Provide a comprehensive financial analysis with the following sections. Be specific, actionable, and encouraging.

Return ONLY valid JSON matching this schema:
{{
  "executive_summary": "2-3 sentence overview of financial health this month",
  "key_metrics": {{
    "total_expenses": {total_expense},
    "total_income": {total_income},
    "net_savings": {total_income - total_expense},
    "savings_rate_percent": {((total_income - total_expense) / total_income * 100) if total_income > 0 else 0},
    "projected_month_end_expenses": 0,
    "daily_average_spending": {total_expense / today.day if today.day > 0 else 0},
    "days_remaining_in_month": {days_remaining}
  }},
  "category_analysis": [
    {{"category": "Food", "current": 0, "previous": 0, "change_percent": 0, "trend": "up/down/stable", "insight": "string"}},
    ...
  ],
  "spending_patterns": {{
    "peak_spending_day": "string",
    "peak_spending_category": "string",
    "weekend_vs_weekday_ratio": 0,
    "most_expensive_time": "string",
    "pattern_insight": "string"
  }},
  "comparisons": {{
    "vs_last_month": {{"expense_change": 0, "income_change": 0, "savings_rate_change": 0, "summary": "string"}},
    "vs_6month_average": {{"difference_percent": 0, "summary": "string"}}
  }},
  "projected_forecast": {{
    "projected_total_expenses": 0,
    "projected_savings": 0,
    "confidence": "high/medium/low",
    "key_assumptions": ["string"]
  }},
  "wins": ["string"],
  "concerns": ["string"],
  "actionable_recommendations": [
    {{"priority": "high/medium/low", "action": "string", "impact": "string", "effort": "easy/medium/hard"}}
  ],
  "budget_health": {{
    "overall_status": "on_track/attention_needed/critical",
    "categories_over_budget": ["string"],
    "categories_near_limit": ["string"],
    "projected_over_budget": ["string"]
  }},
  "milestones": ["string"],
  "motivational_note": "string"
}}

RULES:
- Be specific with numbers and percentages
- Identify real patterns, not generic advice
- Celebrate genuine improvements
- Flag actual concerns with data
- Make recommendations actionable and specific
- Tone: encouraging but honest financial advisor
"""

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        data = json.loads(response.text)
        return data

    except Exception as e:
        print(f"Gemini analysis error: {e}")
        return {
            "error": str(e),
            "fallback": True,
            "executive_summary": f"You've spent ₹{total_expense:,.2f} this month with ₹{total_income:,.2f} income.",
            "key_metrics": {
                "total_expenses": total_expense,
                "total_income": total_income,
                "net_savings": total_income - total_expense,
                "savings_rate_percent": ((total_income - total_expense) / total_income * 100) if total_income > 0 else 0,
                "projected_month_end_expenses": 0,
                "daily_average_spending": total_expense / today.day if today.day > 0 else 0,
                "days_remaining_in_month": days_remaining,
            }
        }


def get_budget_config() -> dict:
    """Get user's budget configuration from environment or defaults."""
    # Could be extended to read from a config file or database
    # For now, return default budget structure
    return {
        "Food": 7000,
        "Transport": 3000,
        "Shopping": 5000,
        "Entertainment": 3000,
        "Health": 2000,
        "Utilities": 4000,
        "Education": 2000,
        "Personal": 2000,
        "Other": 2000,
    }


def calculate_budget_health(category_totals: dict, budget_config: dict) -> dict:
    """Calculate budget health status."""
    over_budget = []
    near_limit = []
    projected_over = []

    today = datetime.now(ZoneInfo(TIMEZONE))
    days_elapsed = today.day
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month_start = (month_start + timedelta(days=32)).replace(day=1)
    days_in_month = (next_month_start - timedelta(days=1)).day
    projection_factor = days_in_month / days_elapsed if days_elapsed > 0 else 1

    for category, budget in budget_config.items():
        spent = category_totals.get(category, 0)
        projected = spent * projection_factor

        if spent > budget:
            over_budget.append(f"{category} (₹{spent:,.0f}/₹{budget:,.0f})")
        elif spent > budget * 0.75:
            near_limit.append(f"{category} (₹{spent:,.0f}/₹{budget:,.0f}, {spent/budget*100:.0f}%)")
        elif projected > budget:
            projected_over.append(f"{category} (projected ₹{projected:,.0f}/₹{budget:,.0f})")

    if over_budget:
        overall = "critical"
    elif near_limit or projected_over:
        overall = "attention_needed"
    else:
        overall = "on_track"

    return {
        "overall_status": overall,
        "categories_over_budget": over_budget,
        "categories_near_limit": near_limit,
        "projected_over_budget": projected_over,
    }
