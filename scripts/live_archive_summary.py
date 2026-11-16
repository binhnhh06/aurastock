"""Tóm tắt dữ liệu SSI WebSocket đã lưu (dùng cho mục Kiểm thử của báo cáo).

Chạy: python scripts/live_archive_summary.py
Ghi kết quả ra docs/evidence/live_archive_summary.csv (chỉ số liệu tổng hợp, không chứa tick thô).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.live_archive import ARCHIVE_DIR, summarize  # noqa: E402


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT), help="Thư mục dự án chứa data/ssi_cache/live_archive")
    ap.add_argument("--out", default=str(ROOT / "docs" / "evidence"))
    a = ap.parse_args()
    archive = Path(a.root) / "data" / "ssi_cache" / "live_archive"
    df = summarize(archive)
    if df.empty:
        print(f"Chưa có dữ liệu trong {archive}. Hãy chạy scripts/ssi_live_worker.py trong giờ giao dịch.")
        return 1
    out = Path(a.out) / "live_archive_summary.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(df.to_string(index=False))
    print(f"\nSố phiên đã thu: {len(df)} | Tổng dòng: {int(df['Số dòng'].sum()):,} | File: {out}")
    if len(df) < 5:
        print(f"Đề khuyến nghị tối thiểu 5 phiên (tốt nhất 10): còn thiếu {5 - len(df)} phiên.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
