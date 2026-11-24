import streamlit as st
from html import escape
from core.aura_brand import logo_html, banner_html

MAU = {
    "muc": "#1B1233", "nen": "#F4EFFF", "trang": "#FFFFFF",
    "tim": "#6C3BFF", "tim_dam": "#5B2EFF", "hong": "#FF4F9A", "lime": "#B8F13C",
    "cyan": "#22D3EE", "vang": "#FFD43B", "cam": "#FF8A3D", "do": "#E5254B",
    "xanh_la": "#078A4F", "chu_mo": "#6B6389", "vien": "#DCCFFB",
}
DAY_MAU = [MAU["tim"], MAU["hong"], MAU["cyan"], MAU["cam"], MAU["lime"], MAU["vang"]]
PASTEL = {
    "tim": MAU["tim"],
    "hong": MAU["hong"],
    "cyan": MAU["cyan"],
    "vang": MAU["vang"],
    "lime": MAU["lime"],
    "cam": MAU["cam"],
    "do": MAU["do"],
    "xanh_la": MAU["xanh_la"],
    "trang": MAU["trang"],
    "nen": MAU["nen"],
    "muc": MAU["muc"],
}
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&display=swap');
html, body, .stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea, .stApp select, .stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp td, .stApp th {font-family:'Be Vietnam Pro',system-ui,sans-serif;}
[data-testid="stIconMaterial"], span.material-icons, span.material-symbols-rounded, span.material-symbols-outlined {font-family:"Material Symbols Rounded","Material Symbols Outlined"!important;}
.stApp{background:#F4EFFF;color:#1B1233}
.block-container{padding-top:1.2rem;max-width:1280px}
header[data-testid="stHeader"]{background:transparent}
h1,h2,h3,h4{font-weight:800;letter-spacing:-0.01em;color:#1B1233}
[data-testid="stSidebar"]{background:#FFFFFF;border-right:2px solid #1B1233}
[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{color:#6C3BFF}
[data-testid="stMetric"]{background:#fff;border:2px solid #1B1233;border-radius:18px;padding:12px 16px}
[data-testid="stMetricLabel"]{font-weight:600;color:#3A3158}
[data-testid="stMetricValue"]{font-weight:800}
[data-testid="stHorizontalBlock"]>div:nth-child(4n+1) [data-testid="stMetric"]{background:#DDF9A4}
[data-testid="stHorizontalBlock"]>div:nth-child(4n+2) [data-testid="stMetric"]{background:#FFD0E5}
[data-testid="stHorizontalBlock"]>div:nth-child(4n+3) [data-testid="stMetric"]{background:#C6F3FC}
[data-testid="stHorizontalBlock"]>div:nth-child(4n+4) [data-testid="stMetric"]{background:#FFE9A3}
.stButton>button,.stDownloadButton>button{border:2px solid #1B1233;border-radius:14px;font-weight:800;color:#1B1233;background:#fff;box-shadow:3px 3px 0 #1B1233;transition:transform .08s,box-shadow .08s}
.stButton>button:hover,.stDownloadButton>button:hover{transform:translate(-1px,-1px);box-shadow:5px 5px 0 #1B1233;border-color:#1B1233;color:#1B1233}
.stButton>button:active,.stDownloadButton>button:active{transform:translate(2px,2px);box-shadow:1px 1px 0 #1B1233}
.stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"],button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primary"]:hover{background:#FF4F9A;color:#1B1233}
button[data-baseweb="tab"]{font-weight:700;font-size:15px}
button[data-baseweb="tab"][aria-selected="true"]{color:#6C3BFF}
[data-baseweb="tab-highlight"]{background:#6C3BFF;height:4px;border-radius:2px}
[data-testid="stAlert"]{border:2px solid #1B1233;border-radius:16px}
[data-testid="stExpander"]{border:2px solid #1B1233;border-radius:16px;background:#fff}
[data-testid="stDataFrame"]{border:2px solid #1B1233;border-radius:14px;overflow:hidden}
.x10-hero{display:flex;align-items:center;gap:14px;margin-bottom:6px}
.x10-logo{width:52px;height:52px;border-radius:16px;background:#6C3BFF;border:2px solid #1B1233;box-shadow:3px 3px 0 #1B1233;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:18px;color:#B8F13C}
.x10-title{font-size:26px;font-weight:800;line-height:30px;color:#1B1233}
.x10-sub{font-size:13px;color:#6B6389}
.x10-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;background:#FFD43B;border:2px solid #1B1233;box-shadow:4px 4px 0 #1B1233;border-radius:20px;padding:14px 18px;margin:12px 0 18px 0}
.x10-step{display:flex;align-items:center;gap:10px;font-size:14px;line-height:19px}
.x10-num{width:32px;height:32px;border-radius:50%;border:2px solid #1B1233;display:flex;align-items:center;justify-content:center;font-weight:800;flex:none}
.x10-signal{background:linear-gradient(145deg,#5B2EFF 0%,#9B3BFF 60%,#D13BFF 100%);color:#fff;border:2px solid #1B1233;box-shadow:5px 5px 0 #1B1233;border-radius:24px;padding:18px 22px;display:flex;flex-wrap:wrap;gap:18px;align-items:center;justify-content:space-between;margin-bottom:14px}
.x10-chip{display:inline-block;padding:6px 16px;border-radius:12px;border:2px solid #1B1233;font-weight:800;letter-spacing:1px;color:#1B1233}
.x10-big{font-size:34px;font-weight:800;line-height:38px}
.x10-small{font-size:12px;opacity:.85}
.x10-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:2px solid #EFE8FF;font-size:14px}
.x10-tag{display:inline-block;padding:2px 10px;border-radius:8px;border:1.5px solid #1B1233;font-size:12px;font-weight:800;color:#1B1233;white-space:nowrap}
.x10-card{background:#fff;border:2px solid #1B1233;border-radius:20px;padding:16px 18px;margin-bottom:12px}
.x10-bar{height:10px;border-radius:5px;background:#fff;border:1.5px solid #1B1233;overflow:hidden;margin-top:8px}
.x10-bar>div{height:100%;background:#1B1233}
"""


def ap_dung_theme():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def theme_plotly(fig, cao=None):
    fig.update_layout(
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        font=dict(family="Be Vietnam Pro, system-ui, sans-serif", color=MAU["muc"], size=13),
        colorway=DAY_MAU, margin=dict(t=30, l=10, r=10, b=10),
        legend=dict(orientation="h", y=1.04, x=0),
    )
    fig.update_xaxes(gridcolor="#EFE8FF", linecolor=MAU["muc"])
    fig.update_yaxes(gridcolor="#EFE8FF", linecolor=MAU["muc"])
    if cao:
        fig.update_layout(height=cao)
    return fig


def tieu_de_trang(tieu_de="AURA", phu_de="Phân tích cổ phiếu Việt Nam theo khẩu vị của bạn"):
    st.markdown(
        f'<div class="x10-hero">{logo_html(size=54)}<div>'
        f'<div class="x10-title">{escape(tieu_de)}</div>'
        f'<div class="x10-sub">{escape(phu_de)}</div></div></div>', unsafe_allow_html=True)


def huong_dan_3_buoc():
    st.markdown(
        '<div class="x10-steps">'
        '<div class="x10-step"><div class="x10-num" style="background:#FF4F9A">1</div><div><b>Chọn khẩu vị</b><br>An toàn, cân bằng, tăng trưởng...</div></div>'
        '<div class="x10-step"><div class="x10-num" style="background:#22D3EE">2</div><div><b>Nhập mã</b><br>Rồi bấm Phân tích</div></div>'
        '<div class="x10-step"><div class="x10-num" style="background:#B8F13C">3</div><div><b>Đọc kết luận</b><br>Hợp hay không, vì sao, tải PDF</div></div>'
        '</div>', unsafe_allow_html=True)


_MAU_TIN_HIEU = {"CÓ THỂ XEM XÉT MUA": MAU["lime"], "THEO DÕI": MAU["vang"], "THEO DÕI · CẢNH BÁO": MAU["vang"], "TRÁNH / RỦI RO CAO": "#FF8FA3"}


def the_tin_hieu(ma, tin_hieu, diem_tong, diem_ta, diem_fa, gia=None, ten_nganh=""):
    mau = _MAU_TIN_HIEU.get(tin_hieu, MAU["vang"])
    gia_html = f'<div><div class="x10-small">GIÁ ĐÓNG CỬA</div><div class="x10-big">{gia}</div></div>' if gia else ""
    nganh = f'<div class="x10-small">{ten_nganh}</div>' if ten_nganh else ""
    st.markdown(
        f'<div class="x10-signal"><div><div class="x10-big">{ma}</div>{nganh}</div>'
        f'<div class="x10-chip" style="background:{mau};font-size:20px">{tin_hieu}</div>{gia_html}'
        f'<div><div class="x10-small">ĐIỂM ĐÁNH GIÁ</div><div class="x10-big">{diem_tong:.0f}<span style="font-size:16px">/100</span></div>'
        f'<div class="x10-small">Kỹ thuật {diem_ta:.0f} · Cơ bản {'chưa có BCTC' if diem_fa is None else f'{diem_fa:.0f}'}</div></div></div>',
        unsafe_allow_html=True)


_MAU_TRANG_THAI = {"Đạt": MAU["lime"], "Không đạt": "#FF8FA3", "Thiếu dữ liệu": "#E3E0EE",
                   "Kích hoạt": "#FF8FA3", "Không": MAU["lime"], "N/A": "#E3E0EE",
                   "Không áp dụng": "#D6E4F0",
                   "Tham khảo": "#FFE8A3", "Thiếu BCTC": "#E3E0EE"}


def tag_trang_thai(trang_thai):
    mau = _MAU_TRANG_THAI.get(trang_thai, "#E3E0EE")
    return f'<span class="x10-tag" style="background:{mau}">{trang_thai}</span>'


def dong_tieu_chi(ten, trang_thai, chi_tiet):
    return (f'<div class="x10-row">{tag_trang_thai(trang_thai)}<div><b>{ten}</b>'
            f'<div class="x10-small" style="color:#6B6389;opacity:1">{chi_tiet}</div></div></div>')


def thanh_phan_tram(ty_le, mau=None):
    mau = mau or MAU["muc"]
    return f'<div class="x10-bar"><div style="width:{max(0, min(100, ty_le)):.0f}%;background:{mau}"></div></div>'
# Shared navigation and finishing touches for the two-page SSI 2.0 interface.
# Keep the existing X10 palette; only soften surfaces and unify page styling.
CSS += """
[data-testid="stSidebarNav"]{display:none!important}
[data-testid="stSidebar"]{background:#FEFDFF;border-right:1px solid #E1D5FA}
.stApp{background:#F7F4FF}
.block-container{max-width:1450px;padding-top:1.45rem}
[data-testid="stMetric"]{border:1px solid #E0D5F9;box-shadow:0 3px 12px rgba(53,31,112,.055);border-radius:17px}
[data-testid="stDataFrame"]{border:1px solid #DFD4F4;border-radius:15px;box-shadow:0 4px 14px rgba(53,31,112,.045)}
[data-testid="stExpander"]{border:1px solid #DED2F4;border-radius:15px}
[data-testid="stSelectbox"]>div,[data-testid="stMultiSelect"]>div{border-radius:12px}
.stButton>button,.stDownloadButton>button{box-shadow:0 2px 0 #271640;border:1.5px solid #271640;border-radius:11px}
.stButton>button:hover,.stDownloadButton>button:hover{box-shadow:0 4px 0 #271640}
.stButton>button[kind="primary"],button[data-testid="stBaseButton-primary"]{background:#6C3BFF;color:#fff}
.stButton>button[kind="primary"]:hover,button[data-testid="stBaseButton-primary"]:hover{color:#fff;background:#592BDB}
[data-testid="stSidebar"] .batday-nav-brand{padding:14px 16px;border-radius:17px;
 color:#fff;background:linear-gradient(118deg,#4724AE,#8045FB 68%,#C24EDA);
 box-shadow:0 5px 14px rgba(86,47,172,.16);margin:3px 0 14px}
.batday-nav-brand strong{display:block;font-size:18px;letter-spacing:-.03em}
.batday-nav-brand span{font-size:11px;color:#E9DBFF}
[data-testid="stSidebar"] [data-testid="stPageLink"]{border-radius:12px}
[data-testid="stSidebar"] [data-testid="stPageLink"]:hover{background:#F0E9FF}
[data-testid="stSidebar"] a{color:#38205D}
.batday-overline{font-size:11px;font-weight:800;letter-spacing:.14em;color:#8565CF;text-transform:uppercase}
.batday-note{font-size:12px;color:#6B6389}
"""


def _badge_suc_khoe_du_lieu():
    """Nhãn trạng thái hệ thống ở sidebar: chỉ đọc, không gọi API, không bao giờ làm vỡ trang."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now_vn = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        try:
            from core.aura_ssi_realtime_v97 import get_feed
            ws_on = get_feed() is not None
        except Exception:
            ws_on = False
        ws_html = (f'<span class="x10-tag" style="background:{MAU["lime"]}">WebSocket: Live</span>'
                   if ws_on else
                   f'<span class="x10-tag" style="background:#E3E0EE">WebSocket: Ngoài giờ</span>')
        st.markdown(
            f'<div class="x10-card" style="padding:9px 13px;margin:0 0 12px;font-size:11.5px;'
            f'line-height:17px;color:#3A3158">'
            f'<b style="color:#1B1233">Trạng thái hệ thống</b><br>'
            f'SSI EOD · R2: Tham khảo &nbsp;·&nbsp; BCTC: Sơ bộ, chưa xác minh<br>'
            f'{ws_html} &nbsp;·&nbsp; Giờ VN {now_vn:%H:%M %d/%m}'
            f'</div>', unsafe_allow_html=True)
    except Exception:
        pass


def dieu_huong_trang():
    """Replace Streamlit's default 'app' label with consistent Vietnamese links."""
    with st.sidebar:
        st.markdown(
            f'<div class="aura-brand-banner" style="margin:4px 7px 18px 0;">'
            f'{banner_html()}</div>',
            unsafe_allow_html=True)
        _badge_suc_khoe_du_lieu()
        st.markdown('<div class="aura-nav-kicker">KHÁM PHÁ THỊ TRƯỜNG · 3 BƯỚC</div>', unsafe_allow_html=True)
        st.page_link("pages/01_Tram_loc_thi_truong.py",
                     label="01  ·  TRẠM LỌC THỊ TRƯỜNG", use_container_width=True)
        st.page_link("app.py", label="02  ·  PHÂN TÍCH CỔ PHIẾU",
                     use_container_width=True)
        st.page_link("pages/02_Danh_muc_dau_tu.py",
                     label="03  ·  DANH MỤC ĐẦU TƯ", use_container_width=True)
        st.divider()

# AURA minimal finishing layer: keep the existing scoring styles, soften decorative accents.
CSS += """
.x10-hero{margin:3px 0 11px;gap:13px}
.x10-title{font-size:27px;letter-spacing:-.035em}
[data-testid="stSidebar"] .batday-nav-brand{padding:12px 13px}
[data-testid="stSidebar"] .batday-nav-brand strong{font-size:20px;letter-spacing:.02em}
"""

# AURA 3.0: polished, consistent palette from the supplied neon logo.
# Presentation only. No changes to screening logic or calculations.
CSS += """
:root{--aura-night:#1B0A35;--aura-violet:#7638EF;--aura-pink:#EE4FC5;--aura-cyan:#67DBEE}
.stApp{background:linear-gradient(180deg,#FAF8FF 0%,#F5F0FF 100%);color:#211534}
[data-testid="stSidebar"]{background:#FEFCFF;border-right:1px solid #E0D3F8}
[data-testid="stSidebar"] .batday-nav-brand{
  background:linear-gradient(112deg,#27104F 0%,#5C27CD 52%,#A735BA 100%);
  border:1.5px solid #1B0A35;border-radius:20px;padding:16px 17px;
  box-shadow:5px 5px 0 #1B0A35,0 14px 25px rgba(48,13,90,.16);
  margin:4px 6px 18px 0;min-height:77px}
[data-testid="stSidebar"] .batday-nav-brand img{border-radius:14px;
  border:1px solid rgba(255,255,255,.20);
  box-shadow:3px 3px 0 rgba(9,4,25,.92),0 8px 16px rgba(4,1,17,.37)}
[data-testid="stSidebar"] .batday-nav-brand strong{font-size:22px;color:#fff;letter-spacing:.045em}
[data-testid="stSidebar"] .batday-nav-brand span{color:#F3E8FF;font-size:10.5px}
[data-testid="stSidebar"] [data-testid="stPageLink"]{border-radius:13px;margin:4px 0}
[data-testid="stSidebar"] [data-testid="stPageLink"]:hover{
  background:#EDE1FF;box-shadow:inset 3px 0 0 #8F40F3}
[data-testid="stSidebar"] a[aria-current="page"],
[data-testid="stSidebar"] [data-testid="stPageLinkCurrent"]{
  background:linear-gradient(105deg,#E6D6FF,#F3E7FC)!important;
  border-left:4px solid #7B38E8!important;
  border-radius:11px;box-shadow:2px 3px 0 rgba(27,10,53,.17)!important}
[data-testid="stSidebar"] a{font-weight:700;color:#3A2260}
.x10-steps{
  background:linear-gradient(110deg,#EFE3FF 0%,#F8E9FF 55%,#FFE2F2 100%);
  border:1.5px solid #D7BFF6;box-shadow:4px 4px 0 #1B0A35;
  border-radius:21px;color:#29193F}
.x10-num{border:2px solid #27113F}
.x10-signal{box-shadow:5px 5px 0 #1B0A35,0 16px 32px rgba(67,29,124,.16);
  background:linear-gradient(112deg,#402093,#7838EF 55%,#C529B9 100%)}
.x10-card{border:1.5px solid #DFCEF8;box-shadow:3px 4px 0 rgba(27,10,53,.18)}
[data-testid="stTabs"] button[aria-selected="true"]{color:#6827DD!important}
[data-testid="stTabs"] [data-baseweb="tab-highlight"]{background:#8E44E8}
@media(max-width:700px){[data-testid="stSidebar"] .batday-nav-brand{min-height:60px}}
"""


# AURA 3.1 - vivid ORIGINAL AURA colors, not a new black/neon theme.
# Applied last to intentionally override the preceding pastel-only finish.
CSS += """
.stApp{background:#F6F0FF!important;color:#1B1233!important}
[data-testid="stSidebar"]{background:#FFF9FF!important;border-right:2px solid #D8C3FC!important}
[data-testid="stSidebar"] .aura-brand-banner img{
  border:2px solid #1B1233!important;border-radius:20px!important;
  box-shadow:6px 6px 0 #1B1233,0 15px 27px rgba(55,18,116,.24)!important;
  height:auto!important;aspect-ratio:2.35/1;object-fit:cover!important}
[data-testid="stSidebar"] [data-testid="stPageLink"]{
  background:linear-gradient(110deg,#7436FA 0%,#B931DF 100%)!important;
  border:2px solid #27123C!important;border-radius:13px!important;
  box-shadow:3px 3px 0 #27123C!important;
  margin:8px 4px 10px 0!important;min-height:43px;
  transition:filter .12s ease,transform .12s ease!important}
[data-testid="stSidebar"] [data-testid="stPageLink"]:hover{
  filter:brightness(1.09);transform:translateY(-1px);box-shadow:4px 5px 0 #27123C!important}
[data-testid="stSidebar"] [data-testid="stPageLink"] a,
[data-testid="stSidebar"] [data-testid="stPageLink"] p,
[data-testid="stSidebar"] [data-testid="stPageLink"] span,
[data-testid="stSidebar"] [data-testid="stPageLink"] svg{color:white!important;fill:white!important;font-weight:800!important}
[data-testid="stSidebar"] [data-testid="stPageLink"]:has(a[aria-current="page"]),
[data-testid="stSidebar"] [data-testid="stPageLinkCurrent"],
[data-testid="stSidebar"] a[aria-current="page"]{
  background:linear-gradient(105deg,#E734BB 0%,#8137F9 56%,#16BDE7 100%)!important;
  border-color:#27123C!important;box-shadow:4px 4px 0 #27123C!important}
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"]{color:white!important}
[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3{color:#682CF0!important;font-weight:900!important}
.x10-steps{
  background:#FFD43B!important;border:2px solid #1B1233!important;
  color:#1B1233!important;box-shadow:5px 6px 0 #1B1233!important}
.x10-signal{
  background:linear-gradient(107deg,#6528F6 0%,#8B2BEC 53%,#CE27D9 100%)!important;
  color:#fff!important;border:2px solid #1B1233!important;
  box-shadow:5px 6px 0 #1B1233!important}
.x10-card{background:#fff;border:2px solid #1B1233!important;
  box-shadow:3px 4px 0 rgba(27,18,51,.18)!important}
[data-testid="stMetric"]{
  border:1.5px solid #E2D1F9!important;
  box-shadow:2px 3px 0 rgba(27,18,51,.11)!important}
[data-testid="stHorizontalBlock"]>div:nth-child(4n+1) [data-testid="stMetric"]{background:#DDF9A4!important}
[data-testid="stHorizontalBlock"]>div:nth-child(4n+2) [data-testid="stMetric"]{background:#FFD0E5!important}
[data-testid="stHorizontalBlock"]>div:nth-child(4n+3) [data-testid="stMetric"]{background:#C6F3FC!important}
[data-testid="stHorizontalBlock"]>div:nth-child(4n+4) [data-testid="stMetric"]{background:#FFE9A3!important}
[data-testid="stTabs"] button[aria-selected="true"]{
 color:#6C3BFF!important;font-weight:900!important}
[data-testid="stTabs"] [data-baseweb="tab-highlight"]{
 background:#6C3BFF!important;height:4px!important}
[data-testid="stExpander"],[data-testid="stDataFrame"]{
 border:1.5px solid #CCB7F4!important}
@media(max-width:680px){[data-testid="stSidebar"] [data-testid="stPageLink"]{min-height:41px}}
"""

# AURA 3.4 navigation: keep user-selected saturated brand colors; no dark theme.
CSS += """
[data-testid="stSidebar"] .aura-nav-kicker{
  font-size:10px;font-weight:900;letter-spacing:.13em;color:#5E289F;
  padding:2px 4px 7px;margin:0;text-transform:uppercase}
[data-testid="stSidebar"] [data-testid="stPageLink"]{
  min-height:57px!important;padding:6px 7px!important;
  background:linear-gradient(108deg,#6930EC 0%,#9E35E9 75%,#C128D8 100%)!important;
  border:2px solid #26103E!important;border-radius:16px!important;
  box-shadow:4px 4px 0 #26103E!important;
}
[data-testid="stSidebar"] [data-testid="stPageLink"]:hover{
  background:linear-gradient(105deg,#802DFF,#D02BC8)!important;
  transform:translate(-1px,-1px)!important;box-shadow:5px 5px 0 #26103E!important}
[data-testid="stSidebar"] [data-testid="stPageLink"]:has(a[aria-current="page"]),
[data-testid="stSidebar"] [data-testid="stPageLinkCurrent"]{
  background:linear-gradient(109deg,#E72AA8 0%,#8C35FF 57%,#10B8DC 100%)!important;
  outline:2px solid rgba(255,212,59,.65)!important;outline-offset:1px!important}
[data-testid="stSidebar"] [data-testid="stPageLink"] p,
[data-testid="stSidebar"] [data-testid="stPageLink"] span,
[data-testid="stSidebar"] [data-testid="stPageLink"] a{
  font-size:12.5px!important;letter-spacing:.025em!important;
  font-weight:900!important;color:#fff!important;text-transform:uppercase!important}
@media(max-width:700px){[data-testid="stSidebar"] [data-testid="stPageLink"]{min-height:49px!important}}
"""
