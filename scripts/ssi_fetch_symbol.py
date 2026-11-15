"""Fetch one stock's daily OHLCV on-demand, or controlled batches after catalogue refresh.

Examples:
 python scripts/ssi_fetch_symbol.py FPT
 python scripts/ssi_fetch_symbol.py HPG --days 900
 python scripts/ssi_fetch_symbol.py --batch 30 --offset 0
"""
from __future__ import annotations
import argparse
import os
import sys
import time
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.ssi_universe import screener_symbols, validate_symbol

OUTPUT = ROOT / 'data' / 'ssi_cache' / 'ohlcv'
TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def from_ohlc(symbol, candles):
    rows = []
    for c in candles or []:
        rows.append({'symbol':symbol,'date':getattr(c,'trading_date',None),
                     'open':getattr(c,'open_price',None),'high':getattr(c,'high_price',None),
                     'low':getattr(c,'low_price',None),'close':getattr(c,'close_price',None),
                     'volume':getattr(c,'volume',None)})
    return pd.DataFrame(rows, columns=['symbol','date','open','high','low','close','volume'])


def persist(symbol, data, target, cutoff):
    if data.empty:
        return 0
    data = data.copy()
    data['date'] = pd.to_datetime(data['date'], errors='coerce').dt.normalize()
    data = data[data['date'].le(pd.Timestamp(cutoff))]
    frames = [data]
    if target.is_file():
        frames.insert(0, pd.read_csv(target, encoding='utf-8-sig'))
    result = pd.concat(frames, ignore_index=True)
    result['date'] = pd.to_datetime(result['date'], errors='coerce').dt.normalize()
    for c in ('open','high','low','close','volume'):
        result[c] = pd.to_numeric(result[c], errors='coerce')
    result = result.dropna(subset=['date','open','high','low','close','volume'])
    result = result.sort_values('date').drop_duplicates('date', keep='last')
    if result.empty or (result[['open','high','low','close']] <= 0).any().any() or (result['volume'] < 0).any():
        raise ValueError(f'{symbol}: OHLCV invalid')
    if ((result['high'] < result[['open','low','close']].max(axis=1)) | (result['low'] > result[['open','high','close']].min(axis=1))).any():
        raise ValueError(f'{symbol}: invalid OHLC range')
    if not result['symbol'].astype(str).str.upper().eq(symbol).all():
        raise ValueError(f'{symbol}: mixed symbols')
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix('.tmp')
    result.to_csv(tmp, index=False, encoding='utf-8-sig')
    os.replace(tmp, target)
    return len(result)


def download_with_service(data, symbol, days=900, root=ROOT, now=None):
    from ssi_sdk.enums import Timeframe
    symbol = validate_symbol(symbol, root)
    now = now or datetime.now(TZ)
    cutoff = now.date() if now.time() >= dtime(15,30) else (now - timedelta(days=1)).date()
    path = Path(root)/'data'/'ssi_cache'/'ohlcv'/f'{symbol}.csv'
    start = cutoff - timedelta(days=days)
    if path.is_file():
        old = pd.read_csv(path, encoding='utf-8-sig', usecols=['date'])
        last = pd.to_datetime(old['date'], errors='coerce').max()
        if pd.notna(last):
            start = max(start, last.date() - timedelta(days=15))
    candles = data.market_data.get_ohlc_all(
        symbol=symbol, timeframe=Timeframe.DAY_1,
        from_date=start.strftime('%Y/%m/%d 00:00:00'),
        to_date=cutoff.strftime('%Y/%m/%d 23:59:59'),
        size=1000, ascending=True)
    new = from_ohlc(symbol, candles)
    if new.empty:
        return ('NO_BARS', 0)
    return ('OK', persist(symbol, new, path, cutoff))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('symbol', nargs='?', help='Mã muốn tải, ví dụ FPT, SHS, VGI')
    p.add_argument('--days', type=int, default=900, help='Lịch sử ban đầu (ngày lịch)')
    p.add_argument('--batch', type=int, default=0, help='Lấy theo lô, tối đa 100 mã mỗi lần')
    p.add_argument('--offset', type=int, default=0)
    p.add_argument('--pause', type=float, default=1.0, help='Nghỉ giữa các request để hạn chế rate limit')
    a = p.parse_args()
    if not (220 <= a.days <= 3000): p.error('--days phải trong khoảng 220..3000')
    if not (0 <= a.batch <= 100): p.error('--batch phải trong khoảng 0..100')
    if a.symbol and a.batch: p.error('Chọn mã hoặc --batch, không dùng cả hai')
    if not a.symbol and not a.batch: p.error('Truyền một mã hoặc --batch N')
    symbols = [validate_symbol(a.symbol)] if a.symbol else screener_symbols(include_candidates=False)[a.offset:a.offset+a.batch]
    if not symbols: raise SystemExit('Chưa có mã. Chạy scripts/ssi_sync_universe.py trước.')
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT/'.env', override=False)
    except ImportError: pass
    from ssi_sdk import Auth, Data, Config
    config = Config(client_id=os.environ['SSI_CLIENT_ID'], api_key=os.environ['SSI_API_KEY'], api_secret=os.environ['SSI_API_SECRET'])
    problems = []
    with Auth(config) as auth:
        auth.authenticate()
        with Data(auth) as data:
            for i,s in enumerate(symbols, 1):
                try:
                    status,n = download_with_service(data,s,a.days)
                    print(f'[{i}/{len(symbols)}] {s}: {status}, {n} phiên')
                except Exception as exc:
                    print(f'[{i}/{len(symbols)}] {s}: ERROR {type(exc).__name__}')
                    problems.append(s)
                if i < len(symbols) and a.pause > 0: time.sleep(a.pause)
    print('Thành công:', len(symbols)-len(problems), '| lỗi:', len(problems))
    if problems: print('Mã cần kiểm tra lại:', ', '.join(problems))

if __name__ == '__main__':
    main()
