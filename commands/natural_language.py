import html
import os
from datetime import date

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from services.google_sheets import (
    append_transaction,
)
from services.transaction_parser import (
    parse_transaction_message,
)


def is_admin(update: Update) -> bool:
    """Check whether the user is the configured admin."""

    user = update.effective_user

    return (
        user is not None
        and user.id
        == int(
            os.environ["ADMIN_ID"]
        )
    )


def format_transaction_date(
    date_text: str,
) -> str:
    """Convert YYYY-MM-DD into 28 Aug 26 style."""

    transaction_date = date.fromisoformat(
        date_text
    )

    return (
        f"{transaction_date.day} "
        f"{transaction_date.strftime('%b %y')}"
    )


def build_confirmation_message(
    transaction: dict,
) -> str:
    """Build Telegram confirmation message."""

    transaction_type = (
        transaction[
            "transaction_type"
        ]
    )

    amount = transaction[
        "amount"
    ]

    item = html.escape(
        transaction[
            "item"
        ]
    )

    category = html.escape(
        transaction[
            "category"
        ]
    )

    payment_method = html.escape(
        transaction[
            "payment_method"
        ]
    )

    transaction_date = html.escape(
        format_transaction_date(
            transaction[
                "date"
            ]
        )
    )

    description = html.escape(
        transaction.get(
            "description",
            "",
        )
    )

    if transaction_type == "expense":
        title = "💸 NEW EXPENSE"
    else:
        title = "💰 NEW INCOME"

    lines = [
        f"<b>{title}</b>",
        "",
        f"Amount: <b>₹{amount:,.2f}</b>",
        f"Item: <b>{item}</b>",
        f"Category: <b>{category}</b>",
        f"Payment: <b>{payment_method}</b>",
        f"Date: <b>{transaction_date}</b>",
    ]

    if description:
        lines.append(
            f"Description: {description}"
        )

    lines.extend([
        "",
        "Save this transaction?",
    ])

    return "\n".join(
        lines
    )


async def handle_natural_language_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Interpret ordinary Telegram messages as
    possible finance transactions.
    """

    if not is_admin(update):
        return

    message = (
        update.effective_message
    )

    if (
        not message
        or not message.text
    ):
        return

    text = message.text.strip()

    if not text:
        return

    # Slash commands are handled by
    # their existing CommandHandlers.
    if text.startswith("/"):
        return

    try:
        transaction = (
            await parse_transaction_message(
                text
            )
        )

    except Exception as error:
        print(
            "Natural-language parser error: "
            f"{error}"
        )

        await message.reply_text(
            "⚠️ I couldn't understand that clearly "
            "as a transaction.\n\n"
            "Try something like:\n"
            "Spent ₹350 on dinner at Domino's\n"
            "Got salary ₹62,000 today"
        )

        return

    if not transaction.get(
        "is_transaction"
    ):
        # IMPORTANT:
        # Normal conversational messages
        # are ignored silently.
        return

    confidence = transaction.get(
        "confidence",
        0,
    )

    if confidence < 0.65:
        await message.reply_text(
            "🤔 I think that's a transaction, "
            "but I'm not confident enough to save it.\n\n"
            "Please make the amount and what you "
            "spent/received the money for clearer."
        )

        return

    context.user_data[
        "pending_transaction"
    ] = transaction

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Confirm",
                    callback_data="nl_confirm",
                ),
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data="nl_cancel",
                ),
            ]
        ]
    )

    await message.reply_text(
        build_confirmation_message(
            transaction
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def natural_language_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Handle Confirm / Cancel buttons."""

    query = update.callback_query

    await query.answer()

    if not is_admin(update):
        await query.edit_message_text(
            "⛔ You are not authorized to use this."
        )
        return

    transaction = context.user_data.get(
        "pending_transaction"
    )

    if not transaction:
        await query.edit_message_text(
            "⌛ This transaction is no longer pending."
        )
        return

    if query.data == "nl_cancel":

        context.user_data.pop(
            "pending_transaction",
            None,
        )

        await query.edit_message_text(
            "❌ Transaction cancelled."
        )

        return

    try:
        transaction_date = (
            date.fromisoformat(
                transaction["date"]
            )
        )

        formatted_date = (
            f"{transaction_date.day} "
            f"{transaction_date.strftime('%b %y')}"
        )

        append_transaction(
            date=formatted_date,
            item=transaction[
                "item"
            ],
            amount=(
                f"{transaction['amount']:.2f}"
            ),
            transaction_type=transaction[
                "transaction_type"
            ],
            description=transaction.get(
                "description",
                "",
            ),
            payment_method=transaction.get(
                "payment_method",
                "Bank",
            ),
            category=transaction.get(
                "category",
                "Other",
            ),
        )

        context.user_data.pop(
            "pending_transaction",
            None,
        )

        if (
            transaction[
                "transaction_type"
            ]
            == "expense"
        ):
            transaction_word = "Expense"
        else:
            transaction_word = "Income"

        await query.edit_message_text(
            f"✅ {transaction_word} added!\n\n"
            f"₹{transaction['amount']:,.2f} · "
            f"{transaction['item']}\n"
            f"{transaction['category']} · "
            f"{formatted_date}"
        )

    except Exception as error:
        print(
            "Natural-language transaction save error: "
            f"{error}"
        )

        await query.edit_message_text(
            "⚠️ I understood the transaction, "
            "but couldn't save it.\n\n"
            "Your transaction is still pending. "
            "Please try again."
        )