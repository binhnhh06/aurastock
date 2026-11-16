"""Giá realtime chỉ để hiển thị: đọc được giờ khớp nhiều định dạng; nếu không đọc được thì
dùng thời điểm nhận tick (đang trong phiên + đang kết nối) thay vì loại tick."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import aura_ssi_realtime_v97 as rt  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 11, 16, 10, 13, 30, tzinfo=VN).astimezone(timezone.utc)


class TradeMessage:  # cùng tên lớp với SDK
    def __init__(self, symbol, price, t):
        self.symbol, self.price, self.trading_time, self.quantity = symbol, price, t, 100


class TestParse(unittest.TestCase):
    def test_cac_dinh_dang(self):
        for raw in ("10:13:21", "101321", "2026-11-16T10:13:21+07:00", "16/11/2026 10:13:21",
                    str(int(datetime(2026, 11, 16, 10, 13, 21, tzinfo=VN).timestamp() * 1000))):
            d = rt.parse_exchange_time(raw, NOW)
            self.assertEqual((d.date().isoformat(), d.strftime("%H:%M:%S")), ("2026-11-16", "10:13:21"), raw)
        self.assertIsNone(rt.parse_exchange_time("abc", NOW))


class TestHienThi(unittest.TestCase):
    def feed(self, t):
        f = rt.LiveFeed(("a", "b", "c"))
        f._start = lambda: None           # không mở kết nối thật
        f._connected = True
        f.watch("FPT", NOW)               # đăng ký mã
        orig = rt.datetime

        class FixedNow(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW if tz else NOW.replace(tzinfo=None)
        rt.datetime = FixedNow
        try:
            f._on_data(TradeMessage("FPT", 95.1, t))
        finally:
            rt.datetime = orig
        return f

    def test_gio_khop_doc_duoc_la_live(self):
        q = rt.display_live_quote("FPT", 95000, "2026-11-13", now=NOW, feed=self.feed("10:13:21"))
        self.assertEqual(q["status"], "LIVE_TICK")
        self.assertEqual(q["price"], 95100)          # tick đơn vị nghìn đồng được quy đổi
        self.assertTrue(q["detail"].startswith("Khớp lúc 16/11/2026 10:13:21"))

    def test_gio_khop_khong_doc_duoc_van_hien_thi_theo_gio_nhan(self):
        q = rt.display_live_quote("FPT", 95000, "2026-11-13", now=NOW, feed=self.feed("??"))
        self.assertEqual(q["status"], "LIVE_TICK")
        self.assertTrue(q["detail"].startswith("Nhận lúc "))

    def test_ngoai_gio(self):
        evening = datetime(2026, 11, 16, 20, 0, tzinfo=VN).astimezone(timezone.utc)
        f = rt.LiveFeed(("a", "b", "c"))
        f._start = lambda: None
        q = rt.display_live_quote("FPT", 95000, now=evening, feed=f)
        self.assertIsNone(q["price"])
        self.assertIn("Ngoài giờ", q["detail"])


if __name__ == "__main__":
    unittest.main()
