"""Audit rankings locally, recording EOD & universe to distinguish genuine rank changes.
No changes to cache/strategy/scores; imports same current screener as AURA.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description='Lưu và so sánh snapshots xếp hạng AURA theo EOD')
    parser.add_argument('--root', default='.', help='Đường dẫn dự án AURA')
    parser.add_argument('--previous', default='', help='Snapshot CSV cũ để so sánh (nếu có)')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not (root / 'core' / 'smart_screener.py').is_file():
        print('[SAFE] Không thấy core/smart_screener.py trong thư mục dự án.')
        return 2
    sys.path.insert(0, str(root))
    from core.smart_screener import scan_cached_universe

    out = root / 'reports' / 'aura_ranking_history'
    out.mkdir(parents=True, exist_ok=True)
    prior = Path(args.previous).expanduser().resolve() if args.previous else None
    if prior is None:
        candidates = sorted(out.glob('AURA_RANK_*.csv'))
        if candidates:
            prior = candidates[-1]

    frame, meta = scan_cached_universe(root)
    ready = frame.loc[frame['Trạng thái'].eq('Đủ dữ liệu')].copy()
    if ready.empty:
        print(f'[STOP] Phiên {meta.as_of} chưa có mã đủ điều kiện. Không tạo bảng so sánh rỗng.')
        return 3
    keep = [k for k in ['Mã', 'Thứ hạng', 'Smart Rating /10', 'Ngày dữ liệu', 'Trạng thái', 'Lý do'] if k in ready]
    snap = ready[keep].copy()
    snap.insert(0, 'Phiên chốt', str(meta.as_of))
    snap.insert(1, 'Tổng mã đủ điều kiện', int(meta.eligible))
    snap.insert(2, 'Danh mục EQUITY', int(meta.universe_size))
    stamp = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%d_%H%M%S')
    path = out / f'AURA_RANK_{stamp}.csv'
    snap.to_csv(path, index=False, encoding='utf-8-sig')
    print(f'[OK] Phiên EOD {meta.as_of} | Đủ dữ liệu: {meta.eligible}/{meta.universe_size}')
    print(f'[SNAPSHOT] {path}')
    print('[TOP 10]')
    for _, r in snap.sort_values(['Thứ hạng', 'Mã']).head(10).iterrows():
        print(f"{int(r['Thứ hạng']):>3} | {r['Mã']:<6} | {float(r['Smart Rating /10']):.2f}")

    if prior:
        if not prior.is_file():
            print(f'[WARN] Không tìm thấy bảng cũ: {prior}')
            return 0
        try:
            old = pd.read_csv(prior, encoding='utf-8-sig')
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            print(f'[WARN] Không đọc được bảng cũ: {exc}')
            return 0
        req = {'Mã', 'Thứ hạng', 'Smart Rating /10'}
        if not req.issubset(old):
            print(f'[WARN] Bảng cũ thiếu cột {req - set(old.columns)}; chỉ lưu snapshot hiện tại.')
            return 0
        old = old.drop_duplicates('Mã')
        new = snap.drop_duplicates('Mã')
        pair = new.merge(old, on='Mã', how='outer', suffixes=('_mới', '_cũ'), indicator=True)
        pair['Đổi hạng (mới − cũ)'] = (
            pd.to_numeric(pair.get('Thứ hạng_mới'), errors='coerce') -
            pd.to_numeric(pair.get('Thứ hạng_cũ'), errors='coerce')
        )
        pair['Đổi điểm'] = (
            pd.to_numeric(pair.get('Smart Rating /10_mới'), errors='coerce') -
            pd.to_numeric(pair.get('Smart Rating /10_cũ'), errors='coerce')
        )
        pair.to_csv(out / f'AURA_SO_SANH_{stamp}.csv', index=False, encoding='utf-8-sig')
        same = pair.loc[pair['_merge'].eq('both')]
        print(f'[SO SÁNH] Cũ: {len(old)} mã; mới: {len(new)} mã; chung: {len(same)} mã')
        print(f"[CHUYỂN TẬP] Mới thêm: {int(pair['_merge'].eq('left_only').sum())}; không còn đủ điều kiện: {int(pair['_merge'].eq('right_only').sum())}")
        days = old['Phiên chốt'].dropna().unique() if 'Phiên chốt' in old else []
        if len(days):
            print(f"[NGÀY] Cũ: {', '.join(map(str, days[:4]))}; mới: {meta.as_of}")
            if str(meta.as_of) not in [str(x) for x in days]:
                print('[NOTE] Khác ngày EOD: không quy thay đổi điểm/hạng thành lỗi thuật toán.')
        print(f'[SO SÁNH CSV] {out / f"AURA_SO_SANH_{stamp}.csv"}')
    else:
        print('[NOTE] Chưa có snapshot cũ. Chạy lại sau khi đồng bộ EOD để tự so sánh.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
