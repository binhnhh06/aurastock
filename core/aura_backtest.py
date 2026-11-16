"""Event study cho điểm kỹ thuật AURA trên dữ liệu SSI EOD đã lưu (không gọi API).

Câu hỏi kiểm chứng: những mã được AURA chấm điểm kỹ thuật cao tại phiên t có lợi suất
các phiên SAU ĐÓ tốt hơn (a) VN-Index và (b) toàn bộ mã đủ điều kiện cùng ngày hay không?

Quy tắc (đóng băng, giống core/strategy.py):
- Điểm kỹ thuật = diem_ta(): giá/MA20/MA50, động lượng 63 phiên, RSI14 Wilder, KL20/KL60 (0–100).
- Tín hiệu tại đóng cửa phiên t: điểm ≥ 60, đủ ≥ 200 phiên, GTGD TB20 ≥ 2 tỷ, VN-Index ≥ MA50.
- Vào lệnh giá MỞ CỬA phiên t+1 (không nhìn trước); thoát giá đóng cửa phiên t+h.
- Chi phí khứ hồi mặc định 0,40% (phí mua/bán + thuế bán 0,1%), có thể chỉnh.
- Lấy mẫu mỗi 5 phiên để giảm chồng lấp; chia trong mẫu / ngoài mẫu theo ngày.

Giới hạn: giá chưa điều chỉnh cổ tức/chia tách → loại cửa sổ có biến động 1 ngày > 30%;
danh mục là các mã đang niêm yết (survivorship bias); điểm cơ bản KHÔNG được kiểm định vì
BCTC chưa có ngày công bố (tránh look-ahead).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

THRESHOLD = 60.0
MIN_BARS = 200
MIN_GTGD = 2e9
COST_ROUNDTRIP = 0.004
HORIZONS = (5, 10, 20)
JUMP = 0.30
BUCKETS = [0, 40, 60, 80, 101]


def rsi_wilder(close: pd.Series, n: int = 14) -> pd.Series:
    from core.technical_chart import _rsi_wilder
    return _rsi_wilder(close, n)


def score_series(df: pd.DataFrame) -> pd.Series:
    """Điểm kỹ thuật cho TỪNG phiên, chỉ dùng dữ liệu đến phiên đó (vector hóa diem_ta)."""
    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    ma20, ma50 = c.rolling(20).mean(), c.rolling(50).mean()
    d = (c > ma20) * 10.0 + (c > ma50) * 15.0 + (ma20 > ma50) * 15.0
    pos = np.arange(len(c))
    lag = np.minimum(63, pos)
    base = pd.Series(c.to_numpy()[pos - lag], index=c.index)
    ret3m = (c / base - 1) * 100
    d += (ret3m / 20 * 30).clip(lower=0, upper=30)
    rsi = rsi_wilder(c)
    d += np.where((rsi >= 45) & (rsi <= 70), 15.0, np.where(((rsi >= 30) & (rsi < 45)) | ((rsi > 70) & (rsi <= 80)), 8.0, 0.0))
    r = v.rolling(20, min_periods=1).mean() / v.rolling(60, min_periods=1).mean()
    d += np.where(r >= 1, 15.0, np.where(r >= 0.8, 8.0, 0.0))
    return d.round(1)


def load_prices(folder: Path, symbol: str) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(Path(folder) / f"{symbol}.csv")
    except (OSError, ValueError, pd.errors.ParserError):
        return None
    col = "date" if "date" in df else "time" if "time" in df else None
    need = {"open", "high", "low", "close", "volume"}
    if col is None or not need.issubset(df.columns):
        return None
    df = df.rename(columns={col: "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    for k in need:
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df = df.dropna(subset=["date", *need]).drop_duplicates("date", keep="last").sort_values("date")
    df = df.loc[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    return df.reset_index(drop=True) if len(df) >= 60 else None


def events_for_symbol(symbol, df, vni_ok: pd.Series, sample_dates: set, *, cost=COST_ROUNDTRIP,
                      horizons=HORIZONS, threshold=THRESHOLD):
    """Một dòng cho mỗi (mã, ngày lấy mẫu) đủ điều kiện dữ liệu và thanh khoản."""
    df = df.copy()
    df["score"] = score_series(df)
    df["gtgd20"] = (df["close"] * df["volume"]).rolling(20, min_periods=1).mean()
    df["n_bars"] = np.arange(1, len(df) + 1)
    daily = df["close"].pct_change().abs()
    rows = []
    hmax = max(horizons)
    for i in np.flatnonzero(df["date"].isin(sample_dates).to_numpy()):
        if i + hmax >= len(df) or df.at[i, "n_bars"] < MIN_BARS or df.at[i, "gtgd20"] < MIN_GTGD:
            continue
        day = df.at[i, "date"]
        if day not in vni_ok.index:
            continue
        window_jump = bool(daily.iloc[i + 1:i + hmax + 1].gt(JUMP).any())
        entry = df.at[i + 1, "open"]
        row = {"symbol": symbol, "date": day, "score": df.at[i, "score"],
               "market_ok": bool(vni_ok.loc[day]), "jump": window_jump}
        row["signal"] = bool(row["score"] >= threshold and row["market_ok"])
        for h in horizons:
            row[f"ret_{h}"] = df.at[i + h, "close"] / entry - 1 - cost
        rows.append(row)
    return rows


def benchmark(vni: pd.DataFrame, horizons=HORIZONS) -> pd.DataFrame:
    v = vni.set_index("date")
    out = pd.DataFrame(index=v.index)
    entry = v["open"].shift(-1).where(v["open"].shift(-1) > 0, v["close"])
    for h in horizons:
        out[f"vni_{h}"] = v["close"].shift(-h) / entry - 1
    out["vni_ok"] = v["close"] >= v["close"].rolling(50).mean()
    return out


def run(folder: Path, *, split=None, every=5, cost=COST_ROUNDTRIP, symbols=None, progress=None):
    folder = Path(folder)
    vni = load_prices(folder, "VNINDEX")
    if vni is None:
        raise FileNotFoundError("Thiếu data/ssi_cache/ohlcv/VNINDEX.csv")
    bench = benchmark(vni)
    sample = set(vni["date"].iloc[60::every])
    names = symbols or sorted(p.stem.upper() for p in folder.glob("*.csv")
                              if p.stem.upper() not in {"VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"})
    rows = []
    for k, sym in enumerate(names):
        if progress and k % 100 == 0:
            progress(k, len(names))
        df = load_prices(folder, sym)
        if df is not None:
            rows += events_for_symbol(sym, df, bench["vni_ok"], sample, cost=cost)
    ev = pd.DataFrame(rows)
    if ev.empty:
        return ev, pd.DataFrame(), pd.DataFrame()
    ev = ev.merge(bench.drop(columns="vni_ok"), left_on="date", right_index=True, how="left")
    for h in HORIZONS:
        ev[f"excess_{h}"] = ev[f"ret_{h}"] - ev[f"vni_{h}"]
    if split is None:
        dates = sorted(ev["date"].unique())
        split = dates[int(len(dates) * 0.6)]
    ev["period"] = np.where(ev["date"] < pd.Timestamp(split), "Trong mẫu", "Ngoài mẫu")
    ev = ev.loc[~ev["jump"]].copy()
    return ev, summarize(ev), by_bucket(ev)


def _stats(x: pd.Series):
    x = x.dropna()
    n = len(x)
    if n == 0:
        return n, math.nan, math.nan, math.nan, math.nan
    sd = x.std(ddof=1) if n > 1 else math.nan
    t = x.mean() / (sd / math.sqrt(n)) if n > 1 and sd > 0 else math.nan
    return n, x.mean() * 100, x.median() * 100, (x > 0).mean() * 100, t


def _date_tstat(g: pd.DataFrame, col: str):
    """t-stat trên chuỗi TRUNG BÌNH THEO NGÀY (kiểu Fama–MacBeth): các mã cùng ngày tương quan
    với nhau nên không coi mỗi sự kiện là một quan sát độc lập."""
    daily = g.groupby("date")[col].mean().dropna()
    n = len(daily)
    if n < 3:
        return n, math.nan
    sd = daily.std(ddof=1)
    return n, (daily.mean() / (sd / math.sqrt(n)) if sd > 0 else math.nan)


def summarize(ev: pd.DataFrame) -> pd.DataFrame:
    """So sánh nhóm tín hiệu với toàn bộ mã đủ điều kiện (baseline) theo giai đoạn và kỳ hạn."""
    out = []
    for period in ("Trong mẫu", "Ngoài mẫu", "Toàn bộ"):
        p = ev if period == "Toàn bộ" else ev.loc[ev["period"].eq(period)]
        for h in HORIZONS:
            for group, g in (("Tín hiệu AURA (điểm ≥ 60, VN-Index ≥ MA50)", p.loc[p["signal"]]),
                             ("Toàn bộ mã đủ điều kiện (baseline)", p)):
                n, mean, med, win, _ = _stats(g[f"ret_{h}"])
                _, ex, _, beat, _ = _stats(g[f"excess_{h}"])
                days, tx = _date_tstat(g, f"excess_{h}")
                out.append({"Giai đoạn": period, "Kỳ hạn (phiên)": h, "Nhóm": group, "Số sự kiện": n,
                            "Số ngày": days, "LS TB sau phí (%)": round(mean, 2), "LS trung vị (%)": round(med, 2),
                            "Tỷ lệ dương (%)": round(win, 1), "Vượt VN-Index TB (%)": round(ex, 2),
                            "Tỷ lệ thắng VN-Index (%)": round(beat, 1), "t-stat vượt VN-Index (theo ngày)": round(tx, 2)})
    return pd.DataFrame(out)


def by_bucket(ev: pd.DataFrame, h: int = 20) -> pd.DataFrame:
    """Lợi suất theo nhóm điểm: điểm cao hơn có đi kèm lợi suất cao hơn không (đơn điệu)."""
    e = ev.copy()
    e["Nhóm điểm"] = pd.cut(e["score"], BUCKETS, right=False,
                            labels=["0–39", "40–59", "60–79", "80–100"])
    g = e.groupby(["period", "Nhóm điểm"], observed=True)
    out = g.agg(**{"Số sự kiện": (f"ret_{h}", "size"),
                   f"LS TB {h} phiên (%)": (f"ret_{h}", lambda s: round(s.mean() * 100, 2)),
                   f"Vượt VN-Index {h} phiên (%)": (f"excess_{h}", lambda s: round(s.mean() * 100, 2))})
    return out.reset_index().rename(columns={"period": "Giai đoạn"})
