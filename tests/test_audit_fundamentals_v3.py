import tempfile
import unittest
from pathlib import Path

import pandas as pd

from audit_fundamentals_v3 import audit, normalize


class FinancialAuditTests(unittest.TestCase):
    def test_vietnamese_normalization(self):
        self.assertEqual(normalize("CHI PHÍ THUẾ THU NHẬP DOANH NGHIỆP"),
                         "chi phi thue thu nhap doanh nghiep")

    def test_flags_tax_label_collision_and_preserves_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            staging = base / "staging"
            staging.mkdir()
            rows = pd.DataFrame({"item": ["CHI PHÍ THUẾ THU NHẬP DOANH NGHIỆP",
                                          "LỢI NHUẬN KẾ TOÁN SAU THUẾ"],
                                 "2023": [2848567000000, 2294473000000],
                                 "2024": [3543527000000, 2845109000000]})
            rows.to_csv(staging / "SSI_income_statement.csv", index=False)
            pd.DataFrame({"item": ["LỢI NHUẬN TRƯỚC THUẾ"],
                          "2023": [2848567000000], "2024": [3543527000000]}).to_csv(
                          staging / "SSI_cash_flow.csv", index=False)
            pd.DataFrame({"item": ["TỔNG TÀI SẢN", "NỢ PHẢI TRẢ", "VỐN CHỦ SỞ HỮU"],
                          "2023": [100, 60, 40], "2024": [105, 63, 42]}).to_csv(
                          staging / "SSI_balance_sheet.csv", index=False)
            pd.DataFrame({"ratio": ["ROE (%)"], "2023": [10]}).to_csv(
                          staging / "SSI_ratios.csv", index=False)
            result = audit(staging, base / "out")
            self.assertEqual(result["files"], 4)
            flagged = [x for x in result["flags"] if x["test"] == "tax_equals_pretax"]
            self.assertEqual(len(flagged), 2)
            self.assertEqual(pd.read_csv(staging / "SSI_income_statement.csv").shape, (2, 3))

    def test_unverified_names_do_not_raise_false_tax_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            staging = Path(folder) / "staging"
            staging.mkdir()
            pd.DataFrame({"item": ["CHI PHÍ THUẾ THU NHẬP DOANH NGHIỆP"], "2025": [-400]}).to_csv(
                staging / "FPT_income_statement.csv", index=False)
            result = audit(staging, Path(folder) / "audit")
            self.assertFalse(any(x["test"] == "tax_equals_pretax" for x in result["flags"]))


if __name__ == "__main__":
    unittest.main()
