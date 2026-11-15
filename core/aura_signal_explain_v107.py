# -*- coding: utf-8 -*-
"""Explain positive buy setups separately from risk conditions, without adding trades.
Actual scoring policy remains in core/aura_investment_policy.py.
"""
from __future__ import annotations
from typing import Any
import streamlit as st

def describe_signal(xep: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Pure, side-effect-free presentation logic; never fabricate a BUY."""
    approved = [str(s) for s in (xep.get('phong_cach_dat') or []) if s]
    observing = [str(s) for s in (xep.get('phong_cach_theo_doi') or []) if s]
    styles = [str(s) for s in (candidate.get('phong_cach') or []) if s]
    risks = [str(s) for s in (xep.get('canh_bao_rui_ro') or []) if s]
    old_label = str(xep.get('tin_hieu_x10_goc') or '')
    new_label = str(xep.get('tin_hieu') or 'CHƯA XÁC ĐỊNH')
    blockers = [
        (str(name), str(detail)) for name, status, detail in (xep.get('dk_mua') or [])
        if status in ('Không đạt', 'N/A')
    ]
    if approved:
        heading = 'ỨNG VIÊN MUA ĐỂ NGHIÊN CỨU · ĐÃ QUA BỘ LỌC'
        explanation = 'Đạt các thiết lập: ' + ', '.join(approved) + '. Đây không phải lệnh mua tự động.'
        severity = 'success'
    elif risks:
        heading = 'CHƯA CÓ ĐIỂM MUA HỢP LỆ · ĐANG CÓ RỦI RO'
        explanation = 'Cảnh báo rủi ro: ' + '; '.join(risks) + '. Không đồng nghĩa một lệnh bán.'
        severity = 'warning'
    elif observing or styles:
        heading = 'CÓ THIẾT LẬP THEO DÕI · CHƯA XÁC NHẬN MUA'
        explanation = 'Đang theo dõi: ' + ', '.join(observing or styles) + '. Cần đủ điều kiện xác nhận.'
        severity = 'info'
    else:
        heading = 'CHƯA CÓ THIẾT LẬP MUA'
        explanation = 'Không có thiết lập mua thỏa điều kiện đã định. Không tạo tín hiệu mua giả.'
        severity = 'info'
    return dict(heading=heading, explanation=explanation, severity=severity,
                old_label=old_label, new_label=new_label, blockers=blockers,
                styles=styles, observing=observing, approved=approved, risks=risks)

def render_signal_explanation(xep: dict[str, Any], candidate: dict[str, Any]) -> None:
    info = describe_signal(xep, candidate)
    st.markdown('#### Đánh giá cơ hội mua & rủi ro')
    if info['severity'] == 'success':
        st.success('**' + info['heading'] + '** — ' + info['explanation'])
    elif info['severity'] == 'warning':
        st.warning('**' + info['heading'] + '** — ' + info['explanation'])
    else:
        st.info('**' + info['heading'] + '** — ' + info['explanation'])
    st.caption('“Điểm mua” ở đây là điều kiện nghiên cứu theo EOD, không phải lệnh đặt mua/bán hay dự báo chắc chắn.')
    with st.expander('Vì sao có / chưa có cơ hội mua? So với tín hiệu X10 cũ', expanded=False):
        if info['old_label']:
            st.write('**X10 cũ (tham khảo):**', info['old_label'])
        st.write('**Bộ xác nhận hiện tại:**', info['new_label'])
        if info['old_label'] and info['old_label'] != info['new_label']:
            st.caption('Hai bộ lọc có điều kiện khác nhau: nhãn X10 cũ không được dùng để vượt qua bộ xác nhận mới.')
        if info['observing']:
            st.write('**Thiết lập kỹ thuật đã xuất hiện:**', '; '.join(info['observing']))
        elif info['styles']:
            st.write('**Ứng viên theo phong cách:**', '; '.join(info['styles']))
        if info['blockers']:
            st.write('**Các điều kiện đang thiếu / không đạt:**')
            for name, detail in info['blockers']:
                st.write('•', name + ':', detail)
        if info['risks']:
            st.write('**Cảnh báo:**', '; '.join(info['risks']))
        st.caption('BCTC chưa đối chiếu nhà phát hành không được dùng để xác nhận thiết lập giá trị.')
