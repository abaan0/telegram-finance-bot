"""Google Sheets storage for the personal finance bot.

Monthly worksheets are resolved from the transaction date. Missing months are
created by duplicating the previous month's sheet, clearing the transaction
area, and inserting an opening-balance row. Spreadsheet/client connections are
cached for the lifetime of the bot process.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials


logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")

# A single-user bot does not need to re-authenticate or reopen the spreadsheet
# for every transaction. These caches are refreshed automatically for sheets
# created by this module; restart the bot after manually renaming a worksheet.
_worksheet_lock = threading.RLock()
_write_lock = threading.Lock()
_worksheet_cache: dict[str, Any] | None = None
_resolved_month_cache: dict[tuple[int, int], Any] = {}
_initialized_months: set[tuple[int, int]] = set()


def _today() -> date:
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def _parse_date(value: date | datetime | str | None) -> date:
    if value is None:
        return _today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    raw = str(value).strip()
    formats = (
        "%Y-%m-%d",
        "%d %b %y",
        "%d %b %Y",
        "%d %B %Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unsupported transaction date: {value!r}")


def _display_date(value: date | datetime | str) -> str:
    parsed = _parse_date(value)
    return f"{parsed.day} {parsed.strftime('%b %y')}"


def _parse_sheet_date(value: str | None) -> date | None:
    if value is None or not str(value).strip():
        return None
    try:
        return _parse_date(str(value))
    except (TypeError, ValueError):
        return None


def _month_key(value: date) -> tuple[int, int]:
    return (value.year, value.month)


def _previous_month(value: date) -> date:
    return (value.replace(day=1) - timedelta(days=1)).replace(day=1)


def _month_title_candidates(value: date) -> list[str]:
    full = value.strftime("%B")
    short = value.strftime("%b")
    yy = value.strftime("%y")
    yyyy = value.strftime("%Y")
    # Existing user-defined titles remain supported. New tabs use "Nov 26".
    return [
        f"{short} {yy}",
        f"{short} {yyyy}",
        f"{full} {yyyy}",
        f"{full} {yy}",
        short,
        full,
    ]


def _credentials():
    credentials_json = os.getenv("GOOGLE_CREDENTIALS")
    if credentials_json:
        return Credentials.from_service_account_info(
            json.loads(credentials_json), scopes=SCOPES
        )

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE") or os.path.join(
        project_root, "credentials", "google-service-account.json"
    )
    if not os.path.isfile(credentials_file):
        raise FileNotFoundError(
            "Google credentials were not found. Set GOOGLE_CREDENTIALS or "
            "GOOGLE_CREDENTIALS_FILE to your service-account credentials."
        )
    return Credentials.from_service_account_file(credentials_file, scopes=SCOPES)


@lru_cache(maxsize=1)
def _get_spreadsheet():
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    client = gspread.authorize(_credentials())
    return client.open_by_key(spreadsheet_id)


def _worksheets_by_title() -> dict[str, Any]:
    global _worksheet_cache
    with _worksheet_lock:
        if _worksheet_cache is None:
            _worksheet_cache = {
                worksheet.title: worksheet
                for worksheet in _get_spreadsheet().worksheets()
            }
        return _worksheet_cache


def _refresh_worksheet_cache() -> dict[str, Any]:
    global _worksheet_cache
    with _worksheet_lock:
        _worksheet_cache = {
            worksheet.title: worksheet
            for worksheet in _get_spreadsheet().worksheets()
        }
        return _worksheet_cache


def _worksheet_years(worksheet: Any) -> set[int]:
    years: set[int] = set()
    for raw_date in worksheet.col_values(1)[1:]:
        parsed = _parse_sheet_date(raw_date)
        if parsed:
            years.add(parsed.year)
    return years


def _find_existing_month_sheet(target: date) -> Any | None:
    key = _month_key(target)
    if key in _resolved_month_cache:
        return _resolved_month_cache[key]

    sheets = _worksheets_by_title()

    # Year-aware tabs are unambiguous and take precedence.
    for title in _month_title_candidates(target)[:4]:
        worksheet = sheets.get(title)
        if worksheet is not None:
            _resolved_month_cache[key] = worksheet
            return worksheet

    # Older tabs such as "Sep", "Aug", and "October" have no year in their
    # names. Prefer a populated tab whose rows belong to the requested year
    # before considering an empty placeholder tab for the current year.
    empty_candidates = []
    for title in dict.fromkeys(_month_title_candidates(target)[4:]):
        worksheet = sheets.get(title)
        if worksheet is None:
            continue
        years = _worksheet_years(worksheet)
        if years == {target.year}:
            _resolved_month_cache[key] = worksheet
            return worksheet
        if not years:
            empty_candidates.append(worksheet)

    if empty_candidates and target.year == _today().year:
        worksheet = empty_candidates[0]
        _resolved_month_cache[key] = worksheet
        return worksheet

    return None


def _carryover_formula(source_sheet_title: str) -> str:
    """Build a live reference to the previous worksheet's closing bank balance."""
    escaped_title = source_sheet_title.replace("'", "''")
    quoted_title = f"'{escaped_title}'"
    return (
        f'=SUMIF({quoted_title}!$G:$G,"Bank",{quoted_title}!$D:$D)-'
        f'SUMIF({quoted_title}!$G:$G,"Bank",{quoted_title}!$C:$C)'
    )


def _to_amount(value: str | int | float | None) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "").replace("₹", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        # Formula text is not expected with FORMATTED_VALUE (the default), but
        # ignoring it is safer than failing a transaction save.
        return 0.0


def _find_most_recent_prior_sheet(target: date) -> Any | None:
    """Find the latest worksheet with dated transactions before target month."""
    target_key = _month_key(target)
    latest_key: tuple[int, int] | None = None
    latest_sheet = None

    for worksheet in _worksheets_by_title().values():
        sheet_months = set()
        for raw_date in worksheet.col_values(1)[1:]:
            parsed = _parse_sheet_date(raw_date)
            if parsed:
                key = _month_key(parsed)
                if key < target_key:
                    sheet_months.add(key)
        if sheet_months:
            candidate_key = max(sheet_months)
            if latest_key is None or candidate_key > latest_key:
                latest_key = candidate_key
                latest_sheet = worksheet

    return latest_sheet


def _find_template_sheet(target: date) -> Any | None:
    """Prefer the immediately previous month; otherwise use a prior sheet."""
    previous = _previous_month(target)
    previous_sheet = _find_existing_month_sheet(previous)
    if previous_sheet is not None:
        return previous_sheet

    prior_sheet = _find_most_recent_prior_sheet(target)
    if prior_sheet is not None:
        return prior_sheet

    # Formatting fallback only. It does not imply a carryover amount.
    sheets = list(_worksheets_by_title().values())
    return sheets[-1] if sheets else None


def _create_month_sheet(target: date) -> Any:
    spreadsheet = _get_spreadsheet()
    existing = _worksheets_by_title()
    title = f"{target.strftime('%b')} {target.strftime('%y')}"
    if title in existing:
        _resolved_month_cache[_month_key(target)] = existing[title]
        return existing[title]

    previous = _previous_month(target)
    previous_sheet = _find_existing_month_sheet(previous)
    # If a month had no tab at all, carry forward the most recent known balance
    # instead of resetting to zero. No transactions in a month means no ledger
    # movement was recorded for that month.
    balance_source = previous_sheet or _find_most_recent_prior_sheet(target)
    template = previous_sheet or balance_source or _find_template_sheet(target)

    if template is not None:
        worksheet = spreadsheet.duplicate_sheet(
            source_sheet_id=template.id,
            new_sheet_name=title,
            insert_sheet_index=len(existing),
        )
        # Keep the previous month’s formatting, helper formulas, and summary
        # cells (J onward), but clear old transaction rows and balance formulas.
        clear_through = max(2, int(getattr(worksheet, "row_count", 1000)))
        worksheet.batch_clear([f"A2:H{clear_through}"])
    else:
        worksheet = spreadsheet.add_worksheet(
            title=title,
            rows=1000,
            cols=15,
        )
        worksheet.update(
            values=[[
                "Date", "Item", "Expenses", "Income", "Remaining",
                "Description", "Payment Method", "Category",
            ]],
            range_name="A1:H1",
            value_input_option="RAW",
        )

    # A formula keeps the opening balance in sync if a transaction is later
    # added to the preceding month. If no earlier sheet exists, start at zero.
    opening_balance = (
        _carryover_formula(balance_source.title)
        if balance_source is not None
        else "0.00"
    )
    opening_row = [
        _display_date(target.replace(day=1)),
        "previous month carry over",
        "",
        opening_balance,
        _remaining_formula(2),
        "",
        "Bank",
        "",
    ]
    worksheet.update(
        values=[opening_row],
        range_name="A2:H2",
        value_input_option="USER_ENTERED",
    )

    # Register the duplicate immediately so later transactions do not need to
    # fetch the worksheet list again.
    with _worksheet_lock:
        if _worksheet_cache is None:
            _refresh_worksheet_cache()
        else:
            _worksheet_cache[title] = worksheet
        _resolved_month_cache[_month_key(target)] = worksheet
        _initialized_months.add(_month_key(target))

    logger.info(
        "Created monthly worksheet %s with carryover source %s",
        title,
        balance_source.title if balance_source is not None else "none (₹0.00)",
    )
    return worksheet


def _remaining_formula(row_number: int) -> str:
    return (
        f'=IF(OR(C{row_number}<>"",D{row_number}<>""),'
        f'SUMIF($G$2:$G{row_number},"Bank",$D$2:$D{row_number})-'
        f'SUMIF($G$2:$G{row_number},"Bank",$C$2:$C{row_number}),"")'
    )


def get_sheet(
    transaction_date: date | datetime | str | None = None,
    *,
    create: bool = True,
):
    """Return the worksheet matching the transaction date.

    Set create=False for read-only operations such as undo lookup, so merely
    checking for a transaction does not create a fresh monthly worksheet.
    """
    parsed_date = _parse_date(transaction_date)
    key = _month_key(parsed_date)
    with _worksheet_lock:
        cached = _resolved_month_cache.get(key)
        if cached is not None:
            if create and key not in _initialized_months:
                _initialize_empty_month(cached, parsed_date)
            return cached

        worksheet = _find_existing_month_sheet(parsed_date)
        if worksheet is not None:
            _resolved_month_cache[key] = worksheet
            if create:
                _initialize_empty_month(worksheet, parsed_date)
            return worksheet

        if not create:
            return None
        return _create_month_sheet(parsed_date)


def _initialize_empty_month(worksheet: Any, target: date) -> None:
    """Initialize a pre-created but empty month tab with its opening balance."""
    key = _month_key(target)
    if key in _initialized_months:
        return

    dates = worksheet.col_values(1)
    # Only initialize genuinely empty tabs. Existing ledgers must not be
    # silently rewritten or have transactions shifted around.
    if len(dates) > 1 and any(str(value).strip() for value in dates[1:]):
        _initialized_months.add(key)
        return

    previous = _previous_month(target)
    previous_sheet = _find_existing_month_sheet(previous)
    balance_source = previous_sheet or _find_most_recent_prior_sheet(target)
    opening_balance = (
        _carryover_formula(balance_source.title)
        if balance_source is not None
        else "0.00"
    )
    opening_row = [
        _display_date(target.replace(day=1)),
        "previous month carry over",
        "",
        opening_balance,
        _remaining_formula(2),
        "",
        "Bank",
        "",
    ]
    worksheet.update(
        values=[opening_row],
        range_name="A2:H2",
        value_input_option="USER_ENTERED",
    )
    _initialized_months.add(key)
    logger.info(
        "Initialized existing empty worksheet %s with carryover source %s",
        worksheet.title,
        balance_source.title if balance_source is not None else "none (₹0.00)",
    )


def get_all_months_data() -> list[dict]:
    """Fetch transactions for summaries; carryover is not treated as earned income."""
    all_transactions: list[dict] = []

    for worksheet in _worksheets_by_title().values():
        try:
            rows = worksheet.get_all_values()
            if len(rows) < 2:
                continue

            for row in rows[1:]:
                if len(row) < 4:
                    continue

                date_text = row[0].strip()
                item = row[1].strip() if len(row) > 1 else ""
                if not date_text:
                    continue
                # Carryover affects the spreadsheet's bank balance but is not
                # new income for budget/earnings analysis.
                if item.casefold().replace(" ", "") in {
                    "previousmonthcarryover", "previousmonthcarryoverbalance"
                }:
                    continue

                transaction_date = _parse_sheet_date(date_text)
                if transaction_date is None:
                    continue

                expense = _to_amount(row[2] if len(row) > 2 else "")
                income = _to_amount(row[3] if len(row) > 3 else "")
                if expense <= 0 and income <= 0:
                    continue

                description = row[5].strip() if len(row) > 5 else ""
                payment_method = row[6].strip() if len(row) > 6 else ""
                # Category is column H (index 7), not G/payment method.
                category = row[7].strip() if len(row) > 7 else ""
                all_transactions.append({
                    "date": datetime.combine(transaction_date, datetime.min.time()),
                    "item": item,
                    "expense": expense,
                    "income": income,
                    "description": description,
                    "payment_method": payment_method,
                    "category": category or "Other",
                    "month": worksheet.title,
                })
        except Exception:
            logger.exception("Error reading worksheet %s", worksheet.title)
            continue

    return all_transactions


def append_transaction(
    date: str | date | datetime,
    item: str,
    amount: str | int | float,
    transaction_type: str,
    description: str,
    payment_method: str = "Bank",
    category: str = "",
) -> dict[str, Any]:
    """Append a transaction to the worksheet for its actual transaction date."""
    if transaction_type not in {"expense", "income"}:
        raise ValueError("transaction_type must be 'expense' or 'income'")
    if payment_method not in {"Bank", "Cash"}:
        raise ValueError("payment_method must be 'Bank' or 'Cash'")

    parsed_date = _parse_date(date)
    numeric_amount = round(_to_amount(amount), 2)
    if numeric_amount < 0:
        raise ValueError("Transaction amount cannot be negative")

    # Avoid allocating the same row if two Telegram updates arrive together.
    with _write_lock:
        sheet = get_sheet(parsed_date)
        dates = sheet.col_values(1)
        next_row = max(2, len(dates) + 1)

        row = [
            _display_date(parsed_date),
            item.strip(),
            f"{numeric_amount:.2f}" if transaction_type == "expense" else "",
            f"{numeric_amount:.2f}" if transaction_type == "income" else "",
            _remaining_formula(next_row),
            description.strip(),
            payment_method,
            category.strip(),
        ]
        sheet.update(
            values=[row],
            range_name=f"A{next_row}:H{next_row}",
            value_input_option="USER_ENTERED",
        )

    return {
        "worksheet_title": sheet.title,
        "row_number": next_row,
        "date": parsed_date.isoformat(),
        "item": item.strip(),
        "amount": numeric_amount,
        "transaction_type": transaction_type,
        "payment_method": payment_method,
        "category": category.strip(),
    }


def get_last_expense():
    sheet = get_sheet(create=False)
    if sheet is None:
        return None
    rows = sheet.get_all_values()

    for row_number in range(len(rows), 1, -1):
        row = rows[row_number - 1]
        if len(row) >= 3 and row[2].strip():
            return {
                "row_number": row_number,
                "item": row[1] if len(row) > 1 else "",
                "amount": row[2],
                "worksheet_title": sheet.title,
            }
    return None


def delete_transaction(row_number: int, worksheet_title: str | None = None):
    """Delete a specific transaction row from the named worksheet."""
    sheet = None
    if worksheet_title:
        sheet = _worksheets_by_title().get(worksheet_title)
    if sheet is None:
        sheet = get_sheet()
    sheet.delete_rows(row_number)


def delete_expense(row_number: int, worksheet_title: str | None = None):
    """Backward-compatible wrapper used by the /undoexpense command."""
    return delete_transaction(row_number, worksheet_title)
