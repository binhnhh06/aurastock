"""Đẩy file dữ liệu khối ngoại (data/ssi_cache/foreign_flow_eod.csv) lên R2,
đúng key mà core/aura_foreign_r2_v105.py đọc cho trang Dòng tiền khối ngoại.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
    except ImportError:
        pass

    from core.aura_r2_market import client, enabled, prefix, setting
    from core.aura_macro_foreign import FLOW_REL

    if not enabled():
        print('THIEU CAU HINH: can du 5 bien AURA_R2_* trong .env')
        sys.exit(1)

    path = ROOT / FLOW_REL
    if not path.is_file():
        print(f'KHONG THAY FILE: {path} — chay scripts/aura_sync_foreign.py truoc.')
        sys.exit(1)

    body = path.read_bytes()
    if len(body) > 8 * 1024 * 1024:
        print('TAP TIN QUA LON (>8MB).')
        sys.exit(1)

    s3 = client()
    bucket, base = setting('AURA_R2_BUCKET'), prefix()
    key = f'{base}/foreign_flow/v1/foreign_flow_eod.csv'
    s3.put_object(Bucket=bucket, Key=key, Body=body,
                  ContentType='text/csv', CacheControl='no-store')

    import pandas as pd
    d = pd.read_csv(path, encoding='utf-8-sig')
    last = pd.to_datetime(d.get('date'), errors='coerce').max()
    print(f'DA_UPLOAD · {len(d):,} dong · ngay moi nhat {last:%d/%m/%Y} · key={key}')


if __name__ == '__main__':
    main()