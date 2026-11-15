import unittest
from datetime import datetime
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.smart_rating_v2 import (RATING_WEIGHTS, BASE_COLS, _group_percentiles, empty_input_template,
                                  read_financial_snapshot, build_multifactor_table)

SYMBOLS = ["ACB", "BID", "CTG", "FPT", "HPG", "MWG"]


def financial_rows():
    result = empty_input_template(SYMBOLS)
    result["sector_type"] = ["BANK", "BANK", "BANK", "NONBANK", "NONBANK", "NONBANK"]
    result["peer_group"] = ["BANK"] * 3 + ["INDUSTRIAL"] * 3
    result["report_period_end"] = "2026-06-30"
    result["published_at"] = "2026-08-01"
    result["source"] = "Bao cao doanh nghiep - input kiem thu synthetic"
    result["valuation_asof"] = "2026-11-09"
    result["valuation_source"] = "Synthetic EOD valuation"
    for i in range(6):
        result.loc[i, "roe_pct"] = [12, 16, 18, 9, 15, 22][i]
        result.loc[i, "roa_pct"] = [1, 1.5, 2, 5, 7, 10][i]
        result.loc[i, "pe"] = [12, 10, 8, 9, 11, 13][i]
        result.loc[i, "pb"] = [2, 1.6, 1.2, 1.0, 1.5, 2.2][i]
        if i < 3:
            result.loc[i, "npl_pct"] = [3.0, 2.0, 1.5][i]
            result.loc[i, "car_pct"] = [10, 11, 12][i]
        else:
            result.loc[i, "gross_margin_pct"] = [10, 15, 20][i-3]
            result.loc[i, "eps_growth_pct"] = [0, 10, 20][i-3]
            result.loc[i, "debt_equity"] = [2, 1.5, 0.6][i-3]
            result.loc[i, "current_ratio"] = [1, 1.4, 2.0][i-3]
    return result


def tech_rows():
    return pd.DataFrame({"Mã": SYMBOLS, "Smart Rating /10": [5,6,7,5,6,7],
                         "Trạng thái": ["Đủ dữ liệu"]*6,
                         "Biến động 60 phiên (%)": [10]*6,
                         "GTGD 20 phiên (tỷ VND)": [10]*6,
                         "Lợi suất 20 phiên (%)": [3]*6,
                         "Lợi suất 63 phiên (%)": [4]*6,
                         "Sụt giảm từ đỉnh 60 phiên (%)": [5]*6})


class Tests(unittest.TestCase):
    def test_weights_and_template(self):
        self.assertAlmostEqual(sum(RATING_WEIGHTS.values()), 1)
        self.assertEqual(len(empty_input_template(SYMBOLS)), 6)
        self.assertEqual(set(BASE_COLS), set(empty_input_template(SYMBOLS).columns))

    def test_no_financials_no_composite(self):
        output = build_multifactor_table(tech_rows(), as_of="2026-11-09", financial_table=None,
                                         root=Path("/tmp/path_that_does_not_exist"))
        self.assertTrue(output["Smart Rating tổng hợp /10"].isna().all())
        self.assertTrue(output["Điểm kỹ thuật /10"].notna().all())

    def test_future_published_is_excluded(self):
        x = financial_rows()
        x.loc[x["symbol"].eq("ACB"), "published_at"] = "2026-11-10"
        result = read_financial_snapshot(table=x, as_of="2026-11-09")
        self.assertNotIn("ACB", result["symbol"].tolist())

    def test_future_valuation_is_excluded(self):
        x = financial_rows()
        x["valuation_asof"] = "2026-11-10"
        result = read_financial_snapshot(table=x, as_of="2026-11-09")
        self.assertTrue(result["pe"].isna().all())
        self.assertTrue(result["pb"].isna().all())

    def test_bank_nonbank_not_cross_peer(self):
        x = financial_rows()
        res = build_multifactor_table(tech_rows(), as_of="2026-11-09", financial_table=x)
        self.assertEqual(int(res["Smart Rating tổng hợp /10"].notna().sum()), 6)
        self.assertTrue(res["Smart Rating tổng hợp /10"].between(1,10).all())
        acb = res.loc[res["Mã"].eq("ACB")].iloc[0]
        self.assertEqual(acb["Loại doanh nghiệp"], "BANK")
        self.assertEqual(int(acb["Số chỉ tiêu cơ bản hợp lệ"]), 4)

    def test_rank_direction_is_correct(self):
        df = pd.DataFrame({"sector_type": ["BANK"]*3, "peer_group": ["BANK"]*3,
                           "roe_pct": [5., 10., 20.], "npl_pct": [4., 2., 1.]})
        roe = _group_percentiles(df, "roe_pct", True, {"BANK"})
        npl = _group_percentiles(df, "npl_pct", False, {"BANK"})
        self.assertEqual(roe.tolist(), [0., 0.5, 1.])
        self.assertEqual(npl.tolist(), [0., 0.5, 1.])

    def test_tied_metrics_neutral(self):
        df = pd.DataFrame({"sector_type": ["BANK"]*3, "peer_group": ["BANK"]*3,
                           "roe_pct": [10., 10., 10.]})
        result = _group_percentiles(df, "roe_pct", True, {"BANK"})
        self.assertEqual(result.tolist(), [0.5, 0.5, 0.5])

    def test_no_complete_peer_group(self):
        x = financial_rows().iloc[:2]
        res = build_multifactor_table(tech_rows(), as_of="2026-11-09", financial_table=x)
        self.assertTrue(res["Smart Rating tổng hợp /10"].isna().all())

    def test_unverified_source_excluded(self):
        x = financial_rows()
        x["source"] = ""
        res = build_multifactor_table(tech_rows(), as_of="2026-11-09", financial_table=x)
        self.assertTrue(res["Điểm cơ bản /10"].isna().all())

    def test_negative_pe_not_discounted(self):
        x = financial_rows()
        x.loc[x["symbol"].eq("ACB"), "pe"] = -12
        result = read_financial_snapshot(table=x, as_of="2026-11-09")
        self.assertTrue(pd.isna(result.loc[result["symbol"].eq("ACB"), "pe"].iloc[0]))

if __name__ == "__main__":
    unittest.main()
