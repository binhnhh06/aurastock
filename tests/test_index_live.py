"""Dải 4 chỉ số trên bản online lấy realtime từ kết nối SSI WebSocket của app (chỉ hiển thị)."""
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import aura_ssi_realtime_v97 as rt  # noqa: E402
from core.ssi_index_parse import parse_index_message  # noqa: E402
from core.vnindex_dashboard import market_data  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime.now(VN).replace(hour=10, minute=20, second=0, microsecond=0).astimezone(timezone.utc)


class IndexTickMessage:
    def __init__(self, symbol, value, **kw):
        self.symbol, self.value, self.trading_time = symbol, value, kw.pop("t", "")
        for k, v in kw.items():
            setattr(self, k, v)


class IndexSummaryMessage:
    def __init__(self, index, data):
        self.index, self.data = index, data


class TestParse(unittest.TestCase):
    def test_tick_va_summary(self):
        s, f = parse_index_message(IndexTickMessage("VNINDEX", 1740.2, change=5.3, change_percent=0.31,
                                                    advances=210, declines=120, no_change=50,
                                                    total_quantity=3.1e8, total_value=9.8e12), NOW)
        self.assertEqual((s, f["price"], f["advances"], f["nochanges"]), ("VNINDEX", 1740.2, 210, 50))
        s, f = parse_index_message(IndexSummaryMessage("HNXUPCOMINDEX", {"IndexValue": "121.9", "cr": "-0.2"}), NOW)
        self.assertEqual((s, f["price"], f["change_percent"]), ("UPCOMINDEX", 121.9, -0.2))

    def test_loai_gia_tri_vo_ly(self):
        self.assertIsNone(parse_index_message(IndexTickMessage("VNINDEX", 9.8e12), NOW))
        self.assertIsNone(parse_index_message(IndexTickMessage("FPT", 95.0), NOW))


class TestDaiChiSo(unittest.TestCase):
    def test_feed_cua_app_cho_trang_thai_live(self):
        feed = rt.LiveFeed(("a", "b", "c"))
        feed._start = lambda: None
        feed._connected = True
        feed._on_data(IndexTickMessage("VNINDEX", 1740.2, change=5.3, change_percent=0.31))
        snap = rt.live_index_snapshot(now=NOW, feed=feed)
        # received_at dùng giờ thật; đặt lại về NOW để kiểm thử độc lập thời điểm chạy
        snap["indices"]["VNINDEX"]["received_at"] = NOW.isoformat()
        snap["worker_at"] = NOW.isoformat()
        with tempfile.TemporaryDirectory() as td:
            d = market_data(Path(td), snapshot=snap, clock=NOW)
        self.assertEqual(d["VNINDEX"]["status"], "LIVE")
        self.assertAlmostEqual(d["VNINDEX"]["price"], 1740.2)

    def test_chua_bat_thi_rong(self):
        self.assertEqual(rt.live_index_snapshot(now=NOW, feed=None) if rt.get_feed() is None else {}, {})


if __name__ == "__main__":
    unittest.main()
