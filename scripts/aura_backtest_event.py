"""Chạy event study cho điểm kỹ thuật AURA trên dữ liệu SSI EOD đã lưu trong máy.

Chạy:   python scripts/aura_backtest_event.py
Tùy chọn: --split 2025-09-01  --every 5  --cost 0.004  --limit 300 (chạy thử ít mã)
Kết quả:
  docs/evidence/backtest_summary.csv   bảng so sánh tín hiệu vs baseline vs VN-Index
  docs/evidence/backtest_buckets.csv   lợi suất 20 phiên theo nhóm điểm
  docs/evidence/backtest_buckets.png   biểu đồ cho báo cáo
  reports/backtest/events.csv          toàn bộ sự kiện (không commit)
Không gọi API, không sửa dữ liệu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.aura_backtest import run  # noqa: E402


def chart(buckets, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    col = [c for c in buckets.columns if c.startswith("Vượt VN-Index")][0]
    fig, ax = plt.subplots(figsize=(7, 3.8), dpi=150)
    periods = [p for p in ("Trong mẫu", "Ngoài mẫu") if p in set(buckets["Giai đoạn"])]
    labels = list(dict.fromkeys(buckets["Nhóm điểm"].astype(str)))
    w = 0.8 / max(len(periods), 1)
    for k, p in enumerate(periods):
        sub = buckets.loc[buckets["Giai đoạn"].eq(p)]
        sub = sub.set_index(sub["Nhóm điểm"].astype(str))
        vals = [sub[col].get(l, float("nan")) for l in labels]
        ax.bar([i + k * w for i in range(len(labels))], vals, width=w, label=p,
               color=["#7C3AED", "#F59E0B"][k % 2])
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_xticks([i + w * (len(periods) - 1) / 2 for i in range(len(labels))], labels)
    ax.set_xlabel("Nhóm điểm kỹ thuật AURA tại phiên t")
    ax.set_ylabel("Vượt VN-Index sau 20 phiên (%)")
    ax.set_title("Lợi suất vượt VN-Index theo nhóm điểm (sau phí, vào lệnh mở cửa t+1)", fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "ssi_cache" / "ohlcv"))
    ap.add_argument("--split", default=None, help="Ngày bắt đầu ngoài mẫu (mặc định: 60%% thời gian)")
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--cost", type=float, default=0.004)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    data = Path(a.data)
    syms = None
    if a.limit:
        syms = sorted(p.stem.upper() for p in data.glob("*.csv"))[: a.limit]
    ev, summary, buckets = run(data, split=a.split, every=a.every, cost=a.cost, symbols=syms,
                               progress=lambda k, n: print(f"  {k}/{n} mã...", flush=True))
    if ev.empty:
        print("Không có sự kiện nào: kiểm tra thư mục dữ liệu và VNINDEX.csv")
        return 1
    ev_dir = ROOT / "reports" / "backtest"
    out = ROOT / "docs" / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    ev.to_csv(ev_dir / "events.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(out / "backtest_summary.csv", index=False, encoding="utf-8-sig")
    buckets.to_csv(out / "backtest_buckets.csv", index=False, encoding="utf-8-sig")
    try:
        chart(buckets, out / "backtest_buckets.png")
    except Exception as exc:  # noqa: BLE001
        print("Không vẽ được biểu đồ:", type(exc).__name__)
    split = ev.loc[ev["period"].eq("Ngoài mẫu"), "date"].min()
    print(f"\nSự kiện: {len(ev):,} | Mã: {ev['symbol'].nunique():,} | Từ {ev['date'].min():%d/%m/%Y} "
          f"đến {ev['date'].max():%d/%m/%Y} | Ngoài mẫu từ {split:%d/%m/%Y}")
    import pandas as pd
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(summary.loc[summary["Kỳ hạn (phiên)"].eq(20)].to_string(index=False))
        print()
        print(buckets.to_string(index=False))
    print(f"\nĐã ghi: {out / 'backtest_summary.csv'}, backtest_buckets.csv/.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
