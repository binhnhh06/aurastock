"""Đọc bản tin chỉ số từ SSI WebSocket (IndexTickMessage / IndexSummaryMessage) thành dict
cùng định dạng snapshot của worker: {'price','change','change_percent','total_quantity',
'total_value','total_match_quantity','total_match_value','advances','declines','nochanges',
'trading_time','received_at','source_type'}.

Chỉ để HIỂN THỊ dải chỉ số; không tính chỉ báo. Không đoán đơn vị: giá trị điểm ngoài
30–10.000 bị loại; phần so khớp với EOD (±35%) do core/vnindex_dashboard.py kiểm tra.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

INDEX_CODES = ('VNINDEX', 'VN30', 'HNXINDEX', 'UPCOMINDEX')
_NAME = type


def norm_index(value) -> str:
    code = str(value or '').strip().upper()
    return 'UPCOMINDEX' if code in ('HNXUPCOMINDEX', 'UPCOM') else code


def _num(v, *, nonnegative=False):
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(f) or (nonnegative and f < 0):
        return None
    return f


def _points(v):
    n = _num(v)
    return n if n is not None and 30 <= n <= 10000 else None


_SUMMARY_KEYS = {
    'price': ('IndexValue', 'indexValue', 'index_value', 'IndexVal', 'IndexPoint', 'indexPoint', 'v'),
    'change': ('c', 'Change', 'change'),
    'change_percent': ('cr', 'RatioChange', 'ChangePercent', 'changePercent'),
    'total_match_quantity': ('tmq', 'Totalmatchvol', 'TotalMatchQuantity'),
    'total_match_value': ('tmv', 'Totalmatchval', 'TotalMatchValue'),
    'total_quantity': ('tq', 'Totalvol', 'AllQty', 'TotalQtty', 'TotalQuantity'),
    'total_value': ('tv', 'Totalval', 'AllValue', 'TotalValue'),
    'advances': ('adv', 'Advances', 'advances', 'TotalAdvanceStock'),
    'declines': ('dec', 'Declines', 'declines', 'TotalDeclineStock'),
    'nochanges': ('nc', 'Nochanges', 'nochanges', 'TotalSteadyStock'),
}


def parse_index_message(msg, now: datetime | None = None):
    """Trả về (mã chỉ số, fields) hoặc None nếu không phải bản tin chỉ số hợp lệ."""
    now = now or datetime.now(timezone.utc)
    kind = _NAME(msg).__name__
    if kind == 'IndexTickMessage':
        symbol = norm_index(getattr(msg, 'symbol', ''))
        price = _points(getattr(msg, 'value', None))
        if symbol not in INDEX_CODES or price is None:
            return None
        fields = {'price': price, 'source_type': 'INDEX_TICK',
                  'trading_time': str(getattr(msg, 'trading_time', '') or '')}
        for name, attr, nonneg in (('change', 'change', False), ('change_percent', 'change_percent', False),
                                   ('total_match_quantity', 'total_match_quantity', True),
                                   ('total_match_value', 'total_match_value', True),
                                   ('total_quantity', 'total_quantity', True), ('total_value', 'total_value', True),
                                   ('advances', 'advances', True), ('declines', 'declines', True),
                                   ('nochanges', 'no_change', True)):
            v = _num(getattr(msg, attr, None), nonnegative=nonneg)
            if v is not None:
                fields[name] = v
    elif kind == 'IndexSummaryMessage':
        data = getattr(msg, 'data', None)
        data = data if isinstance(data, dict) else {}
        symbol = norm_index(getattr(msg, 'index', '') or data.get('s') or data.get('IndexID'))
        price = next((p for p in (_points(data.get(k)) for k in _SUMMARY_KEYS['price']) if p is not None), None)
        if symbol not in INDEX_CODES or price is None:
            return None
        fields = {'price': price, 'source_type': 'INDEX_SUMMARY',
                  'trading_time': str(data.get('t') or data.get('Time') or data.get('TradingTime') or '')}
        for name, keys in _SUMMARY_KEYS.items():
            if name == 'price':
                continue
            nonneg = name not in ('change', 'change_percent')
            v = next((x for x in (_num(data.get(k), nonnegative=nonneg) for k in keys) if x is not None), None)
            if v is not None:
                fields[name] = v
    else:
        return None
    fields['received_at'] = now.isoformat(timespec='seconds')
    return symbol, fields
