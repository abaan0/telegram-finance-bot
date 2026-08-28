import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


def get_sheet():
    spreadsheet_id = os.environ["SPREADSHEET_ID"]

    worksheet_name = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%B")

    credentials_json = os.getenv("GOOGLE_CREDENTIALS")

    if credentials_json:
        credentials = Credentials.from_service_account_info(
            json.loads(credentials_json),
            scopes=SCOPES,
        )
    else:
        project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

        credentials_file = os.path.join(
            project_root,
            "credentials",
            "google-service-account.json",
        )

        credentials = Credentials.from_service_account_file(
            credentials_file,
            scopes=SCOPES,
        )

    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)

    return spreadsheet.worksheet(worksheet_name)


def append_transaction(
    date: str,
    item: str,
    amount: str,
    transaction_type: str,
    description: str,
    payment_method: str = "Bank",
):
    sheet = get_sheet()

    next_row = len(sheet.get_all_values()) + 1

    expense = amount if transaction_type == "expense" else ""
    income = amount if transaction_type == "income" else ""

    remaining_formula = (
        f'=IF(OR(C{next_row}<>"",D{next_row}<>""),'
        f'SUMIF($G$2:$G{next_row},"Bank",$D$2:$D{next_row})-'
        f'SUMIF($G$2:$G{next_row},"Bank",$C$2:$C{next_row}),"")'
    )

    row = [
        date,
        item,
        expense,
        income,
        remaining_formula,
        description,
        payment_method,
        "",
    ]

    sheet.append_row(
        row,
        value_input_option="USER_ENTERED",
    )


def get_last_expense():
    sheet = get_sheet()
    rows = sheet.get_all_values()

    for row_number in range(len(rows), 1, -1):
        row = rows[row_number - 1]

        if len(row) >= 3 and row[2].strip():
            return {
                "row_number": row_number,
                "item": row[1],
                "amount": row[2],
            }

    return None


def delete_expense(row_number: int):
    sheet = get_sheet()
    sheet.delete_rows(row_number)