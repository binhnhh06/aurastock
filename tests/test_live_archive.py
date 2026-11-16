"""Lưu lịch sử tick WebSocket: chỉ ghi tick mới, ghi sự kiện kết nối, tóm tắt theo ngày."""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.live_archive import LiveArchive, summarize  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def state(price, received, conn="CONNECTED"):
    return {"connection": conn,
            "quotes": {"FPT": {"price": price, "received_at": received, "quantity": 100}},
            "indices": {"VNINDEX": {"price": 1250.5, "received_at": received, "change": -2.1}}}


class TestArchive(unittest.TestCase):
    def test_chi_ghi_tick_moi_va_tom_tat(self):
        t0 = datetime(2026, 11, 16, 9, 30, tzinfo=VN)
        with tempfile.TemporaryDirectory() as td:
            a = LiveArchive(Path(td))
            self.assertEqual(a.capture(state(95000, "r1"), t0), 2)
            self.assertEqual(a.capture(state(95000, "r1"), t0 + timedelta(minutes=1)), 0)  # không tick mới
            self.assertEqual(a.capture(state(95100, "r2"), t0 + timedelta(minutes=2)), 2)
            a.capture(state(95100, "r2", "DISCONNECTED"), t0 + timedelta(minutes=3))
            d = pd.read_csv(Path(td) / "2026-11-16.csv", encoding="utf-8-sig")
            s = summarize(Path(td))
        self.assertEqual(len(d), 4)
        self.assertEqual(list(d["symbol"]), ["FPT", "VNINDEX", "FPT", "VNINDEX"])
        row = s.iloc[0]
        self.assertEqual((row["Số dòng"], row["Số mã cổ phiếu"], row["Số chỉ số"]), (4, 1, 1))
        self.assertEqual(row["Phút có dữ liệu"], 2)
        self.assertEqual(row["Lần mất kết nối"], 1)
        self.assertEqual(row["Giá trùng/không hợp lệ"], 0)

    def test_thu_muc_rong(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(summarize(Path(td)).empty)


if __name__ == "__main__":
    unittest.main()
