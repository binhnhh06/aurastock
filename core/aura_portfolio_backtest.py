"""Backtest danh mục (portfolio-level) dựa trên tín hiệu điểm kỹ thuật AURA.

Khác với event study (core/aura_backtest.py — đo lợi suất TRUNG BÌNH của từng sự kiện,
không nhìn theo thời gian), module này DỰNG DANH MỤC và nối các kỳ tái cân bằng liên
tiếp (không chồng lấp) thành một đường equity curve theo thời gian, từ đó tính các
thước đo chuẩn của quản lý danh mục: CAGR, biến động năm hóa, Sharpe ratio, maximum
drawdown, tỷ lệ kỳ thắng.

Quy tắc danh mục (tái dùng toàn bộ hạ tầng của core/aura_backtest.py để đảm bảo nhất
quán tín hiệu, chi phí, và tránh nhìn trước dữ liệu):
- Mỗi kỳ tái cân bằng dài `period` phiên (mặc định 20 ~ 1 tháng giao dịch), KHÔNG chồng
  lấp (every == period) để các kỳ nối tiếp nhau thành một chuỗi thời gian liên tục.
- "Danh mục tín hiệu AURA": tại đầu mỗi kỳ, chọn đều tỷ trọng (equal-weight) các mã có
  signal=True (điểm kỹ thuật >= 60, đủ điều kiện thanh khoản/dữ liệu, VN-Index >= MA50)
  tại phiên đó; nếu KHÔNG có mã nào đạt tín hiệu trong kỳ, danh mục coi như giữ tiền mặt
  (lợi suất kỳ đó = 0%) - một giả định đơn giản hóa, nêu rõ trong hạn chế.
- "Danh mục baseline": tương tự nhưng equal-weight TOÀN BỘ mã đủ điều kiện dữ liệu/thanh
  khoản tại phiên đó (không lọc theo điểm), để so sánh xem tín hiệu có tạo giá trị tăng
  thêm so với việc nắm giữ dàn trải hay không.
- "VN-Index": mua-giữ (buy & hold) chỉ số cùng kỳ, dùng làm đối chứng thị trường.
- Lợi suất mỗi kỳ ĐÃ trừ chi phí khứ hồi (COST_ROUNDTRIP, mặc định 0,40%) - kế thừa từ
  core/aura_backtest.events_for_symbol.
- Tính riêng cho giai đoạn Trong mẫu / Ngoài mẫu (chia theo ngày, giống event study) và
  Toàn bộ.

Giới hạn (nêu trong báo cáo):
- Giá chưa điều chỉnh cổ tức/chia tách (kế thừa từ event study).
- Không có chi phí trượt giá (slippage) ngoài phí khứ hồi cố định.
- Danh mục rời rạc theo kỳ 20 phiên, không mô phỏng tái cân bằng liên tục hay quản lý
  rủi ro trong kỳ (stop-loss, cắt lỗ giữa kỳ).
- Không có lãi suất phi rủi ro trong Sharpe ratio (giả định rf = 0%/năm) - nêu rõ đây là
  Sharpe ratio thô (gross Sharpe), không trừ lãi suất tiền gửi kỳ hạn.
- Sống sót thiên lệch (survivorship bias): danh sách mã là các mã đang niêm yết tại thời
  điểm lấy dữ liệu.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from core.aura_backtest import run as run_event_study, COST_ROUNDTRIP

TRADING_DAYS_PER_YEAR = 252


def _max_drawdown(equity: pd.Series) -> float:
    """Trả về mức sụt giảm tối đa (số dương, %) từ đỉnh xuống đáy của đường equity."""
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(-dd.min() * 100) if len(dd) else math.nan


def _metrics(returns: pd.Series, period_days: int) -> dict:
    """Thước đo portfolio chuẩn từ chuỗi lợi suất theo KỲ (không chồng lấp)."""
    r = returns.dropna()
    n = len(r)
    if n == 0:
        return {"Số kỳ": 0, "CAGR (%/năm)": math.nan, "Biến động năm hóa (%)": math.nan,
                "Sharpe (năm hóa, rf=0)": math.nan, "Max Drawdown (%)": math.nan,
                "Tỷ lệ kỳ thắng (%)": math.nan, "Tổng lợi suất (%)": math.nan}
    equity = (1.0 + r).cumprod()
    periods_per_year = TRADING_DAYS_PER_YEAR / period_days
    total_return = float(equity.iloc[-1] - 1.0)
    cagr = float(equity.iloc[-1] ** (periods_per_year / n) - 1.0) if equity.iloc[-1] > 0 else math.nan
    mean_r, sd_r = r.mean(), (r.std(ddof=1) if n > 1 else math.nan)
    ann_vol = float(sd_r * math.sqrt(periods_per_year)) if n > 1 else math.nan
    sharpe = float((mean_r / sd_r) * math.sqrt(periods_per_year)) if n > 1 and sd_r and sd_r > 0 else math.nan
    return {"Số kỳ": n, "CAGR (%/năm)": round(cagr * 100, 2) if cagr == cagr else math.nan,
            "Biến động năm hóa (%)": round(ann_vol * 100, 2) if ann_vol == ann_vol else math.nan,
            "Sharpe (năm hóa, rf=0)": round(sharpe, 2) if sharpe == sharpe else math.nan,
            "Max Drawdown (%)": round(_max_drawdown(equity), 2),
            "Tỷ lệ kỳ thắng (%)": round(float((r > 0).mean() * 100), 1),
            "Tổng lợi suất (%)": round(total_return * 100, 2)}


def build_portfolio_curves(ev: pd.DataFrame, h: int) -> pd.DataFrame:
    """Gộp các sự kiện cùng ngày thành lợi suất DANH MỤC (equal-weight) theo kỳ.

    ev: kết quả của core.aura_backtest.run(..., every=h) - bắt buộc every == h để các
    kỳ liền kề không chồng lấp lên nhau (mới nối được thành 1 equity curve hợp lệ).
    """
    ret_col, vni_col = f"ret_{h}", f"vni_{h}"
    rows = []
    for date, g in ev.groupby("date"):
        sig = g.loc[g["signal"]]
        rows.append({
            "date": date,
            "Giai đoạn": g["period"].iloc[0],
            "Số mã tín hiệu": len(sig),
            "Số mã đủ điều kiện": len(g),
            "r_tin_hieu": float(sig[ret_col].mean()) if len(sig) else 0.0,
            "r_baseline": float(g[ret_col].mean()),
            "r_vnindex": float(g[vni_col].iloc[0]),
        })
    curves = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    for col, out in (("r_tin_hieu", "equity_tin_hieu"), ("r_baseline", "equity_baseline"),
                     ("r_vnindex", "equity_vnindex")):
        curves[out] = (1.0 + curves[col]).cumprod()
    return curves


def summarize_portfolio(curves: pd.DataFrame, h: int) -> pd.DataFrame:
    out = []
    strategies = [("Danh mục tín hiệu AURA (equal-weight)", "r_tin_hieu"),
                  ("Danh mục baseline (toàn bộ mã đủ điều kiện)", "r_baseline"),
                  ("VN-Index (mua và giữ)", "r_vnindex")]
    for giai_doan in ("Trong mẫu", "Ngoài mẫu", "Toàn bộ"):
        sub = curves if giai_doan == "Toàn bộ" else curves.loc[curves["Giai đoạn"].eq(giai_doan)]
        for name, col in strategies:
            m = _metrics(sub[col], h)
            out.append({"Giai đoạn": giai_doan, "Chiến lược": name, **m})
    return pd.DataFrame(out)


def run(folder: Path, *, period: int = 20, split=None, cost: float = COST_ROUNDTRIP,
        symbols=None, progress=None):
    """Chạy event study (every=period) rồi dựng backtest danh mục không chồng lấp.

    Trả về (curves, summary, ev) - ev là kết quả event-study gốc, hữu ích để đối chiếu
    chéo với mục 8.4 (biểu đồ bucket điểm số).
    """
    if period not in (5, 10, 20):
        raise ValueError("period phải là 5, 10 hoặc 20 (trùng với các kỳ hạn event study)")
    ev, _, _ = run_event_study(folder, split=split, every=period, cost=cost,
                               symbols=symbols, progress=progress)
    if ev.empty:
        return pd.DataFrame(), pd.DataFrame(), ev
    curves = build_portfolio_curves(ev, period)
    summary = summarize_portfolio(curves, period)
    return curves, summary, ev
