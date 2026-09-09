import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


TIMEZONE = os.getenv(
    "TIMEZONE",
    "Asia/Kolkata",
)


def get_sheet():
    spreadsheet_id = os.environ[
        "SPREADSHEET_ID"
    ]

    worksheet_name = datetime.now(
        ZoneInfo(TIMEZONE)
    ).strftime("%B")

    credentials_json = os.getenv(
        "GOOGLE_CREDENTIALS"
    )

    if credentials_json:
        credentials = (
            Credentials.from_service_account_info(
                json.loads(credentials_json),
                scopes=SCOPES,
            )
        )
    else:
        project_root = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )

        credentials_file = os.path.join(
            project_root,
            "credentials",
            "google-service-account.json",
        )

        credentials = (
            Credentials.from_service_account_file(
                credentials_file,
                scopes=SCOPES,
            )
        )

    client = gspread.authorize(
        credentials
    )

    spreadsheet = client.open_by_key(
        spreadsheet_id
    )

    return spreadsheet.worksheet(
        worksheet_name
    )


def get_all_months_data() -> list[dict]:
    """Fetch all months' data from Google Sheets."""
    spreadsheet_id = os.environ["SPREADSHEET_ID"]

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

    all_transactions = []

    for worksheet in spreadsheet.worksheets():
        try:
            month_name = worksheet.title
            rows = worksheet.get_all_values()

            if len(rows) < 2:
                continue

            for row_idx, row in enumerate(rows[1:], start=2):
                if len(row) < 6:
                    continue

                date_str = row[0].strip()
                item = row[1].strip()
                expense_str = row[2].strip()
                income_str = row[3].strip()
                description = row[5].strip() if len(row) > 5 else ""
                category = row[6].strip() if len(row) > 6 else ""

                if not date_str:
                    continue

                try:
                    transaction_date = datetime.strptime(
                        date_str, "%d %b %y"
                    )
                except ValueError:
                    try:
                        transaction_date = datetime.strptime(
                            date_str, "%d %b %Y"
                        )
                    except ValueError:
                        continue

                expense = (
                    float(expense_str.replace(",", ""))
                    if expense_str
                    else 0
                )

                income = (
                    float(income_str.replace(",", ""))
                    if income_str
                    else 0
                )

                if expense > 0 or income > 0:
                    all_transactions.append({
                        "date": transaction_date,
                        "item": item,
                        "expense": expense,
                        "income": income,
                        "description": description,
                        "category": category,
                        "month": month_name,
                    })

        except Exception as e:
            print(
                f"Error reading worksheet {worksheet.title}: {e}"
            )
            continue

    return all_transactions

def append_transaction(
    date: str,
    item: str,
    amount: str,
    transaction_type: str,
    description: str,
    payment_method: str = "Bank",
    category: str = "",
):
    sheet = get_sheet()

    # Look only at column A, which belongs to the transaction table.
    dates = sheet.col_values(1)

    # Find the first empty row after the header.
    next_row = None

    for row_number in range(2, len(dates) + 2):
        if row_number > len(dates) or not dates[row_number - 1].strip():
            next_row = row_number
            break

    expense = (
        amount
        if transaction_type == "expense"
        else ""
    )

    income = (
        amount
        if transaction_type == "income"
        else ""
    )

    remaining_formula = (
        f'=IF(OR(C{next_row}<>"" ,'
        f'D{next_row}<>""),'
        f'SUMIF($G$2:$G{next_row},"Bank",'
        f'$D$2:$D{next_row})-'
        f'SUMIF($G$2:$G{next_row},"Bank",'
        f'$C$2:$C{next_row}),"")'
    )

    row = [
        date,
        item,
        expense,
        income,
        remaining_formula,
        description,
        payment_method,
        category,
    ]

    # Write specifically to A:H of the transaction row.
    sheet.update(
        f"A{next_row}:H{next_row}",
        [row],
        value_input_option="USER_ENTERED",
    )

def get_last_expense():
    sheet = get_sheet()

    rows = sheet.get_all_values()

    for row_number in range(
        len(rows),
        1,
        -1,
    ):
        row = rows[
            row_number - 1
        ]

        if (
            len(row) >= 3
            and row[2].strip()
        ):
            return {
                "row_number": row_number,
                "item": row[1],
                "amount": row[2],
            }

    return None


def delete_expense(
    row_number: int,
):
    sheet = get_sheet()

    sheet.delete_rows(
        row_number
    )