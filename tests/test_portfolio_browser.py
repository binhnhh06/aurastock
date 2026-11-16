"""Danh mục bản online: lưu riêng trong trình duyệt (localStorage), khôi phục khi mở lại."""
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.portfolio_store import PortfolioInputError, all_trades, record_trade, watch, watched_symbols  # noqa: E402
from core import portfolio_browser as pb  # noqa: E402


class FakeBrowser:
    """Giả lập localStorage + hành vi streamlit_js_eval (lần đầu trả None, lần sau trả kết quả)."""
    def __init__(self, stored=None):
        self.store = {} if stored is None else {pb.STORAGE_KEY: stored}
        self.seen = set()

    def new_session(self):
        other = FakeBrowser()
        other.store = self.store          # cùng trình duyệt: chung localStorage, khác phiên Streamlit
        return other

    def __call__(self, js_expressions, key):
        if key not in self.seen:
            self.seen.add(key)
            if "setItem" in js_expressions:
                import json
                text = json.loads(js_expressions.split(", ", 1)[1].rsplit(");", 1)[0])
                self.store[pb.STORAGE_KEY] = text
            return None
        return self.store.get(pb.STORAGE_KEY, pb._EMPTY)


class TestBrowserPortfolio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def db(self, name):
        return Path(self.tmp.name) / name / "p.sqlite3"

    def test_luu_roi_khoi_phuc_o_phien_moi(self):
        browser = FakeBrowser()
        s1, db1 = {}, self.db("phien1")
        self.assertEqual(pb.sync_with_browser(db1, s1, js_eval=browser), "pending")
        self.assertEqual(pb.sync_with_browser(db1, s1, js_eval=browser), "saved")      # danh mục rỗng
        watch(db1, "FPT")
        record_trade(db1, "FPT", "BUY", 100, Decimal("95000"), date(2026, 11, 10), fee_pct="0.15")
        self.assertEqual(pb.sync_with_browser(db1, s1, js_eval=browser), "saved")
        self.assertEqual(pb.sync_with_browser(db1, s1, js_eval=browser), "unchanged")
        # Đóng tab → phiên mới, file SQLite mới, cùng trình duyệt
        s2, db2 = {}, self.db("phien2")
        browser = browser.new_session()
        self.assertEqual(pb.sync_with_browser(db2, s2, js_eval=browser), "pending")
        self.assertEqual(pb.sync_with_browser(db2, s2, js_eval=browser), "restored")
        self.assertEqual(watched_symbols(db2), ["FPT"])
        self.assertEqual(len(all_trades(db2)), 1)

    def test_may_khac_khong_thay_danh_muc(self):
        db_a, db_b = self.db("a"), self.db("b")
        a, b = FakeBrowser(), FakeBrowser()
        sa, sb = {}, {}
        pb.sync_with_browser(db_a, sa, js_eval=a)
        pb.sync_with_browser(db_a, sa, js_eval=a)
        watch(db_a, "HPG")
        pb.sync_with_browser(db_a, sa, js_eval=a)
        pb.sync_with_browser(db_b, sb, js_eval=b)
        pb.sync_with_browser(db_b, sb, js_eval=b)
        self.assertEqual(watched_symbols(db_b), [])

    def test_chua_doc_xong_thi_khong_ghi_de(self):
        browser = FakeBrowser(stored=pb.to_text({"version": 1, "watched": [{"symbol": "VCB", "added_at": "x"}], "trades": []}))
        s, db = {}, self.db("c")
        pb.sync_with_browser(db, s, js_eval=browser)          # pending: không được ghi danh mục rỗng
        self.assertIn("VCB", browser.store[pb.STORAGE_KEY])

    def test_file_loi_bi_tu_choi(self):
        db = self.db("d")
        with self.assertRaises(PortfolioInputError):
            pb.import_state(db, '{"version": 9}')
        bad = {"version": 1, "watched": [], "trades": [
            {"id": 1, "symbol": "FPT", "trade_date": "2026-11-10", "side": "SELL", "quantity": 10,
             "price_vnd": "95000", "fee_pct": "0", "tax_pct": "0", "created_at": "x"}]}
        with self.assertRaises(PortfolioInputError):
            pb.import_state(db, pb.to_text(bad))                # bán khi chưa có cổ phiếu


if __name__ == "__main__":
    unittest.main()
