"""AURA V9.7: best-effort SSI realtime *display*; analytics remain EOD.

One shared WebSocket per Streamlit Python process, subscribers are short-lived.
No trading API; no keys in repository/logs, and no claim of live prices unless
both the event timestamp and connection freshness can be verified.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import math
import os
import re
import threading
import time
from zoneinfo import ZoneInfo

VN = ZoneInfo('Asia/Ho_Chi_Minh')
MAX_SUBSCRIPTIONS = 20
WATCH_TTL = 120.0
LIVE_TTL = 120.0
IDLE_STOP = 900.0
TICKER = re.compile(r'[A-Z0-9]{2,10}\Z')


def session_open(now=None):
    """Indicative cash-market session, not a holiday calendar."""
    now = (now or datetime.now(timezone.utc)).astimezone(VN)
    m = now.hour * 60 + now.minute
    return now.weekday() < 5 and ((540 <= m <= 690) or (780 <= m <= 900))


def parse_exchange_time(value, received_at):
    """Parse SDK trading_time; do not treat an old/replayed trade as LIVE."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=VN) if value.tzinfo is None else value.astimezone(VN)
    s = str(value or '').strip()
    if not s:
        return None
    # ISO timestamps (including explicit offsets).
    try:
        d = datetime.fromisoformat(s.replace('Z', '+00:00'))
        return (d if d.tzinfo else d.replace(tzinfo=VN)).astimezone(VN)
    except ValueError:
        pass
    for fmt in ('%Y/%m/%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y%m%d %H:%M:%S',
                '%Y%m%d%H%M%S', '%H:%M:%S', '%H:%M'):
        try:
            d = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if fmt.startswith('%H:'):
            day = received_at.astimezone(VN).date()
            d = datetime.combine(day, d.time())
        return d.replace(tzinfo=VN)
    return None


def normalize_price(raw, eod_vnd):
    """Accept SSI tick in either VND or 1,000 VND, with a plausibility guard."""
    try:
        v, eod = float(raw), float(eod_vnd)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (math.isfinite(v) and math.isfinite(eod) and v > 0 and eod > 0):
        return None
    for candidate in (v, v * 1000):
        if 0.5 <= candidate / eod <= 1.5:
            return candidate
    return None


class LiveFeed:
    def __init__(self, credentials):
        self._credentials = credentials
        self._guard = threading.RLock()
        self._wanted = OrderedDict()
        self._ticks = {}
        self._connected = False
        self._worker = None
        self._last_watch = time.monotonic()
        self._error_type = None

    def _connection(self, event):
        state = str(getattr(event, 'state', event)).upper()
        with self._guard:
            self._connected = ('CONNECTED' in state and 'DISCONNECTED' not in state
                               and 'FAILED' not in state)

    def _on_data(self, msg):
        # SDK invokes one callback for all market message types. Only trade ticks
        # are eligible to replace the displayed last-matched price.
        if type(msg).__name__ != 'TradeMessage':
            return
        symbol = str(getattr(msg, 'symbol', '')).strip().upper()
        if not TICKER.fullmatch(symbol):
            return
        try:
            price = float(getattr(msg, 'price', 0))
        except (ValueError, TypeError, OverflowError):
            return
        if not (math.isfinite(price) and price > 0):
            return
        now = datetime.now(timezone.utc)
        exchanged = parse_exchange_time(getattr(msg, 'trading_time', None), now)
        with self._guard:
            if symbol in self._wanted:
                self._ticks[symbol] = {
                    'price': price,
                    'received_at': now,
                    'exchange_at': exchanged,
                    'quantity': getattr(msg, 'quantity', None),
                }

    def _start(self):
        with self._guard:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._run, name='AURA-SSI-LIVE', daemon=True)
            self._worker.start()

    def watch(self, symbol, now=None):
        symbol = str(symbol).strip().upper()
        if not TICKER.fullmatch(symbol):
            return {'status': 'INVALID_SYMBOL', 'price': None}
        now = now or datetime.now(timezone.utc)
        if session_open(now):
            with self._guard:
                self._last_watch = time.monotonic()
                self._wanted.pop(symbol, None)
                self._wanted[symbol] = time.monotonic()
                while len(self._wanted) > MAX_SUBSCRIPTIONS:
                    old, _ = self._wanted.popitem(last=False)
                    self._ticks.pop(old, None)
            self._start()
        with self._guard:
            tick = dict(self._ticks.get(symbol, {}))
            connected = self._connected
            error_type = self._error_type
        if not tick:
            return {'status': 'NO_TICK' if session_open(now) else 'CLOSED',
                    'price': None, 'connection': 'CONNECTED' if connected else (error_type or 'WAITING')}
        exchange_at, received_at = tick.get('exchange_at'), tick.get('received_at')
        age_received = (now - received_at).total_seconds() if received_at else float('inf')
        age_exchange = (now - exchange_at.astimezone(timezone.utc)).total_seconds() if exchange_at else float('inf')
        valid_date = (exchange_at is not None and exchange_at.astimezone(VN).date() == now.astimezone(VN).date())
        fresh = (connected and session_open(now) and valid_date
                 and 0 <= age_received <= LIVE_TTL and -10 <= age_exchange <= LIVE_TTL)
        status = 'LIVE' if fresh else ('LAST' if valid_date else 'OLD')
        return {'status': status, 'price': tick['price'], 'received_at': received_at,
                'exchange_at': exchange_at, 'quantity': tick.get('quantity'),
                'connection': 'CONNECTED' if connected else (error_type or 'OFFLINE')}

    def _run(self):
        # WebSocket is owned by exactly one daemon thread for this Streamlit process.
        # Auto-reconnect is enabled by default in SSI SDK.
        client_id, api_key, api_secret = self._credentials
        backoff = 5
        while True:
            with self._guard:
                if time.monotonic() - self._last_watch > IDLE_STOP:
                    self._connected = False
                    return
            try:
                from ssi_sdk import Auth, Stream, Config
                config = Config(client_id=client_id, api_key=api_key, api_secret=api_secret)
                with Auth(config) as auth:
                    auth.authenticate()  # DATA market stream: no OTP for market-only subscription
                    with Stream(auth) as stream:
                        ws = stream.streaming
                        ws.on_data = self._on_data
                        ws.on_connection = self._connection
                        ws.connect()
                        with self._guard:
                            self._connected = True
                            self._error_type = None
                        subscribed = set()
                        backoff = 5
                        while True:
                            t = time.monotonic()
                            with self._guard:
                                self._wanted = OrderedDict((s, ts) for s, ts in self._wanted.items()
                                                           if t - ts < WATCH_TTL)
                                desired = set(self._wanted)
                                idle = t - self._last_watch > IDLE_STOP
                            if idle:
                                with self._guard:
                                    self._connected = False
                                return
                            removed, added = sorted(subscribed - desired), sorted(desired - subscribed)
                            if removed:
                                ws.unsubscribe_symbol_trade(removed)
                            if added:
                                ws.subscribe_symbol_trade(added)
                            subscribed = desired
                            ws.wait(timeout_ms=2000)
            except Exception as exc:
                # Never write exception messages; SDK may include a sensitive URL.
                with self._guard:
                    self._connected = False
                    self._error_type = type(exc).__name__
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)


def _setting(name):
    try:
        import streamlit as st
        v = st.secrets.get(name)
        if v is not None:
            return str(v).strip()
    except (ImportError, FileNotFoundError, KeyError, RuntimeError, AttributeError):
        pass
    return os.environ.get(name, '').strip()


def get_feed():
    """Streamlit process-wide singleton; only starts if explicitly enabled."""
    if _setting('AURA_LIVE_ENABLED').lower() not in ('1', 'true', 'yes', 'on'):
        return None
    try:
        import streamlit as st
        return _cached_feed()
    except (ImportError, RuntimeError, FileNotFoundError, KeyError, AttributeError):
        return None


def _credentials():
    names = ('SSI_CLIENT_ID', 'SSI_API_KEY', 'SSI_API_SECRET')
    values = tuple(_setting(n) for n in names)
    return values if all(values) else None


def _create_feed():
    creds = _credentials()
    return LiveFeed(creds) if creds else None


try:
    import streamlit as _st
    _cached_feed = _st.cache_resource(show_spinner=False)(_create_feed)
except ImportError:
    def _cached_feed():
        return _create_feed()


def display_live_quote(symbol, eod_vnd, eod_date=None, *, now=None, feed=None):
    """Return card fields on usable SSI trades; otherwise a safe EOD hint.

    This function only decides what PRICE to display; it must never modify
    indicators, charts, stored transactions or any historical EOD CSV.
    """
    now = now or datetime.now(timezone.utc)
    feed = feed if feed is not None else get_feed()
    if feed is None:
        return {'price': None, 'detail': 'Giá EOD · Chưa bật/thiếu cấu hình SSI WebSocket'}
    tick = feed.watch(symbol, now)
    status = tick.get('status')
    if status == 'CLOSED':
        return {'price': None, 'detail': 'Ngoài giờ giao dịch · Giá đóng cửa EOD'}
    if status in ('NO_TICK', 'INVALID_SYMBOL'):
        return {'price': None, 'detail': 'Chờ giá khớp SSI WebSocket · ' + str(tick.get('connection', 'WAITING'))[:35]}
    if status not in ('LIVE', 'LAST'):
        return {'price': None, 'detail': 'Giá EOD · Tick SSI không thuộc phiên hiện tại'}
    price = normalize_price(tick.get('price'), eod_vnd)
    exchange_at = tick.get('exchange_at')
    if price is None or exchange_at is None:
        return {'price': None, 'detail': 'Giá EOD · Tick SSI chưa xác minh được đơn vị/thời điểm'}
    if eod_date:
        try:
            if exchange_at.date() < datetime.fromisoformat(str(eod_date)[:10]).date():
                return {'price': None, 'detail': 'Giá EOD · Tick SSI cũ hơn dữ liệu phân tích'}
        except (ValueError, TypeError):
            pass
    label = 'GIÁ REALTIME SSI' if status == 'LIVE' else 'GIÁ KHỚP GẦN NHẤT SSI'
    displayed_time = exchange_at.astimezone(VN).strftime('%d/%m/%Y %H:%M:%S')
    suffix = ' · Đang trong phiên' if status == 'LIVE' else ' · Chưa xác nhận realtime'
    return {'price': price, 'status': 'LIVE_TICK' if status == 'LIVE' else 'LAST_TICK',
            'label': label, 'detail': 'Khớp lúc ' + displayed_time + suffix}
