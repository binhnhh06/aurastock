import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.smart_screener import scan_cached_universe


class SmartScreenerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data/ssi_cache/ohlcv").mkdir(parents=True)
        pd.DataFrame({"symbol": ["AAA", "BBB", "CCC"]}).to_csv(
            self.root / "data/ssi_cache/vn30_symbols.csv", index=False
        )
        self.dates = pd.bdate_range("2025-01-01", periods=260)
        for sym, trend in [("AAA", 0.2), ("BBB", -0.1), ("CCC", 0.02)]:
            close = np.linspace(100, 100 * (1+trend), 260) + 0.5 * np.sin(np.arange(260))
            data = pd.DataFrame({
                "symbol": sym, "date": self.dates.strftime("%Y-%m-%d"),
                "open": close, "high": close + 1, "low": close - 1,
                "close": close, "volume": np.full(260, 1000000),
            })
            data.to_csv(self.root / f"data/ssi_cache/ohlcv/{sym}.csv", index=False)

    def tearDown(self):
        self.temp.cleanup()

    def test_scores_range_and_same_date(self):
        scores, meta = scan_cached_universe(self.root)
        self.assertEqual(meta.eligible, 3)
        self.assertEqual(meta.as_of, self.dates[-1].strftime("%Y-%m-%d"))
        self.assertTrue(scores["Smart Rating /10"].between(1, 10).all())
        self.assertEqual(scores["Ngày dữ liệu"].nunique(), 1)

    def test_historical_cutoff_ignores_future(self):
        cutoff = self.dates[-15].strftime("%Y-%m-%d")
        earlier, _ = scan_cached_universe(self.root, cutoff)
        p = self.root / "data/ssi_cache/ohlcv/AAA.csv"
        df = pd.read_csv(p)
        df.loc[df["date"] > cutoff, "close"] *= 100
        df.loc[df["date"] > cutoff, "high"] *= 100
        df.loc[df["date"] > cutoff, "low"] *= 100
        df.loc[df["date"] > cutoff, "open"] *= 100
        df.to_csv(p, index=False)
        later, _ = scan_cached_universe(self.root, cutoff)
        pd.testing.assert_series_equal(
            earlier.set_index("Mã")["Smart Rating /10"].sort_index(),
            later.set_index("Mã")["Smart Rating /10"].sort_index(),
        )

    def test_stale_symbol_is_excluded_not_mixed(self):
        p = self.root / "data/ssi_cache/ohlcv/CCC.csv"
        df = pd.read_csv(p).iloc[:-1]
        df.to_csv(p, index=False)
        result, meta = scan_cached_universe(self.root)
        self.assertEqual(meta.eligible, 2)
        self.assertTrue(pd.isna(result.loc[result["Mã"]=="CCC", "Smart Rating /10"].iloc[0]))

    def test_duplicate_dates_rejected(self):
        p = self.root / "data/ssi_cache/ohlcv/CCC.csv"
        df = pd.read_csv(p)
        pd.concat([df, df.tail(1)]).to_csv(p, index=False)
        result, meta = scan_cached_universe(self.root)
        self.assertEqual(meta.eligible, 2)
        self.assertIn("trùng", result.loc[result["Mã"]=="CCC", "Lý do"].iloc[0])


if __name__ == "__main__":
    unittest.main()
