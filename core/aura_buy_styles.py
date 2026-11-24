"""AURA: research candidate styles. Not an order recommendation.

This module is deliberately independent of the existing strict X10 BUY engine.
No external APIs, no file writes, no use of unverified financial data as verified.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import math
import pandas as pd

TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def _num(x):
    try:
        z = float(x)
        return z if math.isfinite(z) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _is_uptrend(vni):
    if vni is None or not isinstance(vni, pd.DataFrame) or len(vni) < 50 or 'close' not in vni:
        return None
    c = pd.to_numeric(vni['close'], errors='coerce').dropna()
    if len(c) < 50:
        return None
    return bool(c.iloc[-1] >= c.tail(50).mean())


def _trading_weekdays_lag(last_date, now=None):
    """Approximate freshness, excluding weekends only (VN exchange holidays not included)."""
    if now is None:
        now = datetime.now(TZ)
    try:
        d = pd.Timestamp(last_date).date()
        target = pd.Timestamp(now).date()
        if d > target:
            return 0
        # Exclude last-date itself and count weekdays to today.
        return len(pd.bdate_range(pd.Timestamp(d) + pd.Timedelta(days=1), pd.Timestamp(target)))
    except (ValueError, TypeError, OverflowError):
        return None


def danh_gia_ung_vien(gia, ty_so=None, vni=None, *, gtgd=None, now=None):
    """Separate independent investment philosophies rather than AND-ing them.

    Returns structured diagnostics and candidate watch labels. A candidate is never
    an automated BUY signal. The existing strict X10 signal remains unchanged.
    """
    out = {
        'nhan': 'CHƯA ĐỦ DỮ LIỆU', 'phong_cach': [], 'ly_do': [],
        'du_lieu_moi': False, 'so_phien_tre': None, 'thi_truong_tang': None,
        'thanh_khoan_dat': False, 'so_phien': 0,
        'chua_xac_minh_fa': True,
    }
    if not isinstance(gia, pd.DataFrame) or gia.empty or 'close' not in gia:
        out['ly_do'].append('Chưa có lịch sử giá')
        return out

    c = pd.to_numeric(gia['close'], errors='coerce')
    v = pd.to_numeric(gia['volume'], errors='coerce') if 'volume' in gia else pd.Series(dtype='float64')
    n = len(c)
    out['so_phien'] = n
    if n < 200 or pd.isna(c.iloc[-1]) or c.iloc[-1] <= 0:
        out['ly_do'].append(f'Chỉ có {n} phiên hoặc giá đóng cửa không hợp lệ (cần ≥200 phiên)')
        return out
    last = float(c.iloc[-1])
    ma20 = _num(c.tail(20).mean())
    ma50 = _num(c.tail(50).mean())
    ma200 = _num(c.tail(200).mean())
    if any(z is None or z <= 0 for z in (ma20, ma50, ma200)):
        out['ly_do'].append('Không tính được MA20/50/200')
        return out
    if 'RSI' in gia:
        rsi = _num(gia['RSI'].iloc[-1])
    else:
        delta = c.diff()
        up = delta.clip(lower=0).rolling(14).mean()
        dn = -delta.clip(upper=0).rolling(14).mean()
        rs = up.div(dn.replace(0, float('nan')))
        rsi = _num((100 - 100 / (1 + rs)).iloc[-1])
    rsi = rsi if rsi is not None else float('nan')
    ret63 = _num((last / c.iloc[-64] - 1) * 100)
    ret63 = ret63 if ret63 is not None else float('-inf')
    max20_prior = _num(c.iloc[-21:-1].max())

    if gtgd is not None:
        turnover = _num(gtgd)
    elif len(v) and v.notna().sum() >= 20:
        # Assumption: cached close already stored in VND; DO NOT guess scaling.
        turnover = _num((c * v).tail(20).mean())
    else:
        turnover = None
    out['thanh_khoan_dat'] = bool(turnover is not None and turnover >= 2e9)
    if not out['thanh_khoan_dat']:
        out['ly_do'].append('GTGD bình quân <2 tỷ đồng/phiên hoặc thiếu đơn vị giá chuẩn')

    last_date = gia['time'].iloc[-1] if 'time' in gia else (gia['date'].iloc[-1] if 'date' in gia else None)
    lag = _trading_weekdays_lag(last_date, now)
    out['so_phien_tre'] = lag
    out['du_lieu_moi'] = bool(lag is not None and lag <= 2)
    if not out['du_lieu_moi']:
        out['ly_do'].append('EOD cũ so với hiện tại; cần cập nhật trước khi diễn giải tín hiệu')

    market_up = _is_uptrend(vni)
    out['thi_truong_tang'] = market_up
    if market_up is False:
        out['ly_do'].append('VN-Index dưới MA50: thị trường không thuận lợi cho mua theo xu hướng')
    if market_up is None:
        out['ly_do'].append('Thiếu VN-Index đồng ngày; không xác nhận xu hướng thị trường')

    # Independent setups, not a single universal conjunctive filter.
    prior_vol = _num(v.tail(20).mean()) if len(v) >= 20 else None
    strong_volume = bool(prior_vol and _num(v.iloc[-1]) is not None and v.iloc[-1] >= 1.3 * prior_vol)
    breakout = bool(last > ma50 and max20_prior is not None and last > max20_prior
                    and strong_volume and 50 <= rsi <= 78)
    trend = bool(last > ma20 > ma50 > ma200 and 45 <= rsi <= 75 and ret63 > 0)
    pullback = bool(ma50 > ma200 and last >= ma50 and 0.97 * ma20 <= last <= 1.05 * ma20
                    and 40 <= rsi <= 68 and ret63 > 0)

    styles = []
    if trend:
        styles.append('Xu hướng / động lượng')
    if breakout:
        styles.append('Breakout kiểu CANSLIM (chỉ kỹ thuật)')
    if pullback:
        styles.append('Pullback trong xu hướng tăng')
    out['phong_cach'] = styles

    risky = last < ma200 or (c.tail(60).max() - last) / c.tail(60).max() >= 0.15
    if risky:
        out['ly_do'].append('Có cảnh báo xu hướng/rút lui khỏi đỉnh; chưa phù hợp mở vị thế ngắn hạn')
    if not (trend or breakout or pullback):
        out['ly_do'].append('Chưa xuất hiện cấu trúc kỹ thuật theo ba phong cách')

    if not out['du_lieu_moi']:
        out['nhan'] = 'DỮ LIỆU CŨ · CHỜ ĐỒNG BỘ'
    elif not out['thanh_khoan_dat']:
        out['nhan'] = 'THEO DÕI · THANH KHOẢN THẤP'
    elif risky:
        out['nhan'] = 'THEO DÕI · CẢNH BÁO RỦI RO'
    elif trend or breakout or pullback:
        if market_up is True:
            out['nhan'] = 'ỨNG VIÊN KỸ THUẬT · CẦN THẨM ĐỊNH'
        else:
            out['nhan'] = 'THEO DÕI TÍN HIỆU KỸ THUẬT'
    else:
        out['nhan'] = 'CHƯA CÓ TÍN HIỆU'
    return out
