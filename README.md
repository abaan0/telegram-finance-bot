# Telegram Finance Bot

A dedicated Telegram bot for personal finance management with AI-powered insights.

## Features

- **Expense Tracking**: Log expenses with `/expense item amount [description] [date]`
- **Income Tracking**: Log income with `/income item amount [description] [date]`
- **Cash Transactions**: Track cash payments with `/expensecash` and `/incomecash`
- **Undo**: Undo the last expense with `/undoexpense`
- **Budget Summary**: Get AI-powered financial analysis with `/budgetsummary`
- **Optional Fast Entry**: Save very clear natural-language transactions automatically, with an Undo button

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
4. Set `SPREADSHEET_ID`, `BOT_TOKEN`, `ADMIN_ID`, and `GEMINI_API_KEY`. Set either `GOOGLE_CREDENTIALS` (service-account JSON as a string) or `GOOGLE_CREDENTIALS_FILE` (path to the JSON file).
5. For optional fast entry, set `FAST_ENTRY_MODE=true`; the default `false` keeps Confirm/Cancel for every natural-language transaction. You can set `FAST_ENTRY_MIN_CONFIDENCE` (default `0.92`) to control how clear a message must be before auto-save. Each fast save has an Undo button.
6. Run the bot: `python bot.py`

## Environment Variables

See `.env.example` for required configuration.

## Google Sheets Integration

The bot stores transactions in Google Sheets with the following structure:

| Date | Item | Expense | Income | Remaining | Description | Payment Method | Category |
|------|------|---------|--------|-----------|-------------|----------------|----------|

Each month has its own worksheet. Existing names such as `Aug`, `Sep`, and `October` are supported. New worksheets use short year-aware names such as `Nov 26` so next year's months do not collide with this year's. When a month is missing, the bot duplicates the previous month's layout, clears the old transaction rows, and inserts a carryover row that references the prior month's bank balance. Transactions dated in a previous month are written to that month's worksheet. The category is read from column H, and carryover is excluded from income in AI budget analysis.

## AI Analysis

The bot uses Google Gemini to provide:
- Monthly spending insights
- Category breakdowns
- Budget health checks
- Month-over-month comparisons
- Personalized recommendations
- Spending pattern analysis
