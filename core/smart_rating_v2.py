"""SSI Smart Rating v2: transparent, point-in-time-aware multi-factor prototype.

Never calls trading APIs or reads credentials. Existing X10 and v1 stay untouched.
Unverified financial inputs are not automatically imputed or scored.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

RATING_WEIGHTS = {"technical": 0.50, "fundamental": 0.35, "valuation": 0.15}
MIN_PEERS = 3
MAX_REPORT_AGE_DAYS = 540
MAX_VALUATION_AGE_DAYS = 20

BASE_COLS = [
    "symbol", "sector_type", "peer_group", "report_period_end", "published_at", "source",
    "roe_pct", "roa_pct", "gross_margin_pct", "eps_growth_pct", "debt_equity", "current_ratio",
    "npl_pct", "car_pct", "pe", "pb", "ev_ebitda", "valuation_asof", "valuation_source"
]
BANK_METRICS = {"roe_pct": True, "roa_pct": True, "npl_pct": False, "car_pct": True}
CORP_METRICS = {
    "roe_pct": True, "roa_pct": True, "gross_margin_pct": True,
    "eps_growth_pct": True, "debt_equity": False, "current_ratio": True,
}
VALUATION_METRICS = {"pe": False, "pb": False, "ev_ebitda": False}
NUMERIC_COLS = list(dict.fromkeys([*BANK_METRICS, *CORP_METRICS, *VALUATION_METRICS]))


def empty_input_template(symbols: list[str]) -> pd.DataFrame:
    """Create a blank, auditable template without making up company financials."""
    symbols = sorted(set(str(s).upper().strip() for s in symbols if str(s).strip()))
    result = pd.DataFrame({"symbol": symbols})
    for col in BASE_COLS[1:]:
        result[col] = ""
    return result[BASE_COLS]


def _ensure_inputs(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(BASE_COLS) - set(frame.columns)
    if missing:
        raise ValueError("Thiếu các cột bắt buộc trong BCTC: " + ", ".join(sorted(missing)))
    out = frame[BASE_COLS].copy()
    for col in ("symbol", "sector_type", "peer_group", "source", "valuation_source"):
        out[col] = out[col].fillna("").astype(str).str.strip()
    out["symbol"] = out["symbol"].str.upper()
    out["sector_type"] = out["sector_type"].str.upper()
    out["peer_group"] = out["peer_group"].str.upper()
    for col in ("report_period_end", "published_at", "valuation_asof"):
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.normalize()
    for col in NUMERIC_COLS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
        out.loc[~np.isfinite(out[col]), col] = np.nan
    # Negative / zero earnings multiples are not cheap valuation signals.
    for col in ("pe", "pb", "ev_ebitda"):
        out.loc[out[col] <= 0, col] = np.nan
    for col in ("current_ratio", "debt_equity", "npl_pct", "car_pct"):
        out.loc[out[col] < 0, col] = np.nan
    for col in ("npl_pct", "car_pct"):
        out.loc[out[col] > 100, col] = np.nan
    return out


def read_financial_snapshot(
    path: Optional[Path] = None,
    *,
    table: Optional[pd.DataFrame] = None,
    as_of: str,
) -> pd.DataFrame:
    """Pick latest valid, published BCTC per symbol as of scan date.

    Missing/unverified accounting date, provenance, or sector prevents scoring.
    Valuation is only used when it has its own recent as-of date and source.
    """
    if table is None:
        if path is None or not Path(path).exists():
            return _ensure_inputs(pd.DataFrame(columns=BASE_COLS))
        table = pd.read_csv(path, encoding="utf-8-sig", dtype={"symbol": str})
    raw = _ensure_inputs(table)
    target = pd.Timestamp(as_of).normalize()
    if pd.isna(target):
        raise ValueError("Ngày chốt dữ liệu không hợp lệ")
    # No look-ahead: future publication is not available on the scan date.
    eligible = (
        raw["symbol"].ne("") & raw["source"].ne("")
        & raw["published_at"].notna()
        & raw["report_period_end"].notna()
        & raw["published_at"].le(target)
        & raw["report_period_end"].le(raw["published_at"])
        & (target - raw["published_at"]).dt.days.between(0, MAX_REPORT_AGE_DAYS)
        & raw["sector_type"].isin(["BANK", "NONBANK"])
        & raw["peer_group"].ne("")
    )
    raw = raw.loc[eligible].copy()
    raw = raw.sort_values(["symbol", "published_at", "report_period_end"])
    raw = raw.drop_duplicates("symbol", keep="last").reset_index(drop=True)
    if raw.empty:
        return raw
    # Valuation ratios require time-stamped sources; old/future values are missing.
    vdate = raw["valuation_asof"]
    valid_valuation = (
        vdate.notna() & vdate.le(target)
        & ((target - vdate).dt.days.between(0, MAX_VALUATION_AGE_DAYS))
        & raw["valuation_source"].ne("")
    )
    raw.loc[~valid_valuation, list(VALUATION_METRICS)] = np.nan
    return raw


def _group_percentiles(
    df: pd.DataFrame, col: str, higher_is_better: bool, allowed_sectors: set[str]
) -> pd.Series:
    """A group must contain at least MIN_PEERS valid observations for a metric."""
    output = pd.Series(np.nan, index=df.index, dtype=float)
    for (_, peer), sub in df.loc[df["sector_type"].isin(allowed_sectors)].groupby(
        ["sector_type", "peer_group"], dropna=True
    ):
        values = sub[col].dropna()
        if len(values) < MIN_PEERS:
            continue
        if values.nunique() == 1:
            output.loc[values.index] = 0.5
        else:
            # Lower PE/PB/indebtedness/NPL/risk ranks higher.
            output.loc[values.index] = (
                values.rank(method="average", pct=False, ascending=higher_is_better) - 1
            ) / (len(values) - 1)
    return output


def _score_group(frame: pd.DataFrame, metrics: dict[str, bool], sector: str,
                 min_covered: int) -> tuple[pd.Series, pd.Series]:
    factor_cols = []
    for metric, higher in metrics.items():
        col = f"_pct_{sector}_{metric}"
        frame[col] = _group_percentiles(frame, metric, higher, {sector})
        factor_cols.append(col)
    # Require independent evidence rather than imputing missing metrics.
    coverage = frame[factor_cols].notna().sum(axis=1)
    factor = (1 + 9 * frame[factor_cols].mean(axis=1)).where(coverage >= min_covered)
    return factor, coverage


def build_multifactor_table(
    technical: pd.DataFrame, *, as_of: str, root: Optional[Path] = None,
    financial_table: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Augment v1 technical scan without modifying X10 or v1 output.

    Financial scores are NA without validated, time-aligned financial records.
    Ranking of complete multi-factor scores includes only companies with all groups.
    """
    if "Mã" not in technical.columns or "Smart Rating /10" not in technical.columns:
        raise ValueError("Thiếu cột của core.smart_screener")
    out = technical.copy().reset_index(drop=True)
    out["Mã"] = out["Mã"].astype(str).str.upper().str.strip()
    root = Path(root) if root is not None else Path(__file__).resolve().parent.parent
    path = root / "data" / "fundamentals" / "fundamentals_snapshot.csv"
    fundamental = read_financial_snapshot(path, table=financial_table, as_of=as_of)
    out["Điểm kỹ thuật /10"] = pd.to_numeric(out["Smart Rating /10"], errors="coerce")
    out["Điểm cơ bản /10"] = np.nan
    out["Điểm định giá /10"] = np.nan
    out["Smart Rating tổng hợp /10"] = np.nan
    out["BCTC nguồn"] = ""
    out["Ngày công bố BCTC"] = ""
    out["Kỳ BCTC"] = ""
    out["Nhóm so sánh"] = ""
    out["Loại doanh nghiệp"] = ""
    out["Số chỉ tiêu cơ bản hợp lệ"] = 0
    out["Số chỉ tiêu định giá hợp lệ"] = 0
    out["Ghi chú dữ liệu"] = "Chưa có BCTC đủ nguồn/ngày công bố và nhóm so sánh"
    out["Thứ hạng tổng hợp"] = np.nan
    if fundamental.empty:
        return out

    scored = fundamental.copy()
    fund_bank, coverage_bank = _score_group(scored, BANK_METRICS, "BANK", 3)
    fund_corp, coverage_corp = _score_group(scored, CORP_METRICS, "NONBANK", 3)
    scored["_f"] = fund_bank.combine_first(fund_corp)
    scored["_f_covered"] = np.where(scored["sector_type"].eq("BANK"), coverage_bank, coverage_corp)
    val_bank, val_bank_n = _score_group(scored, {"pe": False, "pb": False}, "BANK", 1)
    val_corp, val_corp_n = _score_group(scored, VALUATION_METRICS, "NONBANK", 1)
    scored["_v"] = val_bank.combine_first(val_corp)
    scored["_v_covered"] = np.where(scored["sector_type"].eq("BANK"), val_bank_n, val_corp_n)
    scored = scored.set_index("symbol")

    for ix, row in out.iterrows():
        symbol = row["Mã"]
        if symbol not in scored.index:
            continue
        f = scored.loc[symbol]
        out.at[ix, "BCTC nguồn"] = f["source"]
        out.at[ix, "Ngày công bố BCTC"] = f["published_at"].strftime("%Y-%m-%d")
        out.at[ix, "Kỳ BCTC"] = f["report_period_end"].strftime("%Y-%m-%d")
        out.at[ix, "Nhóm so sánh"] = f["peer_group"]
        out.at[ix, "Loại doanh nghiệp"] = f["sector_type"]
        out.at[ix, "Số chỉ tiêu cơ bản hợp lệ"] = int(f["_f_covered"])
        out.at[ix, "Số chỉ tiêu định giá hợp lệ"] = int(f["_v_covered"])
        out.at[ix, "Điểm cơ bản /10"] = f["_f"]
        out.at[ix, "Điểm định giá /10"] = f["_v"]
        missing_groups = []
        if not pd.notna(row["Điểm kỹ thuật /10"]): missing_groups.append("kỹ thuật")
        if not pd.notna(f["_f"]): missing_groups.append("cơ bản/nhóm đối chứng")
        if not pd.notna(f["_v"]): missing_groups.append("định giá đúng thời điểm/nhóm đối chứng")
        if missing_groups:
            out.at[ix, "Ghi chú dữ liệu"] = "Chưa đủ: " + ", ".join(missing_groups)
        else:
            out.at[ix, "Ghi chú dữ liệu"] = "Đủ 3 nhóm (ngưỡng/trọng số vẫn đang thử nghiệm)"
            value = (RATING_WEIGHTS["technical"] * row["Điểm kỹ thuật /10"]
                     + RATING_WEIGHTS["fundamental"] * f["_f"]
                     + RATING_WEIGHTS["valuation"] * f["_v"])
            out.at[ix, "Smart Rating tổng hợp /10"] = round(float(value), 2)
    ready = out["Smart Rating tổng hợp /10"].notna()
    if ready.any():
        out.loc[ready, "Thứ hạng tổng hợp"] = out.loc[ready, "Smart Rating tổng hợp /10"].rank(
            method="min", ascending=False)
    return out.sort_values(
        ["Smart Rating tổng hợp /10", "Điểm kỹ thuật /10", "Mã"],
        ascending=[False, False, True], na_position="last"
    ).reset_index(drop=True)
