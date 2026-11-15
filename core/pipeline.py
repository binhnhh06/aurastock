import pandas as pd
from core.data import lay_gia, lay_bctc, lay_ratio
from core.analysis import phan_tich, tinh_ty_so
from core.strategy import danh_gia_x10
from core.profiles import xay_ngu_canh, danh_gia
from core import industry


def phan_tich_ma(ma, so_ngay, so_nam, vni):
    gia0 = lay_gia(ma, so_ngay)
    # Giữ nguyên nguồn BCTC/ratio hiện tại; đây chưa phải dữ liệu SSI.
    ratio, bctc = lay_ratio(ma), lay_bctc(ma, so_nam)
    ty_so = tinh_ty_so(bctc)
    gia, kq, diem, toi_da, ly_do, kn = phan_tich(gia0, ratio, ty_so)
    xep = danh_gia_x10(gia, kq, ty_so, vni)
    return {"ma": ma, "gia": gia, "kq": kq, "bctc": bctc, "ty_so": ty_so, "xep": xep,
            "diem": diem, "toi_da": toi_da, "ly_do": ly_do, "kn": kn, "vni": vni,
            "nguon_gia": gia0.attrs.get("nguon_gia", "Chưa xác định"),
            "che_do_gia": gia0.attrs.get("che_do", ""),
            "gia_cap_nhat_den": gia0.attrs.get("gia_cap_nhat_den", ""),
            "canh_bao_gia": gia0.attrs.get("canh_bao", ""),
            "nguon_bctc": "vnfinancialdata / vnstock (nguồn bổ trợ)",
            "nguon_vni": (
                vni.attrs.get("nguon_chi_so", vni.attrs.get("nguon_gia", "SSI FastConnect V3"))
                if isinstance(vni, pd.DataFrame) and not vni.empty
                else "VN-Index SSI: không có dữ liệu"
            )}


def ngu_canh_tu_ket_qua(r):
    return xay_ngu_canh(r["gia"], r["kq"], r["ty_so"], r["xep"], r["vni"])


def quet_nhieu_ma(danh_sach, so_ngay, so_nam, vni, cau_hinh, tien_do=None):
    hang = []
    for i, ma in enumerate(danh_sach):
        if tien_do:
            tien_do(i, len(danh_sach), ma)
        info = industry.thong_tin(ma)
        dong = {"Mã": ma, "Ngành": info.get("icb2", ""), "Sàn": info.get("san", "")}
        try:
            r = phan_tich_ma(ma, so_ngay, so_nam, vni)
            kv = danh_gia(ngu_canh_tu_ket_qua(r), cau_hinh)
            dong.update({
                "% hợp khẩu vị": round(kv["ty_le"], 0) if kv["ty_le"] is not None else None,
                "Đạt": f"{kv['dat']}/{kv['dat'] + kv['khong']}",
                "Mức hợp": kv["hang"],
                "Tín hiệu đánh giá": r["xep"]["tin_hieu"],
                "Điểm đánh giá": r["xep"]["diem_tong"],
                "Giá đóng cửa": r["kq"]["Giá đóng cửa"],
                "ROE (%)": r["kq"].get("ROE (%) (từ BCTC)"),
                "P/E": r["kq"].get("P/E"),
                "Lợi suất 6T (%)": r["kq"]["Lợi suất 6 tháng (%)"],
                "Nguồn giá": r.get("nguon_gia", ""),
                "Cập nhật đến": r.get("gia_cap_nhat_den", ""),
                "Ghi chú": (
                    "Thiếu chỉ số cơ bản; điểm đánh giá đang dùng 50 điểm cơ bản trung tính"
                    if not r["xep"].get("co_fa", False)
                    else r.get("canh_bao_gia", "")
                ),
            })
        except Exception as e:
            dong["Ghi chú"] = f"Lỗi: {str(e)[:60]}"
        hang.append(dong)
    if tien_do:
        tien_do(len(danh_sach), len(danh_sach), "")
    df = pd.DataFrame(hang)
    if "% hợp khẩu vị" in df:
        df = df.sort_values(["% hợp khẩu vị", "Điểm đánh giá"], ascending=False, na_position="last")
    return df.reset_index(drop=True)



def phan_tich_lai_voi_bctc(r, bctc):
    """Chấm lại 1 kết quả đã có, dùng BCTC do người dùng cung cấp thay cho dữ liệu tự động."""
    ty_so = tinh_ty_so(bctc)
    ratio = pd.DataFrame({k: [r["kq"][k]] for k in ("P/E", "P/B") if k in r["kq"]})
    gia, kq, diem, toi_da, ly_do, kn = phan_tich(r["gia"], ratio, ty_so)
    xep = danh_gia_x10(gia, kq, ty_so, r["vni"])
    return {**r, "gia": gia, "kq": kq, "bctc": bctc, "ty_so": ty_so, "xep": xep,
            "diem": diem, "toi_da": toi_da, "ly_do": ly_do, "kn": kn}