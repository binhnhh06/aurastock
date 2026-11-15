"""AURA market overview: VN-Index, VN30, HNX-Index, UPCoM-Index.

Uses four dedicated SSI indexsummary WebSocket topics; uses trade.index only
when trustworthy index points are present. A stale index is explicitly dated.
Never fabricates trading value from price × volume. Does not touch X10,
historical prices, financials, or individual stock quotes.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, date, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')
INDICES = (
    ('VNINDEX', 'VN-INDEX', 'HOSE', 'green'),
    ('VN30', 'VN30', '30 cổ phiếu vốn hóa lớn HOSE', 'blue'),
    ('HNXINDEX', 'HNX-INDEX', 'HNX', 'yellow'),
    ('UPCOMINDEX', 'UPCOM-INDEX', 'UPCoM', 'pink'),
)


def _number(value, *, nonnegative=False):
    try:
        if value is None or str(value).strip() in ('', 'None', '—'):
            return None
        n = float(value)
        if not math.isfinite(n) or (nonnegative and n < 0):
            return None
        return n
    except (ValueError, TypeError, OverflowError):
        return None


def _parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _trade_date(value, received):
    if value:
        try:
            # SSI: YYYY/MM/DD HH:mm:ss, possibly milliseconds
            dt = datetime.fromisoformat(str(value).strip().replace('/', '-'))
            if dt.year >= 2000:
                return dt.date()
        except (ValueError, OverflowError):
            pass
    return received.astimezone(VN_TZ).date() if received else None


def _rest_index_cache(root: Path, symbol: str):
    """Validated SSI REST indexSummary EOD, independent of stock OHLCV CSV."""
    path = Path(root) / 'data' / 'ssi_cache' / 'index_summary' / (symbol + '.json')
    try:
        with path.open(encoding='utf-8') as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            return None
        d = date.fromisoformat(str(raw['date']))
        value = _number(raw.get('price'))
        if value is None or not 30 <= value <= 10000:
            return None
        if d > datetime.now(VN_TZ).date():
            return None
        def numeric(name):
            return _number(raw.get(name), nonnegative=name not in ('change', 'percent'))
        return dict(
            date=d, price=value, change=numeric('change'),
            percent=numeric('percent'), volume=numeric('volume'),
            value=numeric('value'), advances=numeric('advances'),
            declines=numeric('declines'), nochanges=numeric('nochanges'),
            volume_type=str(raw.get('volume_type') or 'Tổng KLGD phiên'),
            value_type=str(raw.get('value_type') or 'Tổng GTGD phiên'),
            status='EOD', source='SSI FastConnect REST · indexSummary',
        )
    except (OSError, UnicodeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _eod(root: Path, symbol: str):
    folder = Path(root) / 'data' / 'ssi_cache' / 'ohlcv'
    names = {'UPCOMINDEX': ['UPCOMINDEX', 'HNXUPCOMINDEX', 'UPCOM'],
             'HNXINDEX': ['HNXINDEX', 'HNX'],
             'VNINDEX': ['VNINDEX'],
             'VN30': ['VN30']}.get(symbol, [symbol])
    path = next((folder / (n + '.csv') for n in names if (folder / (n + '.csv')).is_file()), None)
    recent_rest = _rest_index_cache(root, symbol)
    if path is None:
        return recent_rest
    try:
        with path.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        records = []
        for item in rows:
            rawdate = item.get('date') or item.get('time')
            try:
                dt = datetime.fromisoformat(str(rawdate).replace('/', '-')).date()
            except (ValueError, TypeError):
                continue
            price = _number(item.get('close'))
            if price is None or not 30 <= price <= 10000:
                continue
            records.append((dt, price, item))
        if not records:
            return None
        records.sort(key=lambda x: x[0])
        d, price, item = records[-1]
        prior = records[-2][1] if len(records) > 1 else None
        delta = price - prior if prior else None
        percent = delta / prior * 100 if prior else None
        def firstnum(*names):
            return next((v for k in names if (v := _number(item.get(k), nonnegative=True)) is not None), None)
        legacy_csv = dict(
            date=d, price=price, change=delta, percent=percent,
            volume=firstnum('total_quantity', 'total_match_quantity', 'volume'),
            value=firstnum('total_value', 'total_match_value', 'trading_value', 'value'),
            volume_type='KLGD theo file EOD', value_type='GTGD theo file EOD',
            advances=None, declines=None, nochanges=None,
            status='EOD', source='SSI · Dữ liệu EOD',
        )
        # Prefer the most recent dated summary. When the same day's
        # summaries exist, prefer REST (it has verified turnover & breadth).
        if recent_rest is not None and recent_rest['date'] >= legacy_csv['date']:
            return recent_rest
        return legacy_csv
    except (OSError, UnicodeError, csv.Error, KeyError, ValueError):
        return recent_rest


def _live(snapshot, symbol, eod, *, now):
    rec = snapshot.get('indices', {}).get(symbol)
    if not isinstance(rec, dict):
        return None
    received = _parse_time(rec.get('received_at'))
    d = _trade_date(rec.get('trading_time'), received)
    price = _number(rec.get('price'))
    if received is None or d is None or price is None or not 30 <= price <= 10000:
        return None
    # Do not trust values received from future, impossibly old snapshots, or
    # values far removed from a SAME/RECENT EOD reference.
    age_days = (now.astimezone(VN_TZ).date() - d).days
    if age_days < 0 or age_days > 7:
        return None
    if eod is not None and eod['date'] > d:
        # Never let older live snapshots override a newer EOD.
        return None
    if eod is not None and (d - eod['date']).days <= 7:
        if not (0.65 <= price / eod['price'] <= 1.35):
            return None
    delta = _number(rec.get('change'))
    pct = _number(rec.get('change_percent'))
    if pct is not None and not -40 <= pct <= 40:
        pct = None
    if delta is None and eod and 0 < (d - eod['date']).days <= 4:
        delta = price - eod['price']
    if pct is None and delta is not None and price - delta > 0:
        pct = delta / (price - delta) * 100
    if delta is not None and abs(delta) > price * .35:
        delta, pct = None, None
    vol_total = _number(rec.get('total_quantity'), nonnegative=True)
    val_total = _number(rec.get('total_value'), nonnegative=True)
    vol_match = _number(rec.get('total_match_quantity'), nonnegative=True)
    val_match = _number(rec.get('total_match_value'), nonnegative=True)
    # Never treat invalid negative/unitless fields as a traded volume/value.
    vol = vol_total if vol_total is not None else vol_match
    val = val_total if val_total is not None else val_match
    voltype = 'Tổng KLGD (khớp + thỏa thuận)' if vol_total is not None else 'KL khớp lệnh'
    valtype = 'Tổng GTGD (khớp + thỏa thuận)' if val_total is not None else 'GT khớp lệnh'
    age_s = (now - received).total_seconds()
    worker_at = _parse_time(snapshot.get('worker_at'))
    worker_age = (now - worker_at).total_seconds() if worker_at else float('inf')
    in_market = _market_hours(now.astimezone(VN_TZ))
    is_fresh = (d == now.astimezone(VN_TZ).date() and 0 <= age_s <= 120
                and snapshot.get('connection') == 'CONNECTED' and 0 <= worker_age <= 40 and in_market)
    status = 'LIVE' if is_fresh else ('LAST_SESSION' if d != now.astimezone(VN_TZ).date() else 'LAST_TICK')
    def count(name):
        v = _number(rec.get(name), nonnegative=True)
        return int(v) if v is not None else None
    return dict(date=d, price=price, change=delta, percent=pct,
                volume=vol, value=val, volume_type=voltype, value_type=valtype,
                advances=count('advances'), declines=count('declines'), nochanges=count('nochanges'),
                status=status, source='SSI WebSocket · ' + str(rec.get('source_type', 'INDEX_SUMMARY')),
                received_at=received, type=rec.get('source_type'))


def _market_hours(vn_now):
    # Indicative, holidays are not assumed.
    minute = vn_now.hour * 60 + vn_now.minute
    return vn_now.weekday() < 5 and ((9*60 <= minute <= 11*60+30) or (13*60 <= minute <= 14*60+45))


def _choose(eod, live):
    if live is None:
        return eod
    if eod is None:
        return live
    # Fresh, timestamped streaming data may supersede a same-session EOD cache.
    return live if live['date'] >= eod['date'] else eod


def market_data(root: Path, *, snapshot=None, clock=None):
    """Pure, testable dict of data for four indices; never predicts missing data."""
    if clock is None:
        clock = datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    if snapshot is None:
        try:
            from core.ssi_market_live import read_snapshot
            snapshot = read_snapshot()
        except (ImportError, OSError, ValueError):
            snapshot = {}
    if not isinstance(snapshot, dict):
        snapshot = {}
    result = {}
    for symbol, *_ in INDICES:
        eod = _eod(root, symbol)
        live = _live(snapshot, symbol, eod, now=clock)
        result[symbol] = _choose(eod, live)
    return result


def current_index(root: Path, *, clock=None, snapshot=None):
    """Backward-compatible VN-Index accessor for existing code."""
    return market_data(root, snapshot=snapshot, clock=clock)['VNINDEX']


def _fmt(v, places=2):
    if v is None:
        return '—'
    return f'{v:,.{places}f}'.replace(',', '@').replace('.', ',').replace('@', '.')


def _compact(v, suffix):
    if v is None:
        return '—'
    if v >= 1_000_000_000_000:
        return _fmt(v/1_000_000_000_000) + (' nghìn tỷ ' if suffix=='đ' else ' nghìn tỷ ') + suffix
    if v >= 1_000_000_000:
        return _fmt(v/1_000_000_000) + ' tỷ ' + suffix
    if v >= 1_000_000:
        return _fmt(v/1_000_000) + ' triệu ' + suffix
    return _fmt(v, 0) + ' ' + suffix


def _delta(d):
    n = d.get('change')
    p = d.get('percent')
    if n is None:
        return 'Chưa có biến động phiên'
    s = ('+' if n > 0 else '') + _fmt(n) + ' điểm'
    if p is not None:
        s += ' (' + ('+' if p > 0 else '') + _fmt(p) + '%)'
    return s


def _status(d, today):
    if d is None:
        return 'CHƯA CÓ DỮ LIỆU'
    if d['status'] == 'LIVE':
        return 'TRONG PHIÊN · LIVE'
    if d['date'] == today:
        return 'PHIÊN HÔM NAY · ' + ('EOD' if d['status']=='EOD' else 'TICK CUỐI')
    days = (today - d['date']).days
    return 'PHIÊN GẦN NHẤT' if days <= 4 else 'DỮ LIỆU CŨ'


def _one_card(code, title, board, color, data, today):
    if data is None:
        return (f'<div class="aura-idx-card aura-{color}"><div class="aura-idx-name">{title}'
                f'<small>{escape(board)}</small></div><span class="aura-idx-status">CHƯA CÓ SSI</span>'
                '<div class="aura-idx-point">—</div><div class="aura-idx-delta">Chưa nhận được bản tin hợp lệ</div>'
                '<div class="aura-idx-facts"><div><span>KHỐI LƯỢNG</span><strong>—</strong></div>'
                '<div><span>GIÁ TRỊ GIAO DỊCH</span><strong>—</strong></div></div></div>')
    delta = data.get('change')
    delta_class = 'up' if delta is not None and delta > 0 else ('down' if delta is not None and delta < 0 else 'flat')
    breadth = ''
    adv, dec = data.get('advances'), data.get('declines')
    if adv is not None and dec is not None:
        nc = data.get('nochanges')
        breadth = '<div class="aura-idx-breadth">Tăng <b>' + str(adv) + '</b> · Giảm <b>' + str(dec) + '</b>'
        if nc is not None:
            breadth += ' · Đứng <b>' + str(nc) + '</b>'
        breadth += '</div>'
    return (f'<div class="aura-idx-card aura-{color}">'
            f'<div class="aura-idx-name">{title}<small>{escape(board)}</small></div>'
            f'<span class="aura-idx-status">{escape(_status(data,today))}</span>'
            f'<div class="aura-idx-point">{_fmt(data["price"])}</div>'
            f'<div class="aura-idx-delta {delta_class}">{escape(_delta(data))}</div>'
            '<div class="aura-idx-facts">'
            '<div><span>KHỐI LƯỢNG</span><strong>' + escape(_compact(data.get('volume'), 'CP')) + '</strong></div>'
            '<div><span>GTGD</span><strong>' + escape(_compact(data.get('value'), 'đ')) + '</strong></div>'
            '</div>' + breadth +
            f'<div class="aura-idx-day">Phiên {data["date"]:%d/%m/%Y} · {escape(data["source"])}</div>'
            '</div>')


CSS = '''
<style>
.aura-market-overview{background:linear-gradient(115deg,#6429ED 0%,#9830E9 55%,#CA26D5 100%);
 border:2px solid #1B1233;border-radius:25px;padding:20px 21px 23px;margin:12px 5px 25px 0;
 box-shadow:6px 7px 0 #1B1233,0 16px 26px rgba(47,22,93,.14);color:#fff}
.aura-market-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:17px}
.aura-market-head strong{font-size:22px;font-weight:900;letter-spacing:-.035em}
.aura-market-head span{font-size:12px;font-weight:700;color:#F7E5FF}
.aura-market-stamp{background:#fff;border:1.5px solid #1B1233;color:#57239B!important;
 border-radius:999px;padding:6px 13px;font-size:11px!important;font-weight:900!important}
.aura-market-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.aura-idx-card{border:2px solid #1B1233;border-radius:19px;box-shadow:4px 5px 0 #1B1233;
 padding:14px 13px 13px;color:#1B1233;min-width:0}
.aura-green{background:#DDF9A4}.aura-blue{background:#C6F3FC}.aura-yellow{background:#FFE9A3}.aura-pink{background:#FFD0E5}
.aura-idx-name{font-size:18px;font-weight:900;letter-spacing:-.035em;line-height:1.25}
.aura-idx-name small{display:block;font-size:11px;font-weight:600;opacity:.8;margin:4px 0 8px;letter-spacing:0}
.aura-idx-status{font-size:9px;font-weight:850;letter-spacing:.025em;display:inline-block;
 background:rgba(255,255,255,.68);border:1px solid rgba(27,18,51,.26);padding:4px 7px;border-radius:30px}
.aura-idx-point{font-size:clamp(23px,2.25vw,35px);font-weight:900;margin:12px 0 4px;
 font-variant-numeric:tabular-nums;line-height:1.22}
.aura-idx-delta{font-size:12px;font-weight:900;min-height:37px}
.aura-idx-delta.up{color:#06633E}.aura-idx-delta.down{color:#B01B4A}.aura-idx-delta.flat{color:#4D4663}
.aura-idx-facts{display:grid;grid-template-columns:1fr;gap:6px;margin-top:12px}
.aura-idx-facts>div{background:rgba(255,255,255,.40);border:1px solid rgba(27,18,51,.16);
 padding:7px 9px;border-radius:10px;display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.aura-idx-facts span{font-size:10px;font-weight:700;color:#513A66;white-space:nowrap}
.aura-idx-facts strong{font-size:12px;font-weight:900;text-align:right;overflow-wrap:anywhere}
.aura-idx-breadth{font-size:11px;margin-top:11px;font-weight:700;line-height:1.5}
.aura-idx-day{font-size:10px;opacity:.83;border-top:1px solid rgba(27,18,51,.22);
 padding-top:9px;margin-top:11px;line-height:1.45;word-break:break-word}
.aura-market-foot{font-size:11px;font-weight:650;color:#FFFFFF;margin-top:18px;line-height:1.65}
@media(max-width:1250px){.aura-market-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:650px){.aura-market-grid{grid-template-columns:1fr}.aura-market-overview{padding:15px}}
</style>'''


def render_vnindex_strip(root: Path):
    """Keep old entrypoint so app.py stays unchanged. Displays all four indexes."""
    cards = market_data(root)
    today = datetime.now(VN_TZ).date()
    latest = [d['date'] for d in cards.values() if d is not None]
    stamp = max(latest).strftime('%d/%m/%Y') if latest else 'Chưa có phiên'
    inner = ''.join(_one_card(code, title, board, color, cards[code], today)
                    for code, title, board, color in INDICES)
    has_live = any(d is not None and d['status'] == 'LIVE' for d in cards.values())
    latest_status = 'Có bản tin LIVE' if has_live else 'Dữ liệu phiên gần nhất / EOD'
    title = 'AURA · TOÀN CẢNH THỊ TRƯỜNG'
    header = ('<div class="aura-market-head"><div><strong>' + title + '</strong>'
              '<div><span>4 chỉ số · Điểm, biến động, khối lượng, giá trị giao dịch</span></div></div>'
              '<span class="aura-market-stamp">' + escape(latest_status) + ' · ' + stamp + '</span></div>')
    foot = ('<div class="aura-market-foot">Nguồn: SSI FastConnect V3 (indexsummary / trade.index / EOD). '
            'Dữ liệu mỗi chỉ số có thời điểm riêng, hiển thị rõ ngày phiên; dấu — nghĩa là SSI chưa cung cấp dữ liệu hợp lệ. '
            'VN30 thuộc HOSE nên không cộng khối lượng VN30 vào tổng HOSE. '
            'Realtime chỉ được ghi khi có tick mới và Worker hoạt động trong phiên.</div>')
    st.markdown(CSS + '<div class="aura-market-overview">' + header +
                '<div class="aura-market-grid">' + inner + '</div>' + foot + '</div>',
                unsafe_allow_html=True)
