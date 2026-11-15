# -*- coding: utf-8 -*-
"""AURA V3: nghiên cứu có triết lý, không tạo lệnh đặt mua/bán.

Lớp đánh giá dùng thông tin tại thời điểm nến EOD, không sửa X10/TA/FA.
Các ngưỡng là giả thuyết để backtest, KHÔNG là kết quả tối ưu hóa.
"""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import math
import pandas as pd

TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _date(df):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    for name in ('time', 'date', 'Date', 'trading_date'):
        if name in df:
            t = pd.to_datetime(df[name].iloc[-1], errors='coerce')
            if pd.notna(t):
                if getattr(t,'tzinfo',None) is not None:
                    t=t.tz_convert(TZ)
                return t.date()
    return None


def _last_ratio(ty_so, name):
    if not isinstance(ty_so, pd.DataFrame) or ty_so.empty or name not in ty_so.index:
        return None
    x=pd.to_numeric(ty_so.loc[name], errors='coerce')
    if isinstance(x, pd.DataFrame):
        x=x.iloc[-1]
    if isinstance(x, pd.Series):
        x=x.dropna()
        return _num(x.iloc[-1]) if len(x) else None
    return _num(x)


def audit_policy(gia, kq, ty_so, vni, base, *, now=None):
    """Compatible dict, preserves numeric scores; conservative research labels.

    kq: output of existing core.analysis; ty_so.attrs['verified']=True and
    'published_on' are required to qualify any fundamental/valuation setup.
    """
    x = dict(base)
    x['dk_mua_x10_goc'] = base.get('dk_mua', [])
    x['dk_ban_x10_goc'] = base.get('dk_ban', [])
    x['tin_hieu_x10_goc'] = base.get('tin_hieu', 'CHƯA XÁC ĐỊNH')
    x['phong_cach_dat'] = []
    x['chien_luoc'] = {}
    x['ly_do_tin_hieu'] = ''
    if now is None:
        now=datetime.now(TZ)
    today=pd.Timestamp(now).date()
    reasons=[]
    if not isinstance(gia, pd.DataFrame) or 'close' not in gia or len(gia)<200:
        x.update(tin_hieu='CHỜ DỮ LIỆU',ly_do_tin_hieu='Cần tối thiểu 200 nến EOD hợp lệ',
                 dk_mua=[('Lịch sử tối thiểu 200 phiên','Không đạt','Không đủ OHLCV')],dk_ban=[])
        return x

    c=pd.to_numeric(gia['close'],errors='coerce')
    last=_num(c.iloc[-1]); ma20=_num(c.tail(20).mean()); ma50=_num(c.tail(50).mean())
    ma200=_num(c.tail(200).mean()); ma50_prev=_num(c.iloc[-70:-20].mean())
    volume=pd.to_numeric(gia['volume'],errors='coerce') if 'volume' in gia else pd.Series(dtype='float64')
    stock_day=_date(gia)
    lag=(len(pd.bdate_range(pd.Timestamp(stock_day)+pd.Timedelta(days=1),pd.Timestamp(today)))
         if stock_day is not None and stock_day<=today else None)
    fresh=lag is not None and lag<=2  # weekday approximation; local market holidays excluded
    valid=all(z is not None and z>0 for z in (last,ma20,ma50,ma200)) and bool(c.tail(200).notna().all() and (c.tail(200)>0).all())
    daily=c.pct_change(fill_method=None)
    anomalous=bool((daily.tail(200).abs()>0.30).any())
    if anomalous: reasons.append('Có nến biến động >30%, cần kiểm tra điều chỉnh giá/corporate actions')
    if not fresh: reasons.append('EOD chưa đủ mới hoặc ngày nến không hợp lệ')
    if not valid: reasons.append('OHLCV có giá không hợp lệ')

    liquidity=_num(base.get('gtgd'))
    liq_ok=liquidity is not None and liquidity>=2e9
    if not liq_ok: reasons.append('Giá trị giao dịch bình quân 20 phiên chưa đạt 2 tỷ đồng/phiên')
    rsi=_num(gia['RSI'].iloc[-1]) if 'RSI' in gia else None
    if rsi is None and c.notna().sum()>30:
        delta=c.diff(); up=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        dn=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        if _num(dn.iloc[-1]) not in (None,0):
            rsi=_num(100-100/(1+up.iloc[-1]/dn.iloc[-1]))
    ret63=_num((last/c.iloc[-64]-1)*100) if valid and _num(c.iloc[-64]) not in (None,0) else None
    prior55=_num(c.iloc[-56:-1].max()) if len(c)>=56 else None
    prev20vol=_num(volume.iloc[-21:-1].mean()) if len(volume)>=21 else None
    volnow=_num(volume.iloc[-1]) if len(volume) else None
    lowlast=_num(gia['low'].iloc[-1]) if 'low' in gia else None
    prevlast=_num(c.iloc[-2])
    prev5low=_num(pd.to_numeric(gia['low'].tail(5),errors='coerce').min()) if 'low' in gia else None
    max60=_num(c.tail(60).max())
    dd60=100*(max60-last)/max60 if valid and max60 else None

    market_ok=False; market_up=None; market_note='Chưa có VNINDEX EOD cùng phiên ≥50 nến'
    if isinstance(vni,pd.DataFrame) and len(vni)>=50 and 'close' in vni:
        idx=pd.to_numeric(vni['close'],errors='coerce')
        if idx.tail(50).notna().all() and _date(vni)==stock_day:
            m50=_num(idx.tail(50).mean()); current=_num(idx.iloc[-1])
            if current is not None and m50 is not None and m50>0:
                market_ok=True; market_up=current>=m50
                market_note=f'VNINDEX {current:,.2f}; MA50 {m50:,.2f}; cùng phiên {stock_day}'
    if not market_ok: reasons.append('Thiếu xác nhận VNINDEX đúng phiên EOD')
    elif not market_up: reasons.append('VNINDEX đang dưới MA50: không kích hoạt mở vị thế mới theo xu hướng')

    risk=[]
    if valid and last<ma200: risk.append('Giá dưới MA200')
    if dd60 is not None and dd60>=15: risk.append(f'Giảm {dd60:.1f}% so với đỉnh 60 phiên')
    if _num(base.get('diem_tong')) is not None and _num(base.get('diem_tong'))<35:
        risk.append('Điểm X10 dưới 35')
    technical_score=_num(base.get('diem_ta'))
    quality_gate=bool(valid and fresh and not anomalous and liq_ok and market_ok and market_up and not risk)

    trend=bool(valid and ma50_prev is not None and last>ma50>ma200 and ma50>ma50_prev
               and rsi is not None and 45<=rsi<=72 and ret63 is not None and 5<=ret63<=45)
    breakout=bool(valid and prior55 is not None and prev20vol and volnow is not None and
                  last>prior55 and last>ma50>ma200 and volnow>=1.5*prev20vol and
                  rsi is not None and 48<=rsi<=76 and daily.iloc[-1]<=0.15)
    pullback=bool(valid and prev5low is not None and lowlast is not None and prevlast is not None and
                  last>prevlast and last>=ma50>ma200 and prev5low<=ma20*1.02 and
                  last>=ma20*0.99 and rsi is not None and 42<=rsi<=68)
    # Fundamental data used only when supplied as verified point-in-time source.
    verified=bool(isinstance(ty_so,pd.DataFrame) and ty_so.attrs.get('verified') is True)
    pub=ty_so.attrs.get('published_on') if isinstance(ty_so,pd.DataFrame) else None
    published=pd.to_datetime(pub,errors='coerce') if pub is not None else pd.NaT
    fa_asof=bool(verified and pd.notna(published) and stock_day and published.date()<=stock_day)
    roe=_last_ratio(ty_so,'ROE (%)')
    growth=_last_ratio(ty_so,'Tăng trưởng LNST (%)')
    pe=_num(kq.get('P/E')) if isinstance(kq,dict) else None
    pb=_num(kq.get('P/B')) if isinstance(kq,dict) else None
    value=bool(fa_asof and roe is not None and roe>=12 and growth is not None and growth>0 and
               pe is not None and 0<pe<=15 and pb is not None and 0<pb<=2)

    checks={
        'Trend Following':{'setup':trend,'confirmed':quality_gate and trend and (technical_score is None or technical_score>=65),
            'note':'MA50>MA200, MA50 dốc lên, 3 tháng +5..45%, RSI 45..72'},
        'Breakout (thiết lập kỹ thuật)':{'setup':breakout,'confirmed':quality_gate and breakout,
            'note':'Vượt đỉnh 55 phiên, KL≥1.5×TB20, thị trường thuận lợi; KHÔNG phải CANSLIM đầy đủ'},
        'Pullback':{'setup':pullback,'confirmed':quality_gate and pullback,
            'note':'Giữ MA50/MA200, hồi phục gần MA20, RSI 42..68'},
        'Quality & Value':{'setup':value,'confirmed':quality_gate and value,
            'note':'BCTC có ngày công bố kiểm chứng, ROE≥12%, LN tăng, P/E≤15, P/B≤2; ngưỡng nghiên cứu, không áp dụng đồng loạt ngân hàng'},
    }
    confirmed=[name for name, v in checks.items() if v['confirmed']]
    setups=[name for name, v in checks.items() if v['setup']]
    x['chien_luoc']=checks
    x['phong_cach_dat']=confirmed
    x['phong_cach_theo_doi']=setups
    x['du_lieu_moi']=bool(fresh)
    x['co_so_co_ban_xac_minh']=fa_asof
    x['ngay_eod']=str(stock_day) if stock_day else None
    x['canh_bao_rui_ro']=risk
    x['thi_truong_xac_nhan']=market_ok
    x['dk_mua']=[
        ('Dữ liệu EOD và 200 phiên','Đạt' if valid and fresh else 'Không đạt',f'{len(gia)} nến; {stock_day}; trễ {lag} ngày làm việc'),
        ('Chất lượng giá','Không đạt' if anomalous else 'Đạt','Rà soát giá điều chỉnh nếu có biến động 1 ngày >30%'),
        ('Thanh khoản ≥2 tỷ/phiên','Đạt' if liq_ok else 'Không đạt',f'{liquidity/1e9:.2f} tỷ' if liquidity is not None else 'Thiếu GTGD'),
        ('VNINDEX cùng phiên ≥MA50','Đạt' if market_ok and market_up else 'Không đạt' if market_ok else 'N/A',market_note),
        ('Thiết lập theo triết lý','Đạt' if confirmed else 'Theo dõi' if setups else 'Không đạt', ', '.join(confirmed or setups) if confirmed or setups else 'Chưa xuất hiện setup đủ điều kiện'),
        ('BCTC/định giá có chứng cứ','Đạt' if fa_asof else 'N/A','BCTC sơ bộ hoặc thiếu ngày công bố không được dùng xác nhận Value/CANSLIM đầy đủ'),
    ]
    x['dk_ban']=[
        ('Giá dưới MA200','Kích hoạt' if 'Giá dưới MA200' in risk else 'Không' if valid else 'N/A','Cảnh báo xu hướng dài hạn'),
        ('Sụt ≥15% từ đỉnh 60 phiên','Kích hoạt' if dd60 is not None and dd60>=15 else 'Không' if dd60 is not None else 'N/A', f'{dd60:.1f}%' if dd60 is not None else 'Chưa tính được'),
        ('Điểm X10 <35','Kích hoạt' if 'Điểm X10 dưới 35' in risk else 'Không','Chỉ là yếu tố cảnh báo'),
    ]
    if not valid or not fresh:
        label='CHỜ DỮ LIỆU'; reasons.insert(0,'Không phát tín hiệu với OHLCV thiếu hoặc cũ')
    elif anomalous:
        label='CHỜ RÀ SOÁT GIÁ'; reasons.insert(0,'Phát hiện biến động giá bất thường')
    elif len(risk)>=2:
        label='CẢNH BÁO RỦI RO CAO'; reasons[:0]=risk
    elif risk:
        label='CẢNH BÁO RỦI RO'; reasons[:0]=risk
    elif not liq_ok:
        label='THEO DÕI THANH KHOẢN'
    elif not market_ok or not market_up:
        label='THEO DÕI THỊ TRƯỜNG'
    elif confirmed:
        label='ỨNG VIÊN NGHIÊN CỨU'; reasons.insert(0,'Đạt: '+', '.join(confirmed)+'; CHƯA phải lệnh mua')
    elif setups:
        label='THEO DÕI THIẾT LẬP'; reasons.insert(0,'Có setup: '+', '.join(setups)+'; thiếu xác nhận')
    else:
        label='CHƯA CÓ TÍN HIỆU'; reasons.insert(0,'Không đạt chiến lược định sẵn, không nới điều kiện để tạo lệnh')
    x['tin_hieu']=label
    x['ly_do_tin_hieu']='. '.join(dict.fromkeys(reasons)) if reasons else 'Đủ điều kiện nghiên cứu theo một triết lý, vẫn cần thẩm định'
    return x
