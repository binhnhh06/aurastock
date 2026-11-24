"""Đẩy 4 file EOD chỉ số (VNINDEX, VN30, HNXINDEX, UPCOMINDEX) lên R2 private,
đúng key mà core/aura_four_index_private_v103.py đọc cho 4 thẻ ở tab Tổng quan.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CODES = ('VNINDEX', 'VN30', 'HNXINDEX', 'UPCOMINDEX')
SCHEMA = 'aura_ssi_index_summary_v103'
SRC = ROOT / 'data' / 'ssi_cache' / 'index_summary'


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
    except ImportError:
        pass

    from core.aura_r2_market import client, enabled, prefix, setting
    from core.aura_four_index_private_v103 import validate

    if not enabled():
        print('THIẾU CẤU HÌNH: cần đủ 5 biến AURA_R2_ENDPOINT / AURA_R2_BUCKET / '
              'AURA_R2_ACCESS_KEY_ID / AURA_R2_SECRET_ACCESS_KEY / AURA_R2_PREFIX trong .env')
        sys.exit(1)

    s3 = client()
    bucket, base = setting('AURA_R2_BUCKET'), prefix()
    uploaded, skipped = 0, 0

    for code in CODES:
        path = SRC / f'{code}.json'
        if not path.is_file():
            print(f'{code}: BO_QUA (khong co file local {path.name}, hay chay ssi_refresh_indices.py truoc)')
            skipped += 1
            continue
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            print(f'{code}: LOI_DOC_FILE ({type(exc).__name__})')
            skipped += 1
            continue

        record['symbol'] = code
        record['schema'] = SCHEMA

        checked = validate(record, code)
        if checked is None:
            print(f'{code}: TU_CHOI (du lieu khong qua duoc kiem tra validate() cua app - '
                  f'kiem tra lai gia/ngay/don vi trong {path.name})')
            skipped += 1
            continue

        key = f'{base}/index_summary/v103/{code}.json'
        body = json.dumps(record, ensure_ascii=False).encode('utf-8')
        s3.put_object(Bucket=bucket, Key=key, Body=body,
                      ContentType='application/json', CacheControl='no-store')
        print(f'{code}: DA_UPLOAD · phien {record["date"]} · {record["price"]:,.2f} diem · key={key}')
        uploaded += 1

    print(f'Hoan tat: {uploaded} chi so da upload, {skipped} bi bo qua.')
    print('Mo lai Streamlit app (cho khoang 5 phut de het cache TTL=300s) va kiem tra lai tab Tong quan.')


if __name__ == '__main__':
    main()