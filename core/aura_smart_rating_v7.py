"""AURA Smart Rating V7: point-in-time audit + explicitly provisional research view.

No SSI requests, no brokerage actions, no invented accounting/valuation data.
The legacy technical score (and existing X10 strategy) are never modified.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

SNAPSHOT_NAME = 'data/fundamentals/fundamentals_snapshot.csv'
ANNUAL_NAME = 'data/fundamentals/processed/financial_features_annual.csv'
CAT_NAME = 'data/ssi_cache/market_symbols.csv'
EXTRA_COLUMNS = ['source_verified', 'score_eligible', 'source_document',
                 'valuation_verified', 'valuation_document', 'reviewed_by']
MIN_PROVISIONAL_PEERS = 5

# Nonbanks share accounting conventions, but require industry-specific peer sets.
PRELIM_METRICS = {
    'BANK': {
        'roe_pct_provisional': True,
        'roa_pct_provisional': True,
        'eps_growth_pct_provisional': True,
    },
    'NONBANK': {
        'roe_pct_provisional': True,
        'roa_pct_provisional': True,
        'gross_margin_pct_provisional': True,
        'net_margin_pct_provisional': True,
        'eps_growth_pct_provisional': True,
        'liabilities_to_equity_provisional': False,
    },
}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path, encoding='utf-8-sig', low_memory=False, dtype={'symbol': str})


def _yes(series: pd.Series) -> pd.Series:
    return series.fillna('').astype(str).str.strip().str.upper().eq('YES')


def verified_template(symbols: Optional[list[str]] = None) -> pd.DataFrame:
    from core.smart_rating_v2 import empty_input_template
    out = empty_input_template(symbols or [])
    for c in EXTRA_COLUMNS:
        out[c] = ''
    return out


def prepare_verified_snapshot(raw: pd.DataFrame, as_of: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Require explicit human verification & document, not just filled ratios.

    Returns the restricted V2 schema for scoring and the per-row audit. `YES`
    is a human attestation, NOT automatic proof that a source is authentic.
    """
    from core.smart_rating_v2 import BASE_COLS
    mandatory = set(BASE_COLS) | {'source_verified', 'score_eligible', 'source_document'}
    missing = mandatory - set(raw.columns)
    if missing:
        raise ValueError('Snapshot thiếu cột kiểm chứng: ' + ', '.join(sorted(missing)))
    d = raw.copy()
    target = pd.Timestamp(as_of).normalize()
    if pd.isna(target):
        raise ValueError('Ngày EOD không hợp lệ.')
    d['symbol'] = d['symbol'].fillna('').astype(str).str.strip().str.upper()
    for col in ('source', 'source_document', 'sector_type', 'peer_group'):
        d[col] = d[col].fillna('').astype(str).str.strip()
    d['sector_type'] = d['sector_type'].str.upper()
    for col in ('report_period_end', 'published_at', 'valuation_asof'):
        d[col] = pd.to_datetime(d[col], errors='coerce').dt.normalize()
    valid_provenance = (_yes(d['source_verified']) & _yes(d['score_eligible'])
                        & d['source'].ne('') & d['source_document'].ne(''))
    valid_date = (d['published_at'].notna() & d['report_period_end'].notna()
                  & d['published_at'].le(target)
                  & d['report_period_end'].le(d['published_at']))
    valid_group = (d['peer_group'].ne('') & d['sector_type'].isin(['BANK', 'NONBANK']))
    status = np.select(
        [~valid_provenance, ~valid_date, ~valid_group],
        ['Chưa xác minh nguồn', 'Ngày báo cáo/công bố không hợp lệ',
         'Thiếu nhóm so sánh hoặc loại hình chưa hỗ trợ'],
        default='Đã qua cổng kiểm chứng',
    )
    audit = pd.DataFrame({'Mã': d['symbol'], 'Trạng thái kiểm chứng': status,
                          'Ngày công bố': d['published_at'].dt.strftime('%Y-%m-%d').fillna(''),
                          'Nhóm so sánh': d['peer_group'], 'Tài liệu nguồn': d['source_document']})
    keep = valid_provenance & valid_date & valid_group & d['symbol'].ne('')
    cleaned = d.loc[keep].copy()
    # Only historical valuation with a separate verified document is considered.
    if 'valuation_verified' not in cleaned:
        cleaned['valuation_verified'] = ''
    if 'valuation_document' not in cleaned:
        cleaned['valuation_document'] = ''
    valid_value = (_yes(cleaned['valuation_verified']) &
                   cleaned['valuation_document'].fillna('').astype(str).str.strip().ne(''))
    cleaned.loc[~valid_value, ['pe', 'pb', 'ev_ebitda']] = np.nan
    cleaned.loc[~valid_value, 'valuation_asof'] = pd.NaT
    cleaned.loc[~valid_value, 'valuation_source'] = ''
    return cleaned[BASE_COLS].copy(), audit


def build_verified_rating(technical: pd.DataFrame, root: Path, as_of: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use the existing V2 scoring math, but only after the V7 evidence gate."""
    from core.smart_rating_v2 import build_multifactor_table
    root = Path(root)
    raw = _read_csv(root / SNAPSHOT_NAME)
    if raw.empty:
        allowed = verified_template([])
        audit = pd.DataFrame(columns=['Mã', 'Trạng thái kiểm chứng', 'Ngày công bố',
                                      'Nhóm so sánh', 'Tài liệu nguồn'])
    else:
        allowed, audit = prepare_verified_snapshot(raw, as_of)
    rated = build_multifactor_table(technical, as_of=as_of,
                                    root=root, financial_table=allowed)
    return rated, audit


def _industry_catalogue(root: Path) -> pd.DataFrame:
    cat = _read_csv(Path(root) / CAT_NAME)
    if cat.empty or 'symbol' not in cat:
        return pd.DataFrame(columns=['symbol', 'sector'])
    cat['symbol'] = cat['symbol'].fillna('').astype(str).str.strip().str.upper()
    if 'sector' not in cat:
        cat['sector'] = ''
    cat['sector'] = cat['sector'].fillna('').astype(str).str.strip()
    return cat[['symbol', 'sector']].drop_duplicates('symbol', keep='last')


def build_provisional_research(root: Path, year: int = 2025) -> pd.DataFrame:
    """Peer-normalized preview only: never a trade signal or official rating.

    All source values are explicitly unverified and publication dates not asserted.
    Banks are compared with banks; nonbanks with exactly their SSI sector.
    Financial intermediaries OTHER and unknown sectors are excluded entirely.
    """
    annual = _read_csv(Path(root) / ANNUAL_NAME)
    cols = ['Mã', 'Năm', 'Nhóm', 'Số chỉ tiêu so sánh', 'Điểm cơ bản SƠ BỘ /10',
            'Trạng thái', 'Giới hạn dữ liệu']
    if annual.empty or not {'symbol', 'year', 'company_type'}.issubset(annual):
        return pd.DataFrame(columns=cols)
    a = annual.copy()
    a['symbol'] = a['symbol'].fillna('').astype(str).str.strip().str.upper()
    a['year'] = pd.to_numeric(a['year'], errors='coerce')
    a = a.loc[a['year'].eq(year) & a['symbol'].ne('')].copy()
    if a.empty:
        return pd.DataFrame(columns=cols)
    dupes = a['symbol'].duplicated(keep=False)
    conflict_symbols = set(a.loc[dupes, 'symbol'])
    a = a.loc[~dupes].copy()
    a['company_type'] = a['company_type'].fillna('').astype(str).str.strip().str.upper()
    a = a.merge(_industry_catalogue(root), how='left', on='symbol', validate='many_to_one')
    a['sector'] = a['sector'].fillna('').astype(str).str.strip()
    a['_type'] = np.select(
        [a['company_type'].eq('BANK'), a['company_type'].isin(['NONFINANCIAL', 'NONBANK'])],
        ['BANK', 'NONBANK'], default='UNSUPPORTED')
    a['_peer'] = np.where(a['_type'].eq('BANK'), 'BANK', a['sector'])
    a.loc[a['_type'].eq('UNSUPPORTED'), '_peer'] = ''
    a['_metric_count'] = 0
    a['_score'] = np.nan
    a['_status'] = 'Chưa đủ nhóm so sánh/chỉ tiêu sơ bộ'
    for company_type, metrics in PRELIM_METRICS.items():
        sub = a.loc[a['_type'].eq(company_type) & a['_peer'].ne('')]
        for peer, idx in sub.groupby('_peer', sort=False).groups.items():
            indices = list(idx)
            g = a.loc[indices]
            factor_scores = pd.DataFrame(index=indices)
            for metric, higher in metrics.items():
                if metric not in a:
                    continue
                x = pd.to_numeric(g[metric], errors='coerce').replace([np.inf, -np.inf], np.nan)
                if metric == 'liabilities_to_equity_provisional':
                    x = x.where(x.ge(0))
                if metric == 'roa_pct_provisional' or metric == 'roe_pct_provisional':
                    x = x.where(x.between(-200, 200))
                if x.notna().sum() < MIN_PROVISIONAL_PEERS:
                    continue
                if x.nunique(dropna=True) == 1:
                    pct = pd.Series(0.5, index=x.dropna().index)
                else:
                    pct = (x.rank(ascending=higher, method='average') - 1) / (x.notna().sum() - 1)
                factor_scores[metric] = pct
            if factor_scores.empty:
                continue
            count = factor_scores.notna().sum(axis=1)
            needed = 2 if company_type == 'BANK' else 3
            avg = factor_scores.mean(axis=1)
            mask = count.ge(needed)
            a.loc[indices, '_metric_count'] = count.astype(int)
            a.loc[indices, '_score'] = (1 + 9 * avg).where(mask).round(2)
            a.loc[indices, '_status'] = np.where(mask, 'SƠ BỘ · không dùng đặt lệnh',
                                                 'Thiếu chỉ tiêu để so sánh')
    d = pd.DataFrame({
        'Mã': a['symbol'], 'Năm': year,
        'Nhóm': a['_peer'].where(a['_peer'].ne(''), 'Chưa phân nhóm'),
        'Số chỉ tiêu so sánh': a['_metric_count'].astype(int),
        'Điểm cơ bản SƠ BỘ /10': a['_score'],
        'Trạng thái': a['_status'],
        'Giới hạn dữ liệu': 'Nguồn BCTC/chứng từ và ngày công bố chưa xác minh; không dùng backtest/MUA',
    })
    if conflict_symbols:
        conflict = pd.DataFrame({'Mã': sorted(conflict_symbols), 'Năm': year,
            'Nhóm': 'Chưa phân nhóm', 'Số chỉ tiêu so sánh': 0,
            'Điểm cơ bản SƠ BỘ /10': np.nan,
            'Trạng thái': 'BCTC trùng mã/năm; cần kiểm tra',
            'Giới hạn dữ liệu': 'Không tính điểm khi nhiều dòng cùng mã/năm'})
        d = pd.concat([d, conflict], ignore_index=True)
    return d.sort_values(['Điểm cơ bản SƠ BỘ /10', 'Mã'],
                         ascending=[False, True], na_position='last').reset_index(drop=True)


def render_smart_rating_v7(root: Path, scan_result=None) -> None:
    """Streamlit panel embedded in the existing Smart Rating tab."""
    import streamlit as st

    root = Path(root)
    st.subheader('Smart Rating V7 · Kiểm chứng dữ liệu và giải thích điểm')
    st.caption('Giữ điểm kỹ thuật SSI EOD như cũ. Điểm cơ bản/định giá chính thức chỉ xuất hiện '
               'khi có bằng chứng và ngày công bố hợp lệ, cùng nhóm so sánh đủ mẫu. '
               'Không lấy điểm cơ bản X10 40/50/60 mặc định làm điểm BCTC đã kiểm chứng.')
    template = verified_template([])
    with st.expander('Nguồn BCTC, dữ liệu cần bổ sung và quy tắc chấm', expanded=False):
        st.markdown('**Trọng số dự kiến:** kỹ thuật ~33% · cơ bản ~33% · định giá ~34% (chia đều). '
                    'Chỉ tổng hợp nếu đủ cả 3 nhóm. Cùng ngày chốt EOD, không nhìn trước ngày công bố.')
        st.markdown('**Công ty phi ngân hàng:** ROE, ROA, biên lợi nhuận, tăng trưởng EPS, '
                    'nợ/VCSH, khả năng thanh toán; **ngân hàng:** ROE, ROA, NPL và CAR '
                    'khi có nguồn; định giá yêu cầu P/E, P/B hoặc EV/EBITDA cùng thời điểm.')
        st.download_button('Tải mẫu nguồn Smart Rating (CSV)',
                           template.to_csv(index=False).encode('utf-8-sig'),
                           'aura_fundamentals_snapshot_TEMPLATE.csv', mime='text/csv',
                           key='aura_v7_template')
        st.caption(f'File hoàn thành cần đặt tại: {SNAPSHOT_NAME}. '
                   'Đánh dấu source_verified=YES và score_eligible=YES sau khi đối chiếu tài liệu gốc; '
                   'valuation_verified=YES chỉ khi có ngày và chứng cứ định giá riêng.')
    if scan_result is None:
        st.info('Hãy chạy Quét / làm mới xếp hạng ở Trạm lọc trước để xem bảng Smart Rating cùng ngày EOD.')
    else:
        technical, metadata = scan_result
        if not isinstance(technical, pd.DataFrame):
            st.warning('Dữ liệu quét chưa đúng định dạng DataFrame.')
        else:
            try:
                scored, audit = build_verified_rating(technical, root, str(metadata.as_of))
                verified = int(scored['Điểm cơ bản /10'].notna().sum())
                valuated = int(scored['Điểm định giá /10'].notna().sum())
                complete = int(scored['Smart Rating tổng hợp /10'].notna().sum())
                a, b, c, d = st.columns(4)
                a.metric('Mã chấm kỹ thuật', f'{scored["Điểm kỹ thuật /10"].notna().sum():,}')
                b.metric('Đủ điểm cơ bản', str(verified))
                c.metric('Đủ điểm định giá', str(valuated))
                d.metric('Smart Rating tổng hợp', str(complete))
                st.caption(f'Phiên EOD chấm điểm: {metadata.as_of}. '
                           'Thiếu bằng chứng không đồng nghĩa doanh nghiệp có chất lượng thấp.')
                show_cols = ['Mã', 'Điểm kỹ thuật /10', 'Điểm cơ bản /10',
                             'Điểm định giá /10', 'Smart Rating tổng hợp /10',
                             'Thứ hạng tổng hợp', 'Số chỉ tiêu cơ bản hợp lệ',
                             'Số chỉ tiêu định giá hợp lệ', 'Ghi chú dữ liệu']
                # AURA_V8_3_3: UI-only labels. Numeric values/verified CSV stay unchanged.
                display_scored = scored[[x for x in show_cols if x in scored]].copy()
                for c in ('Điểm cơ bản /10', 'Điểm định giá /10',
                          'Smart Rating tổng hợp /10'):
                    if c in display_scored:
                        display_scored[c] = display_scored[c].map(
                            lambda v: f'{float(v):.2f}' if pd.notna(v) else 'Chưa kiểm chứng')
                if 'Thứ hạng tổng hợp' in display_scored:
                    display_scored['Thứ hạng tổng hợp'] = display_scored['Thứ hạng tổng hợp'].map(
                        lambda v: f'{int(v)}' if pd.notna(v) else '—')
                st.dataframe(display_scored,
                             use_container_width=True, hide_index=True, height=370)
                st.download_button('Xuất Smart Rating đã kiểm chứng (CSV)',
                                  scored.to_csv(index=False).encode('utf-8-sig'),
                                  'aura_smart_rating_verified.csv', mime='text/csv',
                                  key='aura_v7_verified_csv')
                if not audit.empty:
                    with st.expander('Kiểm toán từng hồ sơ đầu vào'):
                        st.dataframe(audit, hide_index=True, use_container_width=True)
            except (ValueError, KeyError, OSError, TypeError, ImportError) as exc:
                st.warning(f'Chưa thể xây bảng kiểm chứng V7: {type(exc).__name__}: {exc}')
    with st.expander('Nghiên cứu BCTC sơ bộ 2025 (không phải tín hiệu đầu tư)', expanded=False):
        preview = build_provisional_research(root)
        if preview.empty:
            st.info('Chưa có bảng financial_features_annual.csv để phân tích sơ bộ.')
        else:
            st.warning('Bảng dưới chỉ so sánh tương đối các chỉ tiêu tài chính sơ bộ '
                       'trong nhóm ngành; KHÔNG tính Smart Rating tổng hợp, KHÔNG phát lệnh MUA.')
            s1, s2, s3 = st.columns(3)
            s1.metric('Có bản ghi BCTC 2025', f'{len(preview):,}')
            s2.metric('Có điểm sơ bộ đủ mẫu', f'{preview["Điểm cơ bản SƠ BỘ /10"].notna().sum():,}')
            s3.metric('Chưa đủ để so sánh', f'{preview["Điểm cơ bản SƠ BỘ /10"].isna().sum():,}')
            names = preview['Mã'].dropna().unique().tolist()
            selected = st.text_input('Lọc mã trong BCTC sơ bộ', '', key='aura_v7_prelim_symbol').strip().upper()
            display = preview.loc[preview['Mã'].str.contains(selected, regex=False)] if selected else preview
            st.dataframe(display, use_container_width=True, hide_index=True, height=360)
            st.download_button('Xuất nghiên cứu BCTC sơ bộ (CSV)',
                               preview.to_csv(index=False).encode('utf-8-sig'),
                               'aura_financial_provisional_research.csv', mime='text/csv',
                               key='aura_v7_prelim_export')
