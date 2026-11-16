"""Biên LN ròng phải tính được dù nguồn BCTC đặt tên dòng doanh thu khác nhau."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.analysis import tinh_ty_so, tim_doanh_thu  # noqa: E402

NAM = [2023, 2024, 2025]


def bang(dong):
    return pd.DataFrame(dong, index=NAM).T


def bctc(dong_kqkd):
    bs = bang({"TỔNG TÀI SẢN": [1000, 1100, 1200], "VỐN CHỦ SỞ HỮU": [400, 450, 500],
               "NỢ PHẢI TRẢ": [600, 650, 700]})
    return {"balance_sheet": bs, "income_statement": bang(dong_kqkd)}


class TestDoanhThu(unittest.TestCase):
    def bien(self, dong):
        ts = tinh_ty_so(bctc(dong))
        return float(ts.loc["Biên LN ròng (%)", 2025]), ts

    def test_ten_vnstock_doanh_so_thuan(self):
        v, _ = self.bien({"Doanh số thuần": [100, 120, 200], "Lãi/(lỗ) thuần sau thuế": [10, 12, 20]})
        self.assertAlmostEqual(v, 10.0)

    def test_ten_vas_doanh_thu_thuan(self):
        v, ts = self.bien({"Doanh thu bán hàng và cung cấp dịch vụ": [110, 130, 210],
                           "Các khoản giảm trừ doanh thu": [10, 10, 10],
                           "Doanh thu thuần về bán hàng và cung cấp dịch vụ": [100, 120, 200],
                           "Doanh thu hoạt động tài chính": [5, 5, 5],
                           "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ": [30, 36, 60],
                           "Lợi nhuận sau thuế thu nhập doanh nghiệp": [10, 12, 30]})
        self.assertAlmostEqual(v, 15.0)  # 30 / 200, không lấy doanh thu tài chính hay doanh thu gộp
        self.assertAlmostEqual(float(ts.loc["Biên LN gộp (%)", 2025]), 30.0)
        self.assertEqual(ts.attrs["mau_so_doanh_thu"], "Doanh thu thuần")

    def test_ngan_hang_dung_tong_thu_nhap_hoat_dong(self):
        v, ts = self.bien({"Thu nhập lãi thuần": [80, 90, 100], "Tổng thu nhập hoạt động": [100, 110, 125],
                           "Lợi nhuận sau thuế": [40, 44, 50]})
        self.assertAlmostEqual(v, 40.0)
        self.assertNotIn("Biên LN gộp (%)", ts.index)  # ngân hàng không có biên gộp
        self.assertIn("ngân hàng", ts.attrs["mau_so_doanh_thu"])

    def test_khong_co_doanh_thu(self):
        rev, loai = tim_doanh_thu(bang({"Lợi nhuận sau thuế": [1, 2, 3]}))
        self.assertIsNone(rev)
        self.assertIsNone(loai)


if __name__ == "__main__":
    unittest.main()


class TestBVPSNganHang(unittest.TestCase):
    def kqkd(self):
        return bang({"Tổng thu nhập hoạt động": [100, 110, 125], "Lợi nhuận sau thuế": [40, 44, 50],
                     "Lãi cơ bản trên cổ phiếu": [2000, 2200, 2500]})

    def test_von_dieu_le(self):
        bs = bang({"TỔNG TÀI SẢN": [1000] * 3, "VỐN CHỦ SỞ HỮU": [400, 450, 500],
                   "NỢ PHẢI TRẢ": [600] * 3, "Vốn điều lệ": [200, 200, 200]})
        ts = tinh_ty_so({"balance_sheet": bs, "income_statement": self.kqkd()})
        self.assertAlmostEqual(float(ts.loc["BVPS (đồng)", 2025]), 500 / (200 / 10000))

    def test_khong_co_von_gop_thi_uoc_tinh_qua_eps(self):
        bs = bang({"TỔNG TÀI SẢN": [1000] * 3, "VỐN CHỦ SỞ HỮU": [400, 450, 500], "NỢ PHẢI TRẢ": [600] * 3})
        ts = tinh_ty_so({"balance_sheet": bs, "income_statement": self.kqkd()})
        so_cp = 50 / 2500
        self.assertAlmostEqual(float(ts.loc["BVPS (đồng)", 2025]), 500 / so_cp)


class TestPipelineR2(unittest.TestCase):
    def test_dung_bctc_r2_khi_nguon_cu_trong(self):
        from unittest.mock import patch
        import core.pipeline as pl
        stm = bctc({"Doanh thu thuần": [100, 120, 200], "Lợi nhuận sau thuế": [10, 12, 20]})
        with patch("core.aura_original_bctc_v99.load_original", return_value=(stm, {})):
            out = pl.bctc_tu_r2("FPT", 2)
        self.assertEqual(list(out["income_statement"].columns), [2024, 2025])
