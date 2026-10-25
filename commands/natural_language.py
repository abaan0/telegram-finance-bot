import asyncio
import html
import os
import uuid
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.google_sheets import append_transaction, delete_transaction
from services.transaction_parser import parse_transaction_message


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == int(os.environ["ADMIN_ID"])


def format_transaction_date(date_text: str) -> str:
    transaction_date = date.fromisoformat(date_text)
    return f"{transaction_date.day} {transaction_date.strftime('%b %y')}"


def _fast_entry_settings() -> tuple[bool, float]:
    enabled = os.getenv("FAST_ENTRY_MODE", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    try:
        threshold = float(os.getenv("FAST_ENTRY_MIN_CONFIDENCE", "0.92"))
    except ValueError:
        threshold = 0.92
    return enabled, min(1.0, max(0.0, threshold))


def build_confirmation_message(transaction: dict) -> str:
    transaction_type = transaction["transaction_type"]
    transaction_word = "Expense" if transaction_type == "expense" else "Income"
    item = html.escape(transaction["item"])
    category = html.escape(transaction.get("category", "Other"))
    payment_method = html.escape(transaction.get("payment_method", "Bank"))
    transaction_date = html.escape(format_transaction_date(transaction["date"]))
    description = html.escape(transaction.get("description", ""))

    lines = [
        f"<b>{transaction_word} detected</b>",
        "",
        f"Amount: <b>₹{transaction['amount']:,.2f}</b>",
        f"Item: <b>{item}</b>",
        f"Category: {category}",
        f"Payment: {payment_method}",
        f"Date: {transaction_date}",
    ]
    if description:
        lines.append(f"Description: {description}")
    lines.extend(["", "Save this transaction?"])
    return "\n".join(lines)


async def handle_natural_language_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Interpret ordinary Telegram messages as possible finance transactions."""
    if not is_admin(update):
        return

    message = update.effective_message
    if not message or not message.text:
        return

    text = message.text.strip()
    if not text or text.startswith("/"):
        return

    try:
        transaction = await parse_transaction_message(text)
    except Exception:
        # Do not leak API keys, request contents, or provider details into chat.
        await message.reply_text(
            "⚠️ I couldn't understand that clearly as a transaction.\n\n"
            "Try something like:\n"
            "Spent ₹350 on dinner at Domino's\n"
            "Got salary ₹62,000 today"
        )
        return

    if not transaction.get("is_transaction"):
        return

    if transaction.get("confidence", 0) < 0.65:
        await message.reply_text(
            "🤔 I think that's a transaction, but I'm not confident enough to save it.\n\n"
            "Please make the amount and what you spent/received the money for clearer."
        )
        return

    fast_entry_enabled, fast_entry_threshold = _fast_entry_settings()
    if (
        fast_entry_enabled
        and transaction.get("confidence", 0) >= fast_entry_threshold
        and transaction.get("amount", 0) > 0
        and transaction.get("item", "").strip()
    ):
        try:
            saved = await asyncio.to_thread(
                append_transaction,
                date=transaction["date"],
                item=transaction["item"],
                amount=f"{transaction['amount']:.2f}",
                transaction_type=transaction["transaction_type"],
                description=transaction.get("description", ""),
                payment_method=transaction.get("payment_method", "Bank"),
                category=transaction.get("category", "Other"),
            )
        except Exception:
            await message.reply_text(
                "⚠️ I understood the transaction, but couldn't save it.\n\n"
                "Please try again in a moment."
            )
            return

        formatted_date = format_transaction_date(transaction["date"])
        undo_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "↩️ Undo",
                callback_data=f"nl_undo:{saved['row_number']}:{saved['worksheet_title']}",
            )]
        ])
        await message.reply_text(
            f"✅ Saved automatically\n\n"
            f"₹{transaction['amount']:,.2f} · {transaction['item']}\n"
            f"{transaction.get('category', 'Other')} · {formatted_date} · "
            f"{saved['worksheet_title']}\n\n"
            "Tap Undo if anything is incorrect.",
            reply_markup=undo_keyboard,
        )
        return

    # Keep pending transactions separately. Each button refers to the exact
    # message that created it, so rapid entries cannot overwrite each other.
    transaction_id = uuid.uuid4().hex[:12]
    pending = context.user_data.setdefault("pending_transactions", {})
    pending[transaction_id] = transaction

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Confirm",
                callback_data=f"nl_confirm:{transaction_id}",
            ),
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data=f"nl_cancel:{transaction_id}",
            ),
        ]
    ])
    await message.reply_text(
        build_confirmation_message(transaction),
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def natural_language_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Handle Confirm / Cancel for the specific pending transaction."""
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        await query.edit_message_text("⛔ You are not authorized to use this.")
        return

    try:
        action, transaction_id = query.data.split(":", 1)
    except (AttributeError, ValueError):
        await query.edit_message_text("⌛ This transaction button is invalid or expired.")
        return

    pending = context.user_data.setdefault("pending_transactions", {})
    transaction = pending.get(transaction_id)
    if not transaction:
        await query.edit_message_text("⌛ This transaction is no longer pending.")
        return

    if action == "nl_cancel":
        pending.pop(transaction_id, None)
        await query.edit_message_text("❌ Transaction cancelled.")
        return

    if action != "nl_confirm":
        await query.edit_message_text("⌛ This transaction button is invalid or expired.")
        return

    if transaction.get("_saving"):
        await query.edit_message_text("⌛ This transaction is already being saved.")
        return

    transaction["_saving"] = True
    try:
        formatted_date = format_transaction_date(transaction["date"])
        saved = await asyncio.to_thread(
            append_transaction,
            date=transaction["date"],
            item=transaction["item"],
            amount=f"{transaction['amount']:.2f}",
            transaction_type=transaction["transaction_type"],
            description=transaction.get("description", ""),
            payment_method=transaction.get("payment_method", "Bank"),
            category=transaction.get("category", "Other"),
        )
        pending.pop(transaction_id, None)

        transaction_word = "Expense" if transaction["transaction_type"] == "expense" else "Income"
        await query.edit_message_text(
            f"✅ {transaction_word} added!\n\n"
            f"₹{transaction['amount']:,.2f} · {transaction['item']}\n"
            f"{transaction.get('category', 'Other')} · {formatted_date}\n"
            f"Sheet: {saved['worksheet_title']}"
        )
    except Exception:
        # Keep that transaction pending to allow a retry. Avoid showing
        # implementation details or secrets in Telegram chat.
        transaction.pop("_saving", None)
        await query.edit_message_text(
            "⚠️ I understood the transaction, but couldn't save it.\n\n"
            "Your transaction is still pending. Please try again."
        )


async def natural_language_undo_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Undo a fast-entry save directly from its success message."""
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        await query.edit_message_text("⛔ You are not authorized to use this.")
        return

    try:
        _, row_text, worksheet_title = query.data.split(":", 2)
        row_number = int(row_text)
        if row_number < 2 or not worksheet_title:
            raise ValueError("Invalid row or worksheet")
        await asyncio.to_thread(delete_transaction, row_number, worksheet_title)
    except Exception:
        await query.edit_message_text(
            "⚠️ I couldn't undo that transaction. Please check the sheet before trying again."
        )
        return

    await query.edit_message_text("↩️ Transaction removed from Google Sheets.")
