import asyncio
import logging
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from commands import command
from services.categories import infer_category
from services.google_sheets import append_transaction, get_last_expense, delete_expense


logger = logging.getLogger(__name__)
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
AMOUNT_PATTERN = r"(?:₹\s*)?(?:(?:\d{1,2}(?:,\d{2})*,\d{3})|(?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.\d{1,2})?"
TRANSACTION_REGEX = re.compile(
    rf"^/(expense|income|expensecash|incomecash)\s+(.+?)\s+({AMOUNT_PATTERN})(?:\s+(.+))?$",
    re.IGNORECASE,
)

DATE_AT_END_REGEX = re.compile(
    r"(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"(?:\s+(\d{2}|\d{4}))?$",
    re.IGNORECASE,
)


def _today() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE))


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == int(os.environ["ADMIN_ID"])


def _parse_month_date(day: int, month_text: str, year_text: str | None) -> datetime | None:
    current_year = _today().year
    if year_text:
        year_value = int(year_text)
        year = year_value + 2000 if len(year_text) == 2 else year_value
    else:
        year = current_year

    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(f"{day} {month_text} {year}", fmt)
        except ValueError:
            continue
    return None


def parse_date_and_description(description: str) -> tuple[str, str]:
    """Extract a trailing date such as '13 Aug' or '13 August 2026'."""
    today = _today()
    if not description:
        return f"{today.day} {today.strftime('%b %y')}", ""

    cleaned = description.strip()
    date_match = DATE_AT_END_REGEX.search(cleaned)
    if not date_match:
        return f"{today.day} {today.strftime('%b %y')}", cleaned

    transaction_date = _parse_month_date(
        int(date_match.group(1)),
        date_match.group(2),
        date_match.group(3),
    )
    if transaction_date is None:
        return f"{today.day} {today.strftime('%b %y')}", cleaned

    remaining_description = cleaned[:date_match.start()].strip()
    return (
        f"{transaction_date.day} {transaction_date.strftime('%b %y')}",
        remaining_description,
    )


async def handle_transaction(
    update: Update,
    transaction_type: str,
    payment_method: str = "Bank",
):
    message = update.effective_message
    if not is_admin(update):
        await message.reply_text("⛔ You are not authorized to use this command.")
        return

    match = TRANSACTION_REGEX.match((message.text or "").strip())
    if not match:
        await message.reply_text(
            "❌ Invalid format.\n\n"
            "Examples:\n"
            "/expense chicken 200\n"
            "/expense shoes ₹2,600 size 10\n"
            "/expense ice cream 250 13 August\n"
            "/income salary 41,667\n"
            "/expensecash turf 200\n"
            "/incomecash tips 500"
        )
        return

    command_name, item, amount_text, description = match.groups()
    if "cash" in command_name.lower():
        payment_method = "Cash"
        transaction_type = "expense" if "expense" in command_name.lower() else "income"
    else:
        payment_method = "Bank"

    amount = float(amount_text.replace("₹", "").replace(",", "").strip())
    transaction_date, description = parse_date_and_description(description or "")
    category = infer_category(item.strip(), description)

    try:
        saved = await asyncio.to_thread(
            append_transaction,
            date=transaction_date,
            item=item.strip(),
            amount=f"{amount:.2f}",
            transaction_type=transaction_type,
            description=description,
            payment_method=payment_method,
            category=category,
        )
    except Exception:
        logger.exception("Could not save slash-command transaction")
        await message.reply_text(
            "⚠️ I couldn't save that transaction to Google Sheets. "
            "No success was recorded, so please try again in a moment."
        )
        return

    await message.reply_text(
        f"✅ {transaction_type.capitalize()} added ({payment_method}): "
        f"₹{amount:,.2f} for {item.strip()}\n"
        f"Category: {category} · Sheet: {saved['worksheet_title']}"
    )


@command("expense", "Add an expense")
async def expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_transaction(update, "expense")


@command("income", "Add income")
async def income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_transaction(update, "income")


@command("expensecash", "Add a cash expense")
async def expensecash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_transaction(update, "expense", payment_method="Cash")


@command("incomecash", "Add cash income")
async def incomecash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_transaction(update, "income", payment_method="Cash")


@command("undoexpense", "Undo the most recent expense")
async def undoexpense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.effective_message.reply_text("⛔ You are not authorized to use this command.")
        return

    expense_data = await asyncio.to_thread(get_last_expense)
    if not expense_data:
        await update.effective_message.reply_text("ℹ️ No expense found to undo.")
        return

    worksheet_title = expense_data["worksheet_title"]
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Yes",
                callback_data=f"undo_yes:{expense_data['row_number']}:{worksheet_title}",
            ),
            InlineKeyboardButton("❌ No", callback_data="undo_no"),
        ]
    ])
    await update.effective_message.reply_text(
        f'Are you sure you want to delete "{expense_data["item"]} '
        f'₹{expense_data["amount"]}" from {worksheet_title}?',
        reply_markup=keyboard,
    )


async def undo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        await query.edit_message_text("⛔ You are not authorized to use this.")
        return

    if query.data == "undo_no":
        await query.edit_message_text("❌ Undo cancelled.")
        return

    parts = query.data.split(":", 2)
    row_number = int(parts[1])
    worksheet_title = parts[2] if len(parts) > 2 else None
    await asyncio.to_thread(delete_expense, row_number, worksheet_title)
    await query.edit_message_text("✅ Last expense has been removed.")
