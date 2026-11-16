"""Event study: điểm vector hóa khớp diem_ta(); không nhìn trước dữ liệu tương lai; vào lệnh t+1."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.aura_backtest import score_series, run  # noqa: E402
from core.strategy import diem_ta  # noqa: E402
from core.technical_chart import _rsi_wilder  # noqa: E402


def prices(n=400, seed=1, drift=0.0006):
    rng = np.random.default_rng(seed)
    c = 20000 * np.cumprod(1 + rng.normal(drift, 0.02, n))
    o = c * (1 + rng.normal(0, 0.005, n))
    return pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=n), "open": o, "high": np.maximum(o, c) * 1.01,
                         "low": np.minimum(o, c) * 0.99, "close": c, "volume": rng.integers(2e5, 2e6, n).astype(float)})


class TestDiem(unittest.TestCase):
    def test_khop_diem_ta_tung_phien(self):
        df = prices()
        s = score_series(df)
        for i in (30, 80, 199, 250, 399):
            g = df.iloc[: i + 1].copy()
            g["RSI"] = _rsi_wilder(g["close"])
            self.assertAlmostEqual(s.iloc[i], diem_ta(g), places=1, msg=f"phiên {i}")

    def test_khong_nhin_truoc(self):
        df = prices()
        a = score_series(df).iloc[:300]
        df2 = df.copy()
        df2.loc[300:, ["close", "volume"]] *= 3   # đổi dữ liệu tương lai
        b = score_series(df2).iloc[:300]
        pd.testing.assert_series_equal(a, b)


class TestEventStudy(unittest.TestCase):
    def test_chay_tren_thu_muc_gia(self):
        with tempfile.TemporaryDirectory() as td:
            vni = prices(seed=9, drift=0.0004)
            vni[["open", "high", "low", "close"]] /= 16
            vni.to_csv(Path(td) / "VNINDEX.csv", index=False)
            for k, sym in enumerate(("AAA", "BBB", "CCC")):
                p = prices(seed=k + 2)
                p["volume"] *= 50
                p.to_csv(Path(td) / f"{sym}.csv", index=False)
            ev, summary, buckets = run(Path(td))
        self.assertFalse(ev.empty)
        self.assertTrue((ev["date"] >= pd.Timestamp("2024-01-01")).all())
        self.assertEqual(set(ev["period"]), {"Trong mẫu", "Ngoài mẫu"})
        self.assertIn("t-stat vượt VN-Index (theo ngày)", summary.columns)
        # lợi suất tính từ giá mở cửa phiên t+1
        row = ev.iloc[0]
        p = prices(seed={"AAA": 2, "BBB": 3, "CCC": 4}[row["symbol"]])
        i = p.index[p["date"].eq(row["date"])][0]
        self.assertAlmostEqual(row["ret_5"], p.at[i + 5, "close"] / p.at[i + 1, "open"] - 1 - 0.004, places=10)


if __name__ == "__main__":
    unittest.main()
