from urllib.parse import quote
from html import escape as html_escape
import math
from pathlib import Path
import pandas as pd

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from core.data import lay_vnindex, STATEMENTS, LOI
from core.pipeline import phan_tich_ma, ngu_canh_tu_ket_qua, quet_nhieu_ma, phan_tich_lai_voi_bctc
from core.bctc_user import mau_excel, doc_bctc
from core.strategy import dong_pdf
from core.report import xuat_pdf
from core.hoso import ve_tab_hoso
from core.profiles import TIEU_CHI, NHOM, KHAU_VI, cau_hinh_khau_vi, danh_gia, tom_tat
from core import industry
from core.dinhdang import so_vn
from core.aura_brand import favicon
from core.theme import (ap_dung_theme, theme_plotly, tieu_de_trang, huong_dan_3_buoc, the_tin_hieu,
                        dong_tieu_chi, tag_trang_thai, thanh_phan_tram, MAU, dieu_huong_trang)

st.set_page_config(page_title="AURA | Phân tích cổ phiếu", page_icon=favicon(), layout="wide")

# AURA_CLOUD_SSI_PILOT_V92
from core.aura_cloud_bootstrap import bootstrap_cloud
bootstrap_cloud()

ap_dung_theme()
dieu_huong_trang()
tieu_de_trang(tieu_de="AURA · Phân tích cổ phiếu",
              phu_de="Nền tảng phân tích chứng khoán · Dữ liệu SSI · Biểu đồ kỹ thuật đa khung")
st.caption("Bộ lọc giúp bạn tìm ứng viên để nghiên cứu, không phải khuyến nghị đầu tư. Hãy sang tab Hiểu doanh nghiệp trước khi quyết định.")
import os


@st.cache_resource(show_spinner=False)
def dang_ky_vnstock():
    try:
        key = st.secrets.get("VNSTOCK_API_KEY", "")
    except Exception:
        key = ""
    key = key or os.environ.get("VNSTOCK_API_KEY", "")
    if key:
        try:
            from vnstock import register_user
            register_user(api_key=key)
        except Exception:
            pass


dang_ky_vnstock()

# A cached Streamlit result must be invalidated when an SSI CSV changes.
# File metadata is a lightweight revision key; reading the CSV happens in core.data.
_SSI_CACHE = Path(__file__).resolve().parent / "data" / "ssi_cache"


def _file_revision(path):
    try:
        info = path.stat()
        return (info.st_mtime_ns, info.st_size)
    except OSError:
        return (None, None)


def _source_revisions(symbol):
    clean = "".join(c for c in str(symbol).strip().upper() if c.isalnum())[:10]
    price = _file_revision(_SSI_CACHE / "ohlcv" / f"{clean}.csv")
    index = (
        _file_revision(_SSI_CACHE / "ohlcv" / "VNINDEX.csv"),
        _file_revision(_SSI_CACHE / "vnindex_ohlcv_ssi.csv"),
    )
    return price, index


@st.cache_data(ttl=3600, show_spinner=False)
def vni_cache(so_ngay, index_revision=None):
    # index_revision intentionally participates in the cache key.
    return lay_vnindex(so_ngay)


@st.cache_data(ttl=3600, show_spinner=False)
def ma_cache(ma, so_ngay, so_nam, price_revision=None, index_revision=None):
    # price_revision intentionally participates in the cache key.
    return phan_tich_ma(ma, so_ngay, so_nam, vni_cache(so_ngay, index_revision))


# ===== BATDAY SSI - gia khop trong CHINH the tong quan, khong tao o rieng =====
def _gia_vnd(value):
    """Convert legacy 1,000-VND EOD units if present. Never apply this to live ticks."""
    try:
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            return None
        return number * 1000 if number < 1000 else number
    except (TypeError, ValueError, OverflowError):
        return None


def _dinh_dang_vnd(value):
    if value is None:
        return "N/A"
    return f"{value:,.0f}".replace(",", ".") + " đ"


def _gia_ssi_cho_the(ma_cp, gia_eod_vnd, ngay_eod=None):
    """Use a verified, unit-consistent SSI tick; otherwise show a transparently labeled EOD.

    This function is DISPLAY ONLY. MA/RSI/X10/PDF continue using the EOD analysis.
    """
    result = {
        "price": gia_eod_vnd,
        "label": "GIÁ ĐÓNG CỬA (EOD)",
        "status": "EOD",
        "detail": f"Phiên {ngay_eod}" if ngay_eod else "Chưa có giá khớp SSI",
    }
    if gia_eod_vnd is None:
        result["detail"] = "Chưa có giá EOD hợp lệ"
        return result
    # AURA_V97_SSI_WEBSOCKET_PRICE_DISPLAY
    # Best-effort, timestamp-verified SSI WebSocket price. EOD continues to drive
    # all analytics, MA/RSI/X10, charts and cached research results.
    try:
        from core.aura_ssi_realtime_v97 import display_live_quote
        live = display_live_quote(ma_cp, gia_eod_vnd, ngay_eod)
        if live.get("price") is not None:
            result.update(live)
            return result
        if live.get("detail"):
            result["detail"] = live["detail"]
    except (ImportError, OSError, RuntimeError, ValueError, TypeError, AttributeError):
        # Fail closed: never label an unknown price as LIVE.
        result["detail"] = "Giá EOD · SSI WebSocket chưa sẵn sàng"
    try:
        from core.ssi_market_live import (request_live_symbol, read_snapshot,
                                          quote_view, date_label)
        if not request_live_symbol(ma_cp):
            return result
        tick = quote_view(read_snapshot(), ma_cp)
        price = float(tick.get("price"))
        status = tick.get("status")
        receipt = tick.get("received_at")
        if not math.isfinite(price) or price <= 0:
            return result
        # Reject mismatched currency units and anomalous stale data.
        if not (0.5 <= price / gia_eod_vnd <= 1.5):
            result["detail"] = "Tick SSI khác đơn vị hoặc chênh lệch lớn; đang hiển thị EOD"
            return result
        if status not in ("LIVE_TICK", "LAST_TICK") or receipt is None:
            return result
        # A tick older than a more recent EOD candle must not replace it.
        if ngay_eod:
            eod_date = pd.to_datetime(ngay_eod, errors="coerce", dayfirst=False)
            received_local = pd.Timestamp(receipt)
            if received_local.tzinfo is not None:
                received_local = received_local.tz_convert("Asia/Ho_Chi_Minh")
            if not pd.isna(eod_date) and received_local.date() < eod_date.date():
                return result
        is_live = status == "LIVE_TICK"
        result.update({
            "price": price,
            "label": "GIÁ REALTIME SSI" if is_live else "GIÁ KHỚP CUỐI SSI",
            "status": status,
            "detail": "Nhận lúc " + date_label(receipt)
                      + (" · Đang trong phiên" if is_live else " · Không phải realtime hiện tại"),
        })
    except (ImportError, AttributeError, OSError, TypeError, ValueError, ZeroDivisionError):
        # WebSocket has not been installed, is offline, or returned invalid data.
        pass
    return result


@st.fragment(run_every="5s")
def _the_tin_hieu_co_gia_live(ma_cp, xep, ten_nganh, gia_dc, ngay_eod):
    """Refresh the existing price card; refresh the full analysis only on EOD changes."""
    context = st.session_state.get("_r_analysis_context")
    if context is not None and context[3] != _source_revisions(ma_cp):
        # A new EOD/SSI file appeared while the page was open. Recompute MA,
        # RSI and X10 from the SAME updated bars, rather than mixing dates.
        st.rerun()  # Full-app rerun is permitted inside a fragment.
    gia_eod = _gia_vnd(gia_dc)
    bao_gia = _gia_ssi_cho_the(ma_cp, gia_eod, ngay_eod)
    ma_html = html_escape(str(ma_cp))
    nganh_html = html_escape(str(ten_nganh or ""))
    tin_hieu_html = html_escape(str(xep.get("tin_hieu", "CHƯA XÁC ĐỊNH")))
    nhan_html = html_escape(bao_gia["label"])
    gia_html = html_escape(_dinh_dang_vnd(bao_gia["price"]))
    time_html = html_escape(bao_gia["detail"])
    diem_tong = float(xep.get("diem_tong", 0))
    diem_ta = float(xep.get("diem_ta", 0))
    diem_fa = float(xep.get("diem_fa", 0))
    st.markdown(f"""
<div style="background:linear-gradient(110deg,#6934f5,#c72ee9);border:2.5px solid #21142e;
            border-radius:24px;box-shadow:0 5px 0 #21142e;color:white;
            padding:20px 22px;display:flex;align-items:center;justify-content:space-between;
            flex-wrap:wrap;gap:16px;margin:12px 0 20px">
  <div style="flex:2;min-width:180px">
    <div style="font-size:33px;line-height:1.15;font-weight:850">{ma_html}</div>
    <div style="font-size:12px;opacity:.9;margin-top:6px">{nganh_html}</div>
  </div>
  <div style="background:#fb8ab6;color:#21142e;border:2px solid #21142e;
              border-radius:14px;padding:10px 14px;font-size:15px;font-weight:800;text-align:center">
    {tin_hieu_html}
  </div>
  <div style="min-width:190px;flex:1.2">
    <div style="font-size:11px;font-weight:700;letter-spacing:.35px">{nhan_html}</div>
    <div style="font-size:26px;font-weight:850;white-space:nowrap">{gia_html}</div>
    <div style="font-size:11px;opacity:.92">{time_html}</div>
  </div>
  <div style="min-width:115px">
    <div style="font-size:11px;font-weight:700">ĐIỂM ĐÁNH GIÁ</div>
    <div style="font-size:27px;font-weight:850">{diem_tong:.0f}<span style="font-size:14px">/100</span></div>
    <div style="font-size:11px;opacity:.9">Kỹ thuật {diem_ta:.1f} · Cơ bản {diem_fa:.1f}</div>
  </div>
</div>
""", unsafe_allow_html=True)




@st.fragment(run_every="5s")
def _dai_thi_truong_vnindex():
    """SSI IndexTick live (when genuinely fresh), else local SSI index EOD."""
    from core.vnindex_dashboard import render_vnindex_strip
    render_vnindex_strip(Path(__file__).resolve().parent)

def dat_khau_vi(ma_kv):
    cfg = cau_hinh_khau_vi(ma_kv)
    for t in TIEU_CHI:
        k = t["key"]
        st.session_state[f"on_{k}"] = k in cfg
        if t["loai"] != "bool":
            st.session_state[f"val_{k}"] = float(cfg.get(k, t["mac_dinh"]))


def cau_hinh_hien_tai():
    cfg = {}
    for t in TIEU_CHI:
        k = t["key"]
        if st.session_state.get(f"on_{k}"):
            cfg[k] = True if t["loai"] == "bool" else float(st.session_state.get(f"val_{k}", t["mac_dinh"]))
    return cfg


if "kv" not in st.session_state:
    st.session_state["kv"] = "can_bang"
    dat_khau_vi("can_bang")

with st.sidebar:
    st.header("1. Khẩu vị đầu tư")
    st.selectbox("Bạn thuộc nhóm nào?", list(KHAU_VI), key="kv", format_func=lambda k: KHAU_VI[k]["ten"],
                 on_change=lambda: dat_khau_vi(st.session_state["kv"]))
    kv_info = KHAU_VI[st.session_state["kv"]]
    st.markdown(f"<div class='x10-card' style='background:{kv_info['mau']}55;padding:10px 14px'>"
                f"<b>{kv_info['mo_ta']}</b><br><span class='x10-small' style='color:#3A3158'>Phù hợp: {kv_info['phu_hop']}</span></div>",
                unsafe_allow_html=True)
    with st.expander("Tuỳ chỉnh tiêu chí lọc", expanded=st.session_state["kv"] == "tuy_chinh"):
        st.caption("Bật tiêu chí nào thì mã phải đạt tiêu chí đó. Sửa ngưỡng theo ý bạn.")
        for nhom in NHOM:
            st.markdown(f"**{nhom}**")
            for t in [x for x in TIEU_CHI if x["nhom"] == nhom]:
                k = t["key"]
                st.checkbox(t["nhan"], key=f"on_{k}", help=t["mo_ta"] or None)
                if t["loai"] != "bool":
                    st.number_input(f"Ngưỡng {t['nhan']}", key=f"val_{k}", min_value=float(t["toi_thieu"]),
                                    max_value=float(t["toi_da"]), step=float(t["buoc"]), format=f"%.{t['thap_phan']}f",
                                    disabled=not st.session_state.get(f"on_{k}"), label_visibility="collapsed")
                    st.caption(f"Đơn vị: {t['don_vi']}" if t["don_vi"] else " ")

    st.header("2. Chọn mã")
    # AURA_FLOW_V6: safely receive a ticker selected on the screener page.
    _pending_analysis = st.session_state.pop("aura_flow_pending_analysis", None)
    if _pending_analysis is not None:
        st.session_state["aura_flow_analysis_input"] = str(_pending_analysis).upper().strip()
        st.session_state["aura_flow_run_once"] = True
    if "aura_flow_analysis_input" not in st.session_state:
        st.session_state["aura_flow_analysis_input"] = "FPT"
    ma = st.text_input("Mã cổ phiếu", key="aura_flow_analysis_input").upper().strip()
    so_ngay = st.slider("Khoảng thời gian giá (ngày)", 365, 1825, 730, step=30)
    so_nam = st.slider("Số năm BCTC (báo cáo năm)", min_value=3, max_value=5, value=5, step=1)
    st.caption("Chọn tối đa 5 năm BCTC (2021–2025 nếu nguồn có đủ).")
    st.header("3. BCTC của bạn (tuỳ chọn)")
    st.caption("Không có BCTC tự động? Tải file mẫu, điền số (đơn vị: tỷ đồng) rồi tải lên.")
    st.download_button("Tải file Excel mẫu", mau_excel(), "mau_bctc_cashgo.xlsx", use_container_width=True)
    file_bctc = st.file_uploader("Tải BCTC của bạn (.xlsx hoặc .csv)", type=["xlsx", "csv"])
    chay = st.button("Phân tích", type="primary", use_container_width=True)
    # AURA_FLOW_V6: auto-run once after explicit screener navigation.
    _auto_run_once = bool(st.session_state.pop("aura_flow_run_once", False))
    chay = bool(chay or _auto_run_once)

huong_dan_3_buoc()

# Streamlit Session State outlives the lifetime of ma_cache. A different page
# may update data/ssi_cache/ohlcv/{symbol}.csv without updating the old result.
_current_context = (ma, so_ngay, so_nam, _source_revisions(ma))
_previous_context = st.session_state.get("_r_analysis_context")

if chay:
    try:
        with st.spinner("Đang lấy lại dữ liệu giá, VN-Index và BCTC..."):
            # The user explicitly requested a fresh analysis, not the old
            # 3600-second cached result.
            ma_cache.clear()
            vni_cache.clear()
            st.session_state["r"] = ma_cache(ma, so_ngay, so_nam, *_current_context[3])
            st.session_state["_r_analysis_context"] = _current_context
            st.session_state.pop("pdf", None)
    except Exception as e:
        st.session_state.pop("r", None)
        st.session_state.pop("_r_analysis_context", None)
        st.error(f"Không lấy được dữ liệu cho mã {ma}: {e}")
elif st.session_state.get("r") is not None:
    old_result = st.session_state["r"]
    old_symbol = str(old_result.get("ma", "")).upper() if isinstance(old_result, dict) else ""
    if old_symbol != ma or (_previous_context and _previous_context[:3] != _current_context[:3]):
        # The input changed; never show the old stock's price and X10.
        st.session_state.pop("r", None)
        st.session_state.pop("_r_analysis_context", None)
        st.session_state.pop("pdf", None)
    elif _previous_context != _current_context:
        # The ticker and settings are unchanged, but its EOD file (or the
        # VN-Index cache) changed. Recalculate automatically once.
        try:
            with st.spinner("SSI có dữ liệu EOD mới; đang đồng bộ phân tích..."):
                st.session_state["r"] = ma_cache(ma, so_ngay, so_nam, *_current_context[3])
                st.session_state["_r_analysis_context"] = _current_context
                st.session_state.pop("pdf", None)
        except Exception as e:
            st.warning(f"Chưa đồng bộ được phân tích từ SSI: {type(e).__name__}")

r = st.session_state.get("r")
# AURA_FLOW_V6: navigation never creates a brokerage transaction.
if isinstance(r, dict) and ma:
    if st.button("⭐ Đưa mã này sang Danh mục theo dõi", key="aura_flow_to_portfolio"):
        st.session_state["aura_flow_pending_portfolio"] = ma
        st.switch_page("pages/02_Danh_muc_dau_tu.py")
if file_bctc is not None:
    try:
        bctc_user = doc_bctc(file_bctc)
        if not bctc_user:
            st.error("Không đọc được BCTC. Hãy dùng đúng file Excel mẫu (tên sheet và cột năm giữ nguyên).")
        elif r:
            r = phan_tich_lai_voi_bctc(r, bctc_user)
            st.session_state.pop("pdf", None)
            st.success("Đang phân tích bằng BCTC do bạn cung cấp (thay cho dữ liệu tự động).")
        else:
            st.info("Đã đọc BCTC. Bấm Phân tích để chấm điểm.")
    except Exception as e:
        st.error(f"Lỗi đọc file BCTC: {e}")
cfg = cau_hinh_hien_tai()
ten_kv = KHAU_VI[st.session_state["kv"]]["ten"]
tabs = st.tabs([
    "Tổng quan",
    "Hợp khẩu vị",
    "Kỹ thuật",
    "Báo cáo tài chính",
    "Tỷ số tài chính",
    "Quét thị trường",
    "Vĩ mô & Chính sách",      # <--- Thêm tab mới ở đây
    "Hiểu doanh nghiệp"         # Tab hồ sơ & luận điểm đầu tư
])

if r:
    ma, bctc, ty_so, gia, kq, xep = r["ma"], r["bctc"], r["ty_so"], r["gia"], r["kq"], r["xep"]
    thong_tin = industry.thong_tin(ma)
    # AURA_V104_COMPANY_IDENTITY: identity only; no financial or score changes.
    from core.company_intelligence import company_meta
    _company_name, _company_sector = company_meta(
        ma,
        sector=thong_tin.get("icb2") or thong_tin.get("icb1", ""),
        company=thong_tin.get("ten", ""),
    )
    ten_nganh = " · ".join(x for x in (_company_name, _company_sector) if x)
    kv = danh_gia(ngu_canh_tu_ket_qua(r), cfg)
    # V10.3: private R2 financial disclosures are shown inside each financial tab.
    # Do not render duplicate global warnings below every tab.
with tabs[0]:
    _dai_thi_truong_vnindex()
    if not r:
        st.info("Chọn khẩu vị và nhập mã ở thanh bên trái, rồi bấm **Phân tích**.")
    else:
        gia_dc = kq["Giá đóng cửa"]
        ngay_eod = None
        try:
            ngay_eod = pd.to_datetime(gia["time"].iloc[-1]).strftime("%Y-%m-%d")
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            pass
        _the_tin_hieu_co_gia_live(ma, xep, ten_nganh, gia_dc, ngay_eod)
        st.markdown(f"<div class='x10-card' style='background:{kv['mau']}'><b style='font-size:18px'>{kv['hang']}</b> "
                    f"· khẩu vị {ten_kv}<br>{tom_tat(ma, ten_kv, kv)}</div>", unsafe_allow_html=True)
        c = st.columns(4)
        c[0].metric("Điểm kỹ thuật (80%)", f"{xep['diem_ta']:.1f}")
        c[1].metric("Điểm cơ bản (20%)", f"{xep['diem_fa']:.1f}")
        c[2].metric("Điểm đánh giá", f"{xep['diem_tong']:.1f}")
        c[3].metric("GTGD 20 phiên", f"{so_vn(xep['gtgd'] / 1e9, 2)} tỷ")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Điều kiện để xem xét mua")
            st.markdown("".join(dong_tieu_chi(n, t, ct) for n, t, ct in xep["dk_mua"]), unsafe_allow_html=True)
        with c2:
            st.subheader("Cảnh báo rủi ro · Không phải lệnh bán")
            st.markdown("".join(dong_tieu_chi(n, t, ct) for n, t, ct in xep["dk_ban"]), unsafe_allow_html=True)
        # AURA_CANDIDATE_STYLES_PANEL_V1: independent research candidates, never auto BUY
        from core.aura_buy_styles import danh_gia_ung_vien
        ung_vien = danh_gia_ung_vien(gia, ty_so, r.get("vni"), gtgd=xep.get("gtgd"))
        # AURA_V107: show both historical and current verdicts without changing scoring.
        from core.aura_signal_explain_v107 import render_signal_explanation
        render_signal_explanation(xep, ung_vien)
        with st.expander("Ứng viên theo triết lý đầu tư (không phải lệnh MUA)", expanded=True):
            st.info(ung_vien["nhan"])
            if ung_vien["phong_cach"]:
                st.write("Các phong cách có tín hiệu: " + "; ".join(ung_vien["phong_cach"]))
            else:
                st.caption("Chưa thỏa setup kỹ thuật cụ thể theo xu hướng, breakout hoặc pullback.")
            for ly_do in ung_vien["ly_do"]:
                st.caption("• " + ly_do)
        st.subheader("Chỉ số chính")
        st.dataframe({k: [so_vn(v, 2)] for k, v in kq.items()}, hide_index=True, use_container_width=True)

        b1, b2 = st.columns([1, 3])
        if b1.button("Tạo báo cáo PDF", type="primary"):
            with st.spinner("Đang dựng PDF..."):
                st.session_state["pdf"] = (ma, xuat_pdf(ma, gia, kq, round(xep["diem_tong"]), 100, dong_pdf(xep),
                                                       xep["tin_hieu"], bctc, ty_so, xep=xep, khau_vi=kv,
                                                       ten_khau_vi=ten_kv, ten_nganh=ten_nganh))
        pdf = st.session_state.get("pdf")
        if pdf and pdf[0] == ma:
            b2.download_button("Tải file PDF", data=pdf[1], file_name=f"AURA_BaoCao_{ma}.pdf", mime="application/pdf")
        st.caption("Tín hiệu định lượng phục vụ học tập, không phải khuyến nghị đầu tư.")

with tabs[1]:
    if not r:
        st.info("Bấm **Phân tích** trước để xem mã có hợp khẩu vị của bạn không.")
    else:
        st.subheader(f"{ma} và khẩu vị {ten_kv}")
        st.caption("Điểm ở phần trên sử dụng dữ liệu đã xác minh; xem phần đánh giá sơ bộ BCTC R2 bên dưới khi có dữ liệu.")
        st.markdown(f"<div class='x10-card' style='background:{kv['mau']}'><b style='font-size:20px'>{kv['hang']}</b><br>"
                    f"{tom_tat(ma, ten_kv, kv)}"
                    f"{thanh_phan_tram(kv['ty_le'] or 0)}</div>", unsafe_allow_html=True)
        if not kv["dong"]:
            st.info("Hãy bật ít nhất một tiêu chí ở thanh bên (mục Tuỳ chỉnh tiêu chí lọc).")
        # AURA_V109_INLINE_R2: show R2 reference values in the missing suitability rows; official score unchanged.
        _kv_display_rows = kv["dong"]
        if file_bctc is None:
            try:
                from core.aura_khauvi_inrow_v109 import annotate_rows
                _kv_display_rows, _ref_count = annotate_rows(
                    ma, kv["dong"], TIEU_CHI, price_vnd=kq.get("Giá đóng cửa"))
                if _ref_count:
                    st.caption(
                        f"{_ref_count} tiêu chí có số liệu BCTC R2 tham khảo. "
                        "Các dòng Tham khảo KHÔNG được tính là Đạt hoặc Không đạt "
                        "và KHÔNG thay đổi % hợp khẩu vị, điểm đánh giá chính thức.")
            except (ImportError, RuntimeError, ValueError, TypeError, KeyError, AttributeError, IndexError, ZeroDivisionError):
                st.caption("Tỷ số BCTC R2 tham khảo chưa đọc được cho bảng khẩu vị.")
        for nhom in NHOM:
            ds = [d for d in _kv_display_rows if d["nhom"] == nhom]
            if ds:
                st.markdown(f"**{nhom}**")
                st.markdown("".join(
                    f"<div class='x10-row'>{tag_trang_thai(d['trang_thai'])}<div style='flex:1'><b>{d['nhan']}</b>"
                    f"<div class='x10-small' style='color:#6B6389;opacity:1'>Ngưỡng: {d['nguong']}</div></div>"
                    f"<div style='font-weight:700'>{d['gia_tri']}</div></div>" for d in ds), unsafe_allow_html=True)
        # AURA_V110_SUITABILITY_COMPARISON: display-only, source-aware ranking.
        from core.aura_suitability_consistency_v110 import render_suitability_comparison
        render_suitability_comparison(
            ma, r, KHAU_VI, cau_hinh_khau_vi, danh_gia, ngu_canh_tu_ket_qua
        )

with tabs[2]:
    st.subheader("Biểu đồ kỹ thuật đa khung thời gian")
    st.caption("Nến SSI EOD · Tùy chọn khung ngày, tuần, tháng, năm · Không dùng tick realtime để tính chỉ báo.")
    if not r:
        st.info("Chọn cổ phiếu ở thanh bên và bấm **Phân tích** để mở biểu đồ kỹ thuật.")
    else:
        from core.technical_chart import (OVERLAY_OPTIONS, PANEL_OPTIONS,
                                          chart_price_history, create_technical_figure,
                                          summary_stats)
        c_period, c_chart, c_range = st.columns([1.4, 1, 1.1])
        period = c_period.radio("Khung nến", ["Ngày", "Tuần", "Tháng", "Năm"],
                                horizontal=True, key="chart_period")
        chart_type = c_chart.radio("Kiểu biểu đồ", ["Nến", "Đường"],
                                   horizontal=True, key="chart_type")
        view_range = c_range.selectbox("Khoảng hiển thị",
                                       ["Toàn bộ", "6 tháng", "1 năm", "2 năm", "3 năm", "5 năm"],
                                       key="chart_range")
        overlay_col, panel_col = st.columns(2)
        overlays = overlay_col.multiselect("Đường & dải trên biểu đồ giá", OVERLAY_OPTIONS,
                                           default=["MA20", "MA50"],
                                           placeholder="Chọn MA, EMA hoặc Bollinger...",
                                           key="chart_overlays")
        panels = panel_col.multiselect("Chỉ báo khung bên dưới", PANEL_OPTIONS,
                                       default=["Khối lượng", "RSI (14)"],
                                       placeholder="Chọn RSI, MACD, Stochastic...",
                                       key="chart_panels")
        # Nến năm ít điểm và đôi khi có râu nến cao bất thường. Mặc định
        # ưu tiên trục dễ đọc, nhưng luôn cho phép xem trọn biên độ gốc.
        annual_full_axis = False
        if period == "Năm":
            with st.expander("Tùy chọn nâng cao cho biểu đồ năm", expanded=False):
                annual_full_axis = st.checkbox(
                    "Hiển thị toàn bộ biên độ cao nhất/thấp nhất, kể cả giá cực trị",
                    value=False, key="chart_annual_full_axis",
                    help="Chỉ thay đổi giới hạn trục giá của đồ thị, không sửa dữ liệu SSI.")
        try:
            chart_source = chart_price_history(Path(__file__).resolve().parent, ma,
                                               gia, r.get("nguon_gia", ""))
            fig, shown_bars, missing = create_technical_figure(
                chart_source, symbol=ma, period=period, chart_type=chart_type,
                overlays=overlays, panels=panels, range_choice=view_range,
                annual_axis_mode="Toàn bộ" if annual_full_axis else "Tối ưu")
            stats = summary_stats(shown_bars)
            last_date = stats["last_date"]
            if period == "Năm":
                first_year = int(shown_bars["time"].iloc[0].year)
                last_year = int(last_date.year)
                st.caption(
                    f"**Nến năm:** {stats['candles']} năm ({first_year}–{last_year}). "
                    "Mỗi nến tóm tắt giao dịch trong một năm, không phải một ngày. "
                    f"Nến cuối chỉ ghi nhận đến **{last_date:%d/%m/%Y}**; "
                    "nếu năm chưa kết thúc, đây là **nến lũy kế**, không thể so trực tiếp "
                    "khối lượng với cả năm trước.")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Giá đóng cửa cuối kỳ", _dinh_dang_vnd(stats.get("last_close")))
            # Chênh lệch giá thô KHÔNG phải lợi suất điều chỉnh quyền/cổ tức.
            if stats["candles"] >= 2 and math.isfinite(stats.get("range_return", float("nan"))):
                m2.metric("Thay đổi giá thô*", f"{stats['range_return']:+.2f}%")
            else:
                m2.metric("Thay đổi giá thô*", "Chưa đủ nến")
            m3.metric("Số nến đang xem", f"{stats['candles']:,}")
            m4.metric("RSI 14 · khung " + period.lower(),
                      f"{stats['rsi']:.1f}" if stats.get("rsi") is not None else "—")
            fig = theme_plotly(fig)
            fig.update_layout(margin=dict(t=82, b=34, l=35, r=18),
                              legend=dict(orientation="h", y=1.12, x=0))
            st.plotly_chart(fig, use_container_width=True,
                            config={"displaylogo": False, "scrollZoom": True})
            if getattr(fig.layout, "meta", None) and fig.layout.meta.get("annual_axis_clipped"):
                st.caption("ⓘ **Trục giá đang thu gọn** để các nến dễ đọc vì có "
                           "giá cao nhất chênh lệch lớn so với vùng giá thông thường. "
                           "Bật **Hiển thị toàn bộ biên độ** ở tùy chọn nâng cao để xem "
                           "đầy đủ râu nến. Nến và dữ liệu CSV gốc không bị thay đổi.")
            if missing:
                if period == "Năm":
                    st.caption("ⓘ Không đủ nến năm cho một số chỉ báo đã chọn. "
                               "MA20 cần 20 năm; RSI14 cần khoảng 15 năm. "
                               "Bạn có thể chuyển sang **Tháng** hoặc **Tuần** để sử dụng các chỉ báo này.")
                else:
                    st.caption("ⓘ Một số chỉ báo chưa hiển thị do thiếu nến: " + " ".join(missing))
            st.caption("* **Thay đổi giá thô** được tính từ giá đóng cửa của nến đầu tiên "
                       "đến giá đóng cửa của nến cuối trong khoảng xem; **không phải lợi suất "
                       "đầu tư**. Dữ liệu SSI EOD chưa được xác minh điều chỉnh chia tách, "
                       "cổ tức hoặc các quyền khác.")
            st.caption(f"Nguồn: {r.get('nguon_gia', 'SSI EOD')} · "
                       f"Nến theo **{period.lower()}**; khung tuần chốt thứ Sáu. "
                       "Chỉ báo tính lại trên toàn bộ lịch sử có sẵn theo khung được chọn; "
                       "**điểm đánh giá không đổi**, vẫn tính theo nến ngày.")
            with st.expander("Xem bảng nến và tải dữ liệu biểu đồ"):
                export = shown_bars[["time", "open", "high", "low", "close", "volume"]].copy()
                export.columns = ["Ngày giao dịch cuối kỳ", "Mở cửa", "Cao nhất", "Thấp nhất",
                                  "Đóng cửa", "Khối lượng"]
                st.dataframe(export.tail(30).iloc[::-1], hide_index=True, use_container_width=True)
                st.download_button("Tải CSV nến " + period.lower(),
                    data=export.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"AURA_{ma}_{period}_EOD.csv", mime="text/csv",
                    key="chart_download")
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            st.error(f"Không thể vẽ biểu đồ kỹ thuật: {type(exc).__name__}. Kiểm tra dữ liệu OHLCV SSI.")

with tabs[3]:
    # AURA_V99_LOCAL_BCTC_PARITY
    _v99_fin_shown = False
    if r:
        try:
            from core.aura_original_bctc_v99 import render_original_statements
            _v99_fin_shown = render_original_statements(ma)
        except (ImportError, RuntimeError, ValueError, TypeError, AttributeError):
            _v99_fin_shown = False
    # AURA_V98_ANNUAL_CANDIDATE_PANEL
    # Supplement the original audited-BCTC tab, never replace real statements.
    if r and not _v99_fin_shown:
        try:
            from core.aura_r2_financial_v98 import render_symbol_annual
            render_symbol_annual(Path(__file__).resolve().parent, ma)
        except (ImportError, RuntimeError, ValueError, TypeError, AttributeError):
            pass
    if _v99_fin_shown:
        pass
    elif not r or not bctc:
        st.info("Chưa có BCTC gốc đã xác minh cho mã này; tỷ số sơ bộ bên trên không thay thế BCTC gốc." if r else "Bấm **Phân tích** để xem báo cáo tài chính.")
    else:
        for k, ten in STATEMENTS.items():
            if k in bctc:
                st.subheader(ten)
                tim = st.text_input(f"Lọc chỉ tiêu ({ten})", key=f"loc_{k}", placeholder="vd: lãi, tài sản, nợ...")
                df = bctc[k]
                if tim:
                    df = df[df.index.astype(str).str.contains(tim, case=False, na=False)]
                st.dataframe(df.style.format("{:,.0f}"), use_container_width=True, height=380)

with tabs[4]:
    # AURA_V99_LOCAL_BCTC_PARITY_RATIOS
    _v99_ratios_shown = False
    if r:
        try:
            from core.aura_original_bctc_v99 import render_original_ratios
            _v99_ratios_shown = render_original_ratios(ma)
        except (ImportError, RuntimeError, ValueError, TypeError, AttributeError):
            _v99_ratios_shown = False
    # AURA_V982_PROVISIONAL_RATIOS_TAB
    if _v99_ratios_shown:
        pass
    elif not r:
        st.info("Bấm **Phân tích** để xem tỷ số tài chính.")
    elif ty_so.empty:
        # Display only: provisional R2 research, not audited source and not scores.
        try:
            from core.aura_financial_ratios_v982 import render_provisional_ratios
            _candidate_shown = render_provisional_ratios(Path(__file__).resolve().parent, ma)
        except (ImportError, OSError, RuntimeError, ValueError, TypeError, AttributeError):
            _candidate_shown = False
        if not _candidate_shown:
            st.info("Chưa có tỷ số tài chính đã xác minh hoặc bảng sơ bộ cho mã này.")
    else:
        st.dataframe(ty_so.style.format("{:,.2f}"), use_container_width=True)
        chon = st.selectbox("Xem biểu đồ tỷ số", list(ty_so.index))
        s = ty_so.loc[chon].dropna()
        f2 = go.Figure(go.Bar(x=[str(i) for i in s.index], y=s.values, marker_color=MAU["tim"]))
        f2.update_layout(title=chon)
        st.plotly_chart(theme_plotly(f2, 350), use_container_width=True)

with tabs[5]:
    st.subheader("Tìm mã hợp khẩu vị của bạn")
    st.caption(f"Quét theo khẩu vị đang chọn: **{ten_kv}** ({len(cfg)} tiêu chí bật). Quét càng nhiều mã càng lâu.")
    q1, q2 = st.columns(2)
    nganh = q1.multiselect("Ngành (ICB cấp 1)", industry.nganh_cap1())
    san = q2.multiselect("Sàn", ["HOSE", "HNX", "UPCOM"], default=["HOSE", "HNX"])
    nhap = st.text_area("Hoặc nhập danh sách mã (cách nhau bằng dấu phẩy)", placeholder="FPT, VNM, HPG, MWG")
    toi_da = st.slider("Số mã tối đa", 5, 60, 20)
    if st.button("Quét theo khẩu vị", type="primary"):
        if not cfg:
            st.warning("Bạn chưa bật tiêu chí nào. Hãy chọn khẩu vị hoặc bật tiêu chí ở thanh bên.")
        else:
            ds = [m.strip().upper() for m in nhap.replace("\n", ",").split(",") if m.strip()] or \
                 industry.loc_ma(nganh or None, None, san or None, toi_da)
            ds = ds[:toi_da]
            if not ds:
                st.warning("Không có mã nào khớp bộ lọc ngành và sàn.")
            else:
                bar = st.progress(0.0, text="Đang quét...")
                vni = vni_cache(so_ngay, _source_revisions("VNINDEX")[1])
                st.session_state["quet"] = quet_nhieu_ma(
                    ds, so_ngay, so_nam, vni, cfg,
                    tien_do=lambda i, n, m: bar.progress(i / n, text=f"Đang quét {m} ({i + 1}/{n})" if m else "Xong"))
                bar.empty()
    if st.session_state.get("quet") is not None:
        df = st.session_state["quet"]
        st.dataframe(df, hide_index=True, use_container_width=True,
                     column_config={"% hợp khẩu vị": st.column_config.ProgressColumn("% hợp khẩu vị", min_value=0, max_value=100, format="%d%%")})
        st.download_button("Tải kết quả CSV", df.to_csv(index=False).encode("utf-8-sig"), "AURA_Quet_Khau_Vi.csv", "text/csv")



# Dynamic source-linked company information. Both tabs remain on this same page.
with tabs[6]:
    # AURA_FOREIGN_MACRO_PANEL_V1: SSI EOD flows and verified policy events
    from core.aura_macro_foreign import render_macro_panel
    render_macro_panel(Path(__file__).resolve().parent, r["ma"] if r else None)
    if not r:
        st.info("Chọn mã và bấm **Phân tích** để xem chính sách liên quan đến ngành.")
    else:
        from core.company_intelligence import render_policy_page
        info = industry.thong_tin(r["ma"])
        render_policy_page(r["ma"], sector=info.get("icb2") or info.get("icb1", ""),
                           company=info.get("ten", ""))

with tabs[7]:
    # Show the business profile FIRST; place external headlines lower down.
    # AURA_V104_HOSO_R2_DISPLAY: private R2 BCTC is used in this tab ONLY.
    # Never mutate session_state["r"] or rerun X10 / Smart Rating with unverified data.
    _hoso_view = r
    if r and file_bctc is None:
        try:
            from core.aura_original_bctc_v99 import load_original
            from core.analysis import tinh_ty_so
            _snapshot = load_original(r["ma"])
            if _snapshot:
                _statements, _source_meta = _snapshot
                if _statements:
                    _hoso_view = dict(r)
                    _hoso_view["bctc"] = _statements
                    _hoso_view["ty_so"] = tinh_ty_so(_statements)
                    _hoso_view["_aura_v104_unverified_display"] = True
        except (ImportError, RuntimeError, ValueError, TypeError, KeyError, AttributeError):
            pass
    ve_tab_hoso(_hoso_view)
    if r:
        st.divider()
        from core.company_intelligence import render_company_news
        info = industry.thong_tin(r["ma"])
        render_company_news(r["ma"], sector=info.get("icb2") or info.get("icb1", ""),
                            company=info.get("ten", ""))
