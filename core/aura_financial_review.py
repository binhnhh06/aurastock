"""Pure, source-transparent 2021–2025 BCTC presentation helpers for AURA.

This module does NOT score equities, certify a source or infer filings dates.
It prepares provisional data already computed by build_financial_features.py.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

ANNUAL_YEARS = (2021, 2022, 2023, 2024, 2025)
CANDIDATE_METRICS = (
    "roe_pct_provisional", "roa_pct_provisional", "eps_growth_pct_provisional",
    "net_margin_pct_provisional", "gross_margin_pct_provisional",
    "liabilities_to_equity_provisional",
)
DISPLAY_METRICS = {
    "symbol": "Mã", "year": "Năm", "company_type": "Loại hình",
    "roe_pct_provisional": "ROE (%)", "roa_pct_provisional": "ROA (%)",
    "eps_growth_pct_provisional": "Tăng trưởng EPS (%)",
    "net_margin_pct_provisional": "Biên LN ròng (%)",
    "gross_margin_pct_provisional": "Biên LN gộp (%)",
    "liabilities_to_equity_provisional": "Nợ phải trả/VCSH",
    "balance_identity_pass": "Cân đối đạt", "score_eligible": "Trạng thái điểm",
}


def prepare_annual(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty or not {"symbol", "year"}.issubset(raw.columns):
        return pd.DataFrame()
    df = raw.copy()
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df.loc[df["year"].isin(ANNUAL_YEARS) & df["symbol"].ne("")].copy()
    for col in CANDIDATE_METRICS:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "status" in df:
        status = df["status"].astype(str).str.upper()
        has_values = df[[c for c in CANDIDATE_METRICS if c in df]].notna().any(axis=1) if any(c in df for c in CANDIDATE_METRICS) else pd.Series(False,index=df.index)
        df["_has_candidate"] = status.eq("PROVISIONAL_REVIEW_REQUIRED") & has_values
    else:
        df["_has_candidate"] = df[[c for c in CANDIDATE_METRICS if c in df]].notna().any(axis=1) if any(c in df for c in CANDIDATE_METRICS) else False
    return df


def coverage_by_year(raw: pd.DataFrame, universe: Iterable[str]) -> pd.DataFrame:
    """Counts distinct symbols with at least one candidate financial ratio by year.

    This is NOT coverage of published original statements nor verification.
    """
    symbols = {str(s).upper().strip() for s in universe if str(s).strip()}
    df = prepare_annual(raw)
    rows = []
    for year in ANNUAL_YEARS:
        subset = df.loc[df["year"].eq(year) & df["symbol"].isin(symbols)] if not df.empty else pd.DataFrame()
        seen = int(subset.loc[subset["_has_candidate"], "symbol"].nunique()) if not subset.empty else 0
        rows.append({"Năm": year, "Mã có chỉ tiêu sơ bộ": seen, "Tổng mã": len(symbols),
                     "Độ phủ (%)": round(100 * seen / len(symbols), 1) if symbols else 0.})
    return pd.DataFrame(rows)


def five_years_with_ratios(raw: pd.DataFrame, universe: Iterable[str]) -> int:
    symbols = {str(s).upper().strip() for s in universe if str(s).strip()}
    df = prepare_annual(raw)
    if df.empty:
        return 0
    valid = df.loc[df["symbol"].isin(symbols) & df["_has_candidate"], ["symbol", "year"]].drop_duplicates()
    return int(valid.groupby("symbol")["year"].nunique().eq(5).sum()) if not valid.empty else 0


def provisional_rows(raw: pd.DataFrame, year: int, *, symbols: Iterable[str] | None = None,
                     groups: Iterable[str] | None = None) -> pd.DataFrame:
    df = prepare_annual(raw)
    if df.empty:
        return df
    df = df.loc[df["year"].eq(year) & df["_has_candidate"]].copy()
    if symbols:
        wanted = {str(s).strip().upper() for s in symbols}
        df = df.loc[df["symbol"].isin(wanted)]
    if groups and "company_type" in df:
        df = df.loc[df["company_type"].isin(set(groups))]
    return df.sort_values("symbol")


def rating_display(raw: pd.DataFrame) -> pd.DataFrame:
    """Blank ratings must never appear as 0, None or NaN."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    cols = ["Mã", "Điểm kỹ thuật /10", "Điểm cơ bản /10", "Điểm định giá /10",
            "Smart Rating tổng hợp /10", "Ghi chú dữ liệu"]
    view = raw[[c for c in cols if c in raw]].copy()
    for col in ("Điểm kỹ thuật /10", "Điểm cơ bản /10", "Điểm định giá /10", "Smart Rating tổng hợp /10"):
        if col in view:
            values = pd.to_numeric(view[col], errors="coerce")
            view[col] = values.map(lambda v: f"{v:.2f}" if pd.notna(v) else "Chưa đủ dữ liệu")
    if "Ghi chú dữ liệu" in view:
        view["Ghi chú dữ liệu"] = view["Ghi chú dữ liệu"].fillna("Cần xác minh nguồn và ngày công bố")
    return view


def preview_display(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    cols = [c for c in DISPLAY_METRICS if c in raw.columns]
    view = raw[cols].rename(columns=DISPLAY_METRICS).copy()
    for col in ("ROE (%)", "ROA (%)", "Tăng trưởng EPS (%)", "Biên LN ròng (%)", "Biên LN gộp (%)", "Nợ phải trả/VCSH"):
        if col in view:
            values = pd.to_numeric(view[col], errors="coerce")
            view[col] = values.map(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
    if "Cân đối đạt" in view:
        view["Cân đối đạt"] = view["Cân đối đạt"].map(lambda v: "Đạt" if str(v).strip().lower() in ("true", "1", "yes") else "Chưa đạt/chưa kiểm tra")
    if "Trạng thái điểm" in view:
        view["Trạng thái điểm"] = view["Trạng thái điểm"].map(
            lambda v: "Đã xác minh" if str(v).strip().upper() == "YES" else "Chưa xác minh")
    return view


def trend_for_symbol(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    df = prepare_annual(raw)
    if df.empty:
        return pd.DataFrame()
    cols = ["year"] + [c for c in ("roe_pct_provisional", "roa_pct_provisional", "eps_growth_pct_provisional") if c in df]
    result = df.loc[df["symbol"].eq(str(symbol).upper()), cols].sort_values("year").copy()
    return result.rename(columns={"year": "Năm", "roe_pct_provisional": "ROE (%)",
                                  "roa_pct_provisional": "ROA (%)", "eps_growth_pct_provisional": "Tăng trưởng EPS (%)"})
