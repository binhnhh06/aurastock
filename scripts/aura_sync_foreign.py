# -*- coding: utf-8 -*-
"""SSI FastConnect V3 foreign trading EOD snapshot; no trading requests.

Run from project root:
  python scripts/aura_sync_foreign.py --days 10 --vn30
  python scripts/aura_sync_foreign.py --days 5 --symbols FPT,HPG,SSI
  python scripts/aura_sync_foreign.py --days 10 --vn30 --dry-run

Data is kept locally and appended by (scope,code,date). No API keys are exported.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

# AURA_V114_UTF8_STDOUT: khi chạy qua Task Scheduler/console cp1252 của Windows,
# print() các dòng tiếng Việt có dấu (vd 'mục tiêu') làm crash UnicodeEncodeError
# ngay từ dòng đầu của main() -> job EOD dừng giữa chừng, khối ngoại không được
# cập nhật. Ép stdout/stderr sang UTF-8 (hoặc thay ký tự lỗi) để không bao giờ
# crash vì encoding nữa, bất kể console đang ở codepage nào.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.aura_macro_foreign import FLOW_REL, FLOW_COLUMNS, read_foreign

TZ = ZoneInfo('Asia/Ho_Chi_Minh')
OUT = ROOT / FLOW_REL


def _num(value):
    if value is None or value == '':
        return float('nan')
    try:
        x = float(value)
        return x if pd.notna(x) and abs(x) < 1e30 else float('nan')
    except (TypeError, ValueError):
        return float('nan')


def _net(preferred, buy, sell):
    a = _num(preferred)
    if pd.notna(a):
        return a
    if pd.notna(buy) and pd.notna(sell):
        return buy - sell
    return float('nan')


def _read(record, field):
    if isinstance(record, dict):
        return record.get(field)
    return getattr(record, field, None)


def format_record(scope, code, item, stamp):
    if item is None:
        return None
    dt = pd.to_datetime(_read(item, 'trading_date'), errors='coerce')
    if pd.isna(dt) or dt.date() > datetime.now(TZ).date():
        return None
    if scope == 'INDEX':
        bv = _num(_read(item, 'total_buy_foreign_value'))
        sv = _num(_read(item, 'total_sell_foreign_value'))
        nv = _net(_read(item, 'net_purchases_foreign_value'), bv, sv)
        bq = _num(_read(item, 'total_buy_foreign'))
        sq = _num(_read(item, 'total_sell_foreign'))
        nq = _net(_read(item, 'net_purchases_foreign_volume'), bq, sq)
        source = 'SSI FastConnect V3 · Index Summary'
    else:
        bv = _num(_read(item, 'total_foreign_buy_value'))
        sv = _num(_read(item, 'total_foreign_sell_value'))
        nv = _net(None, bv, sv)
        bq = _num(_read(item, 'total_foreign_buy'))
        sq = _num(_read(item, 'total_foreign_sell'))
        nq = _net(None, bq, sq)
        source = 'SSI FastConnect V3 · Securities Summary'
    if all(pd.isna(z) for z in (bv,sv,nv,bq,sq,nq)):
        return None
    return {'scope':scope,'code':code,'date':dt.date().isoformat(),
            'buy_value_vnd':bv,'sell_value_vnd':sv,'net_value_vnd':nv,
            'buy_volume':bq,'sell_volume':sq,'net_volume':nq,
            'source':source,'retrieved_at':stamp}


def save_rows(rows):
    if not rows:
        return 0
    old = read_foreign(ROOT)
    fresh = pd.DataFrame(rows, columns=FLOW_COLUMNS)
    combined = (pd.concat([old, fresh], ignore_index=True)
                if not old.empty else fresh.copy())
    combined['date'] = pd.to_datetime(combined['date'], errors='coerce')
    combined = combined[combined['date'].notna()].sort_values('date')
    combined = combined.drop_duplicates(['scope','code','date'],keep='last')
    combined['date'] = combined['date'].dt.strftime('%Y-%m-%d')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix('.csv.aura_tmp')
    try:
        combined[FLOW_COLUMNS].to_csv(tmp, index=False, encoding='utf-8-sig')
        os.replace(tmp, OUT)
    finally:
        tmp.unlink(missing_ok=True)
    return len(fresh)


def target_day(now):
    day = now.date() if (now.hour, now.minute) >= (15, 30) else (now - timedelta(days=1)).date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def plan_days(n, end):
    return [ts.date() for ts in pd.bdate_range(end=end, periods=n)]


def parse_symbols(raw):
    symbols = [x.strip().upper() for x in raw.split(',') if x.strip()]
    invalid = [x for x in symbols if not re.fullmatch(r'[A-Z0-9]{2,12}', x)]
    if invalid:
        raise ValueError('Không hợp lệ: ' + ','.join(invalid[:5]))
    return list(dict.fromkeys(symbols))


def main(argv=None):
    parser = argparse.ArgumentParser(description='SSI EOD khối ngoại cho AURA (không đặt lệnh)')
    parser.add_argument('--days', type=int, default=10, help='Số ngày làm việc gần đây (không xét lễ)')
    parser.add_argument('--indices', default='VNINDEX,VN30,HNXINDEX,UPCOMINDEX')
    parser.add_argument('--symbols', default='', help='Ví dụ: FPT,HPG,SSI')
    parser.add_argument('--vn30', action='store_true', help='Tải riêng rổ VN30 (mẫu, không đại diện toàn thị trường)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if not (1 <= args.days <= 25):
        parser.error('--days phải nằm trong 1..25')
    try:
        indices = parse_symbols(args.indices)
        symbols = parse_symbols(args.symbols)
    except ValueError as exc:
        parser.error(str(exc))
    if not indices:
        parser.error('Cần ít nhất 1 chỉ số')
    end = target_day(datetime.now(TZ))
    days = plan_days(args.days, end)
    print('Phiên mục tiêu:', end, '| số ngày làm việc:', len(days),
          '| chỉ số:', ','.join(indices), '| mã:', ','.join(symbols) or '(trống)',
          '| lấy VN30:', args.vn30)
    if args.dry_run:
        print('[DRY-RUN] Không gọi API hay ghi dữ liệu. Dự kiến', len(indices)*len(days),
              'truy vấn chỉ số +', len(symbols), 'truy vấn cổ phiếu (+ VN30 nếu chọn).')
        return 0
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
    except ImportError:
        pass
    names = ('SSI_CLIENT_ID','SSI_API_KEY','SSI_API_SECRET')
    if any(not os.getenv(x) for x in names):
        parser.error('Chưa đủ 3 biến SSI trong .env. Không đưa API key vào file CSV hoặc GitHub.')
    try:
        from ssi_sdk import Auth, Config, Data
    except ImportError:
        parser.error('Chưa có ssi_sdk; dùng venv của dự án AURA.')
    stamp = datetime.now(TZ).isoformat(timespec='seconds')
    rows, errors = [], 0
    cfg = Config(client_id=os.environ['SSI_CLIENT_ID'], api_key=os.environ['SSI_API_KEY'],
                 api_secret=os.environ['SSI_API_SECRET'])
    try:
        with Auth(cfg) as auth:
            auth.authenticate()
            with Data(auth) as data:
                api = data.market_data
                if args.vn30:
                    try:
                        securities = api.get_securities_info_by_index('VN30') or []
                        symbols += [str(_read(x,'symbol')).upper() for x in securities
                                    if _read(x,'symbol')]
                        symbols = list(dict.fromkeys(s for s in symbols if re.fullmatch(r'[A-Z0-9]{2,12}',s)))
                        print('Mẫu mã VN30:', len(symbols))
                    except Exception as exc:
                        print('[WARN] Không lấy được rổ VN30:', type(exc).__name__)
                        errors += 1
                for code in indices:
                    for dt in days:
                        try:
                            item = api.get_index_summary_historical(code, dt.strftime('%Y/%m/%d'))
                            row = format_record('INDEX', code, item, stamp)
                            if row:
                                rows.append(row)
                        except Exception as exc:
                            errors += 1
                            print('[WARN] Index', code, dt, type(exc).__name__)
                start = days[0].strftime('%Y/%m/%d')
                stop = days[-1].strftime('%Y/%m/%d')
                for i, symbol in enumerate(symbols):
                    try:
                        records = api.get_securities_summary_historical(
                            symbol=symbol, from_date=start, to_date=stop) or []
                        n = 0
                        for item in records:
                            row = format_record('STOCK', symbol, item, stamp)
                            if row:
                                rows.append(row)
                                n += 1
                        print(f'[{i+1}/{len(symbols)}] {symbol}: {n} phiên có dữ liệu ngoại')
                    except Exception as exc:
                        errors += 1
                        print('[WARN] Stock', symbol, type(exc).__name__)
    except Exception as exc:
        print('[STOP] Kết nối SSI gặp lỗi:', type(exc).__name__, '(không ghi token)')
        return 2
    count = save_rows(rows)
    print('[KẾT QUẢ] Đã ghi', count, 'dòng dữ liệu EOD;', errors, 'truy vấn lỗi.')
    print('[FILE]', OUT)
    if not count:
        print('[WARN] SSI chưa trả dữ liệu khối ngoại, giữ nguyên cache cũ.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
