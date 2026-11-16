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
