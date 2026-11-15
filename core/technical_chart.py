"""Interactive technical charts for BatDayStox, based on the current EOD series.

Presentation-only: this module NEVER changes the day-based X10 score, the source
price data, or SSI realtime snapshots. Aggregations use actual trading timestamps.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PERIODS = {"Ngày": None, "Tuần": "W-FRI", "Tháng": "M", "Năm": "Y"}
OVERLAY_OPTIONS = ["MA20", "MA50", "MA200", "EMA12", "EMA26", "Bollinger (20, 2σ)"]
PANEL_OPTIONS = ["Khối lượng", "RSI (14)", "MACD (12,26,9)", "Stochastic (14,3)", "ATR (14)"]
COLORS = {
    "positive": "#13966C", "negative": "#EE4E7B", "ma20": "#FF579C",
    "ma50": "#7045F6", "ma200": "#2F63CD", "ema12": "#FF9D43",
    "ema26": "#00A9B9", "bb": "#8F82E8", "macd": "#6C3BFF",
    "signal": "#FF8A3D", "rsi": "#F09C30", "atr": "#4675D7",
}


def chart_price_history(root: Path, symbol: str, analysis_prices: pd.DataFrame,
                        source_name: str = "") -> pd.DataFrame:
    """Use the full SSI local CSV only when it is at least as current as X10.

    Never query an API from the chart; retain analysis_prices when SSI cache is
    unavailable, invalid, or a non-SSI fallback data source was explicitly used.
    """
    if "SSI" not in str(source_name).upper():
        return analysis_prices
    ticker = str(symbol).strip().upper()
    if not ticker or not ticker.isalnum() or len(ticker) > 10:
        return analysis_prices
    path = Path(root) / "data" / "ssi_cache" / "ohlcv" / f"{ticker}.csv"
    if not path.is_file():
        return analysis_prices
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig")
        full = aggregate_ohlcv(frame, "Ngày")
        if full.empty:
            return analysis_prices
        base = aggregate_ohlcv(analysis_prices, "Ngày")
        if not base.empty and full["time"].iloc[-1] < base["time"].iloc[-1]:
            return analysis_prices
        return full
    except (OSError, KeyError, TypeError, ValueError, pd.errors.ParserError):
        return analysis_prices


def aggregate_ohlcv(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    """Aggregate daily OHLCV into completed/ongoing exchange weeks, months, years.

    Trading date, not calendar boundary, is used for the x-axis to avoid
    pretending that untraded days have a candle. Latest period can be partial.
    """
    if period not in PERIODS:
        raise ValueError(f"Khung thời gian không hợp lệ: {period}")
    required = ("time", "open", "high", "low", "close", "volume")
    if "time" not in frame and "date" in frame:
        frame = frame.rename(columns={"date": "time"})
    if not set(required).issubset(frame.columns):
        raise ValueError("Dữ liệu giá thiếu cột OHLCV cần thiết")
    d = frame[list(required)].copy()
    d["time"] = pd.to_datetime(d["time"], errors="coerce")
    for col in required[1:]:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = (d.dropna(subset=required)
         .loc[lambda x: (x[["open", "high", "low", "close"]] > 0).all(axis=1)
              & x["volume"].ge(0)]
         .sort_values("time").drop_duplicates(subset="time", keep="last"))
    if d.empty:
        return d.reset_index(drop=True)
    freq = PERIODS[period]
    if freq is None:
        return d.reset_index(drop=True)
    group = d.groupby(d["time"].dt.to_period(freq), sort=True)
    out = group.agg(time=("time", "last"), open=("open", "first"),
                    high=("high", "max"), low=("low", "min"),
                    close=("close", "last"), volume=("volume", "sum"))
    return out.reset_index(drop=True)


def _rsi_wilder(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    ups = delta.clip(lower=0)
    downs = (-delta).clip(lower=0)
    avg_up = ups.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    avg_down = downs.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    ratio = avg_up / avg_down.replace(0, float("nan"))
    rsi = 100 - 100 / (1 + ratio)
    rsi = rsi.mask(avg_down.eq(0) & avg_up.gt(0), 100.0)
    rsi = rsi.mask(avg_up.eq(0) & avg_down.gt(0), 0.0)
    return rsi.mask(avg_up.eq(0) & avg_down.eq(0), 50.0)


def add_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    """Calculate indicators per *selected* candle period, not daily-then-resample."""
    d = bars.copy()
    c = d["close"]
    for n in (20, 50, 200):
        d[f"MA{n}"] = c.rolling(n, min_periods=n).mean()
    d["EMA12"] = c.ewm(span=12, adjust=False, min_periods=12).mean()
    d["EMA26"] = c.ewm(span=26, adjust=False, min_periods=26).mean()
    mid = d["MA20"]
    sigma = c.rolling(20, min_periods=20).std(ddof=0)
    d["BB_upper"] = mid + 2*sigma
    d["BB_lower"] = mid - 2*sigma
    d["RSI14"] = _rsi_wilder(c)
    d["MACD"] = d["EMA12"] - d["EMA26"]
    d["MACD_signal"] = d["MACD"].ewm(span=9, adjust=False, min_periods=9).mean()
    d["MACD_hist"] = d["MACD"] - d["MACD_signal"]
    low14 = d["low"].rolling(14, min_periods=14).min()
    high14 = d["high"].rolling(14, min_periods=14).max()
    d["StochK"] = (100 * (c - low14) / (high14 - low14).replace(0, float("nan"))).clip(0, 100)
    d["StochD"] = d["StochK"].rolling(3, min_periods=3).mean()
    prev = c.shift(1)
    tr = pd.concat([(d["high"] - d["low"]).abs(),
                    (d["high"] - prev).abs(),
                    (d["low"] - prev).abs()], axis=1).max(axis=1)
    d["ATR14"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    return d


def _range_filter(data: pd.DataFrame, choice: str) -> pd.DataFrame:
    limits = {"6 tháng": 6, "1 năm": 12, "2 năm": 24, "3 năm": 36, "5 năm": 60}
    if choice not in limits or data.empty:
        return data.copy()
    cutoff = data["time"].max() - pd.DateOffset(months=limits[choice])
    return data.loc[data["time"] >= cutoff].copy()


def create_technical_figure(
    data: pd.DataFrame, *, symbol: str, period: str = "Ngày", chart_type: str = "Nến",
    overlays: Iterable[str] = ("MA20", "MA50"),
    panels: Iterable[str] = ("Khối lượng", "RSI (14)"),
    range_choice: str = "Toàn bộ",
    annual_axis_mode: str = "Tối ưu",
):
    """Return (Plotly Figure, displayed candle DataFrame, missing-indicator hints).

    All indicator calculations run on the full OHLCV history; the display range
    is selected *afterward* to avoid incorrect warm-up artifacts at its edges.
    """
    bars = aggregate_ohlcv(data, period)
    if bars.empty:
        raise ValueError("Không có nến OHLCV hợp lệ để vẽ")
    scored = add_indicators(bars)
    show = _range_filter(scored, range_choice)
    overlay = list(dict.fromkeys(x for x in overlays if x in OVERLAY_OPTIONS))
    panel = list(dict.fromkeys(x for x in panels if x in PANEL_OPTIONS))
    missing = []

    overlay_fields = {"MA20": ("MA20", 20), "MA50": ("MA50", 50),
                      "MA200": ("MA200", 200), "EMA12": ("EMA12", 12),
                      "EMA26": ("EMA26", 26),
                      "Bollinger (20, 2σ)": ("BB_upper", 20)}
    panel_fields = {"Khối lượng": ("volume", 1), "RSI (14)": ("RSI14", 15),
                    "MACD (12,26,9)": ("MACD_signal", 34),
                    "Stochastic (14,3)": ("StochD", 16), "ATR (14)": ("ATR14", 14)}
    valid_overlays = []
    valid_panels = []
    for item in overlay:
        field, needed = overlay_fields[item]
        if scored[field].notna().any():
            valid_overlays.append(item)
        else:
            missing.append(f"{item} cần tối thiểu khoảng {needed} nến {period.lower()} (đang có {len(bars)}).")
    for item in panel:
        field, needed = panel_fields[item]
        if scored[field].notna().any():
            valid_panels.append(item)
        else:
            missing.append(f"{item} cần tối thiểu khoảng {needed} nến {period.lower()} (đang có {len(bars)}).")

    n = len(valid_panels)
    heights = [0.61] + [0.39 / n] * n if n else [1.0]
    fig = make_subplots(rows=n + 1, cols=1, shared_xaxes=True,
                        row_heights=heights, vertical_spacing=0.035 if n < 4 else 0.025)
    # Annual candles are naturally sparse. A categorical axis avoids Plotly's
    # excessive date-axis padding (e.g. a 2024–26 series shown as 2017–37).
    # Only labels change: indicators, OHLCV and trading dates stay intact.
    x = show["time"].dt.strftime("%Y") if period == "Năm" else show["time"]
    annual_hover = show["time"].dt.strftime("%d/%m/%Y") if period == "Năm" else None
    current_vn_year = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).year
    annual_is_ytd = period == "Năm" and int(show["time"].iloc[-1].year) == current_vn_year
    if chart_type == "Đường":
        fig.add_trace(go.Scatter(x=x, y=show["close"], name="Giá đóng cửa",
                                 mode="lines+markers" if period == "Năm" else "lines",
                                 marker=dict(size=10) if period == "Năm" else None,
                                 customdata=annual_hover,
                                 line=dict(color="#6C3BFF", width=2.8),
                                 hovertemplate=("Phiên cuối năm: %{customdata}<br>%{y:,.0f} đ<extra></extra>"
                                                if period == "Năm" else
                                                "%{x|%d/%m/%Y}<br>%{y:,.0f} đ<extra></extra>")), row=1, col=1)
    else:
        fig.add_trace(go.Candlestick(x=x, open=show["open"], high=show["high"],
                                     low=show["low"], close=show["close"],
                                     name=f"{symbol} · {period}",
                                     increasing_line_color=COLORS["positive"],
                                     increasing_fillcolor=COLORS["positive"],
                                     decreasing_line_color=COLORS["negative"],
                                     decreasing_fillcolor=COLORS["negative"]), row=1, col=1)
    overlay_colors = {"MA20": COLORS["ma20"], "MA50": COLORS["ma50"],
                      "MA200": COLORS["ma200"], "EMA12": COLORS["ema12"],
                      "EMA26": COLORS["ema26"]}
    for item in valid_overlays:
        if item.startswith("Bollinger"):
            fig.add_trace(go.Scatter(x=x, y=show["BB_upper"], name="BB trên",
                                     mode="lines", line=dict(color=COLORS["bb"], width=1.4, dash="dot")), row=1, col=1)
            fig.add_trace(go.Scatter(x=x, y=show["BB_lower"], name="BB dưới",
                                     mode="lines", line=dict(color=COLORS["bb"], width=1.4, dash="dot"),
                                     fill="tonexty", fillcolor="rgba(143,130,232,0.07)"), row=1, col=1)
        else:
            fig.add_trace(go.Scatter(x=x, y=show[item], name=item,
                                     mode="lines", line=dict(color=overlay_colors[item], width=1.75)), row=1, col=1)

    fig.update_yaxes(title_text="Giá (VND)", tickformat=",", row=1, col=1)
    axis_clipped = False
    annual_peak = None
    if period == "Năm":
        # Một năm chỉ có một nến; trục dạng category tránh khoảng trống giả.
        labels = x.tolist()
        if annual_is_ytd:
            labels = labels[:-1] + [labels[-1] + " · YTD"]
        for axis in fig.select_xaxes():
            axis.update(type="category", categoryorder="array",
                        categoryarray=x.tolist(), tickangle=0,
                        tickmode="array", tickvals=x.tolist(), ticktext=labels)

        # Đồ thị đường chỉ cần vùng giá đóng cửa; nến cần đủ OHLC.
        if chart_type == "Đường" and annual_axis_mode != "Toàn bộ":
            lo = float(show["close"].min())
            hi = float(show["close"].max())
            annual_peak = float(show["high"].max())
        else:
            lo = float(show["low"].min())
            hi = float(show["high"].max())
            annual_peak = hi
            highest_body = float(show[["open", "close"]].max().max())
            typical_high = float(show["high"].quantile(0.85))
            # Biên độ phần thân và phần lớn râu nến: chỉ dùng cho *khung nhìn*.
            # Một râu rất bất thường có thể đến từ dữ liệu chưa điều chỉnh
            # quyền, chia tách hoặc dữ liệu nguồn. Không sửa nến nào.
            readable_top = max(highest_body * 1.18, typical_high * 1.12)
            if hi > readable_top * 1.65 and annual_axis_mode != "Toàn bộ":
                hi = readable_top
                axis_clipped = True

        for item in valid_overlays:
            columns = ("BB_lower", "BB_upper") if item.startswith("Bollinger") else (item,)
            for field in columns:
                vals = show[field].dropna()
                if not vals.empty:
                    lo = min(lo, float(vals.min()))
                    hi = max(hi, float(vals.max()))
        padding = max((hi - lo) * 0.10, hi * 0.035, 1.0)
        fig.update_yaxes(range=[max(0.0, lo - padding), hi + padding],
                         autorange=False, row=1, col=1)
    for i, item in enumerate(valid_panels, start=2):
        if item == "Khối lượng":
            shades = [COLORS["positive"] if close >= op else COLORS["negative"]
                      for close, op in zip(show["close"], show["open"])]
            max_vol = float(show["volume"].max())
            vol_scale, vol_unit = ((1_000_000_000.0, "Tỷ CP") if max_vol >= 1_000_000_000
                                  else (1_000_000.0, "Triệu CP") if max_vol >= 1_000_000
                                  else (1.0, "CP"))
            fig.add_trace(go.Bar(
                x=x, y=show["volume"] / vol_scale,
                customdata=show["volume"], marker_color=shades,
                hovertemplate="%{x}<br>Khối lượng: %{customdata:,.0f} CP<extra></extra>",
                name="Khối lượng", showlegend=False), row=i, col=1)
            fig.update_yaxes(title_text=vol_unit, tickformat=",.1f" if vol_scale > 1 else ",", row=i, col=1)
        elif item == "RSI (14)":
            fig.add_trace(go.Scatter(x=x, y=show["RSI14"], name="RSI (14)",
                                     line=dict(color=COLORS["rsi"], width=2)), row=i, col=1)
            for v, color in ((70, COLORS["negative"]), (30, COLORS["positive"])):
                fig.add_hline(y=v, line_dash="dash", opacity=.65,
                              line_color=color, row=i, col=1)
            fig.update_yaxes(title_text="RSI", range=[0, 100], row=i, col=1)
        elif item == "MACD (12,26,9)":
            shades = [COLORS["positive"] if v >= 0 else COLORS["negative"] for v in show["MACD_hist"].fillna(0)]
            fig.add_trace(go.Bar(x=x, y=show["MACD_hist"], marker_color=shades,
                                 name="Histogram MACD", opacity=.65), row=i, col=1)
            fig.add_trace(go.Scatter(x=x, y=show["MACD"], name="MACD",
                                     line=dict(color=COLORS["macd"], width=1.8)), row=i, col=1)
            fig.add_trace(go.Scatter(x=x, y=show["MACD_signal"], name="Signal",
                                     line=dict(color=COLORS["signal"], width=1.6)), row=i, col=1)
            fig.update_yaxes(title_text="MACD", row=i, col=1)
        elif item == "Stochastic (14,3)":
            fig.add_trace(go.Scatter(x=x, y=show["StochK"], name="Stoch %K",
                                     line=dict(color=COLORS["ma50"], width=1.9)), row=i, col=1)
            fig.add_trace(go.Scatter(x=x, y=show["StochD"], name="Stoch %D",
                                     line=dict(color=COLORS["signal"], width=1.6)), row=i, col=1)
            for v in (20, 80):
                fig.add_hline(y=v, line_dash="dash", line_color="#A8A0BD", row=i, col=1)
            fig.update_yaxes(title_text="Stoch", range=[0, 100], row=i, col=1)
        elif item == "ATR (14)":
            fig.add_trace(go.Scatter(x=x, y=show["ATR14"], name="ATR (14)",
                                     line=dict(color=COLORS["atr"], width=2)), row=i, col=1)
            fig.update_yaxes(title_text="ATR", row=i, col=1)
    for axis in fig.select_xaxes():
        axis.rangeslider = dict(visible=False)
    fig.update_layout(hovermode="x unified", height=min(1050, 520 + 140 * n),
                      bargap=0.13, legend=dict(orientation="h", y=1.08, x=0),
                      margin=dict(t=72, b=36, l=30, r=20),
                      uirevision=f"{symbol}-{period}-{chart_type}-{annual_axis_mode}",
                      meta={"annual_axis_clipped": axis_clipped,
                            "annual_highest_raw": annual_peak,
                            "annual_is_ytd": annual_is_ytd,
                            "last_bar_date": show["time"].iloc[-1].strftime("%Y-%m-%d")})
    return fig, show, missing


def summary_stats(bars: pd.DataFrame) -> dict:
    if bars.empty:
        return {}
    last = bars.iloc[-1]
    first = bars.iloc[0]
    change = (float(last["close"]) / float(first["close"]) - 1) * 100 if first["close"] > 0 else float("nan")
    return {
        "last_close": float(last["close"]), "range_return": change,
        "candles": len(bars), "last_date": pd.Timestamp(last["time"]),
        "rsi": float(last["RSI14"]) if pd.notna(last.get("RSI14")) else None,
        "macd": float(last["MACD"]) if pd.notna(last.get("MACD")) else None,
    }
