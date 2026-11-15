"""Kiểm tra cache SSI thực tế của NGƯỜI DÙNG và tính X10 baseline, không gọi giao dịch."""
import pandas as pd
from core.data import lay_gia
from core.analysis import phan_tich
from core.strategy import danh_gia_x10

if __name__ == "__main__":
    print("=== BATDAY SSI 2.0 / SMOKE TEST ===")
    print("Mã: SSI | Nguồn giá mong đợi: SSI FastConnect V3")
    gia = lay_gia("SSI", so_ngay=730)
    print("Nguồn:", gia.attrs.get("nguon_gia"))
    print("Chế độ:", gia.attrs.get("che_do"))
    print("Cảnh báo:", gia.attrs.get("canh_bao"))
    print("Phiên:", len(gia))
    print(gia.tail(2).to_string(index=False))
    if gia.attrs.get("nguon_gia") != "SSI FastConnect V3":
        raise RuntimeError("Nguồn giá chưa phải SSI!")
    g, kq, diem, toi_da, ly_do, kn = phan_tich(
        gia, pd.DataFrame(), pd.DataFrame()
    )
    xep = danh_gia_x10(g, kq, pd.DataFrame(), None)
    print("MA20:", round(kq["MA20"], 2))
    print("MA50:", round(kq["MA50"], 2))
    print("RSI14 (SMA):", round(kq["RSI(14)"], 2))
    print("Điểm X10 baseline:", xep["diem_tong"])
    print("Thiếu BCTC:", not xep["co_fa"])
    print("Đã kiểm tra thành công đầu vào SSI -> Phân tích -> X10 baseline")
