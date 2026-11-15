"""BatDayStox SSI: independent experimental EOD technical screener.

Only uses local SSI OHLCV snapshots, never submits orders.
Factors/thresholds are experimental and are NOT investment advice.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
WEIGHTS = {
    "trend": 0.25,
    "momentum": 0.20,
    "liquidity": 0.15,
    "rsi_macd": 0.15,
    "risk": 0.15,
    "breakout": 0.10,
}
REQUIRED = {"date", "open", "high", "low", "close", "volume"}


@dataclass(frozen=True)
class ScanMeta:
    as_of: str
    universe_size: int
    eligible: int
    unavailable: int
    mode: str = "SSI_CACHE_EOD"


def _load_ohlcv(path: Path, symbol: str, as_of: Optional[str]) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    if not REQUIRED.issubset(df.columns):
        raise ValueError(f"{symbol}: thiếu cột {sorted(REQUIRED - set(df.columns))}")
    if "symbol" in df.columns and not df["symbol"].astype(str).str.strip().str.upper().eq(symbol).all():
        raise ValueError(f"{symbol}: CSV chứa sai mã")
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[list(REQUIRED)].isna().any().any():
        raise ValueError(f"{symbol}: dữ liệu trống hoặc sai kiểu")
    if df["date"].duplicated().any():
        raise ValueError(f"{symbol}: ngày bị trùng")
    if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df["volume"] < 0).any():
        raise ValueError(f"{symbol}: giá/khối lượng không hợp lệ")
    if ((df["high"] < df[["open", "low", "close"]].max(axis=1)) |
        (df["low"] > df[["open", "high", "close"]].min(axis=1))).any():
        raise ValueError(f"{symbol}: OHLC không nhất quán")
    df = df.sort_values("date").reset_index(drop=True)
    if as_of is not None:
        df = df.loc[df["date"] <= pd.Timestamp(as_of)].copy()
    return df.reset_index(drop=True)


def _rsi_ewm(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI with Wilder-like exponential smoothing; differs from legacy SMA RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    ratio = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + ratio)
    rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
    rsi = rsi.mask((loss == 0) & (gain == 0), 50.0)
    return rsi


def _extract_one(path: Path, symbol: str, as_of: str) -> dict:
    d = _load_ohlcv(path, symbol, as_of)
    if len(d) < 200:
        raise ValueError(f"thiếu 200 phiên (hiện có {len(d)})")
    if d["date"].iloc[-1] != pd.Timestamp(as_of):
        raise ValueError(f"không có nến ngày chốt {as_of}")
    c, v = d["close"], d["volume"]
    ma20, ma50, ma200 = (float(c.tail(n).mean()) for n in (20, 50, 200))
    rsi = float(_rsi_ewm(c).iloc[-1])
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_hist = float((macd - macd.ewm(span=9, adjust=False).mean()).iloc[-1])
    ret20 = float(c.iloc[-1]/c.iloc[-21] - 1)
    ret63 = float(c.iloc[-1]/c.iloc[-64] - 1)
    avg_vol20_prev = float(v.iloc[-21:-1].mean())
    volume_ratio = float(v.iloc[-1] / avg_vol20_prev) if avg_vol20_prev > 0 else np.nan
    turnover20 = float((c * v).tail(20).mean())  # SSI prices are VND, not thousands of VND
    volatility60 = float(c.pct_change(fill_method=None).tail(60).std() * np.sqrt(252))
    drawdown60 = float(1 - c.iloc[-1] / c.tail(60).max())
    prev_high20 = float(d["high"].iloc[-21:-1].max())
    breakout20 = bool(c.iloc[-1] > prev_high20)
    unusual_move = bool((c.pct_change(fill_method=None).abs().tail(200) > 0.30).any())
    return {
        "Mã": symbol, "Ngày dữ liệu": as_of, "Số phiên": len(d),
        "Giá (VND)": float(c.iloc[-1]), "MA20": ma20, "MA50": ma50, "MA200": ma200,
        "RSI14 EWM": rsi, "MACD histogram": macd_hist,
        "Lợi suất 20 phiên (%)": 100 * ret20, "Lợi suất 63 phiên (%)": 100 * ret63,
        "GTGD 20 phiên (tỷ VND)": turnover20 / 1e9,
        "KL TB20 (CP/phiên)": float(v.tail(20).mean()),
        "Khối lượng đột biến (x)": volume_ratio,
        "Biến động 60 phiên (%)": volatility60 * 100,
        "Sụt giảm từ đỉnh 60 phiên (%)": drawdown60 * 100,
        "Breakout 20 phiên": breakout20,
        "Cờ biến động >30%": unusual_move,
        "Trạng thái": "Đủ dữ liệu", "Lý do": "",
    }


def _rank_percentile(s: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Cross-sectional rank in [0,1]. 1 eligible symbol gets neutral 0.5."""
    if len(s) == 1:
        return pd.Series([0.5], index=s.index)
    r = s.rank(method="average", ascending=True)
    pct = (r - 1) / (len(s) - 1)
    return pct if higher_is_better else 1 - pct


def _score(frame: pd.DataFrame) -> pd.DataFrame:
    good = frame["Trạng thái"].eq("Đủ dữ liệu")
    if not good.any():
        frame["Smart Rating /10"] = np.nan
        frame["Thứ hạng"] = np.nan
        return frame
    x = frame.loc[good].copy()
    trend = (
        (x["Giá (VND)"] > x["MA20"]).astype(float)
        + (x["Giá (VND)"] > x["MA50"]).astype(float)
        + (x["Giá (VND)"] > x["MA200"]).astype(float)
        + (x["MA20"] > x["MA50"]).astype(float)
    ) / 4
    momentum = (0.4 * _rank_percentile(x["Lợi suất 20 phiên (%)"])
                + 0.6 * _rank_percentile(x["Lợi suất 63 phiên (%)"]))
    spike = ((x["Khối lượng đột biến (x)"].clip(0, 2) / 2).fillna(0))
    liquidity = 0.5 * _rank_percentile(x["GTGD 20 phiên (tỷ VND)"]) + 0.5 * spike
    rsi = x["RSI14 EWM"]
    rsi_band = pd.Series(np.select([
        rsi.between(45, 70, inclusive="both"),
        rsi.between(30, 80, inclusive="both")
    ], [1.0, 0.5], default=0), index=x.index)
    rsi_macd = 0.5 * rsi_band + 0.5 * (x["MACD histogram"] > 0).astype(float)
    risk = (0.5 * _rank_percentile(x["Biến động 60 phiên (%)"], False)
            + 0.5 * _rank_percentile(x["Sụt giảm từ đỉnh 60 phiên (%)"], False))
    breakout = pd.Series(np.where(
        x["Breakout 20 phiên"] & (x["Khối lượng đột biến (x)"] >= 1.5), 1.0,
        np.where(x["Breakout 20 phiên"], 0.5, 0.0)
    ), index=x.index)
    factors = {
        "trend": trend, "momentum": momentum, "liquidity": liquidity,
        "rsi_macd": rsi_macd, "risk": risk, "breakout": breakout,
    }
    combined = sum(WEIGHTS[name] * factors[name] for name in WEIGHTS)
    x["Smart Rating /10"] = (1 + 9 * combined).round(2)
    x["Thứ hạng"] = x["Smart Rating /10"].rank(ascending=False, method="min").astype(int)
    x["Mức ưu tiên nghiên cứu"] = pd.cut(
        x["Smart Rating /10"], bins=[0, 4, 7, 10.01],
        labels=["Thấp", "Trung bình", "Cao"], include_lowest=True,
    ).astype(str)
    for name, val in factors.items():
        x[f"Nhân tố: {name}"] = (10 * val).round(2)
    for col in x.columns:
        if col not in frame.columns:
            frame[col] = np.nan if col not in ("Mức ưu tiên nghiên cứu",) else ""
    frame.loc[good, x.columns] = x
    return frame.sort_values(["Smart Rating /10", "Mã"], ascending=[False, True], na_position="last").reset_index(drop=True)



def _aura_cohort_as_of(dates, minimum_coverage=0.60):
    """Choose latest common EOD covering >=60% of valid cached symbols.

    One freshly updated stock must not re-anchor 800 older EOD files and
    make them disappear from the same-date technical ranking.
    A file with a later last candle is still valid at the earlier date.
    """
    ordered = sorted(pd.Timestamp(d).normalize() for d in dates)
    if not ordered:
        raise ValueError('Khong co ngay EOD hop le trong SSI cache')
    count = len(ordered)
    needed = max(1, int(-(-count * minimum_coverage // 1)))
    return ordered[count - needed]

def scan_cached_universe(root: Optional[Path] = None, as_of: Optional[str] = None):
    """Scan local SSI CSV only. Return (full table, metadata), never call network."""
    root = Path(root) if root is not None else DEFAULT_ROOT
    from core.ssi_universe import screener_symbols
    prices_dir = root / "data" / "ssi_cache" / "ohlcv"
    symbols = screener_symbols(root, include_candidates=False)
    if not symbols:
        raise ValueError("Danh sách mã đang rỗng")
    if as_of is None:
        dates = []
        for sym in symbols:
            p = prices_dir / f"{sym}.csv"
            if p.exists():
                try:
                    d = _load_ohlcv(p, sym, None)
                    if not d.empty:
                        dates.append(d["date"].iloc[-1])
                except (ValueError, KeyError, OSError):
                    pass
        if not dates:
            raise ValueError("Không tìm được dữ liệu SSI hợp lệ")
        as_of = _aura_cohort_as_of(dates).strftime("%Y-%m-%d")
    else:
        as_of = pd.Timestamp(as_of).strftime("%Y-%m-%d")
    records = []
    for sym in symbols:
        try:
            path = prices_dir / f"{sym}.csv"
            if not path.exists():
                raise FileNotFoundError("chưa có file OHLCV")
            records.append(_extract_one(path, sym, as_of))
        except (ValueError, KeyError, FileNotFoundError, OSError, IndexError) as e:
            records.append({"Mã": sym, "Trạng thái": "Chưa đủ dữ liệu", "Lý do": str(e)[:120]})
    result = _score(pd.DataFrame(records))
    good_count = int(result["Trạng thái"].eq("Đủ dữ liệu").sum())
    meta = ScanMeta(as_of, len(symbols), good_count, len(symbols)-good_count)
    return result, meta
