"""AURA 3.9 | Audit BCTC thuong nien 2021-2025 (khong cham diem dau tu).

Dau vao duy nhat: financial_features_annual.csv do build_financial_features.py tao.
Khong thay doi so lieu nguon, khong gia lap ngay cong bo, khong tu dong kich hoat Smart Rating.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

YEARS = tuple(range(2021, 2026))
NUMERIC = (
    'total_assets_vnd_candidate', 'total_liabilities_vnd_candidate',
    'equity_vnd_candidate', 'net_profit_vnd_candidate', 'eps_vnd_candidate',
    'revenue_vnd_candidate', 'roe_pct_provisional', 'roa_pct_provisional',
    'eps_growth_pct_provisional', 'net_margin_pct_provisional',
    'gross_margin_pct_provisional', 'current_ratio_provisional',
    'liabilities_to_equity_provisional', 'balance_residual_pct',
)
COLUMN_LABELS = {
    'year': 'Năm', 'symbols_with_data': 'Có chỉ tiêu nguồn',
    'symbols_balance_valid': 'Cân đối hợp lệ',
    'symbols_with_roe': 'Có ROE', 'symbols_with_roa': 'Có ROA',
    'symbols_with_eps_growth': 'Có tăng trưởng EPS',
    'symbols_with_net_margin': 'Có biên LN ròng',
    'symbols_source_verified': 'Có xác minh nguồn & thời điểm',
}


def _true(series: pd.Series) -> pd.Series:
    return series.fillna('').astype(str).str.strip().str.lower().isin(('true', '1', 'yes', 'y'))


def clean_annual(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise ValueError('Chưa có dòng BCTC xử lý nào.')
    if not {'symbol', 'year'}.issubset(raw.columns):
        raise ValueError('Bảng BCTC thiếu cột symbol/year.')
    d = raw.copy()
    d['symbol'] = d['symbol'].fillna('').astype(str).str.strip().str.upper()
    d['year'] = pd.to_numeric(d['year'], errors='coerce')
    d = d.loc[d['symbol'].str.fullmatch(r'[A-Z0-9]{2,8}', na=False) & d['year'].isin(YEARS)].copy()
    if d.empty:
        raise ValueError('Không có dòng BCTC hợp lệ của giai đoạn 2021-2025.')
    if d.duplicated(['symbol', 'year']).any():
        sample = d.loc[d.duplicated(['symbol', 'year'], keep=False), ['symbol', 'year']].head(6).to_dict('records')
        raise ValueError(f'Dòng BCTC trùng mã/năm, cần kiểm tra nguồn: {sample}')
    d['year'] = d['year'].astype(int)
    for c in NUMERIC:
        if c not in d:
            d[c] = float('nan')
        d[c] = pd.to_numeric(d[c], errors='coerce')
    for c in ('company_type', 'issues', 'status', 'source_verified', 'score_eligible', 'published_at'):
        if c not in d:
            d[c] = ''
        d[c] = d[c].fillna('').astype(str)
    d['_balance_ok'] = _true(d.get('balance_identity_pass', pd.Series(False, index=d.index)))
    d['_has_base'] = d[['total_assets_vnd_candidate', 'equity_vnd_candidate',
                         'net_profit_vnd_candidate', 'revenue_vnd_candidate',
                         'eps_vnd_candidate']].notna().any(axis=1)
    d['_has_ratio'] = d[['roe_pct_provisional', 'roa_pct_provisional',
                          'eps_growth_pct_provisional', 'net_margin_pct_provisional',
                          'liabilities_to_equity_provisional']].notna().any(axis=1)
    # Must meet ALL three: source verified, date supplied, eligible flag.
    d['_verified'] = (d['source_verified'].str.strip().str.upper().eq('YES') &
                      d['score_eligible'].str.strip().str.upper().eq('YES') &
                      pd.to_datetime(d['published_at'], errors='coerce').notna())
    return d


def audit_tables(raw: pd.DataFrame, universe=None):
    """Return (annual_summary, company_summary, exception_rows), no I/O."""
    d = clean_annual(raw)
    codes = sorted({str(s).strip().upper() for s in (universe or []) if str(s).strip()})
    if not codes:
        codes = sorted(d['symbol'].unique().tolist())
    d = d.loc[d['symbol'].isin(codes)].copy()
    total = len(codes)
    year_rows = []
    for year in YEARS:
        t = d.loc[d['year'].eq(year)]
        year_rows.append({
            'year': year, 'universe': total,
            'symbols_with_data': int(t.loc[t['_has_base'], 'symbol'].nunique()),
            'symbols_balance_valid': int(t.loc[t['_balance_ok'], 'symbol'].nunique()),
            'symbols_with_roe': int(t.loc[t['roe_pct_provisional'].notna(), 'symbol'].nunique()),
            'symbols_with_roa': int(t.loc[t['roa_pct_provisional'].notna(), 'symbol'].nunique()),
            'symbols_with_eps_growth': int(t.loc[t['eps_growth_pct_provisional'].notna(), 'symbol'].nunique()),
            'symbols_with_net_margin': int(t.loc[t['net_margin_pct_provisional'].notna(), 'symbol'].nunique()),
            'symbols_source_verified': int(t.loc[t['_verified'], 'symbol'].nunique()),
        })
    years = pd.DataFrame(year_rows)

    company_rows = []
    exception_rows = []
    for symbol in codes:
        subset = d.loc[d['symbol'].eq(symbol)]
        observed = set(subset.loc[subset['_has_base'], 'year'].tolist())
        with_ratio = set(subset.loc[subset['_has_ratio'], 'year'].tolist())
        valid_balance = set(subset.loc[subset['_balance_ok'], 'year'].tolist())
        verified_years = set(subset.loc[subset['_verified'], 'year'].tolist())
        bad = subset.loc[subset['issues'].str.strip().ne('') |
                         (~subset['_balance_ok'] & subset['_has_base'])]
        company_rows.append({
            'symbol': symbol,
            'company_type': str(subset.iloc[-1]['company_type']) if not subset.empty else 'UNKNOWN',
            'years_source': len(observed), 'years_with_ratio': len(with_ratio),
            'years_balance_valid': len(valid_balance), 'years_verified': len(verified_years),
            'missing_source_years': ', '.join(str(x) for x in YEARS if x not in observed),
            'missing_ratio_years': ', '.join(str(x) for x in YEARS if x not in with_ratio),
            'issues_count': len(bad),
            'data_status': ('Chưa có chỉ tiêu' if not observed else
                            'Có dữ liệu 5 năm (sơ bộ)' if len(with_ratio) == 5 else
                            'Dữ liệu chưa đủ 5 năm'),
            'rating_status': ('Đã xác minh đủ 5 năm' if len(verified_years) == 5 else
                              'Chưa xác minh đầy đủ'),
        })
        for _, row in bad.iterrows():
            exception_rows.append({'symbol': symbol, 'year': int(row['year']),
                                   'balance_identity_pass': bool(row['_balance_ok']),
                                   'issues': row['issues'] or 'Cân đối chưa đạt / thiếu chỉ tiêu',
                                   'status': row['status']})
    return years, pd.DataFrame(company_rows), pd.DataFrame(exception_rows,
           columns=['symbol', 'year', 'balance_identity_pass', 'issues', 'status'])


def render_financial_quality_panel(root: Path) -> None:
    """Read previously audited CSVs. Never recompute all 1518 symbols on page reruns."""
    import streamlit as st

    root = Path(root)
    base = root / 'data' / 'fundamentals' / 'processed'
    year_file, company_file, issue_file = (base / n for n in (
        'aura_quality_by_year.csv', 'aura_quality_by_symbol.csv', 'aura_quality_issues.csv'))
    st.markdown('#### Kiểm tra chất lượng dữ liệu tài chính 5 năm')
    if not all(p.is_file() for p in (year_file, company_file, issue_file)):
        st.info('BCTC đã tải cần được **tính lại và kiểm tra** trước khi dùng trong hệ thống đánh giá.')
        st.code(r'.\.venv\Scripts\python.exe .\scripts\aura_finalize_bctc.py', language='powershell')
        return
    try:
        years = pd.read_csv(year_file, encoding='utf-8-sig')
        companies = pd.read_csv(company_file, encoding='utf-8-sig', keep_default_na=False)
        issues = pd.read_csv(issue_file, encoding='utf-8-sig', keep_default_na=False)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.warning('Không mở được bảng kiểm tra BCTC. Hãy chạy lại lệnh tổng hợp khi dữ liệu ổn định.')
        return
    if years.empty or companies.empty:
        st.info('Chưa có báo cáo chất lượng BCTC hợp lệ.')
        return
    cur = years.loc[years['year'].eq(2025)]
    r = cur.iloc[0] if not cur.empty else years.iloc[-1]
    n = len(companies)
    five_ratios = int(companies['years_with_ratio'].eq(5).sum())
    source5 = int(companies['years_source'].eq(5).sum())
    a, b, c, d = st.columns(4)
    a.metric('Có số liệu nguồn 5 năm', f'{source5:,}/{n:,}')
    b.metric('Có tỷ số ở cả 5 năm', f'{five_ratios:,}/{n:,}')
    c.metric(f'Có ROE năm {int(r["year"])}', f'{int(r["symbols_with_roe"]):,}/{n:,}')
    d.metric('Đủ nguồn và ngày công bố', f'{int(companies["years_verified"].eq(5).sum()):,}/{n:,}')
    st.caption('Có dữ liệu không đồng nghĩa BCTC chính thức đã được kiểm chứng. '
               'Năm 2021 có thể chưa tính được ROE/ROA do thiếu tài sản, vốn chủ sở hữu bình quân năm 2020.')
    with st.expander('Độ phủ theo năm và chỉ tiêu', expanded=False):
        st.dataframe(years.rename(columns=COLUMN_LABELS), hide_index=True, use_container_width=True)
    with st.expander('Tra cứu trạng thái của từng mã', expanded=False):
        names = companies['symbol'].tolist()
        suggested = 'FPT' if 'FPT' in names else names[0]
        chosen = st.selectbox('Mã cổ phiếu', names, index=names.index(suggested), key='aura_39_quality_symbol')
        one = companies.loc[companies['symbol'].eq(chosen)].iloc[0]
        st.markdown(f'**{chosen} · {one["data_status"]}**')
        st.caption(f'Năm có chỉ tiêu nguồn: {one["years_source"]}/5; '
                   f'năm có tỷ số sơ bộ: {one["years_with_ratio"]}/5; '
                   f'năm kiểm tra cân đối đạt: {one["years_balance_valid"]}/5.')
        if str(one['missing_source_years']).strip():
            st.warning('Thiếu chỉ tiêu nguồn các năm: ' + str(one['missing_source_years']))
        if str(one['missing_ratio_years']).strip():
            st.caption('Chưa tính được tỷ số các năm: ' + str(one['missing_ratio_years']))
        iss = issues.loc[issues['symbol'].eq(chosen)]
        if not iss.empty:
            st.dataframe(iss[['year', 'issues']].rename(columns={'year':'Năm', 'issues':'Điểm cần kiểm tra'}),
                         hide_index=True, use_container_width=True)
    st.download_button('Xuất bảng chất lượng BCTC 5 năm',
        companies.to_csv(index=False).encode('utf-8-sig'),
        file_name='AURA_BCTC_ChatLuong_5Nam.csv', mime='text/csv', key='aura_39_quality_export')
    st.caption('Smart Rating đa nhân tố vẫn cần đối chiếu hồ sơ gốc, ngày công bố và dữ liệu định giá; '
               'bảng này chỉ đánh giá mức độ sẵn sàng của dữ liệu, không phải tín hiệu mua/bán.')
