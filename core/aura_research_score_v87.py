"""AURA V8.7: two-factor RESEARCH score from available technical and provisional financial data.

NEVER a verified Smart Rating, valuation score, historical simulation input, or trading signal.
The 15% valuation component is omitted, not filled with a fabricated figure.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


def build_research_table(technical: pd.DataFrame, root: Path, year: int=2025) -> pd.DataFrame:
    from core.aura_smart_rating_v7 import build_provisional_research
    needed = {'Mã', 'Smart Rating /10'}
    if not needed.issubset(technical.columns):
        raise ValueError('Thiếu cột kỹ thuật Mã / Smart Rating /10')
    t = technical[['Mã', 'Smart Rating /10']].copy()
    t['Mã'] = t['Mã'].fillna('').astype(str).str.strip().str.upper()
    t = t.loc[t['Mã'].ne('') & ~t['Mã'].duplicated(keep=False)].copy()
    t['Điểm kỹ thuật /10'] = pd.to_numeric(t['Smart Rating /10'],errors='coerce').where(lambda x:x.between(1,10))
    t = t[['Mã','Điểm kỹ thuật /10']]
    financial = build_provisional_research(Path(root), year)
    if financial.empty:
        t['Điểm cơ bản SƠ BỘ /10'] = np.nan
        t['Nhóm ngành'] = 'Chưa phân nhóm'
        t['Chỉ tiêu so sánh'] = 0
    else:
        required = {'Mã','Điểm cơ bản SƠ BỘ /10', 'Nhóm','Số chỉ tiêu so sánh'}
        if not required.issubset(financial.columns):
            raise ValueError('Bảng BCTC sơ bộ thiếu cột cần thiết')
        f=financial[['Mã','Điểm cơ bản SƠ BỘ /10','Nhóm','Số chỉ tiêu so sánh']].copy()
        f['Mã']=f['Mã'].fillna('').astype(str).str.strip().str.upper()
        # Duplicates/ambiguous filings are not rated.
        f=f.loc[f['Mã'].ne('') & ~f['Mã'].duplicated(keep=False)].copy()
        f['Điểm cơ bản SƠ BỘ /10']=pd.to_numeric(f['Điểm cơ bản SƠ BỘ /10'],errors='coerce').where(lambda x:x.between(1,10))
        f=f.rename(columns={'Nhóm':'Nhóm ngành','Số chỉ tiêu so sánh':'Chỉ tiêu so sánh'})
        t=t.merge(f, how='left',on='Mã',validate='one_to_one')
        t['Nhóm ngành']=t['Nhóm ngành'].fillna('Chưa phân nhóm')
        t['Chỉ tiêu so sánh']=pd.to_numeric(t['Chỉ tiêu so sánh'],errors='coerce').fillna(0).astype(int)
    # 50% technical + 35% provisional fundamentals, normalized to 100% of AVAILABLE weights.
    # Not a 50/35/15 Smart Rating because the 15% valuation factor is absent.
    both = t['Điểm kỹ thuật /10'].notna() & t['Điểm cơ bản SƠ BỘ /10'].notna()
    t['Điểm nghiên cứu 2 nhóm /10']=np.where(both,
        (50*t['Điểm kỹ thuật /10']+35*t['Điểm cơ bản SƠ BỘ /10'])/85,
        np.nan)
    t['Điểm nghiên cứu 2 nhóm /10']=t['Điểm nghiên cứu 2 nhóm /10'].round(2)
    t['Phạm vi']=np.where(both,'THAM KHẢO · BCTC chưa xác minh',
                           'Chỉ có kỹ thuật / chưa đủ BCTC để so sánh')
    t=t.sort_values(['Điểm nghiên cứu 2 nhóm /10','Điểm kỹ thuật /10','Mã'],ascending=[False,False,True], na_position='last')
    t=t.reset_index(drop=True)
    t['Hạng nghiên cứu']=t['Điểm nghiên cứu 2 nhóm /10'].rank(method='min',ascending=False)
    return t[['Mã','Điểm kỹ thuật /10','Điểm cơ bản SƠ BỘ /10','Điểm nghiên cứu 2 nhóm /10',
              'Hạng nghiên cứu','Nhóm ngành','Chỉ tiêu so sánh','Phạm vi']]


def render_research_rating(root:Path, scan_result):
    import streamlit as st
    st.subheader('AURA · Điểm nghiên cứu 2 nhóm')
    st.caption('Dùng dữ liệu có sẵn: điểm kỹ thuật SSI EOD và chỉ tiêu BCTC 2025 SƠ BỘ. '
               'Không cần nhập 93 bộ hồ sơ thủ công để xem bảng tham khảo.')
    st.info('Công thức điểm NGHIÊN CỨU: (50 × Kỹ thuật + 35 × Cơ bản sơ bộ) / 85. '
            'Định giá 15% CHƯA được tính và KHÔNG thay bằng số giả. '
            'Đây KHÔNG PHẢI Smart Rating 50/35/15 đã kiểm chứng, KHÔNG sử dụng để backtest hoặc phát tín hiệu MUA.')
    if scan_result is None:
        st.info('Vào Bộ lọc thị trường và bấm Quét để xem bảng điểm.')
        return
    technical, meta=scan_result
    if not isinstance(technical,pd.DataFrame):
        st.warning('Bảng kỹ thuật chưa đúng định dạng.');return
    try:
        rating=build_research_table(technical, Path(root))
    except (ValueError, OSError, KeyError, ImportError, pd.errors.ParserError) as exc:
        st.warning(f'Chưa tạo được điểm nghiên cứu: {type(exc).__name__}: {exc}')
        return
    c1,c2,c3=st.columns(3)
    c1.metric('Mã có kỹ thuật',f'{rating["Điểm kỹ thuật /10"].notna().sum():,}')
    c2.metric('Có cơ bản sơ bộ',f'{rating["Điểm cơ bản SƠ BỘ /10"].notna().sum():,}')
    c3.metric('Có điểm nghiên cứu',f'{rating["Điểm nghiên cứu 2 nhóm /10"].notna().sum():,}')
    st.caption(f'Giá kỹ thuật EOD: {getattr(meta,"as_of","không rõ")}. BCTC năm 2025 chưa xác minh nguồn/ngày công bố.')
    show=rating.copy()
    show['Hạng nghiên cứu']=show['Hạng nghiên cứu'].astype('Int64')
    st.dataframe(show, use_container_width=True, hide_index=True, height=440)
    st.download_button('Xuất điểm nghiên cứu SƠ BỘ (CSV)',
        rating.to_csv(index=False).encode('utf-8-sig'), 'aura_score_NGHIEN_CUU_CHUA_XAC_MINH.csv',
        mime='text/csv',key='aura_v87_export')
    with st.expander('Giới hạn / Không dùng cho backtest'):
        st.markdown('BCTC 2025 có số liệu trung gian nhưng chưa đối chiếu báo cáo công bố gốc. '
                    'Việc dùng BCTC 2025 để chấm lại phiên lịch sử có thể gây **look-ahead bias**. '
                    'Phần định giá chưa có ngày và nguồn; các mã thiếu điểm cơ bản không được tự điền 0. '
                    'Điểm giao dịch X10 và bộ lọc kỹ thuật SSI được giữ nguyên.')
