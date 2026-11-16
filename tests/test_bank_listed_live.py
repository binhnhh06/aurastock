"""Ngân hàng: tiêu chí không áp dụng; CP niêm yết từ danh mục SSI; giá realtime qua R2 chỉ để hiển thị."""
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import profiles  # noqa: E402
from core.aura_suitability_consistency_v110 import one_profile_row  # noqa: E402
from core.aura_ssi_listed_v832 import enrich_listed_equity, OUT_VALUE  # noqa: E402
from core import ssi_market_live as live  # noqa: E402
from core import aura_live_r2  # noqa: E402


class TestNganHang(unittest.TestCase):
    def setUp(self):
        self.cfg = {"roe": 10, "no_vcsh": 1.0, "thanh_toan": 1.5, "bien_ln_rong": 5, "cfo_lnst": 0.8}
        self.ctx = {"roe": 18.0, "bien_ln_rong": 40.0, "no_vcsh": 9.5}

    def test_nhan_dien(self):
        self.assertTrue(profiles.la_ngan_hang("ctg"))
        self.assertTrue(profiles.la_ngan_hang("XYZ", "Ngân hàng"))
        self.assertFalse(profiles.la_ngan_hang("FPT", "Công nghệ thông tin"))

    def test_tieu_chi_khong_ap_dung_bi_loai_khoi_mau_so(self):
        kq = profiles.danh_gia(dict(self.ctx, la_ngan_hang=True), self.cfg)
        self.assertEqual(kq["khong_ap_dung"], 3)          # no_vcsh, thanh_toan, cfo_lnst
        self.assertEqual((kq["dat"], kq["khong"], kq["thieu"]), (2, 0, 0))
        row = one_profile_row("x", "An toàn", self.cfg, kq, preliminary=False)
        self.assertEqual(row["Đạt"], "2/2")
        self.assertEqual(row["% hợp"], 100)              # đủ độ phủ, không còn "Chưa đủ dữ liệu"

    def test_doanh_nghiep_thuong_khong_doi(self):
        kq = profiles.danh_gia(dict(self.ctx), self.cfg)
        self.assertEqual(kq["khong_ap_dung"], 0)
        self.assertEqual(kq["khong"], 1)                  # no_vcsh 9.5 > 1.0
        self.assertEqual(kq["thieu"], 2)


class TestCPNiemYet(unittest.TestCase):
    def test_lay_tu_danh_muc_ssi_va_xep_nhom(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data/ssi_cache"
            p.mkdir(parents=True)
            pd.DataFrame({"symbol": ["CTG", "AAA"], "board": ["HOSE", "HOSE"],
                          "listed_shares": ["5369991748", ""], "observed_at": ["2026-11-10", "2026-11-10"]}
                         ).to_csv(p / "market_symbols.csv", index=False)
            table = pd.DataFrame({"Mã": ["CTG", "AAA"], "Giá (VND)": [40000, 10000],
                                  "Ngày dữ liệu": ["2026-11-14", "2026-11-14"],
                                  "Nhóm vốn hóa": ["Chưa có dữ liệu", "Chưa có dữ liệu"]})
            res = enrich_listed_equity(table, Path(td), today="2026-11-16")
        self.assertAlmostEqual(res.loc[0, OUT_VALUE], 5369991748 * 40000 / 1e9)
        self.assertEqual(res.loc[0, "Nhóm vốn hóa"], "Large-cap (ước tính)")
        self.assertTrue(pd.isna(res.loc[1, OUT_VALUE]))
        self.assertEqual(res.loc[1, "Nhóm vốn hóa"], "Chưa có dữ liệu")

    def test_eod_qua_cu_khong_uoc_tinh(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "data/ssi_cache"
            p.mkdir(parents=True)
            pd.DataFrame({"symbol": ["CTG"], "listed_shares": ["100"], "observed_at": ["2026-11-10"]}
                         ).to_csv(p / "market_symbols.csv", index=False)
            table = pd.DataFrame({"Mã": ["CTG"], "Giá (VND)": [40000], "Ngày dữ liệu": ["2026-10-01"]})
            res = enrich_listed_equity(table, Path(td), today="2026-11-16")
        self.assertTrue(pd.isna(res.loc[0, OUT_VALUE]))


class FakeR2:
    def __init__(self):
        self.store = {}
        self.gets = 0

    def put_object(self, Bucket, Key, Body, **kw):
        self.store[Key] = Body

    def get_object(self, Bucket, Key):
        self.gets += 1
        if Key not in self.store:
            raise KeyError("NoSuchKey")
        return {"Body": io.BytesIO(self.store[Key])}


class TestRealtimeR2(unittest.TestCase):
    def setUp(self):
        aura_live_r2._CACHE.update(at=0.0, data={})

    def test_day_va_doc_snapshot_co_cache(self):
        r2 = FakeR2()
        state = {"connection": "CONNECTED", "worker_at": datetime.now(timezone.utc).isoformat(),
                 "quotes": {"FPT": {"price": 95000, "received_at": datetime.now(timezone.utc).isoformat()}}}
        self.assertTrue(aura_live_r2.push_snapshot(state, cli=r2))
        a = aura_live_r2.fetch_snapshot(cli=r2, now=100.0)
        b = aura_live_r2.fetch_snapshot(cli=r2, now=101.0)    # trong 5 giây: dùng cache
        self.assertEqual(a["quotes"]["FPT"]["price"], 95000)
        self.assertEqual(b, a)
        self.assertEqual(r2.gets, 1)

    def test_loi_r2_tra_ve_rong(self):
        self.assertEqual(aura_live_r2.fetch_snapshot(cli=FakeR2(), now=200.0), {})

    def test_read_snapshot_dung_r2_khi_file_local_cu(self):
        now = datetime.now(timezone.utc)
        cloud = {"connection": "CONNECTED", "worker_at": now.isoformat(),
                 "quotes": {"FPT": {"price": 95000, "received_at": now.isoformat()}}}
        with tempfile.TemporaryDirectory() as td:
            old = Path(td) / "live.json"
            old.write_text(json.dumps({"worker_at": (now - timedelta(hours=3)).isoformat()}), encoding="utf-8")
            orig = live.SNAPSHOT
            live.SNAPSHOT = old
            try:
                snap = live.read_snapshot(old, remote=lambda: cloud)
            finally:
                live.SNAPSHOT = orig
        self.assertEqual(snap["quotes"]["FPT"]["price"], 95000)

    def test_pusher_khong_lam_rot_worker_khi_loi(self):
        def boom(_):
            raise ConnectionError("x")
        p = aura_live_r2.R2Pusher(lambda: {}, interval=5, push=boom)
        self.assertFalse(p.run_once())
        self.assertEqual(p.failures, 1)


class TestWatchlist(unittest.TestCase):
    def test_uu_tien_bien_moi_truong_roi_thanh_khoan(self):
        with tempfile.TemporaryDirectory() as td:
            o = Path(td) / "data/ssi_cache/ohlcv"
            o.mkdir(parents=True)
            for sym, vol in (("AAA", 10), ("BBB", 1000), ("CCC", 100)):
                pd.DataFrame({"close": [10000] * 20, "volume": [vol] * 20}).to_csv(o / f"{sym}.csv", index=False)
            w = live.base_watchlist({"AAA", "BBB", "CCC", "FPT"}, Path(td), limit=3, extra="FPT,XXX")
        self.assertEqual(w, ["FPT", "BBB", "CCC"])


if __name__ == "__main__":
    unittest.main()
