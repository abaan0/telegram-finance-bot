# Telegram Finance Bot

A personal finance tracking bot built with Telegram, Google Sheets, and Google Gemini. Log transactions using commands or natural language, automatically organize them by month, track bank and cash balances, and receive AI-powered spending insights.

## Features

- **Expense Tracking:** Record bank expenses using `/expense` or natural language.
- **Income Tracking:** Record bank income using `/income` or natural language.
- **Cash Transactions:** Track cash income and expenses separately from bank transactions.
- **Automatic Monthly Worksheets:** Create missing monthly worksheets automatically using the previous month's layout.
- **Balance Carryover:** Carry forward the previous month's closing bank balance into the new month's worksheet.
- **Backdated Transactions:** Automatically save transactions to the worksheet corresponding to their transaction date, rather than the current month.
- **Natural-Language Parsing:** Extract transaction details such as item, amount, date, payment method, and category from everyday messages using Gemini.
- **Transaction Confirmation:** Review and confirm parsed natural-language transactions before they are saved.
- **Optional Fast Entry:** Automatically save sufficiently clear natural-language transactions without requiring confirmation, with an Undo button.
- **Undo Expense:** Remove the most recently recorded expense using `/undoexpense`.
- **AI Budget Analysis:** Generate spending summaries, category breakdowns, budget health checks, and personalized recommendations.
- **Flexible Amount Formats:** Handle commonly used amount formats, including values such as `₹2,600` and `₹2,50,000`.

## Commands

| Command | Description |
|---|---|
| `/expense <item> <amount> [description] [date]` | Record a bank expense |
| `/income <item> <amount> [description] [date]` | Record bank income |
| `/expensecash <item> <amount> [description] [date]` | Record a cash expense |
| `/incomecash <item> <amount> [description] [date]` | Record cash income |
| `/undoexpense` | Undo the most recent expense |
| `/budgetsummary` | Generate a financial summary with AI-powered insights |

Dates and descriptions are optional where supported. Natural-language messages can be used when you do not want to enter a transaction through a command.

## How It Works

1. Send a transaction command or describe a transaction in natural language.
2. The bot extracts the relevant transaction details.
3. Depending on the entry mode, confirm the transaction or allow a sufficiently clear transaction to be saved automatically.
4. The bot writes the transaction to the appropriate Google Sheets worksheet.
5. Use `/budgetsummary` to review spending patterns and receive AI-generated insights.

## Google Sheets Integration

Transactions are stored in Google Sheets, with a separate worksheet for each month.

The worksheet uses the following columns:

| Column | Field |
|---|---|
| A | Date |
| B | Item |
| C | Expenses |
| D | Income |
| E | Remaining |
| F | Description |
| G | Payment Method |
| H | Category |

### Automatic Monthly Management

- **Worksheet creation:** When a required monthly worksheet does not exist, the bot creates it using the previous month's layout.
- **Carryover balance:** The new worksheet starts with a carryover row based on the previous month's closing bank balance.
- **Backdated transactions:** Transactions are recorded in the worksheet matching their transaction date, including transactions from previous months.
- **Year-aware worksheet names:** Existing names such as `Aug`, `Sep`, and `October` are supported. New worksheets use compact names such as `Nov 26` to avoid month-name collisions across years.
- **Balance calculations:** Bank and cash transactions are tracked separately using the spreadsheet's balance formulas and helper calculations.
- **Category analysis:** The bot reads transaction categories from column H.
- **Accurate income reporting:** Carryover balances are excluded from earned-income totals in AI budget analysis.

## AI Budget Analysis

The `/budgetsummary` command uses Google Gemini to analyze your financial data and provide:

- Monthly spending insights
- Expense breakdowns by category
- Budget health checks
- Month-over-month comparisons
- Spending pattern analysis
- Personalized recommendations

Carryover balances are handled separately from earned income to avoid inflating income totals in the analysis.

## Setup

### Prerequisites

- Python installed on your system
- A Telegram bot created through [BotFather](https://t.me/BotFather)
- A Google Cloud service account with access to the Google Sheets API
- A Google spreadsheet for storing transactions
- A Google Gemini API key

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/abaan0/telegram-finance-bot.git
   cd telegram-finance-bot
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create your environment configuration:

   ```bash
   cp .env.example .env
   ```

   On Windows Command Prompt, you can copy the file using:

   ```cmd
   copy .env.example .env
   ```

4. Configure the required environment variables in `.env`.

5. Ensure your Google service account has the required permissions to access and edit the target spreadsheet.

6. Start the bot:

   ```bash
   python bot.py
   ```

## Environment Variables

Configure the following variables in your `.env` file:

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token obtained from BotFather |
| `ADMIN_ID` | Telegram user ID authorized to use the bot |
| `SPREADSHEET_ID` | ID of the Google spreadsheet used for transactions |
| `GEMINI_API_KEY` | API key used for natural-language parsing and AI budget analysis |
| `GOOGLE_CREDENTIALS` | Optional service-account JSON credentials supplied as a string |
| `GOOGLE_CREDENTIALS_FILE` | Optional path to a service-account JSON credentials file |
| `FAST_ENTRY_MODE` | Enables automatic saving of sufficiently clear natural-language transactions; defaults to `false` |
| `FAST_ENTRY_MIN_CONFIDENCE` | Minimum confidence threshold for automatic saving; defaults to `0.92` |

Set either `GOOGLE_CREDENTIALS` or `GOOGLE_CREDENTIALS_FILE` to configure Google Sheets authentication.

### Fast Entry Mode

By default, `FAST_ENTRY_MODE=false`, so natural-language transactions follow the normal confirmation process.

To enable automatic saving of sufficiently clear transactions:

```env
FAST_ENTRY_MODE=true
FAST_ENTRY_MIN_CONFIDENCE=0.92
```

When enabled, transactions meeting the configured confidence threshold can be saved automatically. Each fast-saved transaction provides an Undo button.

Keep fast entry disabled if you prefer to review every transaction before it is recorded.

## Configuration and Security

- Keep `.env` and service-account credential files private.
- Never commit bot tokens, API keys, or service-account credentials to a public repository.
- Ensure the Google service account has access to the correct spreadsheet.
- Back up your spreadsheet regularly, since it contains your financial records.
- Review automatically parsed transactions and AI-generated insights when accuracy matters.

## Technology Stack

- **Python** for the bot and transaction-processing logic
- **Python Telegram Bot** for Telegram commands and interactions
- **Google Sheets API** for storing and organizing transactions
- **gspread** for Google Sheets integration
- **Google Gemini** for natural-language transaction parsing and financial analysis

## Repository

GitHub: [abaan0/telegram-finance-bot](https://github.com/abaan0/telegram-finance-bot)
