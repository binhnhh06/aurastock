"""AURA BCTC six-month 2026 read-only research panel.

This is not a verified financial score. No future data for the selected EOD.
"""
from pathlib import Path
import pandas as pd
import streamlit as st

NEEDED = ["symbol","report_period","period_end","publication_date","scope","source_url"]
NUMERIC = ["revenue_6m_vnd","net_profit_6m_vnd","revenue_6m_2025_vnd","net_profit_6m_2025_vnd"]


def _load(root: Path, as_of: str):
    path = root / "data" / "fundamentals" / "processed" / "bctc_h1_2026.csv"
    if not path.exists():
        return pd.DataFrame(), "Chưa có tệp BCTC 6T/2026 trong dự án."
    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    except Exception as exc:
        return pd.DataFrame(), f"Không đọc được dữ liệu 6T/2026 ({type(exc).__name__})."
    missing = [x for x in NEEDED if x not in df.columns]
    if missing:
        return pd.DataFrame(), "Thiếu trường bắt buộc: " + ", ".join(missing)
    # Restrict to exact half-year period and disclosure available by EOD.
    df = df.loc[
        df["report_period"].str.upper().isin(["6T/2026","H1/2026","6M/2026"])
        & df["period_end"].eq("2026-06-30")
        & df["publication_date"].str.match(r"^\d{4}-\d{2}-\d{2}$")
        & df["publication_date"].le(as_of)
        & df["source_url"].str.match(r"^https?://")
        & df["scope"].str.upper().isin(["CONSOLIDATED","SEPARATE"])
    ].copy()
    for c in NUMERIC:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if not df.empty:
        df = df.sort_values(["symbol", "scope", "publication_date"], ascending=[True,True,False])
    return df, None


def render_h1_panel(root=None, as_of="2026-11-13"):
    base = Path(root).resolve() if root else Path(__file__).resolve().parents[1]
    st.markdown("### BCTC bán niên 6T/2026")
    st.caption("Kỳ 01/01–30/06/2026 · tách biệt BCTC năm 2021–2025; chưa tham gia điểm nghiên cứu hoặc backtest.")
    df, err = _load(base, as_of)
    if err:
        st.info(err + " Chỉ bổ sung dữ liệu công bố có ngày và nguồn hợp lệ.")
        return
    if df.empty:
        st.info("Chưa có bản ghi 6T/2026 đáp ứng kỳ, ngày công bố và nguồn trước EOD " + as_of)
        return
    st.metric("Mã có dữ liệu bán niên đủ metadata", df["symbol"].nunique())
    cols = [x for x in ["symbol","scope","publication_date","revenue_6m_vnd","net_profit_6m_vnd","revenue_6m_2025_vnd","net_profit_6m_2025_vnd","source_url"] if x in df]
    with st.expander("Xem BCTC 6T/2026 (chưa xác minh độc lập)", expanded=False):
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
        st.caption("Dữ liệu do người vận hành nhập từ công bố; 6T và Q2 không tương đương; các nguồn cần được rà soát trước khi sử dụng.")
