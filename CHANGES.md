# Changes in this update

## Monthly sheets and carryover
- The transaction date selects the worksheet, so a late September entry goes to `Sep` instead of whichever month is current.
- Existing abbreviated or full month names such as `Aug`, `Sep`, and `October` remain supported when the sheet data matches the requested year.
- Missing months are created automatically by duplicating a prior worksheet, clearing the old A:H transaction data while preserving layout and helper formulas, and creating an opening-balance row.
- New tabs use compact year-aware names such as `Nov 26` to avoid collisions in later years.
- The carryover amount is a formula referencing the previous month's bank income and expenses, so a later correction in that source sheet can update the opening balance.

## Transaction handling
- Google Sheets client and worksheet metadata are cached while the bot is running.
- Blocking Sheets calls run in worker threads from async Telegram handlers.
- Pending natural-language confirmations use unique IDs, so confirming one message does not save another message's transaction.
- Slash commands accept common amount formats including `₹2,600`, `41,667`, and Indian grouping such as `₹2,50,000`.
- Slash-command transactions now get a category, and budget summaries read the category from column H.
- Carryover rows are excluded from earned-income totals in the AI budget analysis.
- Fast entry is optional. `FAST_ENTRY_MODE=false` remains the default. When enabled, clear transactions above `FAST_ENTRY_MIN_CONFIDENCE` save automatically and show an Undo button.
- The async budget summary no longer blocks the event loop while reading Sheets or waiting for Gemini.
- Google Sheets updates use keyword arguments compatible with `gspread` 6.x.

## Verification
- Python compilation passed.
- Six automated unit tests passed using mocked Google Sheets / Telegram interfaces.
- No live Google Sheets, Telegram, or Gemini transaction was made during testing. Do one manual test in your own spreadsheet before relying on month-end automation.

## Deployment notes
- Keep the current secrets in your hosting environment; this ZIP does not include `.env`, Google service-account JSON, `.git` history, or Python cache files.
- The bot reads `GOOGLE_CREDENTIALS` or `GOOGLE_CREDENTIALS_FILE` for Google credentials.
- Test the next-month flow by using a separate test worksheet or a temporary date in a test copy of your spreadsheet before relying on the first live rollover.
