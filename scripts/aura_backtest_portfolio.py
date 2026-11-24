"""Chạy backtest DANH MỤC (portfolio-level) cho tín hiệu điểm kỹ thuật AURA.

Khác với scripts/aura_backtest_event.py (event study - lợi suất trung bình từng sự
kiện), script này dựng đường equity curve theo thời gian và tính CAGR/Sharpe/Max
Drawdown/tỷ lệ kỳ thắng cho 3 danh mục: tín hiệu AURA, baseline, VN-Index.

Chạy:   python scripts/aura_backtest_portfolio.py
Tùy chọn: --period 20 (phiên/kỳ, mặc định 20 ~ 1 tháng)  --split 2025-09-01
          --cost 0.004  --limit 300 (chạy thử ít mã trước)
Kết quả:
  docs/evidence/backtest_portfolio_curve.csv     chuỗi lợi suất + equity theo từng kỳ
  docs/evidence/backtest_portfolio_summary.csv   bảng CAGR/Sharpe/Drawdown/tỷ lệ thắng
  docs/evidence/backtest_portfolio_equity.png    biểu đồ equity curve cho báo cáo
Không gọi API, không sửa dữ liệu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.aura_portfolio_backtest import run  # noqa: E402


def chart(curves, path, period):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    series = [("equity_tin_hieu", "Danh mục tín hiệu AURA", "#7C3AED"),
              ("equity_baseline", "Baseline (toàn bộ mã)", "#F59E0B"),
              ("equity_vnindex", "VN-Index (mua & giữ)", "#64748B")]
    for col, label, color in series:
        ax.plot(curves["date"], curves[col], label=label, color=color, lw=1.6)
    out_sample = curves.loc[curves["Giai đoạn"].eq("Ngoài mẫu"), "date"]
    if len(out_sample):
        ax.axvline(out_sample.iloc[0], color="#333", lw=0.8, ls="--")
        ax.text(out_sample.iloc[0], ax.get_ylim()[1], "  Ngoài mẫu", fontsize=7, va="top")
    ax.set_title(f"Equity curve - tái cân bằng mỗi {period} phiên, không chồng lấp, "
                 f"đã trừ phí", fontsize=9)
    ax.set_ylabel("Giá trị danh mục (bắt đầu = 1.0)")
    ax.legend(frameon=False, fontsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "ssi_cache" / "ohlcv"))
    ap.add_argument("--period", type=int, default=20, choices=(5, 10, 20),
                     help="Số phiên mỗi kỳ tái cân bằng (không chồng lấp)")
    ap.add_argument("--split", default=None, help="Ngày bắt đầu ngoài mẫu (mặc định: 60%% thời gian)")
    ap.add_argument("--cost", type=float, default=0.004)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    data = Path(a.data)
    syms = None
    if a.limit:
        syms = sorted(p.stem.upper() for p in data.glob("*.csv"))[: a.limit]
    curves, summary, ev = run(data, period=a.period, split=a.split, cost=a.cost, symbols=syms,
                              progress=lambda k, n: print(f"  {k}/{n} mã...", flush=True))
    if curves.empty:
        print("Không có kỳ nào đủ dữ liệu: kiểm tra thư mục dữ liệu và VNINDEX.csv")
        return 1
    out = ROOT / "docs" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    curves.to_csv(out / "backtest_portfolio_curve.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(out / "backtest_portfolio_summary.csv", index=False, encoding="utf-8-sig")
    try:
        chart(curves, out / "backtest_portfolio_equity.png", a.period)
    except Exception as exc:  # noqa: BLE001
        print("Không vẽ được biểu đồ:", type(exc).__name__)
    import pandas as pd
    split_date = curves.loc[curves["Giai đoạn"].eq("Ngoài mẫu"), "date"].min()
    print(f"\nSố kỳ: {len(curves):,} | Từ {curves['date'].min():%d/%m/%Y} đến "
          f"{curves['date'].max():%d/%m/%Y} | Ngoài mẫu từ {split_date:%d/%m/%Y} | "
          f"kỳ = {a.period} phiên")
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(summary.to_string(index=False))
    print(f"\nĐã ghi: {out / 'backtest_portfolio_curve.csv'}, "
          f"backtest_portfolio_summary.csv, backtest_portfolio_equity.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
