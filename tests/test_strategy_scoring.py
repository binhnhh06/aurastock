"""Kiểm thử hàm chấm điểm X10 trong core/strategy.py (dữ liệu tổng hợp, không gọi SSI)."""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.strategy import diem_ta, diem_fa, tinh_diem_x10 as x10_goc  # noqa: E402

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def gia_tong_hop(n=260, xu_huong=0.002, phien_cuoi=None):
    """Chuỗi giá tăng đều, phiên cuối là hôm nay theo giờ VN."""
    phien_cuoi = phien_cuoi or datetime.now(VN_TZ).date()
    time = pd.bdate_range(end=pd.Timestamp(phien_cuoi), periods=n)
    close = 20000 * np.cumprod(np.full(n, 1 + xu_huong))
    df = pd.DataFrame({"time": time, "open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": np.full(n, 1_000_000.0)})
    delta = df["close"].diff()
    up = delta.clip(lower=0).rolling(14).mean()
    down = (-delta.clip(upper=0)).rolling(14).mean()
    df["RSI"] = (100 - 100 / (1 + up / down.replace(0, np.nan))).fillna(60)
    return df


class TestDiem(unittest.TestCase):
    def test_diem_ta_trong_khoang_0_100(self):
        d = diem_ta(gia_tong_hop())
        self.assertGreaterEqual(d, 0)
        self.assertLessEqual(d, 100)

    def test_xu_huong_tang_diem_cao_hon_xu_huong_giam(self):
        self.assertGreater(diem_ta(gia_tong_hop(xu_huong=0.002)), diem_ta(gia_tong_hop(xu_huong=-0.002)))

    def test_khong_co_bctc_khong_gan_diem_gia_dinh(self):
        fa, co_fa = diem_fa(pd.DataFrame())
        self.assertFalse(co_fa)
        kq = x10_goc(gia_tong_hop(), None, pd.DataFrame(), None)
        # Thiếu BCTC: điểm tổng phải bằng điểm kỹ thuật, không cộng điểm cơ bản 50 mặc định
        self.assertAlmostEqual(kq["diem_tong"], kq["diem_ta"], places=1)

    def test_du_lieu_moi_tinh_theo_gio_viet_nam(self):
        kq = x10_goc(gia_tong_hop(), None, pd.DataFrame(), None)
        dong = dict((ten, trang_thai) for ten, trang_thai, _ in kq["dk_mua"])
        self.assertEqual(dong["Dữ liệu đầy đủ, phiên mới nhất"], "Đạt")

    def test_du_lieu_cu_bi_danh_dau(self):
        cu = datetime.now(VN_TZ).date() - pd.Timedelta(days=30)
        kq = x10_goc(gia_tong_hop(phien_cuoi=cu), None, pd.DataFrame(), None)
        dong = dict((ten, trang_thai) for ten, trang_thai, _ in kq["dk_mua"])
        self.assertEqual(dong["Dữ liệu đầy đủ, phiên mới nhất"], "Không đạt")


if __name__ == "__main__":
    unittest.main()


class TestRSI(unittest.TestCase):
    def test_rsi_cham_diem_trung_rsi_bieu_do(self):
        from core.analysis import phan_tich
        from core.technical_chart import _rsi_wilder
        rng = np.random.default_rng(7)
        close = pd.Series(20000 * np.cumprod(1 + rng.normal(0, 0.02, 300)))
        g = pd.DataFrame({"time": pd.bdate_range("2025-01-01", periods=300), "open": close,
                          "high": close, "low": close, "close": close, "volume": 1e6})
        gia, _ = phan_tich(g, None, pd.DataFrame())[:2]
        self.assertAlmostEqual(float(gia["RSI"].iloc[-1]), float(_rsi_wilder(close).iloc[-1]), places=6)
        self.assertTrue(gia["RSI"].dropna().between(0, 100).all())
