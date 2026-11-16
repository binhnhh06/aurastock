"""AURA V8.3.2: independent SSI listed-share reference (not market cap).

SSIs listed_shares is NOT shares_outstanding; never populate official market-cap
column, size bands, valuations or historical backtests from this observation.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

REL = Path('data/ssi_cache/reference/ssi_listed_shares.csv')
OUT_VALUE = 'Giá trị CP niêm yết (tỷ VND)'
OUT_SHARES = 'CP niêm yết (triệu)'
OUT_SOURCE = 'Nguồn CP niêm yết'
OUT_STATUS = 'Trạng thái CP niêm yết'
MAX_PRICE_AGE = 7
MAX_POST_EOD = 4
MAX_PRE_EOD = 90  # snapshot trước EOD là thông tin đã biết tại EOD; CP niêm yết ít thay đổi


def _now_vietnam():
    return pd.Timestamp(datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date())


CATALOGUE = Path('data/ssi_cache/market_symbols.csv')


def _from_catalogue(root: Path, cols) -> pd.DataFrame:
    """Dự phòng cho bản online: danh mục SSI (market_symbols.csv, có trong gói R2)
    mang sẵn listed_shares + observed_at từ API Securities."""
    f = Path(root) / CATALOGUE
    try:
        d = pd.read_csv(f, dtype=str, encoding='utf-8-sig', keep_default_na=False)
    except (OSError, ValueError, UnicodeError, pd.errors.ParserError):
        return pd.DataFrame(columns=cols)
    if not {'symbol', 'listed_shares', 'observed_at'}.issubset(d.columns):
        return pd.DataFrame(columns=cols)
    d = d.rename(columns={'board': 'exchange'})
    d['source'] = 'SSI FastConnect V3 · Securities'
    if 'exchange' not in d:
        d['exchange'] = ''
    return d[list(cols)]


_SSI_CACHE = {'at': 0.0, 'data': None}
SSI_TTL_SECONDS = 6 * 3600


def _from_ssi_api(cols, *, fetch=None, clock=None) -> pd.DataFrame:
    """Bản online: lấy số CP niêm yết trực tiếp từ SSI Securities (3 lệnh gọi, cache 6 giờ).

    Chỉ chạy khi có khóa SSI trong Streamlit Secrets/biến môi trường. Lỗi → bảng rỗng.
    """
    import time
    clock = clock or time.monotonic
    if _SSI_CACHE['data'] is not None and clock() - _SSI_CACHE['at'] < SSI_TTL_SECONDS:
        return _SSI_CACHE['data']
    out = pd.DataFrame(columns=cols)
    try:
        if fetch is None:
            fetch = _fetch_listed_from_ssi
        rows = fetch()
        if rows:
            out = pd.DataFrame(rows, columns=list(cols))
    except Exception as exc:  # noqa: BLE001 - không có khóa/mất mạng: để trống, không đoán
        from core.aura_log import get_logger
        get_logger('aura.listed').info('Không lấy được CP niêm yết từ SSI: %s', type(exc).__name__)
    _SSI_CACHE.update(at=clock(), data=out)
    return out


def _fetch_listed_from_ssi():
    from core.aura_ssi_realtime_v97 import _credentials
    creds = _credentials()
    if not creds:
        return []
    from ssi_sdk import Auth, Config, Data
    from ssi_sdk.enums import Board
    from core.aura_log import SSI_REST_LIMITER
    observed = _now_vietnam().date().isoformat()
    rows = []
    with Auth(Config(client_id=creds[0], api_key=creds[1], api_secret=creds[2])) as auth:
        auth.authenticate()
        with Data(auth) as data:
            for board in (Board.HOSE, Board.HNX, Board.UPCOM):
                SSI_REST_LIMITER.wait()
                name = str(getattr(board, 'value', board)).split('.')[-1].upper()
                for it in data.market_data.get_securities_info_by_board(board) or []:
                    sym = str(getattr(it, 'symbol', '') or '').strip().upper()
                    shares = getattr(it, 'listed_shares', None)
                    if sym and shares:
                        rows.append({'symbol': sym, 'exchange': name, 'observed_at': observed,
                                     'source': 'SSI FastConnect V3 · Securities', 'listed_shares': str(shares)})
    return rows


def load_listed_reference(root: Path) -> pd.DataFrame:
    """Read versioned SSI snapshots; leave invalid rows out; read-only.

    Thứ tự: file tham chiếu → danh mục SSI có cột listed_shares → gọi SSI trực tiếp (bản online).
    """
    f = Path(root) / REL
    cols = ('symbol', 'exchange', 'observed_at', 'source', 'listed_shares')
    if not f.is_file():
        cat = _from_catalogue(root, cols)
        if not cat.empty and pd.to_numeric(cat['listed_shares'], errors='coerce').gt(0).any():
            return cat
        return _from_ssi_api(cols)
    try:
        d = pd.read_csv(f, dtype=str, encoding='utf-8-sig', keep_default_na=False)
    except (OSError, ValueError, UnicodeError, pd.errors.ParserError):
        return pd.DataFrame(columns=cols)
    if not set(cols).issubset(d.columns):
        return pd.DataFrame(columns=cols)
    return d


def enrich_listed_equity(table: pd.DataFrame, root: Path, *, today=None) -> pd.DataFrame:
    """Attach display-only listed equity value for very recent EOD dates.

    Does not modify the existing capitalisation and ranking fields.
    A snapshot obtained after EOD is a contemporary estimate, NEVER a PIT fact.
    """
    res = table.copy()
    res[OUT_VALUE] = float('nan')
    res[OUT_SHARES] = float('nan')
    res[OUT_SOURCE] = ''
    res[OUT_STATUS] = 'Chưa có tham chiếu SSI'
    needed = {'Mã', 'Giá (VND)', 'Ngày dữ liệu'}
    if not needed.issubset(res.columns):
        return res
    ref = load_listed_reference(root)
    if ref.empty:
        return res
    now = pd.Timestamp(today).normalize() if today is not None else _now_vietnam()
    ref = ref.copy()
    ref['symbol'] = ref['symbol'].astype(str).str.upper().str.strip()
    ref['_day'] = pd.to_datetime(ref['observed_at'], errors='coerce').dt.normalize()
    ref['_shares'] = pd.to_numeric(ref['listed_shares'], errors='coerce')
    ref['source'] = ref['source'].astype(str).str.strip()
    ref = ref.loc[(ref['_shares'] > 0) & (ref['_shares'] < 1e13) &
                  ref['_day'].notna() & (ref['_day'] <= now) &
                  ref['source'].str.contains('SSI', case=False, regex=False)].copy()
    if ref.empty:
        return res
    # Last known retrieved snapshot per symbol, not falsely effective on an older date.
    ref = ref.sort_values('_day').drop_duplicates('symbol', keep='last').set_index('symbol')
    sym = res['Mã'].astype(str).str.upper().str.strip()
    snap = pd.to_datetime(sym.map(ref['_day']), errors='coerce')
    shares = pd.to_numeric(sym.map(ref['_shares']), errors='coerce')
    source = sym.map(ref['source']).fillna('')
    eod = pd.to_datetime(res['Ngày dữ liệu'], errors='coerce').dt.normalize()
    price = pd.to_numeric(res['Giá (VND)'], errors='coerce')
    offset = (snap-eod).dt.days
    age = (now-eod).dt.days
    eligible = (shares.gt(0) & price.gt(0) & offset.between(-MAX_PRE_EOD, MAX_POST_EOD) &
                age.between(0, MAX_PRICE_AGE))
    if eligible.any():
        res.loc[eligible, OUT_VALUE] = (shares.loc[eligible] * price.loc[eligible] / 1e9)
        res.loc[eligible, OUT_SHARES] = shares.loc[eligible] / 1e6
        res.loc[eligible, OUT_SOURCE] = (source.loc[eligible] + ' · quan sát ' +
                                         snap.loc[eligible].dt.strftime('%Y-%m-%d'))
        res.loc[eligible, OUT_STATUS] = 'Ước tính CP niêm yết · không phải vốn hóa'
        # Khi chưa có vốn hóa từ nguồn CP lưu hành, xếp nhóm theo giá trị CP niêm yết
        # và ghi rõ "ước tính" (CP niêm yết có thể khác CP lưu hành do cổ phiếu quỹ).
        if 'Nhóm vốn hóa' in res.columns:
            missing = eligible & res['Nhóm vốn hóa'].astype(str).isin(['Chưa có dữ liệu', 'Chưa có nguồn', '', 'nan'])
            value = res.loc[missing, OUT_VALUE]
            res.loc[missing, 'Nhóm vốn hóa'] = value.map(
                lambda v: 'Large-cap (ước tính)' if v >= 10000 else
                'Mid-cap (ước tính)' if v >= 1000 else 'Small-cap (ước tính)')
    return res
