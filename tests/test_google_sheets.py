"""Lightweight tests for worksheet routing and month initialization.

These tests stub Google libraries so they do not require credentials or make
real Google Sheets requests.
"""

import sys
import types
import unittest
from datetime import date


# Stub optional external dependencies before importing the service module.
gspread_stub = types.ModuleType("gspread")
gspread_stub.authorize = lambda credentials: None
sys.modules.setdefault("gspread", gspread_stub)

google_stub = sys.modules.setdefault("google", types.ModuleType("google"))
google_stub.__path__ = []
oauth2_stub = sys.modules.setdefault("google.oauth2", types.ModuleType("google.oauth2"))
oauth2_stub.__path__ = []
service_account_stub = types.ModuleType("google.oauth2.service_account")


class _UnusedCredentials:
    @staticmethod
    def from_service_account_info(*args, **kwargs):
        return object()

    @staticmethod
    def from_service_account_file(*args, **kwargs):
        return object()


service_account_stub.Credentials = _UnusedCredentials
sys.modules.setdefault("google.oauth2.service_account", service_account_stub)

from services import google_sheets as sheets

# Minimal Telegram import stubs let the parsing helpers be tested without a bot token.
telegram_stub = types.ModuleType("telegram")
class _UnusedTelegramType:
    pass
telegram_stub.Update = _UnusedTelegramType
telegram_stub.InlineKeyboardButton = _UnusedTelegramType
telegram_stub.InlineKeyboardMarkup = _UnusedTelegramType
sys.modules.setdefault("telegram", telegram_stub)
telegram_ext_stub = types.ModuleType("telegram.ext")
telegram_ext_stub.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
sys.modules.setdefault("telegram.ext", telegram_ext_stub)

from commands.expense import TRANSACTION_REGEX, parse_date_and_description
from services.categories import infer_category


class FakeWorksheet:
    def __init__(self, title, rows=None, row_count=1000, sheet_id=None):
        self.title = title
        self.id = sheet_id or (abs(hash(title)) % 100000 + 1)
        self.row_count = row_count
        self.rows = [list(row) for row in (rows or [])]

    def _ensure(self, row_index, col_index):
        while len(self.rows) < row_index:
            self.rows.append([])
        while len(self.rows[row_index - 1]) < col_index:
            self.rows[row_index - 1].append("")

    def get_all_values(self):
        output = []
        for row in self.rows:
            values = list(row)
            while values and values[-1] == "":
                values.pop()
            output.append(values)
        while output and not any(str(x).strip() for x in output[-1]):
            output.pop()
        return output

    def col_values(self, col):
        result = []
        for row in self.rows:
            result.append(row[col - 1] if len(row) >= col else "")
        while result and result[-1] == "":
            result.pop()
        return result

    def update(self, values, range_name=None, value_input_option=None, raw=True):
        start, end = range_name.split(":")
        import re
        m1 = re.fullmatch(r"([A-Z]+)(\d+)", start)
        m2 = re.fullmatch(r"([A-Z]+)(\d+)", end)
        start_col = _col_number(m1.group(1))
        start_row = int(m1.group(2))
        end_col = _col_number(m2.group(1))
        end_row = int(m2.group(2))
        for r_offset, row_values in enumerate(values):
            row_number = start_row + r_offset
            for c_offset, value in enumerate(row_values):
                col_number = start_col + c_offset
                if col_number > end_col or row_number > end_row:
                    continue
                self._ensure(row_number, col_number)
                self.rows[row_number - 1][col_number - 1] = str(value)

    def batch_clear(self, ranges):
        import re
        for range_name in ranges:
            start, end = range_name.split(":")
            m1 = re.fullmatch(r"([A-Z]+)(\d+)", start)
            m2 = re.fullmatch(r"([A-Z]+)(\d+)", end)
            start_col, start_row = _col_number(m1.group(1)), int(m1.group(2))
            end_col, end_row = _col_number(m2.group(1)), int(m2.group(2))
            for r in range(start_row, min(end_row, self.row_count) + 1):
                self._ensure(r, end_col)
                for c in range(start_col, end_col + 1):
                    self.rows[r - 1][c - 1] = ""

    def delete_rows(self, row_number):
        del self.rows[row_number - 1]


def _col_number(letters):
    value = 0
    for char in letters:
        value = value * 26 + ord(char) - 64
    return value


class FakeSpreadsheet:
    def __init__(self, worksheets):
        self._worksheets = list(worksheets)

    def worksheets(self):
        return list(self._worksheets)

    def duplicate_sheet(self, source_sheet_id, new_sheet_name, insert_sheet_index):
        source = next(sheet for sheet in self._worksheets if sheet.id == source_sheet_id)
        clone = FakeWorksheet(new_sheet_name, source.get_all_values(), source.row_count)
        self._worksheets.insert(insert_sheet_index, clone)
        return clone

    def add_worksheet(self, title, rows, cols):
        worksheet = FakeWorksheet(title, row_count=rows)
        self._worksheets.append(worksheet)
        return worksheet


class GoogleSheetsTests(unittest.TestCase):
    def setUp(self):
        self.original_spreadsheet_getter = sheets._get_spreadsheet
        self.original_cache = sheets._worksheet_cache
        self.original_resolved_cache = dict(sheets._resolved_month_cache)
        self.original_initialized_months = set(sheets._initialized_months)
        sheets._worksheet_cache = None
        sheets._resolved_month_cache.clear()
        sheets._initialized_months.clear()

    def tearDown(self):
        sheets._get_spreadsheet = self.original_spreadsheet_getter
        sheets._worksheet_cache = self.original_cache
        sheets._resolved_month_cache.clear()
        sheets._resolved_month_cache.update(self.original_resolved_cache)
        sheets._initialized_months.clear()
        sheets._initialized_months.update(self.original_initialized_months)

    def install_spreadsheet(self, spreadsheet):
        sheets._get_spreadsheet = lambda: spreadsheet

    def test_parse_date_and_formula(self):
        self.assertEqual(sheets._parse_date("1 Sep 26"), date(2026, 9, 1))
        self.assertEqual(sheets._parse_date("2026-11-03"), date(2026, 11, 3))
        self.assertIn('SUMIF($G$2:$G3,"Bank",$D$2:$D3)', sheets._remaining_formula(3))

    def test_slash_commands_accept_rupees_and_grouped_amounts(self):
        match = TRANSACTION_REGEX.match("/expense shoes ₹2,600 size 10")
        self.assertIsNotNone(match)
        self.assertEqual(match.groups(), ("expense", "shoes", "₹2,600", "size 10"))
        income_match = TRANSACTION_REGEX.match("/income salary 41,667")
        self.assertIsNotNone(income_match)
        self.assertEqual(income_match.group(3), "41,667")
        indian_grouping = TRANSACTION_REGEX.match("/income salary ₹2,50,000")
        self.assertIsNotNone(indian_grouping)
        self.assertEqual(indian_grouping.group(3), "₹2,50,000")

    def test_slash_command_date_parsing_and_category(self):
        self.assertEqual(parse_date_and_description("turf 13 August 2026"), ("13 Aug 26", "turf"))
        self.assertEqual(infer_category("turf", "with friends"), "Entertainment")

    def test_backdated_transaction_selects_matching_legacy_tab(self):
        sep = FakeWorksheet("Sep", [
            ["Date", "Item", "Expenses", "Income", "Remaining", "Description", "Payment Method", "Category"],
            ["1 Sep 26", "previous month carry over", "", "500.00", "500.00", "", "Bank", ""],
        ])
        oct_sheet = FakeWorksheet("October", [
            ["Date", "Item", "Expenses", "Income", "Remaining", "Description", "Payment Method", "Category"],
            ["1 Oct 26", "previous month carry over", "", "500.00", "500.00", "", "Bank", ""],
        ])
        self.install_spreadsheet(FakeSpreadsheet([sep, oct_sheet]))
        result = sheets.get_sheet("18 Sep 26")
        self.assertIs(result, sep)

    def test_existing_empty_month_tab_gets_automatic_carryover(self):
        september = FakeWorksheet("Sep", [
            ["Date", "Item", "Expenses", "Income", "Remaining", "Description", "Payment Method", "Category"],
            ["1 Sep 26", "previous month carry over", "", "400.00", "400.00", "", "Bank", ""],
            ["2 Sep 26", "turf", "100.00", "", "300.00", "", "Bank", "Entertainment"],
        ])
        october = FakeWorksheet("October", [
            ["Date", "Item", "Expenses", "Income", "Remaining", "Description", "Payment Method", "Category"],
        ])
        self.install_spreadsheet(FakeSpreadsheet([september, october]))

        # A read-only lookup (for example, /undoexpense) must not mark the
        # empty month as initialized before a real transaction is recorded.
        sheets.get_sheet("25 Oct 26", create=False)
        self.assertEqual(len(october.get_all_values()), 1)

        result = sheets.get_sheet("25 Oct 26")
        rows = result.get_all_values()
        self.assertIs(result, october)
        self.assertEqual(rows[1][1], "previous month carry over")
        self.assertIn("SUMIF('Sep'!$G:$G", rows[1][3])

    def test_new_month_duplicates_layout_and_carries_forward_bank_balance(self):
        october = FakeWorksheet("October", [
            ["Date", "Item", "Expenses", "Income", "Remaining", "Description", "Payment Method", "Category"],
            ["1 Oct 26", "previous month carry over", "", "1000.00", "1000.00", "", "Bank", ""],
            ["2 Oct 26", "salary", "", "500.00", "1500.00", "", "Bank", "Other"],
            ["3 Oct 26", "dinner", "200.00", "", "1300.00", "", "Bank", "Food"],
        ])
        spreadsheet = FakeSpreadsheet([october])
        self.install_spreadsheet(spreadsheet)

        november = sheets.get_sheet("3 Nov 26")
        rows = november.get_all_values()
        self.assertEqual(november.title, "Nov 26")
        self.assertEqual(rows[1][1], "previous month carry over")
        self.assertIn("SUMIF('October'!$G:$G", rows[1][3])
        self.assertIn("SUMIF", rows[1][4])
        # The previous month's item rows were cleared, but headers remain.
        self.assertEqual(len(rows), 2)

        saved = sheets.append_transaction(
            date="3 Nov 26",
            item="petrol",
            amount="50.00",
            transaction_type="expense",
            description="",
            payment_method="Bank",
            category="Transport",
        )
        self.assertEqual(saved["worksheet_title"], "Nov 26")
        self.assertEqual(saved["row_number"], 3)
        self.assertEqual(november.get_all_values()[2][1], "petrol")

    def test_budget_data_reads_category_from_h_and_excludes_carryover(self):
        sep = FakeWorksheet("Sep", [
            ["Date", "Item", "Expenses", "Income", "Remaining", "Description", "Payment Method", "Category"],
            ["1 Sep 26", "previous month carry over", "", "500.00", "500.00", "", "Bank", ""],
            ["2 Sep 26", "turf", "170.00", "", "330.00", "with friends", "Bank", "Entertainment"],
        ])
        self.install_spreadsheet(FakeSpreadsheet([sep]))
        results = sheets.get_all_months_data()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["category"], "Entertainment")
        self.assertEqual(results[0]["payment_method"], "Bank")


if __name__ == "__main__":
    unittest.main()
