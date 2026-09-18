from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.gemini import generate_json_with_fallback_async


TIMEZONE = "Asia/Kolkata"


VALID_CATEGORIES = {
    "Food",
    "Transport",
    "Shopping",
    "Entertainment",
    "Health",
    "Utilities",
    "Education",
    "Personal",
    "Other",
}


TRANSACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_transaction": {
            "type": "boolean",
        },
        "transaction_type": {
            "type": "string",
            "enum": [
                "expense",
                "income",
            ],
        },
        "amount": {
            "type": "number",
        },
        "item": {
            "type": "string",
        },
        "description": {
            "type": "string",
        },
        "date": {
            "type": "string",
        },
        "payment_method": {
            "type": "string",
            "enum": [
                "Bank",
                "Cash",
            ],
        },
        "category": {
            "type": "string",
        },
        "confidence": {
            "type": "number",
        },
    },
    "required": [
        "is_transaction",
        "transaction_type",
        "amount",
        "item",
        "description",
        "date",
        "payment_method",
        "category",
        "confidence",
    ],
}


async def parse_transaction_message(
    text: str,
) -> dict[str, Any]:
    """
    Convert a natural-language message into a
    structured finance transaction.
    """

    today = datetime.now(
        ZoneInfo(TIMEZONE)
    ).date()

    prompt = f"""
You extract personal finance transactions from a
Telegram message.

Today's date is {today.isoformat()}.
Timezone: {TIMEZONE}

Determine whether the message is attempting to record
ONE financial transaction.

If it is NOT a transaction:
- is_transaction = false
- Do not invent transaction information.

If it IS a transaction:

transaction_type:
- expense = money spent
- income = money received

amount:
- Extract the exact numeric amount in Indian rupees.
- Do not invent an amount.

item:
- Keep it short and useful.
- Example: Dinner, Salary, Football boots, Uber ride.

description:
- Store useful context such as merchant name,
  location, or additional details.

date:
- Return YYYY-MM-DD.
- Resolve relative dates using today's date.
- Examples:
  "today"
  "yesterday"
  "last Friday"
  "this Monday"

payment_method:
- Cash -> Cash
- UPI -> Bank
- Debit card -> Bank
- Credit card -> Bank
- Net banking -> Bank
- Bank transfer -> Bank
- Cheque -> Bank
- Any other non-cash method -> Bank

The spreadsheet currently uses only Bank/Cash for
balance tracking.

category must be one of:

Food
Transport
Shopping
Entertainment
Health
Utilities
Education
Personal
Other

confidence:
- Number between 0 and 1.
- Estimate how confident you are that the message
  clearly represents a transaction and that the
  extracted values are correct.

Do not invent:
- amount
- transaction type
- transaction date
- item

Telegram message:

{text}
"""

    data, model_used = await generate_json_with_fallback_async(
        prompt,
        TRANSACTION_SCHEMA,
    )

    if not bool(data.get("is_transaction")):
        return {
            "is_transaction": False,
            "model_used": model_used,
        }

    transaction_type = (
        str(
            data.get(
                "transaction_type",
                "",
            )
        )
        .strip()
        .lower()
    )

    item = str(
        data.get(
            "item",
            "",
        )
    ).strip()

    description = str(
        data.get(
            "description",
            "",
        )
    ).strip()

    date_text = str(
        data.get(
            "date",
            "",
        )
    ).strip()

    payment_method = str(
        data.get(
            "payment_method",
            "Bank",
        )
    ).strip().title()

    category = str(
        data.get(
            "category",
            "Other",
        )
    ).strip().title()

    try:
        amount = float(
            data.get(
                "amount",
                0,
            )
        )
    except (TypeError, ValueError):
        amount = 0.0

    try:
        transaction_date = date.fromisoformat(
            date_text
        )
    except ValueError as error:
        raise ValueError(
            "Gemini returned an invalid transaction date."
        ) from error

    try:
        confidence = float(
            data.get(
                "confidence",
                0,
            )
        )
    except (TypeError, ValueError):
        confidence = 0.0

    if transaction_type not in {
        "expense",
        "income",
    }:
        raise ValueError(
            "Could not determine transaction type."
        )

    if amount < 0:
        raise ValueError(
            "Could not determine a valid amount."
        )

    if not item:
        raise ValueError(
            "Could not determine what the transaction was for."
        )

    if payment_method not in {
        "Bank",
        "Cash",
    }:
        payment_method = "Bank"

    if category not in VALID_CATEGORIES:
        category = "Other"

    confidence = max(
        0.0,
        min(
            confidence,
            1.0,
        ),
    )

    return {
        "is_transaction": True,
        "transaction_type": transaction_type,
        "amount": round(amount, 2),
        "item": item,
        "description": description,
        "date": transaction_date.isoformat(),
        "payment_method": payment_method,
        "category": category,
        "confidence": confidence,
        "model_used": model_used,
    }