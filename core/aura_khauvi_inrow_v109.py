"""AURA V10.9: R2 reference values alongside missing suitability metrics.

Display-only: does NOT mutate original kv, xep, r, or scoring functions.
Only uses unverified stored financial reports as explicitly labeled reference.
"""
from __future__ import annotations

import math

# Existing V10.5 metric labels are paired with profiles.TIEU_CHI keys.
_LABELS = {
    "roe": ("ROE (%)", "%"),
    "bien_ln_rong": ("Biên LN ròng (%)", "%"),
    "bien_ln_gop": ("Biên LN gộp (%)", "%"),
    "no_vcsh": ("Nợ / VCSH (lần)", "lần"),
    "no_vay_vcsh": ("Nợ vay / VCSH (lần)", "lần"),
    "thanh_toan": ("Thanh toán hiện hành (lần)", "lần"),
    "cfo_lnst": ("CFO / LNST (lần)", "lần"),
    "tang_truong_lnst": ("Tăng trưởng LNST (%)", "%"),
    "tang_truong_dt": ("Tăng trưởng doanh thu (%)", "%"),
    "chi_tra_co_tuc": ("Chi trả cổ tức / LNST (%)", "%"),
}


def _vn_number(number: float) -> str:
    return f"{number:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _ref_values(symbol: str, price_vnd):
    import pandas as pd
    from core.aura_original_bctc_v99 import load_original
    from core.analysis import tinh_ty_so
    from core.aura_khauvi_reference_v105 import _last_real_value

    doc = load_original(symbol)
    if not doc or not doc[0]:
        return {}
    ratios = tinh_ty_so(doc[0])
    if ratios is None or ratios.empty:
        return {}

    refs = {}
    for key, (label, unit) in _LABELS.items():
        found = _last_real_value(ratios, label)
        if found is not None:
            year, value = found
            if math.isfinite(value):
                refs[key] = (value, str(year), unit)

    # Average ROE over three distinct years only; never fabricate years.
    if "ROE (%)" in ratios.index:
        series = ratios.loc["ROE (%)"]
        if isinstance(series, pd.Series):
            vals = pd.to_numeric(series, errors="coerce").dropna()
            pairs = []
            for year, val in vals.items():
                try:
                    y, v = int(year), float(val)
                except (ValueError, TypeError):
                    continue
                if math.isfinite(v):
                    pairs.append((y, v))
            pairs.sort()
            if len(pairs) >= 3 and all(pairs[-j][0] - pairs[-j-1][0] == 1 for j in (1, 2)):
                refs["roe_tb3"] = (sum(v for _, v in pairs[-3:]) / 3, f"{pairs[-3][0]}–{pairs[-1][0]}", "%")

    # PE/PB are reference ratios using VND EOD and annual EPS/BVPS.
    # A unit-ambiguous stock price is never converted by guessing x1000.
    try:
        price = float(price_vnd)
    except (TypeError, ValueError, OverflowError):
        price = float("nan")
    if math.isfinite(price) and 1000 <= price <= 10_000_000:
        for key, label in (("pe", "EPS (đồng)"), ("pb", "BVPS (đồng)")):
            found = _last_real_value(ratios, label)
            if found and found[1] > 0:
                multiple = price / found[1]
                if math.isfinite(multiple) and 0 < multiple <= 500:
                    refs[key] = (multiple, str(found[0]) + " + giá EOD", "lần")
    return refs


def annotate_rows(symbol: str, current_rows: list, criteria: list, *, price_vnd=None):
    """Return an independent presentation copy of rows; original score untouched.

    A missing official criterion becomes `Tham khảo` only in the rendered
    copy if a finite reference figure is present. It is never marked `Đạt`.
    """
    label_to_key = {item["nhan"]: item["key"] for item in criteria}
    refs = _ref_values(symbol, price_vnd)
    result = []
    count = 0
    for old in current_rows:
        d = dict(old)
        key = label_to_key.get(d.get("nhan"))
        if d.get("trang_thai") == "Thiếu dữ liệu" and key in refs:
            value, year, unit = refs[key]
            d["trang_thai"] = "Tham khảo"
            d["gia_tri"] = f"{_vn_number(value)} {unit} · BCTC {year} (AURA/R2)"
            count += 1
        result.append(d)
    return result, count
