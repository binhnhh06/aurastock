"""Display-only: reference ratios calculated from unverified private R2 BCTC.

Never alters the original analysis, suitability scores, X10 or Smart Rating.
"""
from __future__ import annotations

import math
import pandas as pd

# Mapping must match the labels produced by core.analysis.tinh_ty_so.
_METRICS = (
    ("roe", "ROE (%)", "ROE", "%"),
    ("bien_ln_rong", "Biên LN ròng (%)", "Biên lợi nhuận ròng", "%"),
    ("no_vcsh", "Nợ / VCSH (lần)", "Nợ / vốn chủ sở hữu", "lần"),
    ("tang_truong_lnst", "Tăng trưởng LNST (%)", "Tăng trưởng lợi nhuận sau thuế", "%"),
    ("bien_ln_gop", "Biên LN gộp (%)", "Biên lợi nhuận gộp", "%"),
    ("cfo_lnst", "CFO / LNST (lần)", "Dòng tiền kinh doanh / LNST", "lần"),
)


def _last_real_value(df: pd.DataFrame, label: str):
    if df is None or df.empty or label not in df.index:
        return None
    series = df.loc[label]
    if isinstance(series, pd.DataFrame):
        # Duplicate labels: never assume a row is the correct metric.
        return None
    values = pd.to_numeric(series, errors="coerce")
    clean = [(year, float(value)) for year, value in values.items()
             if pd.notna(value) and math.isfinite(float(value))]
    if not clean:
        return None
    # Input columns are ordered by annual year in core.analysis.
    def order(pair):
        try:
            return int(pair[0])
        except (ValueError, TypeError):
            return -1
    return max(clean, key=order)


def render_reference_ratios(symbol: str, config: dict | None = None) -> bool:
    """Separate unverified research panel, never an input to a score."""
    import streamlit as st
    from core.aura_original_bctc_v99 import load_original
    from core.analysis import tinh_ty_so

    result = load_original(symbol)
    if not result:
        return False
    statements, metadata = result
    if not statements:
        return False
    try:
        ratios = tinh_ty_so(statements)
    except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError, AttributeError):
        return False
    if ratios is None or ratios.empty:
        return False

    rows = []
    for key, internal_name, label, suffix in _METRICS:
        found = _last_real_value(ratios, internal_name)
        if found is None:
            continue
        year, value = found
        rows.append({
            "Chỉ tiêu": label,
            "Giá trị tham khảo": f"{value:,.2f} {suffix}".replace(",", " "),
            "Năm BCTC": str(year),
            "Ngưỡng khẩu vị": (
                str(config.get(key)) + (" " + suffix if suffix else "")
                if config and key in config else "Chưa bật"
            ),
        })
    if not rows:
        return False
    st.markdown("#### Tỷ số BCTC tham khảo (R2)")
    st.caption("Các tỷ số dưới đây được tính từ BCTC lưu trên R2 và CHƯA đối chiếu "
               "công bố chính thức. Chúng KHÔNG thay thế trạng thái tiêu chí đã xác minh "
               "phía trên, không thay đổi % hợp khẩu vị, điểm X10 hay Smart Rating.")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    return True
