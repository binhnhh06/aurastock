# -*- coding: utf-8 -*-
"""Debug-only: in nguyên văn response SSI trả về cho UPCOMINDEX, không ghi
file nào cả, không gọi API đặt lệnh. Chỉ để kiểm tra SSI có thực sự thiếu
dữ liệu khối ngoại cho UPCOMINDEX hay code đang đọc sai field.

Chạy:
  python scripts/aura_debug_upcom_foreign.py
  python scripts/aura_debug_upcom_foreign.py --date 2026/11/26
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=None, help='YYYY/MM/DD, mặc định = hôm nay')
    parser.add_argument('--code', default='UPCOMINDEX')
    args = parser.parse_args(argv)
    the_date = args.date or datetime.now(TZ).strftime('%Y/%m/%d')

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
    except ImportError:
        pass
    names = ('SSI_CLIENT_ID', 'SSI_API_KEY', 'SSI_API_SECRET')
    if any(not os.getenv(x) for x in names):
        parser.error('Chưa đủ 3 biến SSI trong .env')
    from ssi_sdk import Auth, Config, Data

    cfg = Config(client_id=os.environ['SSI_CLIENT_ID'], api_key=os.environ['SSI_API_KEY'],
                 api_secret=os.environ['SSI_API_SECRET'])
    print(f'--- Tra cứu {args.code} ngày {the_date} ---')
    with Auth(cfg) as auth:
        auth.authenticate()
        from ssi_sdk import Data
        with Data(auth) as data:
            item = data.market_data.get_index_summary_historical(args.code, the_date)
            print('type(item) =', type(item))
            if item is None:
                print('SSI trả về None cho ngày này (có thể không phải phiên giao dịch).')
                return 0
            if isinstance(item, dict):
                keys = item.keys()
            else:
                keys = [k for k in dir(item) if not k.startswith('_')]
            print('--- Toàn bộ field có trong response ---')
            for k in sorted(keys):
                try:
                    v = item.get(k) if isinstance(item, dict) else getattr(item, k)
                except Exception as exc:
                    v = f'<lỗi đọc: {exc}>'
                if callable(v):
                    continue
                print(f'{k!r:45s} = {v!r}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
