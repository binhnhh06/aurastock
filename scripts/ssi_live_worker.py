"""SSI FastConnect market data worker (local prototype).

Run from another terminal: python scripts/ssi_live_worker.py
One worker per key. Dynamically subscribes to recently requested symbols
from the two-page Streamlit interface, up to 20 tickers at once.
No trading/order APIs, no OTP. Does not alter historical OHLCV.
"""
from __future__ import annotations

import sys
import csv
import json
import math
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INDEX_CODES = ('VNINDEX', 'VN30', 'HNXINDEX', 'UPCOMINDEX')


def _norm_index(value):
    code = str(value or '').strip().upper()
    return 'UPCOMINDEX' if code in ('HNXUPCOMINDEX', 'UPCOM') else code


from core.ssi_market_live import (
    SNAPSHOT, get_market_symbols, get_credential_config, now_iso,
    read_live_requests, valid_positive, write_snapshot,
)


def _get_index_field(msg, name, server_key):
    """SSI SDK fields may be optional; read msg.raw when attribute is absent.

    Do not guess units or calculate trading value from closing price.
    """
    val = getattr(msg, name, None)
    if val is None:
        raw = getattr(msg, "raw", None)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = {}
        if isinstance(raw, dict):
            for source in (raw, raw.get("data"), raw.get("Content")):
                if isinstance(source, str):
                    try:
                        source = json.loads(source)
                    except ValueError:
                        source = {}
                if isinstance(source, dict):
                    val = source.get(server_key, source.get(name))
                    if val is not None:
                        break
    try:
        number = float(val)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    # Changes can be negative; volumes/values cannot.
    if name not in ("change", "change_percent") and number < 0:
        return None
    return number



def _number(value):
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if math.isfinite(v) else None


def _last_index_close(symbol='VNINDEX'):
    """Read the last SSI EOD index point, without treating turnover as points."""
    code = _norm_index(symbol)
    path = ROOT / 'data' / 'ssi_cache' / 'ohlcv' / (code + '.csv')
    try:
        with path.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        for row in reversed(rows):
            close = _number(row.get('close'))
            if close is not None and close > 0:
                return close
    except (OSError, UnicodeError, csv.Error):
        pass
    return None


def _valid_index_points(value, anchor):
    n = _number(value)
    if n is None or not (30 <= n <= 10000):
        return None
    if anchor is not None and anchor > 0 and not (0.65 <= n / anchor <= 1.35):
        return None
    return n


def _dict_data(message):
    """Use only index payload fields, never any credential fields."""
    for raw in (getattr(message, 'data', None), getattr(message, 'raw', None)):
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                continue
        if not isinstance(raw, dict):
            continue
        for key in ('data', 'Content'):
            item = raw.get(key)
            if isinstance(item, str):
                try:
                    item = json.loads(item)
                except ValueError:
                    continue
            if isinstance(item, dict):
                return item
        return raw
    return {}


def _find_index_points(message, *, anchor, summary=False):
    """Do not silently divide large values that may be turnover, not points."""
    raw = _dict_data(message)
    # Explicit index point fields take precedence over ambiguous one-letter keys.
    for key in ('IndexValue', 'indexValue', 'index_value', 'IndexVal',
                'indexVal', 'index_val', 'IndexPoint', 'indexPoint'):
        val = _valid_index_points(raw.get(key), anchor)
        if val is not None:
            return val
    # Documented SDK .value is allowed only if its magnitude is sensible.
    val = _valid_index_points(getattr(message, 'value', None), anchor)
    if val is not None:
        return val
    # Documented index tick server abbreviation 'v'. Validate units before use.
    val = _valid_index_points(raw.get('v'), anchor)
    return val


def _summary_field(raw, *names):
    for key in names:
        if key in raw:
            n = _number(raw[key])
            if n is not None and n >= 0:
                return n
    return None


def main():
    from ssi_sdk import Auth, Stream
    from ssi_sdk.models import TradeMessage, IndexTickMessage
    try:
        from ssi_sdk.models import IndexSummaryMessage
    except ImportError:
        IndexSummaryMessage = ()  # Older SSI SDK: leave EOD fallback enabled.

    anchors = {code: _last_index_close(code) for code in INDEX_CODES}

    valid = set(get_market_symbols())
    if not valid:
        raise SystemExit('Danh muc SSI trong market_symbols.csv chua san sang.')

    lock = threading.Lock()
    last_write = [0.0]
    snapshot_failures = [0]
    state = {
        'source': 'SSI FastConnect V3 market WebSocket', 'connection': 'STARTING',
        'worker_at': now_iso(), 'quotes': {}, 'indices': {}, 'subscribed': [],
    }

    def save(force=False):
        if not force and time.monotonic() - last_write[0] < 0.8:
            return
        with lock:
            state['worker_at'] = now_iso()
            try:
                write_snapshot(state, SNAPSHOT)
            except PermissionError as exc:
                # A transient Windows file lock must not terminate the SSI
                # connection. Later ticks/heartbeats will retry the snapshot.
                snapshot_failures[0] += 1
                if snapshot_failures[0] == 1 or snapshot_failures[0] % 20 == 0:
                    print(f'SNAPSHOT_LOCKED: WinError {getattr(exc, "winerror", "?")} '
                          '- khong ghi duoc live_market.json; se thu lai. '
                          'Kiem tra file dang mo trong editor/worker khac.', flush=True)
                last_write[0] = time.monotonic()
                return False
            if snapshot_failures[0]:
                print('SNAPSHOT_RECOVERED: ghi realtime da phuc hoi.', flush=True)
                snapshot_failures[0] = 0
            last_write[0] = time.monotonic()
            return True

    def on_data(msg):
        # All price fields kept in the units provided by the SSI SDK.
        # UI must compare against EOD before trusting as the same VND unit.
        if isinstance(msg, TradeMessage):
            symbol = str(getattr(msg, 'symbol', '')).upper().strip()
            price = valid_positive(getattr(msg, 'price', None))
            if symbol in valid and price is not None:
                with lock:
                    state['quotes'][symbol] = {
                        'price': price, 'quantity': getattr(msg, 'quantity', None),
                        'trading_time': str(getattr(msg, 'trading_time', '') or ''),
                        'received_at': now_iso(),
                    }
                save()
        elif isinstance(msg, IndexTickMessage):
            symbol = _norm_index(getattr(msg, 'symbol', ''))
            if symbol not in INDEX_CODES:
                return
            price = _find_index_points(msg, anchor=anchors.get(symbol))
            if price is None:
                with lock:
                    state['index_diagnostic'] = {
                        'status': 'INVALID_INDEX_VALUE',
                        'symbol': symbol,
                        'received_at': now_iso(),
                        'reported_value': _number(getattr(msg, 'value', None)),
                        'available_fields': sorted(map(str, _dict_data(msg).keys()))[:35],
                    }
                save()
                return
            fields = {
                'price': price, 'received_at': now_iso(),
                'trading_time': str(getattr(msg, 'trading_time', '') or ''),
                'source_type': 'INDEX_TICK',
            }
            for name, server_key in (
                ('change', 'c'), ('change_percent', 'cr'),
                ('total_match_quantity', 'tmq'), ('total_match_value', 'tmv'),
                ('total_quantity', 'tq'), ('total_value', 'tv'),
                ('advances', 'adv'), ('declines', 'dec'), ('nochanges', 'nc'),
            ):
                metric = _get_index_field(msg, name, server_key)
                if metric is not None:
                    fields[name] = metric
            with lock:
                state['indices'][symbol] = fields
                state.pop('index_diagnostic', None)
            save()
        elif isinstance(msg, IndexSummaryMessage):
            raw = _dict_data(msg)
            symbol = _norm_index(getattr(msg, 'index', '') or raw.get('s') or raw.get('Indexcode') or raw.get('IndexID'))
            if symbol not in INDEX_CODES:
                return
            price = _find_index_points(msg, anchor=anchors.get(symbol), summary=True)
            if price is None:
                with lock:
                    state['index_summary_diagnostic'] = {
                        'status': 'SUMMARY_NO_VALID_PRICE',
                        'symbol': symbol,
                        'received_at': now_iso(),
                        'available_fields': sorted(map(str, raw.keys()))[:35],
                    }
                save()
                return
            fields = {'price': price, 'received_at': now_iso(),
                      'trading_time': str(raw.get('t') or raw.get('Time') or raw.get('TradingTime') or ''),
                      'source_type': 'INDEX_SUMMARY'}
            for field, candidates in {
                'change': ('c', 'Change', 'change'),
                'change_percent': ('cr', 'RatioChange', 'ChangePercent', 'changePercent'),
                'total_match_quantity': ('tmq', 'Totalmatchvol', 'TotalMatchQuantity'),
                'total_match_value': ('tmv', 'Totalmatchval', 'TotalMatchValue'),
                'total_quantity': ('tq', 'Totalvol', 'AllQty', 'TotalQtty', 'TotalQuantity'),
                'total_value': ('tv', 'Totalval', 'AllValue', 'TotalValue'),
                'advances': ('adv', 'Advances', 'advances', 'TotalAdvanceStock'),
                'declines': ('dec', 'Declines', 'declines', 'TotalDeclineStock'),
                'nochanges': ('nc', 'Nochanges', 'nochanges', 'TotalSteadyStock'),
            }.items():
                # Change can be negative: preserve sign.
                if field in ('change', 'change_percent'):
                    val = next((_number(raw.get(key)) for key in candidates if _number(raw.get(key)) is not None), None)
                else:
                    val = _summary_field(raw, *candidates)
                if val is not None:
                    fields[field] = val
            with lock:
                state['indices'][symbol] = fields
                state.pop('index_summary_diagnostic', None)
            save()

    def on_connection(event):
        name = str(getattr(event, 'state', event)).upper()
        with lock:
            if 'DISCONNECTED' in name or 'FAILED' in name:
                state['connection'] = 'DISCONNECTED'
            elif 'CONNECTED' in name:
                state['connection'] = 'CONNECTED'
            else:
                state['connection'] = name
        save(force=True)

    print('SSI live worker | KHONG chay song song worker khac dung cung API key.')
    print('Mo Streamlit, chon mot ma de worker dang ky. Ngoai phien khong co tick moi.')
    save(force=True)
    try:
        with Auth(get_credential_config()) as auth:
            auth.authenticate()
            with Stream(auth) as stream:
                ws = stream.streaming
                ws.on_data = on_data
                # SSI SDK dispatches IndexSummaryMessage through a dedicated
                # callback; subscribing alone does not route it into on_data.
                if hasattr(ws, 'on_index_summary'):
                    ws.on_index_summary = on_data
                ws.on_connection = on_connection
                ws.connect()
                ws.subscribe_index_trade(list(INDEX_CODES))
                if hasattr(ws, 'subscribe_index_summary'):
                    try:
                        ws.subscribe_index_summary(list(INDEX_CODES))
                        print('INDEX_SUMMARY:', ', '.join(INDEX_CODES))
                    except (TypeError, ValueError, AttributeError) as exc:
                        print('INDEX_SUMMARY: not available:', type(exc).__name__)
                subscribed = set()
                with lock:
                    state['connection'] = 'CONNECTED'
                save(force=True)
                while True:
                    requested = set(read_live_requests()) & valid
                    added = sorted(requested - subscribed)
                    removed = sorted(subscribed - requested)
                    if added:
                        ws.subscribe_symbol_trade(added)
                        print('SUBSCRIBE:', ', '.join(added))
                    if removed:
                        ws.unsubscribe_symbol_trade(removed)
                        print('UNSUBSCRIBE:', ', '.join(removed))
                    subscribed = requested
                    with lock:
                        state['subscribed'] = sorted(subscribed)
                    save(force=True)
                    ws.wait(timeout_ms=5000)
    except KeyboardInterrupt:
        print('STOPPED')
    except Exception as exc:
        with lock:
            state['error_type'] = type(exc).__name__
            state['connection'] = 'ERROR'
        save(force=True)
        print('LIVE_WORKER_ERROR:', type(exc).__name__)
        raise
    finally:
        with lock:
            state['connection'] = 'DISCONNECTED'
        save(force=True)


if __name__ == '__main__':
    main()
