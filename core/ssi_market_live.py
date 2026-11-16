"""SSI websocket market snapshot, separate from EOD pricing and backtest inputs.

No trading APIs. No credentials persisted. One local streaming process owns Auth.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / 'data' / 'ssi_cache' / 'live_market.json'
VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
MAX_TICK_AGE_SECONDS = 120
LOCK = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def valid_positive(value):
    try:
        v = float(value)
        return v if math.isfinite(v) and v > 0 else None
    except (TypeError, ValueError):
        return None


def _read_file(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


LOCAL_FRESH_SECONDS = 60


def _is_fresh(snapshot, clock=None):
    beat = parse_time(snapshot.get('worker_at')) if snapshot else None
    if beat is None:
        return False
    age = ((clock or datetime.now(timezone.utc)) - beat).total_seconds()
    return 0 <= age <= LOCAL_FRESH_SECONDS


def read_snapshot(path=SNAPSHOT, *, remote=None):
    """Snapshot giá realtime (chỉ hiển thị).

    Ưu tiên file do worker cùng máy ghi; nếu không có hoặc đã cũ (bản online trên
    Streamlit Cloud) thì đọc bản worker đẩy lên R2. Lỗi → {} và giao diện quay về EOD.
    """
    local = _read_file(path)
    if Path(path) != SNAPSHOT or _is_fresh(local):
        return local
    try:
        if remote is None:
            from core.aura_live_r2 import fetch_snapshot as remote
        cloud = remote()
    except (ImportError, OSError, ValueError, RuntimeError):
        cloud = {}
    if isinstance(cloud, dict) and cloud and (not local or _is_fresh(cloud) or not _is_fresh(local)):
        newer_cloud = (parse_time(cloud.get('worker_at')) or datetime.min.replace(tzinfo=timezone.utc)) >= \
                      (parse_time(local.get('worker_at')) or datetime.min.replace(tzinfo=timezone.utc))
        if newer_cloud:
            return cloud
    return local


def write_snapshot(data, path=SNAPSHOT):
    """Crash-safe write; protects Streamlit readers against partial JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix='.live_', suffix='.json', dir=path.parent)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, allow_nan=False)
        # Windows may temporarily deny replacement while Streamlit, an editor,
        # or a security scanner has the destination open. Retry the *same*
        # complete temporary JSON; never write a partial snapshot in place.
        for attempt in range(12):
            try:
                os.replace(tmp, path)
                tmp = None
                return
            except PermissionError:
                if attempt == 11:
                    raise
                time.sleep(min(0.04 * (attempt + 1), 0.25))
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def market_session(vn_now=None):
    """Indicative HOSE session, does not include holidays or exchange closures."""
    d = vn_now or datetime.now(VN_TZ)
    if d.weekday() >= 5:
        return False
    minute = d.hour * 60 + d.minute
    return (9 * 60 <= minute <= 11 * 60 + 30) or (13 * 60 <= minute <= 14 * 60 + 45)


def quote_view(snapshot, symbol, clock=None):
    """Derive display status. Connected != receiving trade ticks."""
    clock = clock or datetime.now(timezone.utc)
    symbol = str(symbol).strip().upper()
    is_index = symbol in ('VNINDEX', 'VN30')
    record = snapshot.get('indices', {}).get(symbol) if is_index else snapshot.get('quotes', {}).get(symbol)
    if not isinstance(record, dict):
        return {'symbol': symbol, 'price': None, 'status': 'NO_TICK', 'received_at': None}
    value = valid_positive(record.get('price'))
    received = parse_time(record.get('received_at'))
    age = (clock - received).total_seconds() if received else float('inf')
    heartbeat = parse_time(snapshot.get('worker_at'))
    heartbeat_age = (clock - heartbeat).total_seconds() if heartbeat else float('inf')
    online = snapshot.get('connection') == 'CONNECTED' and 0 <= heartbeat_age <= 30
    status = ('LIVE_TICK' if online and 0 <= age <= MAX_TICK_AGE_SECONDS and market_session(clock.astimezone(VN_TZ))
              else 'LAST_TICK')
    return {'symbol': symbol, 'price': value, 'received_at': received,
            'age_s': max(0, age) if math.isfinite(age) else None, 'status': status,
            'quantity': record.get('quantity'), 'change': record.get('change'),
            'change_percent': record.get('change_percent')}


def date_label(dt):
    if dt is None:
        return 'Không có thời điểm giao dịch'
    return dt.astimezone(VN_TZ).strftime('%d/%m/%Y %H:%M:%S')


REQUESTS = ROOT / 'data' / 'ssi_cache' / 'live_requests.json'
REQUEST_TTL_SECONDS = 900
MAX_WATCHED = 20


def get_market_symbols(root=ROOT):
    """Permitted symbols from the downloaded SSI catalogue, never fixed to VN30."""
    import pandas as pd
    catalog = Path(root) / 'data' / 'ssi_cache' / 'market_symbols.csv'
    if not catalog.is_file():
        return []
    df = pd.read_csv(catalog, encoding='utf-8-sig', usecols=['symbol', 'asset_class'])
    df = df.loc[df['asset_class'].isin(['EQUITY', 'EQUITY_CANDIDATE'])]
    return sorted(set(df['symbol'].dropna().astype(str).str.upper().str.strip()) - {''})


def _active_requests(payload, now):
    if not isinstance(payload, dict):
        return {}
    allowed = {}
    for symbol, ts in payload.items():
        symbol = str(symbol).upper().strip()
        moment = parse_time(ts)
        if symbol.isalnum() and 2 <= len(symbol) <= 10 and moment:
            age = (now - moment).total_seconds()
            if 0 <= age <= REQUEST_TTL_SECONDS:
                allowed[symbol] = moment.isoformat()
    return dict(sorted(allowed.items(), key=lambda kv: kv[1], reverse=True)[:MAX_WATCHED])


def read_live_requests(path=REQUESTS, *, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        payload = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        return {}
    return _active_requests(payload, now)


def request_live_symbol(symbol, path=REQUESTS, *, now=None):
    """Local prototype: a shared file of recently viewed symbols, max 20.

    For multi-user Streamlit Cloud deployment replace this file with a shared
    request store/queue. Never store SSI credentials here.
    """
    now = now or datetime.now(timezone.utc)
    symbol = str(symbol).strip().upper()
    if symbol not in get_market_symbols():
        return False
    with LOCK:
        requests = read_live_requests(path, now=now)
        requests[symbol] = now.isoformat()
        requests = _active_requests(requests, now)
        write_snapshot(requests, path)
    return True


def get_credential_config():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
    except ImportError:
        pass
    keys = ('SSI_CLIENT_ID', 'SSI_API_KEY', 'SSI_API_SECRET')
    missing = [key for key in keys if not os.environ.get(key, '').strip()]
    if missing:
        raise RuntimeError('Thiếu cấu hình SSI: ' + ', '.join(missing))
    from ssi_sdk import Config
    return Config(client_id=os.environ['SSI_CLIENT_ID'],
                  api_key=os.environ['SSI_API_KEY'], api_secret=os.environ['SSI_API_SECRET'])


def base_watchlist(valid, root=ROOT, *, limit=None, extra=None):
    """Danh sách mã worker luôn theo dõi để bản online có giá realtime.

    Gồm: AURA_LIVE_SYMBOLS (biến môi trường, phân tách dấu phẩy) → VN30 → các mã
    thanh khoản cao nhất theo GTGD 20 phiên EOD trong cache. Giới hạn AURA_LIVE_MAX (mặc định 60).
    Chỉ nhận mã có trong danh mục SSI (`valid`).
    """
    import pandas as pd
    if limit is None:
        try:
            limit = int(os.getenv('AURA_LIVE_MAX', '60'))
        except ValueError:
            limit = 60
    limit = max(0, min(limit, 300))
    valid = {str(v).upper() for v in valid}
    picked = []

    def add(symbols):
        for s in symbols:
            s = str(s).strip().upper()
            if s in valid and s not in picked and len(picked) < limit:
                picked.append(s)

    add((extra if extra is not None else os.getenv('AURA_LIVE_SYMBOLS', '')).split(','))
    vn30 = Path(root) / 'data' / 'ssi_cache' / 'vn30_symbols.csv'
    if vn30.is_file():
        try:
            add(pd.read_csv(vn30, encoding='utf-8-sig')['symbol'].dropna())
        except (OSError, ValueError, KeyError):
            pass
    if len(picked) < limit:
        liquidity = []
        for f in (Path(root) / 'data' / 'ssi_cache' / 'ohlcv').glob('*.csv'):
            sym = f.stem.upper()
            if sym not in valid or sym in picked:
                continue
            try:
                d = pd.read_csv(f, usecols=['close', 'volume']).tail(20)
                value = float((pd.to_numeric(d['close'], errors='coerce')
                               * pd.to_numeric(d['volume'], errors='coerce')).mean())
            except (OSError, ValueError, KeyError):
                continue
            if math.isfinite(value) and value > 0:
                liquidity.append((value, sym))
        add(sym for _, sym in sorted(liquidity, reverse=True))
    return picked
