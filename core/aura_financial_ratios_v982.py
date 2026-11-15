"""AURA V9.8.2: display-only, non-verified historical financial ratios.

This module never changes score_eligible/source_verified, scoring pipelines, or prices.
BCTC source: financial_features_annual.csv restored from private R2 by V9.8.
"""
from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

_RATIOS = (
    ("roe_pct_provisional", "ROE", "%"),
    ("roa_pct_provisional", "ROA", "%"),
    ("eps_growth_pct_provisional", "Tăng trưởng EPS", "%"),
    ("net_margin_pct_provisional", "Biên lợi nhuận ròng", "%"),
    ("gross_margin_pct_provisional", "Biên lợi nhuận gộp", "%"),
    ("current_ratio_provisional", "Khả năng thanh toán hiện hành", "lần"),
    ("liabilities_to_equity_provisional", "Nợ phải trả/VCSH", "lần"),
)
_YEARS = tuple(range(2021, 2026))
_TRUE = {"1", "Y", "YES", "TRUE"}


def build_candidate_ratios(root: Path, symbol: str):
    """Return display frame, per-metric numeric trends, provenance summary.

    Missing or unparseable numbers stay blank. No fabricated zeros or scores.
    """
    symbol = str(symbol or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,12}", symbol):
        return None
    path = Path(root) / "data" / "fundamentals" / "processed" / "financial_features_annual.csv"
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except (OSError, ValueError, UnicodeError, pd.errors.ParserError):
        return None
    if not {"symbol", "year", "source_verified", "score_eligible"}.issubset(df.columns):
        return None
    df = df.loc[df["symbol"].astype(str).str.strip().str.upper().eq(symbol)].copy()
    if df.empty:
        return None
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df[df["year"].isin(_YEARS)].sort_values("year")
    if df.empty or df["year"].duplicated().any():
        return None  # fail closed on duplicate years, don't pick arbitrary values

    years = [int(y) for y in df["year"]]
    records, series = [], {}
    for source, label, unit in _RATIOS:
        if source not in df.columns:
            continue
        vals = pd.to_numeric(df[source], errors="coerce").replace([float("inf"), float("-inf")], float("nan"))
        if not vals.notna().any():
            continue
        vals = vals.reset_index(drop=True)
        numeric = pd.Series(vals.to_list(), index=years, dtype="float64")
        series[label + " (" + unit + ")"] = numeric
        record = {"Chỉ tiêu": label, "Đơn vị": unit}
        for y in _YEARS:
            v = numeric.get(y, float("nan"))
            record[str(y)] = round(float(v), 2) if pd.notna(v) else None
        records.append(record)
    if not records:
        return None
    verified = int(df["source_verified"].fillna("").astype(str).str.strip().str.upper().isin(_TRUE).sum())
    eligible = int(df["score_eligible"].fillna("").astype(str).str.strip().str.upper().isin(_TRUE).sum())
    meta = {"total_years": len(df), "verified": verified, "eligible": eligible, "years": years}
    return pd.DataFrame.from_records(records), series, meta


def render_provisional_ratios(root: Path, symbol: str):
    """Return True if private R2 candidate ratios rendered; not an audited-BCTC replacement."""
    prepared = build_candidate_ratios(root, symbol)
    if prepared is None:
        return False
    import streamlit as st
    table, series, meta = prepared
    st.subheader("Tỷ số tài chính 2021–2025 · dữ liệu sơ bộ")
    st.warning(
        "Các chỉ tiêu dưới đây được tính từ bảng candidate/provisional đã xử lý; "
        "**chưa được đối chiếu với BCTC gốc**. Chỉ dùng tham khảo, "
        "không dùng để tính Smart Rating, điểm cơ bản hoặc backtest."
    )
    st.caption(
        f"Có số liệu cho {meta['total_years']} năm · Đã xác minh nguồn: "
        f"{meta['verified']}/{meta['total_years']} năm · "
        f"Đủ điều kiện chấm điểm: {meta['eligible']}/{meta['total_years']} năm."
    )
    st.dataframe(table, hide_index=True, use_container_width=True)
    if len(series) > 0:
        metric = st.selectbox("Biểu đồ tỷ số sơ bộ", list(series), key="aura_v982_ratio_" + str(symbol))
        trend = series[metric].dropna()
        if len(trend) >= 2:
            st.line_chart(pd.DataFrame({metric: trend}), height=240)
        else:
            st.caption("Chưa đủ hai năm có dữ liệu để vẽ xu hướng cho chỉ tiêu này.")
    st.caption("Nguồn: bộ BCTC 5 năm sơ bộ trên R2 private; giá realtime/EOD không tham gia các tỷ số này.")
    return True
