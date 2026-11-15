r"""Refresh AURA's four market index EOD cards via SSI FastConnect REST.

Run once when the stock exchange is closed, or whenever EOD cards are stale:
    .\.venv\Scripts\python.exe .\scripts\ssi_refresh_indices.py

Unlike WebSocket, REST indexSummary supports past trading dates. This script
never invents prices or derives traded value from index points × volume.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CODES = ('VNINDEX', 'VN30', 'HNXINDEX', 'UPCOMINDEX')
DEST = ROOT / 'data' / 'ssi_cache' / 'index_summary'


def numeric(value, *, nonnegative=False):
    try:
        if value is None or str(value).strip() == '':
            return None
        n = float(value)
        return n if math.isfinite(n) and (not nonnegative or n >= 0) else None
    except (TypeError, ValueError, OverflowError):
        return None


def valid_day(raw):
    if raw is None:
        return None
    try:
        return date.fromisoformat(str(raw).split(' ')[0].replace('/', '-'))
    except (ValueError, TypeError):
        return None


def summary_payload(code, summary):
    """Map the documented MarketIndexSummary dataclass to a safe EOD record."""
    if summary is None:
        return None
    d = valid_day(getattr(summary, 'trading_date', None))
    price = numeric(getattr(summary, 'index_value', None))
    if d is None or price is None or not 30 <= price <= 10000 or d > date.today():
        return None

    def get(field, nonnegative=False):
        return numeric(getattr(summary, field, None), nonnegative=nonnegative)

    vol_total = get('total_trade', True)
    val_total = get('total_trade_value', True)
    vol_match = get('total_match', True)
    val_match = get('total_match_value', True)
    return {
        'symbol': code,
        'date': d.isoformat(),
        'price': price,
        'change': get('index_change'),
        'percent': get('index_change_percent'),
        'volume': vol_total if vol_total is not None else vol_match,
        'value': val_total if val_total is not None else val_match,
        'volume_type': 'Tổng KLGD phiên' if vol_total is not None else 'KL khớp lệnh',
        'value_type': 'Tổng GTGD phiên' if val_total is not None else 'GT khớp lệnh',
        'advances': get('total_advance_stock', True),
        'declines': get('total_decline_stock', True),
        'nochanges': get('total_steady_stock', True),
        'source': 'SSI FastConnect V3 REST indexSummary',
    }


def save_record(record):
    DEST.mkdir(parents=True, exist_ok=True)
    path = DEST / (record['symbol'] + '.json')
    # Never replace a newer, verified record with an older SSI response.
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding='utf-8'))
            if old.get('date', '') > record['date']:
                return 'SKIP_OLDER'
        except (OSError, ValueError, TypeError):
            pass
    fd, temp_name = tempfile.mkstemp(prefix='.idx_', suffix='.json', dir=DEST)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        for attempt in range(8):
            try:
                os.replace(temp_name, path)
                return 'SAVED'
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.25 * (attempt + 1))
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def previous_trading_days(start: date, limit: int):
    dates = []
    cursor = start
    while len(dates) < limit:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    return dates


def fetch(md, code, *, limit):
    reference = previous_trading_days(date.today(), limit)
    latest_expected = reference[0]
    best = None
    errors = []
    for label, fn in [('current', lambda: md.get_index_summary(code))] + [
        (day.isoformat(), lambda day=day: md.get_index_summary_historical(code, day.strftime('%Y/%m/%d')))
        for day in reference
    ]:
        try:
            item = summary_payload(code, fn())
        except Exception as exc:
            # Do not show any auth or SDK objects (may contain secrets).
            errors.append(f'{label}: {type(exc).__name__}')
            item = None
        if item is not None and (best is None or item['date'] > best['date']):
            best = item
        # Stored records use ISO-8601 date strings; compare date with date.
        best_day = valid_day(best.get('date')) if best is not None else None
        if best_day is not None and best_day >= latest_expected:
            break
    return best, errors


def main():
    parser = argparse.ArgumentParser(description='Lấy EOD cho 4 chỉ số AURA từ SSI indexSummary REST.')
    parser.add_argument('--recent-days', type=int, default=5,
                        help='Số ngày làm việc gần nhất được thử (mặc định 5)')
    parser.add_argument('--pause', type=float, default=0.5)
    args = parser.parse_args()
    if args.recent_days < 1 or args.recent_days > 20 or args.pause < 0:
        parser.error('--recent-days phải từ 1..20; --pause không âm')
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
    except ImportError:
        pass
    from ssi_sdk import Auth, Data
    from core.ssi_market_live import get_credential_config
    with Auth(get_credential_config()) as auth:
        auth.authenticate()
        with Data(auth) as data:
            for code in CODES:
                record, errors = fetch(data.market_data, code, limit=args.recent_days)
                if record is None:
                    print(f'{code}: CHUA_CO_DU_LIEU · Loại lỗi: {", ".join(errors[:3]) or "Không có phản hồi hợp lệ"}', flush=True)
                else:
                    try:
                        action = save_record(record)
                        print(f'{code}: {action} · phiên {record["date"]} · {record["price"]:,.2f} điểm · '
                              f'GTGD {record["value"] if record["value"] is not None else "chưa có"}', flush=True)
                    except OSError as exc:
                        print(f'{code}: WRITE_ERROR {type(exc).__name__}', flush=True)
                time.sleep(args.pause)
    print('Hoàn tất cập nhật indexSummary. Mở/tải lại tab Tổng quan AURA.', flush=True)


if __name__ == '__main__':
    main()
