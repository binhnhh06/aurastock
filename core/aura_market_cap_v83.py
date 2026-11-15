"""Safe, source-aware market-cap estimation for AURA.

Only fills a recent EOD screen when an actual outstanding-share count is available.
A shares snapshot observed AFTER the EOD date is labelled an ESTIMATE, never a
point-in-time verified historical value or an input for historical backtests.
"""
from __future__ import annotations

import pandas as pd

MAX_AFTER_EOD_DAYS = 4  # Friday close -> Monday collection, incl. holidays up to 4 days
MAX_EOD_AGE_DAYS = 7    # prevent retrospective leakage to historical screens


def enrich_market_cap_estimate(base: pd.DataFrame, table: pd.DataFrame,
                               reference: pd.DataFrame, *, as_of=None,
                               today=None) -> pd.DataFrame:
    result = base.copy()
    result['Trạng thái vốn hóa'] = 'Chưa có nguồn'
    if 'Vốn hóa (tỷ VND)' not in result:
        result['Vốn hóa (tỷ VND)'] = float('nan')
    cap = pd.to_numeric(result['Vốn hóa (tỷ VND)'], errors='coerce')
    result.loc[cap.gt(0), 'Trạng thái vốn hóa'] = 'Tham chiếu có nguồn'
    mandatory_table = {'Mã', 'Giá (VND)', 'Ngày dữ liệu'}
    mandatory_ref = {'symbol', 'as_of', 'source', 'shares_outstanding'}
    if not mandatory_table.issubset(result.columns) or reference is None or reference.empty or not mandatory_ref.issubset(reference.columns):
        return result
    date_today = pd.Timestamp(today).normalize() if today is not None else pd.Timestamp.now().normalize()
    ref = reference.copy()
    ref['symbol'] = ref['symbol'].astype(str).str.strip().str.upper()
    ref['_snapshot_date'] = pd.to_datetime(ref['as_of'], errors='coerce').dt.normalize()
    ref['_shares_count'] = pd.to_numeric(ref['shares_outstanding'], errors='coerce')
    ref['_origin'] = ref['source'].fillna('').astype(str).str.strip()
    ref = ref.loc[ref['_origin'].ne('') & ref['_shares_count'].gt(0) &
                  ref['_snapshot_date'].notna() & ref['_snapshot_date'].le(date_today)].copy()
    if ref.empty:
        return result
    ref = ref.sort_values('_snapshot_date').drop_duplicates('symbol', keep='last').set_index('symbol')
    symbols = result['Mã'].astype(str).str.strip().str.upper()
    snap_dates = pd.to_datetime(symbols.map(ref['_snapshot_date']), errors='coerce')
    shares = pd.to_numeric(symbols.map(ref['_shares_count']), errors='coerce')
    origins = symbols.map(ref['_origin']).fillna('')
    eod = pd.to_datetime(result['Ngày dữ liệu'], errors='coerce', dayfirst=False).dt.normalize()
    price = pd.to_numeric(result['Giá (VND)'], errors='coerce')
    # Use only the actual displayed EOD date; as_of never overrides each row.
    gap = (snap_dates - eod).dt.days
    age = (date_today - eod).dt.days
    eligible = (cap.isna() & shares.gt(0) & price.gt(0) &
                gap.between(1, MAX_AFTER_EOD_DAYS) & age.between(0, MAX_EOD_AGE_DAYS))
    if eligible.any():
        result.loc[eligible, 'Vốn hóa (tỷ VND)'] = price.loc[eligible] * shares.loc[eligible] / 1e9
        if 'Nhóm vốn hóa' in result.columns:
            def cap_band(value):
                return ("Large-cap · AURA" if value >= 10000 else
                        "Mid-cap · AURA" if value >= 1000 else "Small-cap · AURA")
            result.loc[eligible, 'Nhóm vốn hóa'] = result.loc[eligible, 'Vốn hóa (tỷ VND)'].map(cap_band)
        if 'Nguồn vốn hóa' in result.columns:
            result.loc[eligible, 'Nguồn vốn hóa'] = (
                origins.loc[eligible] + ' | Số CP ghi nhận ' +
                snap_dates.loc[eligible].dt.strftime('%Y-%m-%d') +
                ' | Ước tính cho EOD ' + eod.loc[eligible].dt.strftime('%Y-%m-%d')
            )
        result.loc[eligible, 'Trạng thái vốn hóa'] = 'Ước tính — số CP ghi nhận sau ngày EOD'
    return result
