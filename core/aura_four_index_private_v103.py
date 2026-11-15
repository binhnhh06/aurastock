"""Read four SSI indexSummary records from private Cloudflare R2.

Display only. Does not change stock OHLCV, analysis, backtest, X10, or portfolio.
Missing/invalid objects are ignored, never replaced with manufactured prices.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

CODES = ('VNINDEX', 'VN30', 'HNXINDEX', 'UPCOMINDEX')
SCHEMA = 'aura_ssi_index_summary_v103'
VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def _num(v, *, minimum=0, maximum=None):
    if v is None or isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(n) or n < minimum or (maximum is not None and n > maximum):
        return None
    return n


def validate(document, code, *, today=None):
    """Validate a single object; reject mismatches, future dates and wrong units."""
    if code not in CODES or not isinstance(document, dict):
        return None
    if document.get('schema') != SCHEMA or document.get('symbol') != code:
        return None
    try:
        d = date.fromisoformat(str(document.get('date')))
    except (ValueError, TypeError):
        return None
    today = today or datetime.now(VN_TZ).date()
    if d > today or (today - d).days > 90:
        return None
    price = _num(document.get('price'), minimum=30, maximum=10000)
    if price is None:
        return None
    def optional(field, minimum=0, maximum=None):
        v = document.get(field)
        return _num(v, minimum=minimum, maximum=maximum) if v is not None else None
    delta = optional('change', minimum=-10000, maximum=10000)
    pct = optional('percent', minimum=-40, maximum=40)
    vol = optional('volume', maximum=1e12)
    val = optional('value', maximum=1e17)
    if val is not None and val < 1e8 and val != 0:
        val = None  # Unknown/mismatched units: do not display as VND.
    result = {
        'date': d, 'price': price, 'change': delta, 'percent': pct,
        'volume': vol, 'value': val,
        'advances': optional('advances', maximum=100000),
        'declines': optional('declines', maximum=100000),
        'nochanges': optional('nochanges', maximum=100000),
        'volume_type': str(document.get('volume_type') or 'KLGD từ SSI'),
        'value_type': str(document.get('value_type') or 'GTGD từ SSI'),
        'status': 'EOD',
        'source': 'SSI FastConnect V3 · indexSummary / R2 private',
    }
    return result


def read_index_private(code):
    """R2 get_object, with short-lived Streamlit cache; safe error behavior."""
    if code not in CODES:
        return None
    try:
        import streamlit as st
        from core.aura_r2_market import client, enabled, prefix, setting
        if not enabled():
            return None

        @st.cache_data(ttl=300, show_spinner=False, max_entries=16)
        def read_raw(code_):
            base = prefix()
            key = f'{base}/index_summary/v103/{code_}.json'
            obj = client().get_object(Bucket=setting('AURA_R2_BUCKET'), Key=key)
            raw = obj['Body'].read(32769)
            if len(raw) > 32768:
                return None
            return json.loads(raw)
        return validate(read_raw(code), code)
    except Exception:
        # Deliberately do not leak bucket names, tokens or S3 exception strings.
        return None
