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


def _foreign_signal_table(df: pd.DataFrame):
    """Bảng tín hiệu mua/bán ròng khối ngoại theo 2 sàn, 10 phiên gần nhất.

    Dùng lại đúng dữ liệu EOD đã có trong foreign_flow_eod.csv (scope=INDEX),
    không gọi thêm API, không tự sinh số liệu mới.

    AURA_V110_DROP_UPCOM: bỏ hẳn cột UPCOMINDEX — đã kiểm chứng trực tiếp
    bằng script debug rằng SSI FastConnect Index Summary không trả dữ liệu
    khối ngoại thật cho UPCOMINDEX (mọi field liên quan đều = 0, kể cả các
    field độ rộng thị trường khác), nên hiển thị cột này chỉ gây hiểu nhầm.
    """
    import streamlit as st
    st.markdown('#### 📊 Tín hiệu mua/bán ròng khối ngoại · 2 sàn · 10 phiên gần nhất')
    codes = ['VNINDEX', 'HNXINDEX']
    rename = {'VNINDEX': 'VNINDEX (HOSE)', 'HNXINDEX': 'HNXINDEX (HNX)'}
    indices = df[(df['scope'] == 'INDEX') & (df['code'].isin(codes))]
    if indices.empty:
        pivot = pd.DataFrame(columns=codes)
    else:
        pivot = indices.pivot_table(index='date', columns='code', values='net_value_vnd', aggfunc='last')
        pivot = pivot.sort_index().tail(10)
    pivot = pivot.reindex(columns=codes)  # khoá cứng VNINDEX/HNXINDEX, không rơi cột
    if pivot.empty:
        st.caption('Chưa có phiên nào có dữ liệu khối ngoại cho 2 sàn (VNINDEX, HNXINDEX).')
        return

    # AURA_V109_UPCOM_ZERO_NOTE: cơ chế phòng hờ chung — nếu SSI Index
    # Summary trả về đúng 0/0/0 mọi phiên cho chỉ số nào (như từng thấy ở
    # UPCOMINDEX trước khi bỏ cột này), đây là giới hạn của nguồn dữ liệu,
    # KHÔNG phải tín hiệu khối ngoại trung lập thật. Vẫn hiển thị đúng số
    # 0 đó (không tự ý xóa/thay bằng rỗng) nhưng ghi chú
    # rõ ràng để người đọc không hiểu nhầm.
    ssi_zero_codes = []
    cols = st.columns(len(codes))
    for col_widget, code in zip(cols, codes):
        series = pivot[code].dropna() if code in pivot else pd.Series(dtype=float)
        if series.empty:
            col_widget.metric(rename.get(code, code), 'Chưa có dữ liệu')
            continue
        last_val = float(series.iloc[-1])
        all_zero = len(series) >= 3 and (series == 0).all()
        if all_zero:
            ssi_zero_codes.append(rename.get(code, code))
            col_widget.metric(f'{rename.get(code, code)} · SSI trả về 0',
                               '0 tỷ', 'Giới hạn dữ liệu SSI, không phải tín hiệu thật')
            continue
        positive = last_val > 0
        streak = 0
        for v in series.iloc[::-1]:
            if v == 0:
                break
            if (v > 0) == positive:
                streak += 1
            else:
                break
        label = 'Mua ròng' if positive else ('Bán ròng' if last_val < 0 else 'Cân bằng')
        col_widget.metric(f'{rename.get(code, code)} · {label}',
                           f'{last_val / 1e9:+,.2f} tỷ', f'{streak} phiên liên tiếp cùng chiều')

    if ssi_zero_codes:
        st.caption(f'⚠️ {", ".join(ssi_zero_codes)}: SSI FastConnect trả về đúng 0 cho mọi phiên ở cấp '
                   'chỉ số — đây là giới hạn của nguồn dữ liệu (SSI không theo dõi khối ngoại cấp chỉ số '
                   'cho sàn này), KHÔNG phải tín hiệu khối ngoại trung lập/đứng yên thật.')

    display = (pivot / 1e9).round(2)
    display.index = [d.strftime('%d/%m/%Y') for d in display.index]
    display = display.rename(columns=rename)

    view = st.radio('Xem dạng', ['Bảng', 'Biểu đồ'], horizontal=True, key='aura_foreign_3san_view')

    if view == 'Biểu đồ':
        chart_df = display.copy()
        if chart_df.dropna(how='all').empty:
            st.caption('Chưa có số liệu để vẽ biểu đồ.')
        else:
            st.bar_chart(chart_df, height=320, y_label='Mua ròng (+) / bán ròng (−) · tỷ VND')
    else:
        # AURA_V111_FOREIGN_TOP_GENZ: màu + header đồng bộ với bảng màu
        # theme app (core/theme.py: MAU["do"]/MAU["xanh_la"]/MAU["muc"]).
        MAU_DO = '#E5254B'
        MAU_XANH_LA = '#078A4F'
        MAU_CHU = '#1B1233'
        MAU_LUOI = '#EFE8FF'

        def _color(v):
            if pd.isna(v):
                return ''
            if v > 0:
                return f'background-color: rgba(7,138,79,0.16); color: {MAU_XANH_LA}; font-weight:700'
            if v < 0:
                return f'background-color: rgba(229,37,75,0.14); color: {MAU_DO}; font-weight:700'
            return ''

        def _text(v):
            return '—' if pd.isna(v) else f'{v:+,.2f}'

        # Tự định dạng chuỗi hiển thị và bảng màu riêng (không phụ thuộc
        # Styler.format của từng bản pandas/Streamlit), tránh cột trống
        # hiện chữ "None" khi một sàn chưa có dữ liệu.
        map_fn = getattr(display, 'map', None) or display.applymap
        text_df = map_fn(_text)
        color_df = map_fn(_color)
        try:
            styled = (text_df.style
                      .apply(lambda _: color_df, axis=None)
                      .set_table_styles([
                          {'selector': 'th', 'props': [
                              ('background-color', MAU_CHU), ('color', '#FFFFFF'),
                              ('font-weight', '800'), ('text-align', 'center'),
                              ('border', f'1px solid {MAU_CHU}')]},
                          {'selector': 'td', 'props': [
                              ('text-align', 'right'), ('font-weight', '600'),
                              ('border-bottom', f'1px solid {MAU_LUOI}')]},
                      ]))
            st.dataframe(styled, use_container_width=True)
        except (ValueError, TypeError, AttributeError):
            st.dataframe(text_df, use_container_width=True)

    st.caption('Đơn vị: tỷ VND mua ròng (+) / bán ròng (−) theo chỉ số mỗi sàn · xanh = mua ròng, đỏ = bán ròng. '
               'Đây vẫn là dữ liệu EOD (chốt phiên), không phải tín hiệu realtime trong phiên.')


def _top_stock_flow_chart(stocks: pd.DataFrame, *, top_n: int = 10):
    """Top mua/bán ròng khối ngoại theo mã (kiểu 24HMoney) — xem được cả
    dạng Bảng lẫn Biểu đồ (giống bảng tín hiệu 2 sàn ở trên), chỉ trong số
    các mã đã đồng bộ riêng lẻ qua aura_sync_foreign.py — KHÔNG phải Top
    toàn thị trường, nên luôn ghi rõ phạm vi này.
    """
    import streamlit as st
    st.markdown('#### 📈 Top mua/bán ròng khối ngoại theo mã')
    if stocks.empty:
        st.caption('Chưa có dữ liệu khối ngoại theo từng mã cổ phiếu riêng lẻ.')
        return
    period_label = st.radio('Khung thời gian', ['1 phiên', '7 phiên', '28 phiên'],
                             horizontal=True, key='aura_foreign_top_period')
    n_sessions = {'1 phiên': 1, '7 phiên': 7, '28 phiên': 28}[period_label]
    all_dates = sorted(stocks['date'].dropna().unique())
    if not all_dates:
        st.caption('Chưa có phiên dữ liệu nào.')
        return
    window_dates = all_dates[-n_sessions:]
    window = stocks[stocks['date'].isin(window_dates)]
    net_agg = window.dropna(subset=['net_value_vnd']).groupby('code')['net_value_vnd'].sum()
    if net_agg.empty:
        st.caption('Chưa đủ dữ liệu mua/bán ròng trong khung thời gian này.')
        return
    buy_agg = window.groupby('code')['buy_value_vnd'].sum(min_count=1)
    sell_agg = window.groupby('code')['sell_value_vnd'].sum(min_count=1)

    agg_ty = (net_agg / 1e9).round(2)
    top_buy = agg_ty[agg_ty > 0].sort_values(ascending=False).head(top_n)
    top_sell = agg_ty[agg_ty < 0].sort_values().head(top_n)
    combo = pd.concat([top_buy.sort_values(ascending=False), top_sell.sort_values()])
    if combo.empty:
        st.caption('Chưa có mã nào mua/bán ròng rõ rệt trong khung thời gian này.')
        return

    # AURA_V111_FOREIGN_TOP_GENZ: bảng màu + chữ theo đúng theme app
    # (core/theme.py: MAU["do"]/MAU["xanh_la"]/MAU["muc"]/MAU["tim"]...)
    MAU_DO = '#E5254B'
    MAU_XANH_LA = '#078A4F'
    MAU_CHU = '#1B1233'
    MAU_LUOI = '#EFE8FF'
    MAU_TIM = '#6C3BFF'
    MAU_NEN = '#F4EFFF'

    view = st.radio('Xem dạng', ['Bảng', 'Biểu đồ'], horizontal=True, key='aura_foreign_top_view')

    if view == 'Bảng':
        rows = []
        for code, net_ty in combo.items():
            rows.append({
                'Mã': code,
                'Mua (tỷ)': round(buy_agg.get(code, float('nan')) / 1e9, 2),
                'Bán (tỷ)': round(sell_agg.get(code, float('nan')) / 1e9, 2),
                'Ròng (tỷ)': net_ty,
            })
        table = pd.DataFrame(rows).set_index('Mã')

        def _fmt(v):
            return '—' if pd.isna(v) else f'{v:+,.2f}'

        def _row_color(row):
            net = row['Ròng (tỷ)']
            if pd.isna(net):
                return [''] * len(row)
            bg = (f'background-color: rgba(7,138,79,0.16); color: {MAU_XANH_LA}; font-weight:700'
                  if net > 0 else
                  f'background-color: rgba(229,37,75,0.14); color: {MAU_DO}; font-weight:700')
            return [bg] * len(row)

        try:
            styled = (table.style
                      .apply(_row_color, axis=1)
                      .format(_fmt)
                      .set_table_styles([
                          {'selector': 'th', 'props': [
                              ('background-color', MAU_CHU), ('color', '#FFFFFF'),
                              ('font-weight', '800'), ('text-align', 'center'),
                              ('border', f'1px solid {MAU_CHU}')]},
                          {'selector': 'td', 'props': [
                              ('text-align', 'right'), ('font-weight', '600'),
                              ('border-bottom', f'1px solid {MAU_LUOI}')]},
                      ]))
            st.dataframe(styled, use_container_width=True)
        except (ValueError, TypeError, AttributeError):
            st.dataframe(table, use_container_width=True)
        st.caption(f'Sắp xếp theo mua ròng (+) giảm dần · {period_label} gần nhất.')
    else:
        try:
            import io
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            # AURA_V113_CHART_FIXSIZE: render ra PNG với kích thước pixel
            # cố định rồi hiện bằng st.image(width=...) — tránh bị Streamlit
            # tự kéo giãn to theo chiều ngang của khung (st.pyplot ở một số
            # bản Streamlit bỏ qua use_container_width=False).
            n = len(combo)
            height = min(3.6, max(1.8, 0.19 * n))
            fig, ax = plt.subplots(figsize=(4.6, height), dpi=150)
            fig.patch.set_facecolor(MAU_NEN)
            ax.set_facecolor(MAU_NEN)
            order = combo.sort_values()
            colors = [MAU_DO if v < 0 else MAU_XANH_LA for v in order.values]
            bars = ax.barh(order.index.astype(str), order.values, color=colors, height=0.6,
                            edgecolor=MAU_CHU, linewidth=1.0, zorder=3)
            span = float(order.values.max() - order.values.min()) or 1.0
            offset = span * 0.03
            for rect, v in zip(bars, order.values):
                ax.text(rect.get_width() + (offset if v >= 0 else -offset), rect.get_y() + rect.get_height() / 2,
                        f'{v:+.1f}', va='center', ha='left' if v >= 0 else 'right',
                        fontsize=6, color=MAU_CHU, fontweight='bold')
            ax.margins(x=0.22)
            ax.axvline(0, color=MAU_CHU, linewidth=1.0)
            ax.set_xlabel('Mua ròng (+) / bán ròng (−) · tỷ VND', color=MAU_CHU, fontsize=6.5, fontweight='bold')
            ax.set_title(f'Top mua/bán ròng khối ngoại · {period_label} gần nhất',
                         color=MAU_TIM, fontsize=7.5, fontweight='bold')
            ax.tick_params(axis='both', colors=MAU_CHU, labelsize=6)
            for lbl in ax.get_yticklabels():
                lbl.set_fontweight('bold')
            ax.grid(axis='x', color=MAU_LUOI, linewidth=0.8, zorder=0)
            ax.set_axisbelow(True)
            for spine_name, spine in ax.spines.items():
                spine.set_visible(spine_name == 'bottom')
                if spine_name == 'bottom':
                    spine.set_color(MAU_CHU)
            fig.tight_layout(pad=0.6)
            buf = io.BytesIO()
            fig.savefig(buf, format='png', facecolor=MAU_NEN, bbox_inches='tight', pad_inches=0.15)
            plt.close(fig)
            buf.seek(0)
            st.image(buf, width=460)
        except ImportError:
            st.bar_chart(combo.rename('Ròng (tỷ VND)'), height=max(200, 20 * len(combo)))


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
    # AURA_V112_FOREIGN_TABLE_SHADOW: đổ bóng kiểu "flat shadow" đồng bộ
    # với nút bấm/card của app (core/theme.py dùng box-shadow Npx Npx 0
    # #1B1233), áp cho mọi bảng trong tab Khối ngoại.
    st.markdown(
        '<style>[data-testid="stDataFrame"]{'
        'box-shadow:4px 4px 0 #1B1233 !important;'
        'border:2px solid #1B1233 !important;'
        'border-radius:14px !important;}</style>',
        unsafe_allow_html=True,
    )
    st.markdown('### 🌍 Dòng tiền khối ngoại · SSI EOD')
    st.caption('Dữ liệu **mua, bán, mua ròng/bán ròng** theo ngày; khác với giá SSI WebSocket realtime. '
               'Khối ngoại chỉ là yếu tố bối cảnh, không tự tạo tín hiệu MUA.')
    # AURA_V105_FOREIGN_R2: use private cloud snapshot, then local fallback.
    df = read_foreign(root)
    try:
        from core.aura_foreign_r2_v105 import load_foreign_r2
        cloud_df = load_foreign_r2()
        if cloud_df is not None and not cloud_df.empty:
            df = cloud_df
    except (ImportError, RuntimeError, ValueError, TypeError, AttributeError):
        pass
    if df.empty:
        st.info('Chưa có snapshot khối ngoại SSI trên máy/Cloud. Chạy scripts/aura_sync_foreign.py để lưu bảng EOD; khi không có dữ liệu AURA để trống thay vì điền 0.')
    else:
        # AURA_V107_FOREIGN_LAYOUT: gọn lại thứ tự hiển thị —
        # (1) bảng tín hiệu 2 sàn (VNINDEX, HNXINDEX — đã bỏ UPCOMINDEX);
        # (2) biểu đồ top mua/bán theo mã ngay bên dưới để trực quan;
        # (3) các lựa chọn xem chi tiết theo từng chỉ số/mã gom vào một
        #     mục "Xem chi tiết" có thể đóng/mở, tránh rối màn hình chính.
        _foreign_signal_table(df)

        stocks = df[df['scope'] == 'STOCK']
        if not stocks.empty:
            st.divider()
            _top_stock_flow_chart(stocks)

        st.divider()
        with st.expander('🔍 Xem chi tiết theo từng chỉ số / mã cổ phiếu'):
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
            if symbol:
                symbol = str(symbol).strip().upper()
                subset = stocks[stocks['code'] == symbol]
                if not subset.empty:
                    _series_block(subset, f'Cổ phiếu {symbol}')
                else:
                    st.caption(f'Chưa đồng bộ giao dịch ngoại cho {symbol}. Có thể chạy lệnh --symbols {symbol} ở máy cập nhật.')
            st.download_button('Xuất bảng khối ngoại CSV',
                               df.to_csv(index=False).encode('utf-8-sig'),
                               'aura_foreign_flow_eod.csv', mime='text/csv', key='aura_foreign_export')
    st.divider()
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
