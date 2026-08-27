# Telegram Finance Bot

A dedicated Telegram bot for personal finance management with AI-powered insights.

## Features

- **Expense Tracking**: Log expenses with `/expense item amount [description] [date]`
- **Income Tracking**: Log income with `/income item amount [description] [date]`
- **Cash Transactions**: Track cash payments with `/expensecash` and `/incomecash`
- **Undo**: Undo the last expense with `/undoexpense`
- **Budget Summary**: Get AI-powered financial analysis with `/budgetsummary`

## Commands

- `/expense <item> <amount> [description] [date]` - Add a bank expense
- `/income <item> <amount> [description] [date]` - Add bank income
- `/expensecash <item> <amount> [description] [date]` - Add a cash expense
- `/incomecash <item> <amount> [description] [date]` - Add cash income
- `/undoexpense` - Undo the most recent expense
- `/budgetsummary` - Get comprehensive financial summary with AI insights

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your credentials
4. Run the bot: `python bot.py`

## Environment Variables

See `.env.example` for required configuration.

## Google Sheets Integration

The bot stores transactions in Google Sheets with the following structure:

| Date | Item | Expense | Income | Remaining | Description | Payment Method | Category |
|------|------|---------|--------|-----------|-------------|----------------|----------|

Each month has its own worksheet (e.g., "August", "September").

## AI Analysis

The bot uses Google Gemini to provide:
- Monthly spending insights
- Category breakdowns
- Budget health checks
- Month-over-month comparisons
- Personalized recommendations
- Spending pattern analysis
