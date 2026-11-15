"""Kiểm thử bằng dữ liệu giả lập, KHÔNG chứa dữ liệu thị trường thật."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from core import ssi_adapter
from core.analysis import phan_tich
from core.strategy import danh_gia_x10


def synthetic_prices(symbol="SSI"):
    dates = pd.bdate_range(end=pd.Timestamp("2026-11-09"), periods=260)
    prices = [19000.0 + i * 10 for i in range(len(dates))]
    return pd.DataFrame({
        "symbol": symbol,
        "date": dates.strftime("%Y-%m-%d"),
        "open": prices,
        "high": [x + 200 for x in prices],
        "low": [x - 200 for x in prices],
        "close": prices,
        "volume": [1000000 + i * 50 for i in range(len(dates))],
    })


class TestSSIAdapter(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.patch_cache = patch.object(ssi_adapter, "CACHE_DIR", self.cache)
        self.patch_cache.start()
        self.addCleanup(self.patch_cache.stop)
        self.patch_today = patch.object(ssi_adapter, "_today", return_value=pd.Timestamp("2026-11-09").date())
        self.patch_today.start()
        self.addCleanup(self.patch_today.stop)

    def _write(self, df):
        df.to_csv(self.cache / "SSI.csv", index=False)

    def test_cached_prices_vnd_no_multiplication(self):
        self._write(synthetic_prices())
        df = ssi_adapter.lay_gia_ssi("SSI", so_ngay=730)
        self.assertEqual(df.attrs["nguon_gia"], "SSI FastConnect V3")
        self.assertEqual(df.attrs["che_do"], "SSI_CACHE")
        self.assertEqual(df.attrs["gia_don_vi"], "VND")
        self.assertEqual(df.iloc[0]["close"], 19000.0)
        self.assertEqual(df.iloc[-1]["close"], 21590.0)
        self.assertEqual(list(df.columns), ["time", "open", "high", "low", "close", "volume"])
        self.assertTrue(df["time"].is_monotonic_increasing)

    def test_invalid_ohlc_rejected(self):
        df = synthetic_prices()
        df.loc[10, "high"] = df.loc[10, "close"] - 1
        self._write(df)
        with self.assertRaisesRegex(RuntimeError, "Không thể lấy OHLCV"):
            with patch.object(ssi_adapter, "_fetch_live", side_effect=RuntimeError("no network")):
                ssi_adapter.lay_gia_ssi("SSI", 730)

    def test_duplicate_days_rejected(self):
        bad = pd.concat([synthetic_prices(), synthetic_prices().iloc[[4]]])
        with self.assertRaisesRegex(ValueError, "trùng phiên"):
            ssi_adapter._normalize(bad, "SSI")

    def test_refresh_failure_uses_old_cache_with_warning(self):
        self._write(synthetic_prices())
        with patch.object(ssi_adapter, "_fetch_live", side_effect=RuntimeError("network fail")):
            df = ssi_adapter.lay_gia_ssi("SSI", so_ngay=730, refresh=True)
        self.assertEqual(df.attrs["che_do"], "SSI_CACHE")
        self.assertIn("Không cập nhật", df.attrs["canh_bao"])

    def test_data_lay_gia_uses_ssi_by_default(self):
        from core.data import lay_gia
        self._write(synthetic_prices())
        with patch.dict("os.environ", {"BATDAY_CHO_PHEP_DU_PHONG_GIA": "0", "BATDAY_SSI_REFRESH": "0"}):
            df = lay_gia("SSI", so_ngay=730)
        self.assertEqual(df.attrs["nguon_gia"], "SSI FastConnect V3")
        self.assertIn("đã lưu", df.attrs["canh_bao"])

    def test_existing_scoring_code_still_accepts_ssi_frame(self):
        self._write(synthetic_prices())
        df = ssi_adapter.lay_gia_ssi("SSI", 730)
        analysed, kq, diem, toi_da, ly_do, kn = phan_tich(
            df, pd.DataFrame(), pd.DataFrame()
        )
        result = danh_gia_x10(analysed, kq, pd.DataFrame(), None)
        self.assertTrue(0 <= result["diem_tong"] <= 100)
        self.assertIn("RSI", analysed.columns)
        self.assertFalse(result["co_fa"])
        self.assertIsInstance(diem, (int, float))


if __name__ == "__main__":
    unittest.main()
