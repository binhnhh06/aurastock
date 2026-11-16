import pandas as pd


def tim_cot(df, *tu_khoa):
    for c in df.columns:
        if all(k.lower() in str(c).lower() for k in tu_khoa):
            return c
    return None


def lay_dong(bang, *ten_chinh_xac):
    """Lấy 1 dòng (Series theo năm) theo tên chính xác, rồi theo từ khóa gần đúng."""
    if bang is None or bang.empty:
        return None
    for t in ten_chinh_xac:
        for idx in bang.index:
            if str(idx).strip().lower() == t.lower():
                return bang.loc[idx]
    for t in ten_chinh_xac:
        for idx in bang.index:
            if t.lower() in str(idx).lower():
                return bang.loc[idx]
    return None


def lay_dong_chinh_xac(bang, *ten):
    if bang is None or bang.empty:
        return None
    for t in ten:
        for idx in bang.index:
            if str(idx).strip().lower() == t.lower():
                return bang.loc[idx]
    return None


# Tên dòng doanh thu khác nhau theo nguồn dữ liệu (vnfinancialdata, vnstock VCI/TCBS/KBS, VAS).
_DOANH_THU = ("Doanh số thuần", "Doanh thu thuần",
              "Doanh thu thuần về bán hàng và cung cấp dịch vụ",
              "Doanh thu thuần về hoạt động kinh doanh", "Net revenue", "Net sales")
_LOAI_TRU_DOANH_THU = ("tài chính", "giảm trừ", "nội bộ", "khác", "financial")
# Ngân hàng không có "doanh thu thuần"; dùng Tổng thu nhập hoạt động (TOI) làm mẫu số.
_THU_NHAP_NGAN_HANG = ("Tổng thu nhập hoạt động", "Tổng thu nhập hoạt động thuần",
                       "Total operating income")
_LAI_GOP = ("Lãi gộp", "Lợi nhuận gộp", "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ", "Gross profit")


def tim_doanh_thu(is_):
    """Trả về (Series doanh thu theo năm, loại) với loại = 'doanh_thu' | 'thu_nhap_hoat_dong' | None.

    Thứ tự: tên chính xác → tên chứa "doanh thu thuần"/"doanh số thuần" (bỏ dòng tài chính,
    giảm trừ...) → Tổng thu nhập hoạt động của ngân hàng.
    """
    if is_ is None or is_.empty:
        return None, None
    dong = lay_dong_chinh_xac(is_, *_DOANH_THU)
    if dong is not None:
        return dong, "doanh_thu"
    for idx in is_.index:
        t = str(idx).strip().lower()
        if ("doanh thu thuần" in t or "doanh số thuần" in t) and not any(k in t for k in _LOAI_TRU_DOANH_THU):
            return is_.loc[idx], "doanh_thu"
    dong = lay_dong_chinh_xac(is_, *_THU_NHAP_NGAN_HANG)
    if dong is not None:
        return dong, "thu_nhap_hoat_dong"
    return None, None


# Dòng vốn góp (để tính số CP và BVPS). Ngân hàng thường ghi "Vốn điều lệ"/"Vốn của tổ chức tín dụng".
_VON_GOP = ("Cổ phiếu phổ thông", "Vốn góp của chủ sở hữu", "Vốn đầu tư của chủ sở hữu",
            "Cổ phiếu phổ thông có quyền biểu quyết", "Vốn điều lệ", "Vốn cổ phần",
            "Vốn của tổ chức tín dụng", "Vốn góp", "Paid-in capital", "Charter capital")


def tim_von_gop(bs):
    dong = lay_dong_chinh_xac(bs, *_VON_GOP)
    if dong is not None or bs is None or bs.empty:
        return dong
    for idx in bs.index:
        t = str(idx).strip().lower()
        if any(k in t for k in ("vốn điều lệ", "vốn cổ phần", "vốn góp của chủ sở hữu")) and "thặng dư" not in t:
            return bs.loc[idx]
    return None


def lay_dong_co_tuc(cf):
    """Dòng cổ tức đã TRẢ trong báo cáo lưu chuyển tiền tệ (không lấy dòng cổ tức nhận được)."""
    if cf is None or cf.empty:
        return None
    dong = lay_dong_chinh_xac(cf, "Cổ tức đã trả", "Cổ tức, lợi nhuận đã trả cho chủ sở hữu",
                              "Cổ tức và lợi nhuận đã trả")
    if dong is not None:
        return dong
    loai = ("nhận", "thu", "được chia", "thiểu số")
    for idx in cf.index:
        t = str(idx).lower()
        if any(k in t for k in loai):
            continue
        if ("cổ tức" in t and "trả" in t) or ("lợi nhuận" in t and "trả" in t and "chủ sở hữu" in t):
            return cf.loc[idx]
    return None


def tinh_ty_so(bctc):
    """Tự tính tỷ số từ BCTC. Trả về DataFrame (tỷ số x năm)."""
    bs, is_ = bctc.get("balance_sheet"), bctc.get("income_statement")
    cf = bctc.get("cash_flow")
    if bs is None or is_ is None:
        return pd.DataFrame()

    ta = lay_dong(bs, "TỔNG TÀI SẢN")
    eq = lay_dong(bs, "VỐN CHỦ SỞ HỮU")
    debt = lay_dong(bs, "NỢ PHẢI TRẢ")
    ca = lay_dong(bs, "TÀI SẢN NGẮN HẠN")
    cl = lay_dong(bs, "Nợ ngắn hạn")
    rev, loai_doanh_thu = tim_doanh_thu(is_)
    # Ngân hàng: không tính biên gộp (không có giá vốn/lãi gộp theo nghĩa doanh nghiệp sản xuất).
    gp = lay_dong(is_, *_LAI_GOP) if loai_doanh_thu == "doanh_thu" else None
    npat = lay_dong(is_, "Lãi/(lỗ) thuần sau thuế", "Lợi nhuận sau thuế")

    kq = {}
    if npat is not None and eq is not None:
        kq["ROE (%)"] = npat / eq * 100
    if npat is not None and ta is not None:
        kq["ROA (%)"] = npat / ta * 100
    if npat is not None and rev is not None:
        kq["Biên LN ròng (%)"] = npat / rev * 100
    if gp is not None and rev is not None:
        kq["Biên LN gộp (%)"] = gp / rev * 100
    if debt is not None and eq is not None:
        kq["Nợ / VCSH (lần)"] = debt / eq
    if ca is not None and cl is not None:
        kq["Thanh toán hiện hành (lần)"] = ca / cl
    if rev is not None:
        kq["Tăng trưởng doanh thu (%)"] = rev.pct_change() * 100
    if npat is not None:
        kq["Tăng trưởng LNST (%)"] = npat.pct_change() * 100

    phan_vay = [x for x in (lay_dong_chinh_xac(bs, "Vay ngắn hạn"), lay_dong_chinh_xac(bs, "Vay dài hạn")) if x is not None]
    vay = pd.concat(phan_vay, axis=1).sum(axis=1, min_count=1) if phan_vay else None
    tien = lay_dong_chinh_xac(bs, "Tiền và tương đương tiền")
    ebit = lay_dong_chinh_xac(is_, "EBIT")
    lai_vay = lay_dong_chinh_xac(is_, "Trong đó: Chi phí lãi vay")
    cfo = lay_dong_chinh_xac(cf, "Lưu chuyển tiền thuần từ các hoạt động sản xuất kinh doanh")
    co_tuc = lay_dong_co_tuc(cf)

    if vay is not None and eq is not None:
        kq["Nợ vay / VCSH (lần)"] = vay / eq
    if debt is not None and ta is not None:
        kq["Nợ / Tổng tài sản (%)"] = debt / ta * 100
    if rev is not None and ta is not None:
        kq["Vòng quay tài sản (lần)"] = rev / ta
    if tien is not None and ta is not None:
        kq["Tiền / Tổng tài sản (%)"] = tien / ta * 100
    if ta is not None:
        kq["Tăng trưởng tổng tài sản (%)"] = ta.pct_change() * 100
    if ebit is not None and lai_vay is not None:
        kq["EBIT / Lãi vay (lần)"] = ebit / lai_vay.abs().replace(0, float("nan"))
    if cfo is not None and npat is not None:
        kq["CFO / LNST (lần)"] = cfo / npat.where(npat > 0)
    if co_tuc is not None and npat is not None:
        kq["Chi trả cổ tức / LNST (%)"] = co_tuc.abs() / npat.where(npat > 0) * 100

    # EPS và giá trị sổ sách/cổ phiếu (đồng), dùng để tự tính P/E, P/B từ giá hiện tại
    eps = lay_dong_chinh_xac(is_, "Lãi cơ bản trên cổ phiếu")
    if eps is None:
        eps = lay_dong(is_, "Lãi cơ bản trên cổ phiếu")
    von_gop = tim_von_gop(bs)
    if eps is not None:
        kq["EPS (đồng)"] = eps
    if von_gop is not None and eq is not None:
        kq["BVPS (đồng)"] = eq / (von_gop.where(von_gop > 0) / 10000)  # mệnh giá 10.000 đ/cổ phiếu
    elif eps is not None and npat is not None and eq is not None:
        # Không tìm được dòng vốn góp (thường gặp ở BCTC ngân hàng): số CP ≈ LNST / EPS.
        so_cp = npat / eps.where(eps > 0)
        kq["BVPS (đồng)"] = eq / so_cp.where(so_cp > 0)

    ket_qua = pd.DataFrame(kq).T.sort_index(axis=1)
    # Ghi chú mẫu số của biên LN ròng / tăng trưởng doanh thu để giao diện và báo cáo giải thích được.
    ket_qua.attrs["mau_so_doanh_thu"] = {
        "doanh_thu": "Doanh thu thuần",
        "thu_nhap_hoat_dong": "Tổng thu nhập hoạt động (ngân hàng)",
    }.get(loai_doanh_thu, "Không tìm thấy")
    return ket_qua


def phan_tich(gia, ratio, ty_so):
    gia = gia.copy()
    gia["MA20"] = gia["close"].rolling(20).mean()
    gia["MA50"] = gia["close"].rolling(50).mean()
    # RSI Wilder (1978), dùng CHUNG hàm với biểu đồ kỹ thuật để điểm chấm và đồ thị khớp nhau.
    from core.technical_chart import _rsi_wilder
    gia["RSI"] = _rsi_wilder(gia["close"], 14)
    last = gia.iloc[-1]
    n = min(126, len(gia) - 1)
    kq = {
        "Giá đóng cửa": float(last["close"]),
        "MA20": float(last["MA20"]),
        "MA50": float(last["MA50"]),
        "RSI(14)": float(last["RSI"]),
        "Lợi suất 6 tháng (%)": float((gia["close"].iloc[-1] / gia["close"].iloc[-1 - n] - 1) * 100),
        "Biến động năm (%)": float(gia["close"].pct_change().std() * (252 ** 0.5) * 100),
    }

    # P/E, P/B tự tính từ giá hiện tại và BCTC (không dùng bảng ratio vì dữ liệu có thể cũ)
    # Giá vnstock tính theo nghìn đồng
    gia_dong = kq["Giá đóng cửa"] * (1000 if kq["Giá đóng cửa"] < 1000 else 1)
    pe = None
    if not ty_so.empty and "EPS (đồng)" in ty_so.index:
        e = ty_so.loc["EPS (đồng)"].dropna()
        if len(e) and e.iloc[-1] > 0:
            pe = gia_dong / float(e.iloc[-1])
            kq["P/E"] = pe
    if not ty_so.empty and "BVPS (đồng)" in ty_so.index:
        v = ty_so.loc["BVPS (đồng)"].dropna()
        if len(v) and v.iloc[-1] > 0:
            pb = gia_dong / float(v.iloc[-1])
            if 0.05 <= pb <= 100:  # loại kết quả vô lý do sai đơn vị
                kq["P/B"] = pb

    roe = None
    if not ty_so.empty and "ROE (%)" in ty_so.index:
        roe = float(ty_so.loc["ROE (%)"].dropna().iloc[-1]); kq["ROE (%) (từ BCTC)"] = roe
    if not ty_so.empty and "Nợ / VCSH (lần)" in ty_so.index:
        kq["Nợ / VCSH (lần)"] = float(ty_so.loc["Nợ / VCSH (lần)"].dropna().iloc[-1])

    # Chấm điểm: 4 tiêu chí kỹ thuật + 4 tiêu chí cơ bản (tối đa 8)
    diem, ly_do, toi_da = 0, [], 4
    if kq["Giá đóng cửa"] > kq["MA50"]:
        diem += 1; ly_do.append("Giá trên MA50: xu hướng tăng")
    if kq["MA20"] > kq["MA50"]:
        diem += 1; ly_do.append("MA20 trên MA50: động lượng tích cực")
    if 30 < kq["RSI(14)"] < 70:
        diem += 1; ly_do.append("RSI trong vùng cân bằng (30-70)")
    if kq["Lợi suất 6 tháng (%)"] > 0:
        diem += 1; ly_do.append("Lợi suất 6 tháng dương")
    if roe is not None:
        toi_da += 1
        if roe >= 15:
            diem += 1; ly_do.append(f"ROE {roe:.1f}% (từ 15% trở lên)")
    if pe is not None:
        toi_da += 1
        if 0 < pe < 15:
            diem += 1; ly_do.append(f"P/E {pe:.1f} hấp dẫn (dưới 15)")
    if not ty_so.empty and "Nợ / VCSH (lần)" in ty_so.index:
        toi_da += 1
        if kq["Nợ / VCSH (lần)"] < 2:
            diem += 1; ly_do.append("Đòn bẩy an toàn (Nợ/VCSH dưới 2 lần)")
    if not ty_so.empty and "Tăng trưởng LNST (%)" in ty_so.index:
        toi_da += 1
        g = ty_so.loc["Tăng trưởng LNST (%)"].dropna()
        if len(g) and g.iloc[-1] > 0:
            diem += 1; ly_do.append(f"Lợi nhuận tăng trưởng {g.iloc[-1]:.1f}% so với năm trước")

    ti_le = diem / toi_da
    kn = "MUA / TÍCH LŨY" if ti_le >= 0.7 else "THEO DÕI" if ti_le >= 0.4 else "TRÁNH / CHỜ"
    return gia, kq, diem, toi_da, ly_do, kn