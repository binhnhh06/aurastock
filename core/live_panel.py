"""Reusable SSI live panel, separate from any EOD analysis."""
from __future__ import annotations


def render_legacy_live_panel():
    import streamlit as st
    import pandas as pd
    from pathlib import Path
    from core.ssi_market_live import (get_market_symbols, request_live_symbol,
                                      read_snapshot, quote_view, date_label)

    st.markdown('#### SSI · Giá khớp theo thời gian thực')
    options = get_market_symbols()
    if not options:
        st.caption('Chưa có danh mục market_symbols.csv; hãy đồng bộ danh mục trước.')
        return

    @st.fragment(run_every='5s')
    def live_bar():
        choice = st.selectbox('Mã theo dõi live', options,
                              index=options.index('FPT') if 'FPT' in options else 0,
                              key='legacy_live_symbol_v5')
        request_live_symbol(choice)
        snapshot = read_snapshot()
        r = quote_view(snapshot, choice)
        idx = quote_view(snapshot, 'VNINDEX')
        a, b, c = st.columns([1, 1, 2])
        eod_file = Path(__file__).resolve().parent.parent / 'data' / 'ssi_cache' / 'ohlcv' / f'{choice}.csv'
        eod_close = None
        if eod_file.is_file():
            try:
                eod_close = float(pd.read_csv(eod_file, usecols=['close']).iloc[-1]['close'])
            except (ValueError, KeyError, OSError, IndexError):
                pass
        valid_unit = (r['price'] is not None and eod_close is not None
                      and eod_close > 0 and 0.5 <= r['price'] / eod_close <= 1.5)
        a.metric(f'{choice} · giá khớp', f"{r['price']:,.0f} VND" if valid_unit else 'N/A')
        b.metric('VN-Index · tick', f"{idx['price']:,.2f}" if idx['price'] is not None else 'N/A')
        c.write(f"**Trạng thái:** {r['status']} · Worker: {snapshot.get('connection', 'NO_WORKER')}")
        c.caption('Tick nhận lúc ' + date_label(r.get('received_at')))
        if r['price'] is not None and not valid_unit:
            st.warning('Giá tick cần đối chiếu đơn vị với nến SSI trước khi ghi là VND.')
        if r['status'] != 'LIVE_TICK':
            st.caption('Đây không phải giá khớp realtime xác thực. Ngoài giờ giao dịch, không có tick mới.')

    live_bar()
    st.caption('MA, RSI và điểm đánh giá phía dưới vẫn tính từ dữ liệu nến ngày SSI đã lưu.')
