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

def infer_category(item: str, description: str) -> str:
    """Infer category from item and description."""
    text = f"{item} {description}".lower()

    categories = {
        "food": ["food", "restaurant", "cafe", "coffee", "lunch", "dinner", "breakfast", "groceries", "grocery", "zomato", "swiggy", "delivery", "meal", "eat", "snack", "drink", "water", "juice", "beer", "wine", "alcohol", "ice cream", "icecream", "dessert", "cake", "chocolate", "pizza", "burger", "sandwich", "mamma"],
        "transport": ["uber", "ola", "taxi", "cab", "auto", "metro", "bus", "train", "fuel", "petrol", "diesel", "parking", "toll", "transport", "travel", "flight", "ticket"],
        "shopping": ["amazon", "flipkart", "shopping", "clothes", "clothing", "shoes", "shirt", "pants", "dress", "electronics", "phone", "laptop", "gadget", "accessory", "bag", "watch", "jewelry", "cosmetic", "makeup", "skincare"],
        "entertainment": ["movie", "cinema", "theatre", "netflix", "prime", "hotstar", "spotify", "subscription", "game", "gaming", "concert", "event", "party", "club", "bar", "pub", "entertainment", "turf", "agnels", "sports", "football", "cricket", "tennis", "badminton", "gym", "fitness"],
        "health": ["medicine", "pharmacy", "doctor", "hospital", "clinic", "medical", "health", "dental", "eye", "checkup", "test", "lab", "insurance", "gym", "fitness", "yoga", "therapy"],
        "utilities": ["electricity", "water", "gas", "internet", "wifi", "broadband", "mobile", "phone bill", "recharge", "utility", "bill", "rent", "maintenance"],
        "education": ["course", "book", "education", "learning", "training", "certification", "udemy", "coursera", "workshop", "seminar"],
        "personal": ["haircut", "salon", "spa", "grooming", "personal", "gift", "donation", "charity", "pet", "veterinary"],
    }

    for category, keywords in categories.items():
        if any(keyword in text for keyword in keywords):
            return category.title()

    return "Other"


async def analyze_financial_data(transactions: list[dict]) -> dict:
    """Analyze financial data using Gemini AI for insights."""

    if not transactions:
        return {"error": "No transactions found"}

    # Prepare data summary for AI
    current_month = datetime.now(ZoneInfo(TIMEZONE)).month
    current_year = datetime.now(ZoneInfo(TIMEZONE)).year

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
    thirty_days_ago = datetime.now(
        ZoneInfo(TIMEZONE)
    ) - timedelta(days=30)

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
            # 6-month average
            six_months_ago = datetime.now(
                ZoneInfo(TIMEZONE)
            ) - timedelta(days=180)

            six_month_transactions = [
                t for t in transactions
                if t["date"].replace(
                    tzinfo=ZoneInfo(TIMEZONE)
                ) >= six_months_ago
            ]

            six_month_expense = sum(
                t["expense"] for t in six_month_transactions
            )

            months_with_data = len({
                (t["date"].year, t["date"].month)
                for t in six_month_transactions
            })

            six_month_avg = (
                six_month_expense / months_with_data
                if months_with_data > 0
                else 0
            )

    # Top expenses
    sorted_expenses = sorted(
        [t for t in current_month_transactions if t["expense"] > 0],
        key=lambda x: x["expense"],
        reverse=True
    )[:10]

    # Build prompt for Gemini
    prompt = f"""
You are a personal financial advisor analyzing the user's spending data for {datetime.now().strftime('%B %Y')}.

CURRENT MONTH DATA ({datetime.now().strftime('%B %Y')}):
- Total Expenses: ₹{total_expense:,.2f}
- Total Income: ₹{total_income:,.2f}
- Net Savings: ₹{total_income - total_expense:,.2f}
- Savings Rate: {((total_income - total_expense) / total_income * 100) if total_income > 0 else 0:.1f}%
- Days Elapsed: {datetime.now().day}
- Days Remaining in Month: {(datetime(current_year, current_month + 1, 1) - timedelta(days=1)).day - datetime.now().day if current_month < 12 else (datetime(current_year + 1, 1, 1) - timedelta(days=1)).day - datetime.now().day}

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
    "daily_average_spending": {total_expense / datetime.now().day if datetime.now().day > 0 else 0},
    "days_remaining_in_month": {(datetime(current_year, current_month + 1, 1) - timedelta(days=1)).day - datetime.now().day if current_month < 12 else (datetime(current_year + 1, 1, 1) - timedelta(days=1)).day - datetime.now().day}
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
        response = client.models.generate_content(
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
                "daily_average_spending": total_expense / datetime.now().day if datetime.now().day > 0 else 0,
                "days_remaining_in_month": 0,
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

    days_elapsed = datetime.now().day
    days_in_month = (datetime(datetime.now().year, datetime.now().month + 1, 1) - timedelta(days=1)).day if datetime.now().month < 12 else 31
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
