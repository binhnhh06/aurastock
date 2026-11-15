"""AURA third Streamlit page: local persistent watchlist, virtual trades, daily P/L.

The page records user-declared positions, NEVER places real brokerage orders.
"""
from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo
from decimal import Decimal
from html import escape
from pathlib import Path
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.aura_brand import favicon
from core.theme import ap_dung_theme, dieu_huong_trang
from core.portfolio_store import (
    PortfolioInputError, all_trades, connect, current_eod, daily_pnl_series,
    delete_trade, holdings, normalize_symbol, parse_percent, parse_price,
    record_trade, symbol_price_history, today_vn, unwatch, watch, watched_symbols,
)

DB = ROOT / 'data' / 'portfolio' / 'aura_portfolio.sqlite3'
st.set_page_config(page_title='AURA | Danh mục đầu tư', page_icon=favicon(), layout='wide')
# AURA_CLOUD_SSI_PILOT_V92
from core.aura_cloud_bootstrap import bootstrap_cloud
bootstrap_cloud()
# AURA_CLOUD_PORTFOLIO_ISOLATION_V92
from core.aura_cloud_portfolio import is_cloud_demo, session_db
if is_cloud_demo():
    DB = session_db(st.session_state)
    st.sidebar.info('Danh mục DEMO riêng theo phiên; không lưu lâu dài sau khi đóng phiên.')


ap_dung_theme()
dieu_huong_trang()

st.markdown('''<style>
.aura-portfolio-hero{background:linear-gradient(112deg,#6C3BFF 0%,#942AEC 54%,#CF26D8 100%);
 color:white;border:2px solid #1B1233;border-radius:24px;padding:22px 28px;
 box-shadow:6px 7px 0 #1B1233;margin:2px 0 22px}
.aura-portfolio-hero h1{color:white!important;font-size:27px;margin:4px 0 7px}
.aura-portfolio-hero p{color:#F5E9FF;margin:0;font-size:13px}
.aura-help-box{background:#FFD43B;border:2px solid #1B1233;box-shadow:4px 4px 0 #1B1233;
 border-radius:16px;padding:11px 15px;color:#211534;margin:12px 0 22px}
.aura-portfolio-eyebrow{font-size:11px;letter-spacing:.14em;font-weight:800;color:#F1DBFF}
.aura-pill{display:inline-block;background:#DDF9A4;border:1.5px solid #1B1233;
 color:#1B1233;border-radius:8px;padding:4px 9px;font-size:12px;font-weight:750}
.aura-note{font-size:12px;color:#655C79;margin-top:4px}
[data-testid="stTabs"] button{font-weight:800}
</style>''', unsafe_allow_html=True)

st.markdown('''<section class="aura-portfolio-hero">
<div class="aura-portfolio-eyebrow">03 · QUẢN LÝ VỊ THẾ</div>
<h1>AURA · DANH MỤC ĐẦU TƯ</h1>
<p>Theo dõi cổ phiếu · Ghi nhận mua/bán giả lập · Giá vốn bình quân · Lãi/lỗ theo ngày</p>
</section>''', unsafe_allow_html=True)
st.markdown('''<div class="aura-help-box"><b>Dữ liệu do người dùng tự nhập</b> · AURA chỉ ghi nhận
lịch sử giao dịch để tính toán; không gửi lệnh lên SSI hay công ty chứng khoán.
<b>Mã chỉ theo dõi: vốn = 0, lãi/lỗ = 0.</b> Biểu đồ chỉ xuất hiện sau giao dịch MUA/BÁN được ghi nhận.</div>''',
            unsafe_allow_html=True)


def vn_money(value, *, decimals=0):
    if value is None:
        return '—'
    raw = f'{float(value):,.{decimals}f}'
    return raw.replace(',', '#').replace('.', ',').replace('#', '.') + ' đ'


def vn_num(value):
    return f'{int(value):,}'.replace(',', '.')


def stock_quote(symbol):
    """Local cached EOD for all; optional confirmed live tick for selected symbol."""
    px, eod_day = current_eod(ROOT, symbol)
    if px is None:
        return None, 'Chưa có SSI EOD', None
    source = f'SSI EOD · {eod_day:%d/%m/%Y}'
    try:
        from core.ssi_market_live import read_snapshot, quote_view, request_live_symbol
        # Don't subscribe many symbols automatically: avoid SSI key subscription load.
        if symbol == st.session_state.get('aura_portfolio_selected_symbol'):
            request_live_symbol(symbol)
        rec = quote_view(read_snapshot(), symbol)
        live_raw = rec.get('price')
        received = rec.get('received_at')
        if live_raw is not None and received is not None:
            live = Decimal(str(live_raw))
            when = received.date() if received.tzinfo is None else received.astimezone(ZoneInfo('Asia/Ho_Chi_Minh')).date()
            if live.is_finite() and px * Decimal('.5') <= live <= px * Decimal('1.5') and when >= eod_day:
                is_today = when == today_vn() and rec.get('status') == 'LIVE_TICK'
                return live, (f'SSI realtime · {when:%d/%m/%Y}' if is_today else
                              f'SSI khớp gần nhất · {when:%d/%m/%Y}'), when
    except (ValueError, TypeError, AttributeError, ImportError, OSError, KeyError):
        pass
    return px, source, eod_day


try:
    with connect(DB):
        pass
    # AURA_FLOW_V6: add the selected symbol to watchlist only; never buy.
    _flow_incoming = st.session_state.pop("aura_flow_pending_portfolio", None)
    if _flow_incoming:
        _flow_symbol = normalize_symbol(str(_flow_incoming))
        watch(DB, _flow_symbol)
        st.session_state["aura_portfolio_selected_symbol"] = _flow_symbol
    watched = watched_symbols(DB)
    trades = all_trades(DB)
    book = holdings(trades)
except Exception as exc:
    st.error(f'Không thể mở danh mục lưu trên máy ({type(exc).__name__}). '
             'Kiểm tra quyền ghi thư mục data/portfolio và không xóa file SQLite.')
    st.stop()

# Include held symbols even if removed from watchlist. Closed trades remain in history only.
open_symbols = {sym for sym, state in book.items() if state['quantity'] > 0}
listed = sorted(set(watched) | open_symbols)
all_trade_symbols = sorted({r['symbol'] for r in trades})
market = {}
for symbol in listed:
    market[symbol] = stock_quote(symbol)

invested = sum((s['cost_basis'] for s in book.values() if s['quantity'] > 0), Decimal(0))
realized_total = sum((s['realized'] for s in book.values()), Decimal(0))
market_value = Decimal(0)
missing_prices = []
for sym, s in book.items():
    if s['quantity'] > 0:
        q = market.get(sym, (None, '', None))[0]
        if q is None:
            missing_prices.append(sym)
        else:
            market_value += q * s['quantity']
unrealized_total = (market_value - invested) if not missing_prices else None
cumulative_total = (realized_total + unrealized_total) if unrealized_total is not None else None

m1, m2, m3, m4 = st.columns(4)
m1.metric('Mã đang theo dõi', vn_num(len(listed)))
m2.metric('Vốn vị thế đang mở', vn_money(invested))
m3.metric('Lãi/lỗ đã thực hiện', vn_money(realized_total))
m4.metric('Tổng lãi/lỗ ước tính', vn_money(cumulative_total))
if missing_prices:
    st.warning('Chưa có giá SSI cho vị thế ' + ', '.join(missing_prices) +
               '. Tổng lãi/lỗ chưa tính đủ nên tạm không hiển thị.')
if st.button('Làm mới giá SSI', key='aura_portfolio_refresh_prices'):
    st.rerun()
st.caption('Lãi/lỗ tạm tính = giá thị trường − giá vốn còn lại; lãi/lỗ đã thực hiện tính từ các lệnh BÁN đã nhập. '
           'Phí mua/bán và thuế chỉ tính theo mức bạn tự khai báo trong từng giao dịch. '
           'Chưa tính cổ tức, quyền cổ đông, trượt giá và các khoản tiền nộp/rút khác.')

watch_tab, trade_tab, chart_tab = st.tabs([
    'Danh sách & theo dõi', 'Ghi nhận MUA / BÁN', 'Biểu đồ lãi/lỗ theo ngày'
])

with watch_tab:
    st.subheader('Danh sách cổ phiếu lưu trên máy')
    with st.form('aura_add_to_watch', clear_on_submit=True):
        p1, p2 = st.columns([4, 1])
        symbol_to_add = p1.text_input('Thêm mã chỉ theo dõi', placeholder='FPT, HPG, VCB...', max_chars=10)
        add = p2.form_submit_button('Thêm theo dõi', use_container_width=True)
        if add:
            try:
                watch(DB, symbol_to_add)
                st.success('Đã lưu mã vào danh sách theo dõi. Vốn và lãi/lỗ vẫn bằng 0 khi chưa mua.')
                st.rerun()
            except PortfolioInputError as exc:
                st.error(str(exc))
    if listed:
        rows = []
        for sym in listed:
            state = book.get(sym, {})
            qty = state.get('quantity', 0)
            cost = state.get('cost_basis', Decimal(0))
            realized = state.get('realized', Decimal(0))
            px, source, asof = market.get(sym, (None, 'Chưa có SSI EOD', None))
            avg = cost / qty if qty else None
            unreal = px * qty - cost if px is not None and qty else (None if qty else Decimal(0))
            rows.append({
                'Mã': sym,
                'Trạng thái': ('ĐANG NẮM GIỮ' if qty else ('ĐÃ BÁN HẾT' if state.get('sell_count', 0) else 'CHỈ THEO DÕI')),
                'Số lượng (CP)': qty,
                'Giá vốn bình quân (đ/CP)': float(avg) if avg is not None else None,
                'Giá thị trường (đ/CP)': float(px) if px is not None else None,
                'Lãi/lỗ tạm tính (đ)': float(unreal) if unreal is not None else None,
                'Đã thực hiện (đ)': float(realized),
                'Nguồn giá': source,
            })
        frame = pd.DataFrame(rows)
        st.dataframe(frame, hide_index=True, use_container_width=True, height=min(520, 65+len(rows)*35),
                     column_config={
                         'Số lượng (CP)': st.column_config.NumberColumn(format='%,d'),
                         'Giá vốn bình quân (đ/CP)': st.column_config.NumberColumn(format='%,.2f'),
                         'Giá thị trường (đ/CP)': st.column_config.NumberColumn(format='%,.2f'),
                         'Lãi/lỗ tạm tính (đ)': st.column_config.NumberColumn(format='%,.0f'),
                         'Đã thực hiện (đ)': st.column_config.NumberColumn(format='%,.0f'),
                     })
        st.download_button('Xuất danh mục CSV', frame.to_csv(index=False).encode('utf-8-sig'),
                           file_name='AURA_DanhMuc.csv', mime='text/csv')
        st.caption('Mua thêm hoặc bán: chọn mã tại tab **Ghi nhận MUA / BÁN**. '
                   'Giao dịch được lưu lại, không mất khi khởi động lại Streamlit.')
        with st.expander('Bỏ mã khỏi danh sách theo dõi', expanded=False):
            unw_sym = st.selectbox('Mã cần bỏ theo dõi', listed, key='aura_unwatch_sym')
            if unw_sym in open_symbols:
                st.warning('Mã này còn cổ phiếu đang nắm giữ nên vẫn xuất hiện trong danh sách. '
                           'Bỏ theo dõi không xóa giao dịch hay vị thế.')
            if st.button('Bỏ theo dõi mã này', key='aura_unwatch_btn'):
                unwatch(DB, unw_sym)
                st.rerun()
    else:
        st.info('Chưa có mã nào. Bạn có thể **thêm theo dõi trước**; vốn/lãi/lỗ sẽ vẫn là 0.')

with trade_tab:
    st.subheader('Ghi nhận giao dịch trên danh mục ảo')
    st.caption('Bạn ghi lại giao dịch đã thực hiện hoặc kịch bản giả lập. '
               'Nút MUA/BÁN ở đây **chỉ lưu lịch sử**, không gửi lệnh tới công ty chứng khoán.')
    selected_options = sorted(set(listed) | set(all_trade_symbols))
    default_symbol = selected_options[0] if selected_options else 'FPT'
    stock = st.text_input('Mã cổ phiếu', value=default_symbol,
                          max_chars=10, key='aura_portfolio_selected_symbol').strip().upper()
    current_qty = book.get(stock, {}).get('quantity', 0)
    if stock:
        px, source, _ = stock_quote(stock)
        st.caption(f'Đang giữ **{vn_num(current_qty)} CP** · Giá SSI tham khảo: '
                   f'**{vn_money(px)}** · {source}.')
    with st.form('aura_portfolio_trade_form', clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        trade_day = c1.date_input('Ngày giao dịch', value=today_vn(), max_value=today_vn())
        quantity = c2.number_input('Số lượng giao dịch (CP)', min_value=1,
                                   max_value=1_000_000_000, step=1, value=100)
        raw_price = c3.text_input('Giá giao dịch (có thể nhập lẻ)', value='',
                                  placeholder='Ví dụ 20,84')
        price_unit = st.radio('Đơn vị của giá vừa nhập', ['Nghìn đồng/CP', 'Đồng/CP'], horizontal=True)
        with st.expander('Phí giao dịch và thuế (để trống mặc định = 0)', expanded=False):
            x, y = st.columns(2)
            fee = x.number_input('Phí giao dịch (%)', min_value=0.0, max_value=10.0,
                                 value=0.0, step=0.05, format='%.2f')
            tax = y.number_input('Thuế/chi phí khi bán (%)', min_value=0.0, max_value=10.0,
                                 value=0.0, step=0.05, format='%.2f')
            st.caption('Các mức phí/thuế do bạn tự nhập; AURA không mặc định biểu phí của công ty chứng khoán.')
        buy_btn, sell_btn = st.columns(2)
        buy = buy_btn.form_submit_button('Ghi nhận MUA / MUA THÊM', use_container_width=True,
                                         type='primary')
        sell = sell_btn.form_submit_button('Ghi nhận BÁN', use_container_width=True)
        if buy or sell:
            try:
                sym = normalize_symbol(stock)
                price = parse_price(raw_price, thousands=price_unit == 'Nghìn đồng/CP')
                if buy:
                    record_trade(DB, sym, 'BUY', int(quantity), price, trade_day,
                                 fee_pct=fee, tax_pct=0)
                    st.success(f'Đã ghi nhận MUA {vn_num(quantity)} CP {sym} tại {vn_money(price)}/CP. '
                               'Số lượng và giá vốn bình quân sẽ được tính lại.')
                else:
                    record_trade(DB, sym, 'SELL', int(quantity), price, trade_day,
                                 fee_pct=fee, tax_pct=tax)
                    st.success(f'Đã ghi nhận BÁN {vn_num(quantity)} CP {sym} tại {vn_money(price)}/CP. '
                               'Lãi/lỗ bán được ghi nhận trong lịch sử.')
                st.rerun()
            except (PortfolioInputError, ValueError) as exc:
                st.error(str(exc))
    st.subheader('Lịch sử giao dịch')
    if trades:
        history = pd.DataFrame([{
            'ID': int(t['id']), 'Ngày': t['trade_date'], 'Mã': t['symbol'],
            'Loại': 'MUA' if t['side'] == 'BUY' else 'BÁN', 'Số lượng': t['quantity'],
            'Giá (đ/CP)': float(Decimal(t['price_vnd'])),
            'Phí (%)': float(Decimal(t['fee_pct'])),
            'Thuế/chi phí bán (%)': float(Decimal(t['tax_pct'])),
        } for t in trades]).sort_values(['Ngày', 'ID'], ascending=False)
        st.dataframe(history, use_container_width=True, hide_index=True, height=320)
        st.download_button('Xuất lịch sử giao dịch CSV', history.to_csv(index=False).encode('utf-8-sig'),
                           file_name='AURA_LichSuGiaoDich.csv', mime='text/csv')
        with st.expander('Sửa lỗi nhập nhầm: xóa một giao dịch', expanded=False):
            selected_id = st.selectbox('ID giao dịch cần xóa', history['ID'].astype(int).tolist())
            confirmed = st.checkbox('Tôi xác nhận muốn xóa giao dịch đã chọn (không thể hoàn tác)')
            if st.button('Xóa giao dịch đã chọn', disabled=not confirmed):
                try:
                    delete_trade(DB, selected_id)
                    st.success('Đã xóa giao dịch; lãi/lỗ và giá vốn sẽ được tính lại.')
                    st.rerun()
                except PortfolioInputError as exc:
                    st.error(str(exc))
    else:
        st.info('Chưa có giao dịch MUA/BÁN nào. Các mã chỉ theo dõi chưa tạo lợi nhuận hay thua lỗ.')

with chart_tab:
    st.subheader('Biểu đồ lãi/lỗ theo ngày')
    st.caption('Tách **lãi/lỗ lũy kế** và **thay đổi lãi/lỗ trong ngày**; '
               'tính theo lịch sử giao dịch bạn tự nhập và giá đóng cửa SSI EOD. '
               'Không lấy hiệu suất cổ phiếu làm hiệu suất danh mục khi chưa có giao dịch.')
    if not trades:
        st.metric('Lãi/lỗ danh mục chỉ theo dõi', '0 đ')
        st.info('Chưa có giao dịch nên không vẽ đường hiệu suất. '
                'Thêm lệnh MUA hoặc BÁN trong tab Ghi nhận giao dịch để bắt đầu theo dõi lãi/lỗ hằng ngày.')
    else:
        with st.spinner('Đang tổng hợp giá SSI và lịch sử giao dịch...'):
            historical = {sym: symbol_price_history(ROOT, sym) for sym in all_trade_symbols}
            timeline, unavailable = daily_pnl_series(trades, historical)
        if unavailable:
            st.warning('Không có giá SSI EOD tại một số thời điểm để định giá: ' + ', '.join(unavailable) +
                       '. Những ngày thiếu giá sẽ để trống, không tự xem bằng 0.')
        if timeline:
            tbl = pd.DataFrame(timeline)
            limit = st.selectbox('Khoảng thời gian biểu đồ',
                                 ['90 ngày', '1 năm', '3 năm', 'Toàn bộ'], index=1)
            bounds = {'90 ngày': 90, '1 năm': 365, '3 năm': 1095}
            if limit in bounds:
                from datetime import timedelta
                cutoff = today_vn() - timedelta(days=bounds[limit])
                tbl = tbl.loc[tbl['Ngày'] >= cutoff].copy()
            if tbl.empty or tbl['Lãi/lỗ lũy kế (VND)'].isna().all():
                st.info('Chưa đủ dữ liệu giá SSI và lịch sử mua/bán trong khoảng đã chọn để vẽ biểu đồ.')
            else:
                # AURA_RANK_PNL_V4_LINE_CHART
                from core.aura_pnl_line import build_portfolio_line_figures
                fig, dfig, num_dates = build_portfolio_line_figures(tbl)
                if num_dates == 1:
                    st.info('Mới có một ngày để tính lãi/lỗ: hiển thị một điểm dữ liệu. '
                            'Khi có thêm phiên EOD, biểu đồ sẽ nối các điểm thành đường.')
                st.plotly_chart(fig, use_container_width=True)
                st.plotly_chart(dfig, use_container_width=True)
                st.caption('Hai biểu đồ thể hiện LÃI/LỖ bằng VND, không phải lợi suất (%) của danh mục. '
                           'Muốn tính lợi suất đúng khi mua thêm/bán hoặc nộp/rút vốn, '
                           'cần điều chỉnh dòng tiền và định giá tại từng thời điểm.')
                st.caption('Ngày không có phiên chứng khoán được giữ nguyên giá đóng cửa cuối cùng khả dụng. '
                           'Biểu đồ dùng SSI EOD (không phải biến động intraday); không gồm cổ tức, quyền cổ đông, '
                           'lạm phát và các khoản tiền bên ngoài. Nếu giá chưa điều chỉnh chia tách, '
                           'lãi/lỗ lịch sử có thể sai lệch và cần đối chiếu thêm.')
                st.download_button('Tải bảng lãi/lỗ từng ngày CSV',
                                   tbl.to_csv(index=False).encode('utf-8-sig'),
                                   file_name='AURA_LaiLo_HangNgay.csv', mime='text/csv')

st.divider()
st.caption('Danh mục lưu cục bộ tại `data/portfolio/aura_portfolio.sqlite3`. '
           'Khi sao lưu hoặc chuyển máy, hãy sao lưu file này cùng dự án; không chứa mật khẩu tài khoản chứng khoán. '
           'Dữ liệu không tự đồng bộ qua nhiều thiết bị hoặc lưu ổn định khi triển khai trên hosting không có ổ đĩa bền vững.')
