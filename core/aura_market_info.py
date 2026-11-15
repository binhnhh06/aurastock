"""AURA market facts: market capitalization only from dated, sourced observations.

Optional local file: data/fundamentals/processed/market_cap_reference.csv
Required: symbol, as_of, source, and market_cap_vnd OR shares_outstanding.
The columns have explicitly stated units (VND and actual shares, not million shares).
"""
from __future__ import annotations
import math
from pathlib import Path
import pandas as pd

CAP_FILE = Path('data/fundamentals/processed/market_cap_reference.csv')
LARGE_BILLIONS = 10000.0
MID_BILLIONS = 1000.0


def _num(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def cap_band(billions):
    n = _num(billions)
    if n is None:
        return 'Chưa có dữ liệu'
    if n >= LARGE_BILLIONS:
        return 'Large-cap · AURA'
    if n >= MID_BILLIONS:
        return 'Mid-cap · AURA'
    return 'Small-cap · AURA'


def load_market_cap_reference(root: Path) -> pd.DataFrame:
    """Read optional source-backed CSV; never infer capital from EPS or listed shares.

    Output is one most recently dated row per symbol. Older than 1 year is rejected.
    """
    path = Path(root) / CAP_FILE
    fields = ['symbol','as_of','source','market_cap_vnd','shares_outstanding']
    if not path.is_file():
        return pd.DataFrame(columns=fields)
    try:
        data = pd.read_csv(path, encoding='utf-8-sig', dtype={'symbol':str,'source':str})
    except (OSError, ValueError, pd.errors.ParserError, UnicodeError):
        return pd.DataFrame(columns=fields)
    if not set(['symbol','as_of','source']).issubset(data.columns):
        return pd.DataFrame(columns=fields)
    for col in ('market_cap_vnd','shares_outstanding'):
        if col not in data:
            data[col] = None
    data = data[fields].copy()
    data['symbol'] = data['symbol'].astype(str).str.upper().str.strip()
    data['source'] = data['source'].fillna('').astype(str).str.strip()
    data['as_of'] = pd.to_datetime(data['as_of'], errors='coerce').dt.normalize()
    now = pd.Timestamp.now().normalize()
    data = data.loc[(data['source'] != '') & data['as_of'].notna() &
                    data['as_of'].between(now-pd.Timedelta(days=365),now) &
                    data['symbol'].str.fullmatch(r'[A-Z0-9]{2,12}')].copy()
    for col in ('market_cap_vnd','shares_outstanding'):
        data[col] = pd.to_numeric(data[col], errors='coerce')
        data.loc[~data[col].gt(0),col] = float('nan')
    data = data.loc[data[['market_cap_vnd','shares_outstanding']].notna().any(axis=1)]
    return data.sort_values('as_of').drop_duplicates('symbol',keep='last').reset_index(drop=True)


def add_market_cap(table: pd.DataFrame, reference: pd.DataFrame, *, as_of=None) -> pd.DataFrame:
    """Attach cap in billions VND to screener rows, using same EOD price when possible.

    Supplied market_cap_vnd is only used if dated on the exact as-of EOD day.
    If sourced share count exists, derive EOD market cap = close * outstanding shares.
    No price-unit conversions or guesses are performed.
    """
    result = table.copy()
    result['Vốn hóa (tỷ VND)'] = float('nan')
    result['Nhóm vốn hóa'] = 'Chưa có dữ liệu'
    result['Nguồn vốn hóa'] = ''
    if reference.empty or 'Mã' not in result or 'Giá (VND)' not in result:
        return result
    right = reference.rename(columns={'symbol':'Mã', 'as_of':'_cap_date',
                         'source':'_cap_source', 'shares_outstanding':'_cap_shares',
                         'market_cap_vnd':'_cap_direct'})
    merged = result.merge(right,on='Mã',how='left')
    dates = pd.to_datetime(merged.get('Ngày dữ liệu'),errors='coerce')
    cap_dates = pd.to_datetime(merged['_cap_date'],errors='coerce')
    prices = pd.to_numeric(merged['Giá (VND)'],errors='coerce')
    shares = pd.to_numeric(merged['_cap_shares'],errors='coerce')
    cap_direct = pd.to_numeric(merged['_cap_direct'],errors='coerce')
    # Shares must be known as of the price date; leave out any future reports.
    shares_valid = shares.gt(0) & cap_dates.le(dates) & (dates-cap_dates).dt.days.le(365)
    direct_valid = cap_direct.gt(0) & cap_dates.eq(dates)
    cap = pd.Series(float('nan'),index=merged.index)
    cap.loc[direct_valid] = cap_direct.loc[direct_valid]/1e9
    use_shares = shares_valid & prices.gt(0)
    cap.loc[use_shares] = (prices.loc[use_shares]*shares.loc[use_shares])/1e9
    merged['Vốn hóa (tỷ VND)'] = cap
    merged['Nhóm vốn hóa'] = cap.map(cap_band)
    merged['Nguồn vốn hóa'] = merged['_cap_source'].where(cap.notna(),'').fillna('')
    return merged.drop(columns=['_cap_date','_cap_source','_cap_shares','_cap_direct'])


def volume_value_average(daily: pd.DataFrame):
    """Mean last 20 EOD candles (source columns in VND, shares)."""
    if daily is None or daily.empty or not {'close','volume'}.issubset(daily):
        return None, None
    close=pd.to_numeric(daily['close'], errors='coerce')
    volume=pd.to_numeric(daily['volume'],errors='coerce')
    good=close.gt(0)&volume.ge(0)
    c=close[good].tail(20);v=volume[good].tail(20)
    if len(c)<20:return None,None
    return float(v.mean()),float((c*v).mean()/1e9)

# AURA_V8_3_MARKET_CAP: preserve original calculator; add a labelled, recent-date estimate.
from core.aura_market_cap_v83 import enrich_market_cap_estimate as _aura_v83_enrich_cap
_aura_v83_original_add_market_cap = add_market_cap
def add_market_cap(table, reference, *, as_of=None):
    original = _aura_v83_original_add_market_cap(table, reference, as_of=as_of)
    return _aura_v83_enrich_cap(original, table, reference, as_of=as_of)
