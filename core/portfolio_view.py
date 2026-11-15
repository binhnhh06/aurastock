"""Streamlit presentation for a one-symbol *manual* holding and P/L estimate.

The user never connects a brokerage account; no order is submitted or saved.
"""
from __future__ import annotations

import csv
import math
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from core.portfolio_advisor import calculate_position, review_holding

VN_ZONE = ZoneInfo('Asia/Ho_Chi_Minh')




def _parse_localized_price(raw: str) -> Decimal:
    """Read Vietnamese decimal comma (20,84) without a float-step rounding.

    Accepts 20,84; 20.84; 20.840,50; 20,840.50. Empty is zero.
    For unambiguous amounts, prefer the Vietnamese 20.840,50 style.
    """
    text = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return Decimal(0)
    if text.count(',') and text.count('.'):
        # The rightmost separator is the decimal mark; the other groups thousands.
        decimal_char = ',' if text.rfind(',') > text.rfind('.') else '.'
        thousands_char = '.' if decimal_char == ',' else ','
        text = text.replace(thousands_char, '').replace(decimal_char, '.')
    elif ',' in text:
        text = text.replace(',', '.')
    elif '.' in text:
        # With one dot and exactly three trailing digits, accept VN thousands grouping.
        # In thousand-VND mode, users should enter 20,84 (not 20.840).
        pieces = text.split('.')
        if len(pieces) >= 2 and all(len(part) == 3 for part in pieces[1:]) and pieces[0].isdigit():
            text = ''.join(pieces)
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError('Giá vốn không hợp lệ. Ví dụ: 20,84 (nghìn đồng) hoặc 20.840 (đồng).')
    if not result.is_finite() or result < 0:
        raise ValueError('Giá vốn phải là số dương; có thể nhập dấu phẩy thập phân, ví dụ 20,84.')
    return result


def _format_decimal_vn(value: Decimal) -> str:
    """Format without rounding away a fractional price entered by the user."""
    raw = f'{value:f}'
    integer, dot, fraction = raw.partition('.')
    # Thousands separators use dot; decimal separators use comma in Vietnamese.
    i = f'{int(integer):,}'.replace(',', '.')
    return i + (',' + fraction if dot and any(ch != '0' for ch in fraction) else '')

def _last_eod(root: Path, symbol: str):
    path = Path(root) / 'data' / 'ssi_cache' / 'ohlcv' / (symbol + '.csv')
    if not path.is_file():
        return None
    try:
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            rows = csv.DictReader(handle)
            latest = None
            for row in rows:
                raw_date = row.get('date') or row.get('time')
                try:
                    d = datetime.fromisoformat(str(raw_date).strip().replace('/', '-')).date()
                    v = float(row.get('close'))
                except (ValueError, TypeError):
                    continue
                if math.isfinite(v) and 0 < v < 50_000_000 and (latest is None or d > latest[0]):
                    # Match the established AURA SSI stock-price normalization.
                    latest = (d, v * 1000 if v < 1000 else v)
            return latest
    except (OSError, UnicodeError, csv.Error):
        return None


def _verified_quote(root, symbol):
    anchor = _last_eod(root, symbol)
    if anchor is None:
        return None, 'Chưa có CSV SSI EOD cho mã này', None, False
    d, eod = anchor
    local_today = datetime.now(VN_ZONE).date()
    # For direct-currency SSI CSV stock prices, refuse inconsistent smaller units.
    try:
        from core.ssi_market_live import request_live_symbol, read_snapshot, quote_view, date_label
        request_live_symbol(symbol)
        quote = quote_view(read_snapshot(), symbol)
        tick = quote.get('price')
        status = quote.get('status')
        stamp = quote.get('received_at')
        if stamp is not None and tick is not None:
            tick = float(tick)
            when = stamp.astimezone(VN_ZONE).date() if stamp.tzinfo is not None else stamp.date()
            if math.isfinite(tick) and tick > 0 and 0.5 <= tick / eod <= 1.5 and when >= d:
                fresh = when == local_today and status == 'LIVE_TICK'
                desc = ('SSI realtime' if fresh else 'SSI khớp gần nhất') + ' · ' + date_label(stamp)
                # A tick that is older than EOD is already excluded.
                return tick, desc, when, fresh or ((local_today - when).days <= 4)
    except (ImportError, AttributeError, KeyError, TypeError, ValueError, OSError, ZeroDivisionError):
        pass
    # Weekend/holiday freshness is approximate, not a trade-session calendar.
    recently = 0 <= (local_today - d).days <= 4
    return eod, f'SSI EOD · phiên {d:%d/%m/%Y}', d, recently


def _money(value):
    return f'{value:,.0f}'.replace(',', '.') + ' đ'


def _num(value):
    return f'{value:,.0f}'.replace(',', '.')


def _signal_color(label):
    if label.startswith(('XEM XÉT', 'CHỜ')):
        return '#FFD0E5'
    if 'MUA THÊM' in label:
        return '#C6F3FC'
    return '#DDF9A4' if label.startswith('CÂN NHẮC CHỐT') else '#FFE9A3'


@st.fragment(run_every='5s')
def _calculation_panel(root, symbol, qty, cost, buy_fee, sell_fee, sale_tax,
                       portfolio_total, stop, target, max_weight, selected, analysis):
    price, source, asof, fresh = _verified_quote(root, symbol)
    if price is None:
        st.warning(f'{symbol}: {source}. Chưa thể ước tính lãi/lỗ hoặc đưa gợi ý hành động.')
        return
    if qty <= 0 or cost <= 0:
        st.info('Nhập **số lượng đang nắm giữ** và **giá vốn bình quân (VND/CP)** lớn hơn 0 để tính lãi/lỗ.')
        st.caption(f'Giá tham khảo: **{_money(price)}** · {source}')
        return
    try:
        p = calculate_position(qty, cost, price, buy_fee_pct=buy_fee,
                               sell_fee_pct=sell_fee, sell_tax_pct=sale_tax,
                               total_portfolio_value=portfolio_total or None)
    except ValueError as exc:
        st.warning(str(exc))
        return
    a, b, c, d = st.columns(4)
    a.metric('Giá thị trường', _money(p.market_price))
    b.metric('Giá trị hiện tại', _money(p.market_value))
    c.metric('Lãi/lỗ tạm tính', _money(p.net_pnl), f'{p.net_pct:+.2f}%',
             delta_color='normal')
    d.metric('Giá hòa vốn ước tính', _money(p.break_even))
    st.caption(f'{symbol} · {source} · Vốn gốc {_money(p.invested)} · '
               f'Lãi/lỗ trước chi phí {_money(p.gross_pnl)} ({p.gross_pct:+.2f}%).')
    st.caption('Lãi/lỗ **ước tính nếu bán toàn bộ** theo giá hiển thị, trừ các phí/thuế bạn đã nhập; '
               'không bao gồm cổ tức, quyền cổ đông, trượt giá và biến động giá khi thực sự đặt lệnh.')
    matched = bool(analysis) and selected == symbol
    label, reasons = review_holding(
        p, analysis=analysis if matched else None, price_fresh=fresh,
        stop_loss_pct=stop, take_profit_pct=target, max_weight_pct=max_weight)
    color = _signal_color(label)
    st.markdown(
        f'<div style="background:{color};border:2px solid #1B1233;border-radius:17px;'
        'box-shadow:4px 5px 0 #1B1233;padding:14px 18px;margin:14px 0">'
        '<div style="font-size:12px;font-weight:750">GỢI Ý QUẢN TRỊ VỊ THẾ · THEO BỘ QUY TẮC</div>'
        f'<div style="font-size:23px;font-weight:900;margin:5px 0">{escape(label)}</div>'
        '</div>', unsafe_allow_html=True)
    for reason in reasons:
        st.markdown('• ' + reason)
    if p.weight_pct is not None:
        st.caption(f'Tỷ trọng cổ phiếu theo tổng giá trị danh mục tự nhập: {p.weight_pct:.1f}%.')
    if not matched:
        st.info('Mã vị thế khác mã đang phân tích. Chọn cùng mã ở thanh bên trái và bấm **Phân tích** '
                'để AURA dùng cảnh báo kỹ thuật của đúng cổ phiếu đó.')
    if matched and not analysis.get('co_fa'):
        st.warning('Điểm cơ bản hiện dùng mức trung tính do thiếu nguồn BCTC xác minh; '
                   'không xem điểm tổng hợp này là căn cứ duy nhất để tăng vị thế.')
    if not fresh:
        st.warning('Giá không đủ mới; gợi ý hành động đã được tạm khóa. '
                   'Khi có dữ liệu phiên gần nhất hãy đánh giá lại.')
    st.caption('Đây là kịch bản tham khảo, không phải khuyến nghị đầu tư cá nhân hoặc lệnh giao dịch. '
               'Nếu giá giảm vượt mức chịu lỗ, bán để kiểm soát rủi ro vẫn có thể phù hợp dù chưa có lãi.')


def render_position_tab(root: Path, selected_symbol: str, analysis: dict | None):
    st.subheader('Vị thế đang nắm giữ · Ước tính lãi/lỗ')
    st.caption('Nhập thông tin **bạn tự khai báo**; AURA không kết nối tài khoản giao dịch '
               'và không tự mua/bán. Giá SSI cập nhật khi Worker có tick hợp lệ, hoặc dùng EOD có ngày rõ ràng.')
    stock = st.text_input('Mã cổ phiếu đang nắm giữ', value=selected_symbol,
                          key='aura_position_symbol', max_chars=10).strip().upper()
    if not stock or not stock.isalnum() or len(stock) > 10:
        st.warning('Nhập mã chứng khoán bằng chữ và số, ví dụ FPT, HPG, VCB.')
        return
    col1, col2 = st.columns(2)
    qty = col1.number_input('Số lượng cổ phiếu (CP)', min_value=0, max_value=100_000_000,
                            step=100, value=0, key='aura_position_qty')
    with col2:
        cost_text = st.text_input('Giá vốn bình quân', value='',
                                  placeholder='Ví dụ: 20,84', key='aura_position_cost_decimal')
        unit = st.radio('Đơn vị giá vốn', ['Nghìn đồng/CP', 'Đồng/CP'],
                        horizontal=True, key='aura_position_cost_unit',
                        help='Mã có giá 20.840 đ/CP thì nhập 20,84 ở chế độ Nghìn đồng/CP.')
    try:
        cost_input = _parse_localized_price(cost_text)
        multiplier = Decimal(1000) if unit == 'Nghìn đồng/CP' else Decimal(1)
        cost_vnd = cost_input * multiplier
    except ValueError as exc:
        st.error(str(exc))
        return
    if cost_input > 0:
        st.caption(f'Giá vốn bạn nhập: **{_format_decimal_vn(cost_input)} {unit}** '
                   f'= **{_format_decimal_vn(cost_vnd)} đ/CP** (không tự làm tròn giá nhập).')
    else:
        st.caption('Nhập **20,84** và chọn **Nghìn đồng/CP** nếu giá mua là **20.840 đ/CP**. '
                   'Có thể chọn **Đồng/CP** để nhập trực tiếp 20.840; không nhập tổng tiền vốn.')
    if cost_vnd > 50_000_000:
        st.error('Giá vốn sau quy đổi quá lớn (trên 50 triệu đồng/CP). Kiểm tra lại đơn vị.')
        return
    with st.expander('Thiết lập phí, thuế và nguyên tắc quản trị rủi ro', expanded=False):
        c1, c2, c3 = st.columns(3)
        buy_fee = c1.number_input('Phí mua (%)', 0.0, 5.0, 0.0, 0.05, key='aura_fee_buy')
        sell_fee = c2.number_input('Phí bán (%)', 0.0, 5.0, 0.0, 0.05, key='aura_fee_sell')
        sale_tax = c3.number_input('Thuế/chi phí bán khác (%)', 0.0, 5.0, 0.0, 0.05,
                                   key='aura_tax_sell')
        st.caption('Mặc định 0% để không tự giả định biểu phí/thuế; bạn nhập theo tài khoản và quy định áp dụng.')
        risk1, risk2, risk3 = st.columns(3)
        stop = risk1.number_input('Ngưỡng chịu lỗ tham khảo (%)', 1.0, 50.0, 8.0, 1.0,
                                   key='aura_stop_loss')
        target = risk2.number_input('Mục tiêu chốt lời tham khảo (%)', 1.0, 200.0, 20.0, 5.0,
                                     key='aura_take_profit')
        max_weight = risk3.number_input('Tỷ trọng tối đa một mã (%)', 1.0, 100.0, 20.0, 5.0,
                                         key='aura_position_limit')
        total_portfolio = st.number_input('Tổng giá trị danh mục (VND, có thể bỏ trống = 0)',
                                           min_value=0.0, step=1_000_000.0,
                                           value=0.0, format='%.0f', key='aura_portfolio_value')
    _calculation_panel(Path(root), stock, int(qty), float(cost_vnd),
                       float(buy_fee), float(sell_fee), float(sale_tax), float(total_portfolio),
                       float(stop), float(target), float(max_weight), selected_symbol, analysis)
    st.caption('Thông tin vị thế chỉ lưu tạm trong phiên sử dụng Streamlit. Khi chạy lại máy, '
               'bạn có thể cần nhập lại; AURA không lưu thông tin tài khoản chứng khoán.')
