"""AURA foreign-flow & sourced policy panel (EOD; read-only).

Data is populated by scripts/aura_sync_foreign.py using SSI FastConnect V3.
Never display absent financial fields as zero, never call SSI from public UI.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
import pandas as pd

FLOW_REL = Path('data/ssi_cache/foreign_flow_eod.csv')
POLICY_REL = Path('data/macro/policy_events.csv')
FLOW_COLUMNS = ['scope', 'code', 'date', 'buy_value_vnd', 'sell_value_vnd',
                'net_value_vnd', 'buy_volume', 'sell_volume', 'net_volume',
                'source', 'retrieved_at']


def read_foreign(root: Path) -> pd.DataFrame:
    path = Path(root) / FLOW_REL
    if not path.is_file():
        return pd.DataFrame(columns=FLOW_COLUMNS)
    try:
        df = pd.read_csv(path, encoding='utf-8-sig', dtype={'scope':str, 'code':str})
    except (OSError, UnicodeError, ValueError, pd.errors.ParserError):
        return pd.DataFrame(columns=FLOW_COLUMNS)
    if not {'scope', 'code', 'date', 'source'}.issubset(df.columns):
        return pd.DataFrame(columns=FLOW_COLUMNS)
    for k in FLOW_COLUMNS:
        if k not in df:
            df[k] = float('nan') if k.endswith('_vnd') or k.endswith('_volume') else ''
    df = df[FLOW_COLUMNS].copy()
    df['scope'] = df['scope'].astype(str).str.upper()
    df['code'] = df['code'].astype(str).str.upper().str.strip()
    df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.normalize()
    for k in ('buy_value_vnd', 'sell_value_vnd', 'net_value_vnd',
              'buy_volume', 'sell_volume', 'net_volume'):
        df[k] = pd.to_numeric(df[k], errors='coerce')
    df['source'] = df['source'].fillna('').astype(str).str.strip()
    df = df[df['date'].notna() & df['source'].ne('') & df['scope'].isin(['INDEX', 'STOCK']) &
            df['code'].str.fullmatch(r'[A-Z0-9]{2,12}')]
    df = df.sort_values('date').drop_duplicates(['scope','code','date'], keep='last')
    return df.reset_index(drop=True)


def _money(v):
    return 'Chưa có dữ liệu' if pd.isna(v) else f'{float(v) / 1e9:+,.2f} tỷ VND'


def _amount(v):
    return 'Chưa có dữ liệu' if pd.isna(v) else f'{float(v) / 1e9:,.2f} tỷ VND'


def _series_block(table: pd.DataFrame, title: str, *, cap=30):
    import streamlit as st
    if table.empty:
        st.info(f'Chưa có dữ liệu khối ngoại của {title}.')
        return
    table = table.sort_values('date').tail(cap)
    last = table.iloc[-1]
    st.markdown(f'#### {title} · phiên {last["date"]:%d/%m/%Y}')
    cols = st.columns(3)
    cols[0].metric('Khối ngoại mua', _amount(last['buy_value_vnd']))
    cols[1].metric('Khối ngoại bán', _amount(last['sell_value_vnd']))
    cols[2].metric('Mua ròng (+) / Bán ròng (−)', _money(last['net_value_vnd']))
    latest_age = (date.today() - last['date'].date()).days
    if latest_age >= 4:
        st.warning(f'Dữ liệu khối ngoại đang cũ {latest_age} ngày lịch. Không xem là số liệu mới nhất.')
    good = table.dropna(subset=['net_value_vnd'])
    if len(good) >= 2:
        series = good.set_index('date')['net_value_vnd'] / 1e9
        st.bar_chart(series, height=240, y_label='Mua ròng / bán ròng (tỷ VND)')
    else:
        st.caption('Chưa đủ số phiên có giá trị mua/bán ròng để vẽ xu hướng.')
    st.caption('Nguồn: SSI FastConnect V3 · EOD; số liệu chỉ trong phạm vi chỉ số/mã được ghi trên bảng.')


def _policy_section(root: Path):
    import streamlit as st
    st.markdown('#### Nhật ký chính sách & chỉ báo vĩ mô (có nguồn)')
    policy = Path(root) / POLICY_REL
    if not policy.is_file():
        st.caption('Chưa có bảng sự kiện vĩ mô được kiểm chứng. Có thể bổ sung theo mẫu data/macro/policy_events_template.csv. Không tự sinh tin tức hoặc chỉ số.')
    else:
        try:
            events = pd.read_csv(policy, encoding='utf-8-sig')
            required = {'date','topic','headline','source','url','note'}
            if required.issubset(events.columns):
                events['date'] = pd.to_datetime(events['date'], errors='coerce')
                events = events[events['date'].notna() & events['source'].notna() & events['url'].notna()]
                events = events.sort_values('date', ascending=False).head(20)
                if not events.empty:
                    events['date'] = events['date'].dt.strftime('%d/%m/%Y')
                    st.dataframe(events[['date','topic','headline','source','note','url']], hide_index=True, use_container_width=True)
                else:
                    st.caption('Chưa có sự kiện hợp lệ có nguồn và ngày công bố.')
            else:
                st.warning('policy_events.csv thiếu cột bắt buộc; xem file mẫu.')
        except (OSError, ValueError, UnicodeError, pd.errors.ParserError) as exc:
            st.warning(f'Không đọc được nhật ký chính sách: {type(exc).__name__}')
    st.markdown('Nguồn đối chiếu chính sách: [Ngân hàng Nhà nước](https://www.sbv.gov.vn/) · '
                '[Cục Thống kê](https://www.nso.gov.vn/) · '
                '[Bộ Tài chính](https://mof.gov.vn/).')


def render_macro_panel(root: Path, symbol: str | None = None):
    import streamlit as st
    st.markdown('### 🌍 Dòng tiền khối ngoại · SSI EOD')
    st.caption('Dữ liệu **mua, bán, mua ròng/bán ròng** theo ngày; khác với giá SSI WebSocket realtime. '
               'Khối ngoại chỉ là yếu tố bối cảnh, không tự tạo tín hiệu MUA.')
    df = read_foreign(root)
    if df.empty:
        st.info('Chưa có snapshot khối ngoại SSI trên máy/Cloud. Chạy scripts/aura_sync_foreign.py để lưu bảng EOD; khi không có dữ liệu AURA để trống thay vì điền 0.')
    else:
        indices = df[df['scope'] == 'INDEX']
        options = [x for x in ['VNINDEX','VN30','HNXINDEX','UPCOMINDEX'] if x in indices['code'].values]
        options += [x for x in sorted(indices['code'].unique()) if x not in options]
        if options:
            chosen = st.selectbox('Phạm vi theo dõi', options, key='aura_foreign_index')
            _series_block(indices[indices['code'] == chosen], f'Khối ngoại trong phạm vi {chosen}')
            if chosen == 'VNINDEX':
                st.caption('VNINDEX chủ yếu phản ánh cổ phiếu trên HOSE, không phải tổng hợp đầy đủ cả HNX/UPCOM.')
        else:
            st.info('Chưa có chỉ số thị trường trong bảng khối ngoại.')
        stocks = df[df['scope'] == 'STOCK']
        if symbol:
            symbol = str(symbol).strip().upper()
            subset = stocks[stocks['code'] == symbol]
            if not subset.empty:
                _series_block(subset, f'Cổ phiếu {symbol}')
            else:
                st.caption(f'Chưa đồng bộ giao dịch ngoại cho {symbol}. Có thể chạy lệnh --symbols {symbol} ở máy cập nhật.')
        if not stocks.empty:
            newest = stocks['date'].max()
            newest_df = stocks[(stocks['date'] == newest) & stocks['net_value_vnd'].notna()].copy()
            if not newest_df.empty:
                newest_df = newest_df.sort_values('net_value_vnd', ascending=False)
                st.markdown(f'**Mã mua/bán ròng trong mẫu đã tải · {newest:%d/%m/%Y}**')
                st.caption('Đây chỉ là những mã đã được đồng bộ riêng, KHÔNG phải Top toàn thị trường.')
                show = newest_df[['code','buy_value_vnd','sell_value_vnd','net_value_vnd']].head(30).copy()
                for c in ['buy_value_vnd','sell_value_vnd','net_value_vnd']:
                    show[c] = (show[c] / 1e9).round(2)
                st.dataframe(show.rename(columns={'code':'Mã', 'buy_value_vnd':'Mua (tỷ)',
                            'sell_value_vnd':'Bán (tỷ)', 'net_value_vnd':'Ròng (tỷ)'}),
                             hide_index=True, use_container_width=True)
        st.download_button('Xuất bảng khối ngoại CSV',
                           df.to_csv(index=False).encode('utf-8-sig'),
                           'aura_foreign_flow_eod.csv', mime='text/csv', key='aura_foreign_export')
    _policy_section(root)

# AURA_FOREIGN_MISSING_GROSS_V3
# Read-time quality guard; does not change original CSV or SSI API results.
_aura_original_read_foreign_v3 = read_foreign
def read_foreign(root):
    frame = _aura_original_read_foreign_v3(root)
    if frame.empty or not {'scope','buy_value_vnd','sell_value_vnd','net_value_vnd'}.issubset(frame.columns):
        return frame
    frame = frame.copy()
    bad = (frame['scope'].eq('INDEX') & frame['buy_value_vnd'].eq(0) &
           frame['sell_value_vnd'].eq(0) & frame['net_value_vnd'].notna() &
           frame['net_value_vnd'].abs().gt(1e6))
    frame.loc[bad, ['buy_value_vnd','sell_value_vnd']] = float('nan')
    return frame
