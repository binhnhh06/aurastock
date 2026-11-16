"""Kiểm kê dữ liệu SSI đã lưu trên máy (EOD, chỉ số, realtime) trước khi backtest/viết báo cáo.

Chạy: python scripts/aura_data_inventory.py [--root C:\\duong\\dan\\du_an]
Chỉ đọc file, không gọi API, không in khóa.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    root = Path(ap.parse_args().root)
    cache = root / "data" / "ssi_cache"
    ohlcv = cache / "ohlcv"
    files = sorted(ohlcv.glob("*.csv")) if ohlcv.is_dir() else []
    print(f"Thư mục dự án: {root}")
    print(f"Nến EOD (data/ssi_cache/ohlcv): {len(files):,} file")
    rows = []
    for f in files:
        try:
            d = pd.read_csv(f, usecols=lambda c: c in ("date", "time"))
            col = "date" if "date" in d else "time"
            t = pd.to_datetime(d[col], errors="coerce").dropna()
            if len(t):
                rows.append((f.stem.upper(), len(t), t.min(), t.max()))
        except (OSError, ValueError):
            continue
    if rows:
        inv = pd.DataFrame(rows, columns=["symbol", "bars", "first", "last"])
        print(f"  Số phiên/mã: trung vị {int(inv['bars'].median())}, ≥200 phiên: {(inv['bars'] >= 200).sum():,} mã")
        print(f"  Khoảng ngày: {inv['first'].min():%d/%m/%Y} → {inv['last'].max():%d/%m/%Y}")
        print(f"  Phiên mới nhất phổ biến: {inv['last'].mode().iloc[0]:%d/%m/%Y} "
              f"({(inv['last'] == inv['last'].mode().iloc[0]).sum():,} mã)")
        for idx in ("VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"):
            r = inv.loc[inv["symbol"].eq(idx)]
            print(f"  {idx}: " + (f"{int(r['bars'].iloc[0])} phiên đến {r['last'].iloc[0]:%d/%m/%Y}" if len(r) else "KHÔNG CÓ"))
    cat = cache / "market_symbols.csv"
    if cat.is_file():
        c = pd.read_csv(cat, encoding="utf-8-sig", dtype=str)
        has = "listed_shares" in c.columns
        print(f"Danh mục SSI: {len(c):,} mã · cột listed_shares: {'có' if has else 'chưa'}")
    else:
        print("Danh mục SSI: KHÔNG CÓ market_symbols.csv")
    live = cache / "live_market.json"
    if live.is_file():
        try:
            s = json.loads(live.read_text(encoding="utf-8"))
            print(f"Realtime mới nhất: {len(s.get('quotes', {}))} mã, {len(s.get('indices', {}))} chỉ số · "
                  f"worker_at {s.get('worker_at')} · {s.get('connection')}")
        except (OSError, ValueError):
            print("Realtime: live_market.json không đọc được")
    arch = cache / "live_archive"
    days = sorted(p.stem for p in arch.glob("????-??-??.csv")) if arch.is_dir() else []
    print(f"Lịch sử WebSocket đã lưu: {len(days)} phiên" + (f" ({', '.join(days)})" if days else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
