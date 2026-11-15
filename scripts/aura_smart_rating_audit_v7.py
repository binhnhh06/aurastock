"""CLI read-only overview for AURA Smart Rating V7."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--as-of', default='2026-11-13')
    opt = p.parse_args()
    root = opt.root.resolve()
    sys.path.insert(0, str(root))
    from core.aura_smart_rating_v7 import (build_provisional_research,
        prepare_verified_snapshot, SNAPSHOT_NAME, ANNUAL_NAME)
    print('=== AURA SMART RATING V7 | AUDIT CHI DOC ===')
    print('Thu muc:', root)
    annual = root / ANNUAL_NAME
    print('BCTC so bo:', annual if annual.is_file() else 'Chua co')
    preview = build_provisional_research(root)
    print('So dong BCTC 2025:', len(preview))
    if not preview.empty:
        col = 'Điểm cơ bản SƠ BỘ /10'
        print('Du chi tieu so bo:', int(preview[col].notna().sum()))
        print('Thieu chi tieu/nhom:', int(preview[col].isna().sum()))
    snapshot = root / SNAPSHOT_NAME
    if snapshot.is_file():
        raw = pd.read_csv(snapshot, encoding='utf-8-sig', dtype={'symbol': str})
        try:
            verified, audit = prepare_verified_snapshot(raw, opt.as_of)
            print('So dong ho so co flag & chung tu dat:', len(verified))
            print('Trang thai:')
            if not audit.empty:
                print(audit['Trạng thái kiểm chứng'].value_counts().to_string())
        except (ValueError, KeyError) as exc:
            print('[CANH BAO]', exc)
    else:
        print('Ho so kiem chung: CHUA CO - tai mau CSV tu Smart Rating V7.')
    print('Luu y: diem BCTC so bo KHONG duoc dung lam tin hieu MUA hoac backtest.')


if __name__ == '__main__':
    main()
