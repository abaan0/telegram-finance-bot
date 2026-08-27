import os
import re
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from commands import command
from services.google_sheets import (
    append_transaction,
    get_last_expense,
    delete_expense,
)


TRANSACTION_REGEX = re.compile(
    r"^/(expense|income|expensecash|incomecash)\s+(.+?)\s+([1-9]\d*(?:\.\d{1,2})?)"
    r"(?:\s+(.+))?$",
    re.IGNORECASE,
)

DATE_REGEX = re.compile(
    r"^(.*?)(?:\s+)(\d{1,2})[ /-]"
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|"
    r"Oct|Nov|Dec)(?:\s+(\d{4}))?$",
    re.IGNORECASE,
)


def is_admin(update: Update) -> bool:
    return update.effective_user.id == int(os.environ["ADMIN_ID"])


def parse_date_and_description(description: str) -> tuple[str, str]:
    if not description:
        return (
            datetime.now().strftime("%d %b %y").lstrip("0"),
            "",
        )

    date_match = re.search(
        r"(\d{1,2})\s+"
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"(?:\s+(\d{4}))?$",
        description.strip(),
        re.IGNORECASE,
    )

    if not date_match:
        return (
            datetime.now().strftime("%d %b %y").lstrip("0"),
            description.strip(),
        )

    day = int(date_match.group(1))
    month_text = date_match.group(2)
    year = (
        int(date_match.group(3))
        if date_match.group(3)
        else datetime.now().year
    )

    try:
        transaction_date = datetime.strptime(
            f"{day} {month_text} {year}",
            "%d %B %Y",
        )
    except ValueError:
        try:
            transaction_date = datetime.strptime(
                f"{day} {month_text} {year}",
                "%d %b %Y",
            )
        except ValueError:
            return (
                datetime.now().strftime("%d %b %y").lstrip("0"),
                description.strip(),
            )

    remaining_description = description[:date_match.start()].strip()

    return (
        transaction_date.strftime("%d %b %y").lstrip("0"),
        remaining_description,
    )

async def handle_transaction(
    update: Update,
    transaction_type: str,
    payment_method: str = "Bank",
):
    if not is_admin(update):
        await update.effective_message.reply_text(
            "⛔ You are not authorized to use this command."
        )
        return

    text = update.effective_message.text.strip()
    match = TRANSACTION_REGEX.match(text)

    if not match:
        await update.effective_message.reply_text(
            "❌ Invalid format.\n\n"
            "Examples:\n"
            "/expense chicken 200\n"
            "/expense shoes 260 size 10\n"
            "/expense ice cream 250 13 August\n"
            "/income salary 41667\n"
            "/expensecash turf 200\n"
            "/incomecash tips 500"
        )
        return

    command, item, amount, description = match.groups()

    # Determine payment method from command
    if "cash" in command.lower():
        payment_method = "Cash"
        # Extract base transaction type (expense or income)
        transaction_type = "expense" if "expense" in command.lower() else "income"
    else:
        payment_method = "Bank"

    transaction_date, description = parse_date_and_description(
        description or ""
    )

    append_transaction(
        date=transaction_date,
        item=item.strip(),
        amount=amount,
        transaction_type=transaction_type,
        description=description,
        payment_method=payment_method,
    )

    await update.effective_message.reply_text(
        f"✅ {transaction_type.capitalize()} added ({payment_method}): "
        f"₹{amount} for {item.strip()}"
    )


@command("expense", "Add an expense")
async def expense(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await handle_transaction(update, "expense")


@command("income", "Add income")
async def income(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await handle_transaction(update, "income")


@command("expensecash", "Add a cash expense")
async def expensecash(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await handle_transaction(update, "expense", payment_method="Cash")


@command("incomecash", "Add cash income")
async def incomecash(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await handle_transaction(update, "income", payment_method="Cash")


@command("undoexpense", "Undo the most recent expense")
async def undoexpense(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
        await update.effective_message.reply_text(
            "⛔ You are not authorized to use this command."
        )
        return

    expense_data = get_last_expense()

    if not expense_data:
        await update.effective_message.reply_text(
            "ℹ️ No expense found to undo."
        )
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Yes",
                    callback_data=f"undo_yes:{expense_data['row_number']}",
                ),
                InlineKeyboardButton(
                    "❌ No",
                    callback_data="undo_no",
                ),
            ]
        ]
    )

    await update.effective_message.reply_text(
        f'Are you sure you want to delete '
        f'"{expense_data["item"]} ₹{expense_data["amount"]}"?',
        reply_markup=keyboard,
    )


async def undo_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        await query.edit_message_text(
            "⛔ You are not authorized to use this."
        )
        return

    if query.data == "undo_no":
        await query.edit_message_text(
            "❌ Undo cancelled."
        )
        return

    row_number = int(query.data.split(":")[1])

    delete_expense(row_number)

    await query.edit_message_text(
        "✅ Last expense has been removed."
    )
