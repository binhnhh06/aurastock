"""BatDayStox SSI 2.0 — all-market terminal (second of TWO Streamlit pages).

Price analysis and ranking use verified local SSI EOD CSV files only. No bulk
API calls during page reruns. Realtime tick is an independent, labeled display.
The 2025 financial preview is not silently converted into investable scores.
"""
from __future__ import annotations

import math
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ssi_universe import load_catalogue
from core.smart_screener import scan_cached_universe, WEIGHTS
from core.watchlist import load_watchlist, save_watchlist
from core.aura_brand import favicon
# AURA_V8_3_2_SSI_LISTED_SHARES
from core.aura_ssi_listed_v832 import enrich_listed_equity, OUT_VALUE, OUT_SOURCE
from core.aura_market_info import (
    load_market_cap_reference, add_market_cap, volume_value_average
)
from core.aura_financial_review import (
    prepare_annual, coverage_by_year, five_years_with_ratios, provisional_rows,
    rating_display, preview_display, trend_for_symbol,
)
from core.theme import ap_dung_theme, dieu_huong_trang

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
EOD_DIR = ROOT / "data" / "ssi_cache" / "ohlcv"
FIN_PATH = ROOT / "data" / "fundamentals" / "processed" / "financial_features_annual.csv"
LEDGER_PATH = ROOT / "data" / "ssi_cache" / "market_sync_status.csv"

st.set_page_config(page_title="AURA | Trạm lọc thị trường", page_icon=favicon(), layout="wide")
ap_dung_theme()
dieu_huong_trang()
st.markdown("""<style>
/* AURA brand alignment: restrained neon-purple/pink, black depth. */
.block-container{max-width:1500px;padding-top:1.4rem;padding-bottom:3.6rem}
h1,h2,h3{letter-spacing:-.024em}
.batday-hero{padding:28px 31px;border-radius:22px;margin:5px 0 18px;
 color:white;border:1.5px solid #1B0A35;
 background:linear-gradient(111deg,#2D135C 0%,#6727D8 50%,#C83CB8 100%);
 box-shadow:5px 5px 0 #1B0A35,0 17px 28px rgba(52,18,112,.12)}
.batday-hero-title{font-weight:850;font-size:29px;letter-spacing:-.03em;line-height:1.2}
.batday-hero-subtitle{color:#F2E9FF;margin-top:10px;font-size:13px;line-height:1.7}
.batday-hero-mini{font-size:11px;font-weight:800;letter-spacing:.17em;
 color:#E5D7FF;margin-bottom:10px}
.batday-hero-pills{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
.batday-hero-pill{font-weight:700;font-size:11px;display:inline-block;
 background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.25);
 padding:5px 11px;border-radius:30px;color:#fff}
[data-testid="stTabs"] button{font-weight:750;font-size:13.5px}
[data-testid="stDataFrame"]{overflow:hidden}
[data-testid="stMetricValue"]{font-size:1.7rem}
[data-testid="stMetricLabel"]{color:#5C4B78;font-size:.85rem}
[data-testid="stExpander"]{background:#FFFDFF}
@media(max-width:720px){.batday-hero{padding:19px}.batday-hero-title{font-size:22px}}
</style>""", unsafe_allow_html=True)
# AURA 3.1: consistent with the saturated summary cards on the analysis page.
st.markdown("""<style>
.batday-hero{
  background:linear-gradient(112deg,#5B23EF 0%,#862FEF 51%,#C72ADA 100%)!important;
  border:2px solid #1B1233!important;
  box-shadow:5px 6px 0 #1B1233,0 16px 25px rgba(75,25,122,.13)!important;
  border-radius:23px!important}
.batday-hero-title{font-weight:900!important;color:white!important}
.batday-hero-mini{color:#E8DCFF!important}
.batday-hero-pill{background:rgba(255,255,255,.22)!important;
  border:1.4px solid rgba(255,255,255,.5)!important;color:#fff!important}
[data-testid="stTabs"] [data-baseweb="tab-highlight"]{background:#6C3BFF!important}
</style>""",unsafe_allow_html=True)



# AURA: match the saturated accent cards the user chose; no new color palette.
st.markdown("""<style>
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"]{
 color:#6325E8!important;font-weight:850!important}
[data-testid="stDataFrame"]{border:1.5px solid #CDB6FF!important;
 box-shadow:3px 4px 0 rgba(27,18,51,.12)!important}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]{
 font-weight:750!important}
</style>""", unsafe_allow_html=True)

@st.cache_data(ttl=180, show_spinner=False)
def catalogue_cached() -> pd.DataFrame:
    return load_catalogue(ROOT)


@st.cache_data(ttl=120, show_spinner=False)
def local_ohlcv(symbol: str, revision=None) -> pd.DataFrame:
    """Read local EOD only; revision helps invalidate on external sync."""
    path = EOD_DIR / f"{symbol}.csv"
    if not path.is_file():
        return pd.DataFrame()
    cols = ["date", "open", "high", "low", "close", "volume"]
    d = pd.read_csv(path, encoding="utf-8-sig")
    if not set(cols).issubset(d.columns):
        raise ValueError(f"{symbol}: CSV thiếu cột OHLCV")
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for col in cols[1:]:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=cols).sort_values("date").drop_duplicates("date", keep="last")
    d = d.loc[(d[["open", "high", "low", "close"]] > 0).all(axis=1) & d["volume"].ge(0)].copy()
    if not d.empty:
        for n in (20, 50, 200):
            d[f"MA{n}"] = d["close"].rolling(n, min_periods=n).mean()
    return d


@st.cache_data(ttl=300, show_spinner=False)
def _cap_reference_cached(revision=None):
    return load_market_cap_reference(ROOT)


def cap_reference():
    ref = ROOT / 'data' / 'fundamentals' / 'processed' / 'market_cap_reference.csv'
    try:
        fingerprint = ref.stat().st_mtime_ns
    except OSError:
        fingerprint = None
    return _cap_reference_cached(fingerprint)


def get_ohlcv(symbol: str) -> pd.DataFrame:
    path = EOD_DIR / f"{symbol}.csv"
    try:
        revision = path.stat().st_mtime_ns
    except OSError:
        revision = None
    return local_ohlcv(symbol, revision)


@st.cache_data(ttl=120, show_spinner=False)
def financial_annual(revision=None) -> pd.DataFrame:
    if not FIN_PATH.is_file():
        return pd.DataFrame()
    df = pd.read_csv(FIN_PATH, encoding="utf-8-sig")
    if not {"symbol", "year"}.issubset(df.columns):
        return pd.DataFrame()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    return df


def data_revision() -> tuple[int, int, int, int]:
    """Lightweight fingerprint; detects changes even when file count is unchanged."""
    files = list(EOD_DIR.glob("*.csv")) if EOD_DIR.is_dir() else []
    newest = 0
    size_sum = 0
    for path in files:
        try:
            stat = path.stat()
            newest = max(newest, stat.st_mtime_ns)
            size_sum += stat.st_size
        except OSError:
            continue
    catalogue_file = ROOT / "data" / "ssi_cache" / "market_symbols.csv"
    try:
        catalogue_mtime = catalogue_file.stat().st_mtime_ns
    except OSError:
        catalogue_mtime = 0
    return len(files), newest, size_sum, catalogue_mtime


def enrich_with_catalogue(table: pd.DataFrame, catalogue: pd.DataFrame) -> pd.DataFrame:
    """Bring SSI board/sector/name into both qualified and excluded rows."""
    mapping = catalogue.copy()
    for field in ("symbol", "board", "sector", "name"):
        if field not in mapping:
            mapping[field] = ""
    mapping = mapping[["symbol", "board", "sector", "name"]].drop_duplicates("symbol")
    mapping = mapping.rename(columns={"symbol": "Mã", "board": "Sàn", "sector": "Ngành", "name": "Tên doanh nghiệp"})
    result = table.merge(mapping, on="Mã", how="left", validate="many_to_one")
    for field in ("Sàn", "Ngành", "Tên doanh nghiệp"):
        result[field] = result[field].fillna("").astype(str).str.strip()
    result["Ngành"] = result["Ngành"].replace("", "Chưa phân loại")
    return result


def refresh_one(symbol: str) -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass
    required = ("SSI_CLIENT_ID", "SSI_API_KEY", "SSI_API_SECRET")
    if any(not os.getenv(k) for k in required):
        return "Thiếu cấu hình SSI trên máy này; không nhập API key vào giao diện."
    try:
        from ssi_sdk import Auth, Config, Data
        from scripts.ssi_fetch_symbol import download_with_service
        cfg = Config(client_id=os.environ["SSI_CLIENT_ID"], api_key=os.environ["SSI_API_KEY"],
                     api_secret=os.environ["SSI_API_SECRET"])
        with Auth(cfg) as auth:
            auth.authenticate()
            with Data(auth) as data:
                status, count = download_with_service(data, symbol, 900, ROOT)
        local_ohlcv.clear()
        return f"{symbol}: {status} · {count} phiên EOD được lưu. Quét lại nếu muốn cập nhật xếp hạng."
    except Exception as exc:
        return f"Không thể đồng bộ {symbol}: {type(exc).__name__}. Kiểm tra SSI và giới hạn API."


@st.fragment(run_every="5s")
def live_fragment(symbol: str, eod_close=None):
    """Separate quote in Lookup only; no impact on EOD scores or original X10."""
    try:
        from core.ssi_market_live import request_live_symbol, read_snapshot, quote_view, date_label
        request_live_symbol(symbol)
        snapshot = read_snapshot()
        rec = quote_view(snapshot, symbol)
        status, raw = rec.get("status", "NO_TICK"), rec.get("price")
        value = float(raw) if raw is not None else float("nan")
        valid = math.isfinite(value) and value > 0 and (eod_close is None or
                    (eod_close > 0 and 0.5 <= value / eod_close <= 1.5))
        if raw is not None and not valid:
            st.warning("Tick SSI khác quy mô với giá EOD; chưa sử dụng để hiển thị giá.")
        elif valid:
            label = "Giá khớp đang nhận SSI" if status == "LIVE_TICK" else "Giá khớp cuối SSI"
            if status in ("LIVE_TICK", "LAST_TICK"):
                st.metric(label, f"{float(raw):,.0f} VND")
        st.caption(f"WebSocket: {snapshot.get('connection','NO_WORKER')} · "
                   f"Tick: {status} · Nhận lúc: {date_label(rec.get('received_at'))}")
        if status != "LIVE_TICK":
            st.caption("Chưa xác nhận giá realtime trong phiên; điểm và biểu đồ dùng nến EOD.")
    except (ImportError, OSError, ValueError, TypeError, KeyError, AttributeError):
        st.caption("Chưa có SSI Worker hoặc chưa nhận được tick xác thực. Giá EOD vẫn dùng được.")


def show_eod_freshness(last_date):
    # Business days are only an approximation; holidays/suspensions are not inferred.
    now = datetime.now(TZ)
    cutoff = now.date() if (now.hour, now.minute) >= (15, 30) else (now.date() - pd.Timedelta(days=1))
    age = len(pd.bdate_range(pd.Timestamp(last_date).date() + pd.Timedelta(days=1), cutoff))
    if age >= 2:
        st.warning(f"Nến cuối {pd.Timestamp(last_date):%d/%m/%Y}: khoảng {age} ngày làm việc chưa có nến mới. "
                   "Có thể mã ít giao dịch/ngừng giao dịch hoặc cache chưa cập nhật.")


def show_single(symbol: str):
    d = get_ohlcv(symbol)
    if d.empty:
        st.info(f"{symbol} chưa có lịch sử giá SSI trên máy. Có thể đồng bộ riêng khi cần.")
        live_fragment(symbol, None)
        return
    last = d.iloc[-1]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Giá đóng cửa EOD", f"{last['close']:,.0f} đ")
    k2.metric("Ngày nến cuối", last["date"].strftime("%d/%m/%Y"))
    k3.metric("MA50", f"{last['MA50']:,.0f} đ" if pd.notna(last["MA50"]) else "N/A")
    k4.metric("Số phiên lưu", f"{len(d):,}")
    show_eod_freshness(last["date"])
    st.markdown("#### Thông tin thị trường & thanh khoản")
    basic_cat = catalogue_cached()
    found = basic_cat.loc[basic_cat["symbol"].eq(symbol)]
    info = found.iloc[0] if not found.empty else {}
    c_board, c_sector, c_cap, c_liq = st.columns([1, 1.6, 1.4, 1.5])
    c_board.metric("Sàn giao dịch", str(info.get("board", "—") or "—"))
    c_sector.metric("Ngành", str(info.get("sector", "—") or "—"))
    template = pd.DataFrame([{"Mã":symbol, "Giá (VND)":float(last['close']),
                              "Ngày dữ liệu":last['date'].strftime('%Y-%m-%d')}])
    capital = enrich_listed_equity(add_market_cap(template, cap_reference()), ROOT)
    cap_val = capital.iloc[0]['Vốn hóa (tỷ VND)']
    c_cap.metric("Vốn hóa (tỷ đồng)", f"{cap_val:,.0f}" if pd.notna(cap_val) else "Chưa có nguồn")
    # SSI listed_shares is NOT shares_outstanding or official market capitalization.
    listed_value = capital.iloc[0][OUT_VALUE]
    if pd.notna(listed_value):
        st.caption(f"{symbol}: Giá trị CP niêm yết ước tính = {listed_value:,.2f} tỷ VND "
                   f"(giá SSI EOD × CP niêm yết; {capital.iloc[0][OUT_SOURCE]}). "
                   "Không phải vốn hóa chính thức.")
    else:
        st.caption("Giá trị CP niêm yết: chưa có tham chiếu SSI phù hợp ngày EOD.")
    qty_avg, val_avg = volume_value_average(d)
    c_liq.metric("GTGD TB20 ước tính", f"{val_avg:,.2f} tỷ đ" if val_avg is not None else "Chưa đủ 20 phiên")
    st.caption("Giá và thanh khoản: SSI EOD. GTGD TB20 = bình quân (giá đóng cửa × khối lượng), "
               "chỉ là ước tính, không phải GTGD khớp lệnh thực tế. "
               f"Nhóm vốn hóa: {capital.iloc[0]['Nhóm vốn hóa']} · "
               "Chỉ có khi lưu số CP lưu hành có nguồn hoặc vốn hóa đúng ngày tại market_cap_reference.csv.")
    live_fragment(symbol, float(last["close"]))
    chart, info = st.columns([3, 1])
    with chart:
        st.line_chart(d.set_index("date")[["close", "MA20", "MA50", "MA200"]].tail(260), height=340)
    with info:
        if len(d) >= 64:
            ret = d["close"].iloc[-1] / d["close"].iloc[-64] - 1
            st.metric("Lợi suất 63 phiên", f"{100 * ret:+.2f}%")
        st.metric("Khối lượng phiên cuối", f"{last['volume']:,.0f}")
        if len(d) < 200:
            st.warning("Dưới 200 phiên: không đủ để tính MA200 / xếp hạng dài hạn.")
        st.download_button("Xuất OHLCV CSV", d.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{symbol}_SSI_OHLCV.csv", mime="text/csv")


def numeric_view(table: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    x = table[[col for col in cols if col in table.columns]].copy()
    for col in x.select_dtypes(include="number"):
        if col != "Thứ hạng" and col != "Số phiên":
            x[col] = x[col].round(2)
    return x


def display_table(df: pd.DataFrame, height: int = 410):
    """Keep values numeric for sorting while using readable, consistent display."""
    # AURA_YEAR_DISPLAY_FIX: display 2025 instead of 2,025.00; exported data unchanged.
    df = df.copy()
    for year_column in ("Năm", "year"):
        if year_column in df:
            values = pd.to_numeric(df[year_column], errors="coerce")
            df[year_column] = values.map(lambda x: str(int(x)) if pd.notna(x) and float(x).is_integer() else "—")
    config = {}
    for col in df.select_dtypes(include="number").columns:
        if col == "Giá (VND)":
            config[col] = st.column_config.NumberColumn(col, format="%,.0f đ")
        elif col in ("Thứ hạng", "Số phiên", "Số mã", "KL TB20 (CP/phiên)"):
            config[col] = st.column_config.NumberColumn(col, format="%,d")
        elif "(%)" in col or "RSI" in col:
            config[col] = st.column_config.NumberColumn(col, format="%.2f")
        else:
            config[col] = st.column_config.NumberColumn(col, format="%,.2f")
    st.dataframe(df, hide_index=True, use_container_width=True, height=height,
                 column_config=config)


def explain_one_score(data: pd.DataFrame):
    if data.empty:
        return
    with st.expander("Giải thích điểm kỹ thuật"):
        selected = st.selectbox("Mã cần giải thích", data["Mã"].tolist(), key="explain_stock")
        row = data.loc[data["Mã"].eq(selected)].iloc[0]
        st.caption(f"{selected} · {row.get('Ngành', '')} · Ngày EOD {row.get('Ngày dữ liệu','')} · "
                   f"Thứ hạng {int(row['Thứ hạng'])} trong mẫu đủ điều kiện")
        st.metric("Điểm kỹ thuật", f"{row['Smart Rating /10']:.2f}/10")
        mapping = {
            "trend": "Xu hướng MA", "momentum": "Động lượng 20/63 phiên",
            "liquidity": "Thanh khoản/khối lượng", "rsi_macd": "RSI/MACD",
            "risk": "Biến động và sụt giảm", "breakout": "Vượt đỉnh 20 phiên",
        }
        factors = pd.DataFrame([
            {"Nhân tố": mapping[key], "Trọng số (%)": weight * 100,
             "Điểm thành phần /10": row.get(f"Nhân tố: {key}", float("nan"))}
            for key, weight in WEIGHTS.items()
        ])
        display_table(factors, 255)
        st.caption("Điểm tương đối theo mẫu đủ điều kiện tại cùng ngày, không phải tỷ lệ thắng/khuyến nghị mua. "
                   "Đây là điểm kỹ thuật riêng của Trạm lọc, khác với điểm đánh giá tổng hợp ở trang Phân tích cổ phiếu.")


st.markdown("""<div class="batday-hero">
 <div class="batday-hero-mini">AURA · MARKET INTELLIGENCE</div>
 <div class="batday-hero-title">Trạm lọc & xếp hạng thị trường</div>
 <div class="batday-hero-subtitle">Khám phá cổ phiếu HOSE · HNX · UPCoM bằng dữ liệu lịch sử SSI.<br>
 Xếp hạng định lượng minh bạch, theo dõi danh mục và phân tích rủi ro tại một nơi.</div>
 <div class="batday-hero-pills"><span class="batday-hero-pill">DỮ LIỆU SSI EOD</span>
 <span class="batday-hero-pill">ĐIỂM KỸ THUẬT /10</span>
 <span class="batday-hero-pill">WATCHLIST & SO SÁNH</span></div>
</div>""", unsafe_allow_html=True)

cat = catalogue_cached()
if cat.empty:
    st.warning("Chưa có danh mục SSI. Chạy `python scripts/ssi_sync_universe.py` trước.")
    st.stop()
for col in ("symbol", "asset_class", "board", "sector", "name"):
    if col not in cat:
        cat[col] = ""
cat["symbol"] = cat["symbol"].astype(str).str.upper().str.strip()
cat["board"] = cat["board"].astype(str).str.upper().str.strip()
known = cat["symbol"].drop_duplicates().sort_values().tolist()
if len(known) < 100:
    st.warning("Danh mục SSI hiện chỉ có dưới 100 mã. "
               "Nếu trước đây có hơn 1.000 mã, kiểm tra "
               "data/ssi_cache/market_symbols.csv trước khi đồng bộ. "
               "Không xóa cache giá EOD đang lưu.")
eq = cat.loc[cat["asset_class"].eq("EQUITY"), "symbol"].drop_duplicates().tolist()
price_files = {p.stem.upper() for p in EOD_DIR.glob("*.csv")} if EOD_DIR.is_dir() else set()
valid_cached = set(eq) & price_files
revision_now = data_revision()
x1, x2, x3, x4 = st.columns(4)
x1.metric("Tổng mã danh mục SSI", f"{len(known):,}")
x2.metric("Cổ phiếu phân loại EQUITY", f"{len(eq):,}")
x3.metric("Đã có dữ liệu giá", f"{len(valid_cached):,}", help="Có file không đồng nghĩa đủ 200 phiên hoặc mới nhất")
x4.metric("Độ phủ file giá", f"{len(valid_cached) / max(len(eq), 1) * 100:.1f}%")
st.caption("Vốn hóa doanh nghiệp: chỉ sử dụng bảng tham chiếu có nguồn, ngày và đơn vị rõ ràng. "
           "Không suy từ EPS, vốn điều lệ hoặc số CP niêm yết thiếu xác minh.")
st.caption("Nguồn: SSI FastConnect V3 · HOSE/HNX/UPCoM · "
           f"Giờ Việt Nam {datetime.now(TZ):%d/%m/%Y %H:%M}. "
           "Xếp hạng chỉ tính trên mã đủ lịch sử và có nến đúng phiên chốt.")

tab_lookup, tab_screen, tab_watch, tab_rating, tab_data = st.tabs([
    "Tra cứu cổ phiếu", "Bộ lọc & xếp hạng", "Watchlist & so sánh",
    "Smart Rating & BCTC", "Dữ liệu & phương pháp"
])

with tab_lookup:
    l1, l2, l3 = st.columns([1, 1, 2])
    board = l1.selectbox("Sàn giao dịch", ["Tất cả", "HOSE", "HNX", "UPCOM"], key="lookup_board")
    asset = l2.selectbox("Phạm vi mã", ["Cổ phiếu", "Tất cả chứng khoán"], key="lookup_asset")
    subset = cat if board == "Tất cả" else cat.loc[cat["board"].eq(board)]
    if asset == "Cổ phiếu":
        subset = subset.loc[subset["asset_class"].isin(["EQUITY", "EQUITY_CANDIDATE"])]
    names = subset.sort_values("symbol").drop_duplicates("symbol").set_index("symbol")
    options = names.index.tolist()
    if not options:
        st.info("Không có mã trong phạm vi đã chọn.")
    else:
        default = "FPT" if "FPT" in options else options[0]
        symbol = l3.selectbox("Tra cứu mã SSI", options, index=options.index(default),
                              format_func=lambda s: f"{s} · {names.loc[s, 'name']}", key="lookup_symbol")
        detail = names.loc[symbol]
        st.caption(f"{symbol} · {detail.get('board', '')} · "
                   f"{detail.get('sector') or 'Chưa phân loại ngành'} · {detail.get('asset_class', '')}")
        if detail.get("asset_class") == "EQUITY_CANDIDATE":
            st.warning("Ứng viên cổ phiếu chưa xác nhận: không đưa vào xếp hạng toàn thị trường mặc định.")
        c_fetch, c_star, _ = st.columns([1.35, 1.1, 2.5])
        st.caption("Cập nhật một mã không làm thay đổi danh mục SSI toàn thị trường. "
                   "Muốn đồng bộ nhiều mã, dùng Market Sync theo lô trong Terminal.")
        if c_fetch.button(f"Cập nhật SSI: {symbol} (1 mã)", key="lookup_refresh"):
            with st.spinner("Đang tải giá mã được chọn từ SSI..."):
                st.info(refresh_one(symbol))
        if c_star.button("⭐ Thêm vào theo dõi", key="lookup_watch_add"):
            try:
                saved = save_watchlist(load_watchlist(ROOT) + [symbol], ROOT)
                st.success(f"Đã lưu {symbol} ({len(saved)} mã) trong danh sách theo dõi trên máy.")
            except OSError:
                st.error("Không thể lưu Watchlist; kiểm tra quyền ghi thư mục data/user.")
        try:
            show_single(symbol)
        except (OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
            st.error(f"Không đọc được OHLCV: {type(exc).__name__}. Vui lòng kiểm tra file CSV.")

with tab_screen:
    st.subheader("Sàng lọc cổ phiếu toàn thị trường")
    st.caption("Quét 1.518 mã trong cache SSI; không tự gọi API. Mỗi phiên chốt chỉ "
               "xếp hạng những mã đủ ≥200 nến và có giá ở cùng ngày EOD.")
    scan_col, message_col = st.columns([1, 3])
    if scan_col.button("Quét / làm mới xếp hạng", type="primary", key="run_scan"):
        with st.spinner("Đang đọc giá EOD, tính MA/RSI/MACD và xếp hạng toàn thị trường..."):
            try:
                scan_raw, meta = scan_cached_universe(ROOT)
                scan_enriched = enrich_with_catalogue(scan_raw, cat)
                scan_enriched = add_market_cap(scan_enriched, cap_reference(), as_of=meta.as_of)
                scan_enriched = enrich_listed_equity(scan_enriched, ROOT)
                st.session_state["batday_scan_result"] = (scan_enriched, meta)
                st.session_state["batday_scan_time"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
                st.session_state["batday_scan_revision"] = data_revision()
            except (OSError, ValueError, KeyError, FileNotFoundError, pd.errors.ParserError) as exc:
                st.error(f"Không chạy được bộ lọc: {type(exc).__name__}: {exc}")
    with message_col:
        st.info("Không cần tải lại 1.518 mã khi mở trang. Sau khi Market Sync cập nhật EOD, "
                "bấm **Quét / làm mới** một lần để tính lại điểm.")

    if "batday_scan_result" not in st.session_state:
        st.info("Bấm **Quét / làm mới xếp hạng** để xem các mã có dữ liệu đủ điều kiện.")
    else:
        data, meta = st.session_state["batday_scan_result"]
        if st.session_state.get("batday_scan_revision") != revision_now:
            st.warning("File giá hoặc danh mục SSI đã thay đổi kể từ lần quét trước. "
                       "Bấm **Quét / làm mới xếp hạng** để tránh xem kết quả cũ.")
        st.caption(f"**Phiên chốt EOD:** {meta.as_of} · Quét lúc {st.session_state.get('batday_scan_time', 'N/A')} "
                   "· Không phải giá realtime")
        a, b, c, d = st.columns(4)
        a.metric("Danh mục phân tích", f"{meta.universe_size:,}")
        b.metric("Đủ điều kiện xếp hạng", f"{meta.eligible:,}")
        c.metric("Chưa thể xếp hạng", f"{meta.unavailable:,}")
        d.metric("Tỷ lệ đủ dữ liệu", f"{meta.eligible / max(meta.universe_size, 1) * 100:.1f}%")

        eligible = data.loc[data["Trạng thái"].eq("Đủ dữ liệu")].copy()
        presets = {
            "Toàn bộ mã đủ dữ liệu": (1., 500., 0., 100.),
            "Thận trọng · thử nghiệm": (6., 25., 5., 15.),
            "Cân bằng · thử nghiệm": (5., 40., 2., 30.),
            "Động lượng tích cực": (6., 500., 0., 100.),
            "Vượt đỉnh 20 phiên": (5., 500., 0., 100.),
        }
        preset = st.selectbox("Mẫu lọc nghiên cứu", list(presets), key="filter_preset")
        default_point, default_vol, default_liq, default_drawdown = presets[preset]
        f1, f2, f3, f4 = st.columns(4)
        min_point = f1.slider("Điểm kỹ thuật từ", 1., 10., default_point, .5,
                              key=f"point_{preset}")
        max_vol = f2.number_input("Biến động năm hóa tối đa (%)", 0., 500., default_vol,
                                  key=f"vol_{preset}")
        min_liq = f3.number_input("GTGD bình quân ≥ (tỷ/ngày)", 0., 100000., default_liq,
                                  key=f"liq_{preset}")
        max_dd = f4.number_input("Sụt giảm 60 phiên ≤ (%)", 0., 100., default_drawdown,
                                 key=f"dd_{preset}")

        st.caption("**Thông tin định danh & thị trường:** sàn, ngành, nhóm vốn hóa "
                   "(nếu có nguồn), khối lượng và giá trị giao dịch bình quân 20 phiên.")
        f5, f6, f7 = st.columns([1, 1.5, 1.5])
        boards = f5.multiselect("Sàn giao dịch", ["HOSE", "HNX", "UPCOM"],
                                placeholder="Chọn sàn...", key="screen_boards")
        sectors_all = sorted(eligible["Ngành"].dropna().unique().tolist()) if not eligible.empty else []
        sectors = f6.multiselect("Ngành kinh doanh", sectors_all,
                                 placeholder="Chọn ngành...", key="screen_sectors")
        query = f7.text_input("Tìm mã / tên doanh nghiệp", placeholder="VD: FPT, ngân hàng...", key="screen_search").strip()

        cap_c1, cap_c2, cap_c3 = st.columns([1.6, 1.3, 1.1])
        band_filter = cap_c1.multiselect("Nhóm vốn hóa AURA",
                           ["Large-cap · AURA", "Mid-cap · AURA", "Small-cap · AURA"],
                           placeholder="Tất cả quy mô", key="aura_cap_band")
        min_cap = cap_c2.number_input("Vốn hóa tối thiểu (tỷ đồng)",
                                      min_value=0.0, max_value=10000000.0,
                                      value=0.0, step=1000.0, key="aura_cap_floor")
        min_volume = cap_c3.number_input("KL TB20 (triệu CP/phiên) ≥",
                                         min_value=0.0, max_value=10000.0,
                                         value=0.0, step=0.1, key="aura_volume_floor")
        with st.expander("Bộ lọc nâng cao (RSI, MA, lợi suất, thanh khoản)"):
            t1, t2, t3, t4 = st.columns(4)
            rsi_min = t1.slider("RSI thấp nhất", 0, 100, 0, key="rsi_min")
            rsi_max = t2.slider("RSI cao nhất", 0, 100, 100, key="rsi_max")
            min_ret63 = t3.number_input("Lợi suất 63 phiên ≥ (%)", -100., 1000., -100., key="ret63")
            spike = t4.number_input("Khối lượng phiên cuối ≥ (lần TB20)", 0., 100., 0., .1, key="volume_spike")
            ma_filter = st.selectbox("Giá so với đường MA",
                ["Không yêu cầu", "Giá > MA20", "Giá > MA50", "Giá > MA200", "Giá > MA20 & MA50 & MA200"],
                key="ma_filter")
            m1, m2 = st.columns(2)
            require_breakout = m1.checkbox("Chỉ mã vượt đỉnh 20 phiên", key="require_breakout")
            exclude_unusual = m2.checkbox("Loại mã có biến động giá >30% trong 200 phiên",
                                          value=True, key="exclude_unusual")
            st.caption("Cờ >30% chỉ là tín hiệu cần xem lại điều chỉnh giá hoặc thanh khoản, "
                       "không khẳng định dữ liệu sai.")

        good = eligible.loc[
            (eligible["Smart Rating /10"] >= min_point) &
            (eligible["Biến động 60 phiên (%)"] <= max_vol) &
            (eligible["GTGD 20 phiên (tỷ VND)"] >= min_liq) &
            (eligible["Sụt giảm từ đỉnh 60 phiên (%)"] <= max_dd)
        ].copy()
        if band_filter:
            good = good.loc[good["Nhóm vốn hóa"].isin(band_filter)]
        if min_cap > 0:
            good = good.loc[good["Vốn hóa (tỷ VND)"].ge(min_cap)]
        if min_volume > 0:
            good = good.loc[good["KL TB20 (CP/phiên)"].ge(min_volume * 1_000_000)]
        if preset == "Động lượng tích cực":
            good = good.loc[(good["Lợi suất 20 phiên (%)"] > 0) & (good["Lợi suất 63 phiên (%)"] > 0)]
        if preset == "Vượt đỉnh 20 phiên" or require_breakout:
            good = good.loc[good["Breakout 20 phiên"].fillna(False).astype(bool)]
        if boards:
            good = good.loc[good["Sàn"].isin(boards)]
        if sectors:
            good = good.loc[good["Ngành"].isin(sectors)]
        if query:
            mask = good["Mã"].str.contains(query, case=False, regex=False, na=False) | \
                   good["Tên doanh nghiệp"].str.contains(query, case=False, regex=False, na=False)
            good = good.loc[mask]
        if rsi_min > rsi_max:
            st.warning("RSI thấp nhất đang lớn hơn RSI cao nhất. Hãy điều chỉnh lại hai ngưỡng.")
            good = good.iloc[0:0]
        else:
            good = good.loc[good["RSI14 EWM"].between(rsi_min, rsi_max, inclusive="both")]
        good = good.loc[(good["Lợi suất 63 phiên (%)"] >= min_ret63) &
                        (good["Khối lượng đột biến (x)"] >= spike)]
        if ma_filter != "Không yêu cầu":
            choices = {
                "Giá > MA20": ["MA20"], "Giá > MA50": ["MA50"],
                "Giá > MA200": ["MA200"], "Giá > MA20 & MA50 & MA200": ["MA20", "MA50", "MA200"]
            }
            for column in choices[ma_filter]:
                good = good.loc[good["Giá (VND)"] > good[column]]
        if exclude_unusual:
            good = good.loc[~good["Cờ biến động >30%"].fillna(False).astype(bool)]
        good = good.sort_values(["Smart Rating /10", "Mã"], ascending=[False, True])

        # aura_market_cap_coverage: never invent or impute market cap values.
        if "Vốn hóa (tỷ VND)" in good:
            available_cap = int(pd.to_numeric(good["Vốn hóa (tỷ VND)"], errors="coerce").notna().sum())
            st.caption(f"Vốn hóa có nguồn hợp lệ: {available_cap:,}/{len(good):,} mã trong bộ lọc. "
                       "Các mã còn lại được để thiếu, không ước lượng từ giá hoặc EPS.")
        n1, n2, n3 = st.columns(3)
        n1.metric("Mã vượt bộ lọc", f"{len(good):,}")
        n2.metric("Trong số mã đủ dữ liệu", f"{100 * len(good) / max(meta.eligible, 1):.1f}%")
        n3.metric("Trong toàn danh mục", f"{100 * len(good) / max(meta.universe_size, 1):.1f}%")
        st.caption("Tỷ lệ có mẫu số khác nhau. Thứ hạng được tính trên toàn bộ mã đủ EOD cùng ngày, "
                   "KHÔNG tính lại sau khi bạn lọc ngành hoặc sàn.")
        cols = ["Thứ hạng", "Mã", "Tên doanh nghiệp", "Sàn", "Ngành", "Nhóm vốn hóa",
                OUT_VALUE, "Smart Rating /10", "Giá (VND)",
                "KL TB20 (CP/phiên)", "GTGD 20 phiên (tỷ VND)",
                "Lợi suất 63 phiên (%)", "RSI14 EWM", "Biến động 60 phiên (%)",
                "Breakout 20 phiên", "Ngày dữ liệu"]
        shown = numeric_view(good, cols).rename(columns={"Smart Rating /10": "Điểm kỹ thuật /10"})
        st.caption("SSI: Giá trị CP niêm yết (tỷ VND) = Giá SSI EOD × CP niêm yết "
                   "từ snapshot tham chiếu gần ngày EOD. Đây là ƯỚC TÍNH, không phải "
                   "vốn hóa doanh nghiệp; không tham gia lọc vốn hóa, Smart Rating hay backtest.")
        # AURA_V8_3_MARKET_CAP_DISPLAY: show missing data explicitly, never as numeric zero.
        if "Vốn hóa (tỷ VND)" in shown.columns:
            shown["Vốn hóa (tỷ VND)"] = shown["Vốn hóa (tỷ VND)"].map(
                lambda x: "Chưa có nguồn" if pd.isna(x) else f"{float(x):,.2f}"
            )
        display_table(shown, 470)
        # AURA_FLOW_V6: direct screener -> analysis handoff, with an explicit ticker.
        if not good.empty:
            st.markdown("**Phân tích chuyên sâu mã đang lọc**")
            _flow_opts = good["Mã"].astype(str).dropna().drop_duplicates().tolist()
            _flow_selected = st.selectbox("Chọn mã để phân tích", _flow_opts,
                                          key="aura_flow_screen_symbol")
            if st.button("🔎 Mở Phân tích cổ phiếu", key="aura_flow_open_analysis"):
                st.session_state["aura_flow_pending_analysis"] = _flow_selected
                st.switch_page("app.py")
        st.caption("Nhóm Large/Mid/Small-cap là ngưỡng tham khảo do AURA thiết lập "
                   "(≥10.000 / ≥1.000 / dưới 1.000 tỷ VND), không phải phân loại chính thức của sàn. "
                   "Vốn hóa chỉ hiện khi có nguồn và ngày tham chiếu phù hợp; "
                   "GTGD 20 phiên là ước tính từ giá đóng cửa × khối lượng SSI.")
        if good.empty:
            st.info("Chưa có mã phù hợp; thử bỏ một điều kiện hoặc chọn mẫu Toàn bộ.")
        else:
            left, right = st.columns([2.4, 1.4])
            with left:
                st.markdown("**Top 15 · điểm kỹ thuật /10**")
                score_chart = (good.head(15).sort_values("Smart Rating /10")
                               .set_index("Mã")["Smart Rating /10"])
                st.bar_chart(score_chart, horizontal=True, height=350)
            with right:
                st.markdown("**Thêm mã đang lọc vào Watchlist**")
                favorite = st.selectbox("Chọn mã", good["Mã"].tolist(), key="screen_favorite")
                if st.button("⭐ Lưu mã vào Watchlist", key="screen_favorite_save"):
                    try:
                        saved = save_watchlist(load_watchlist(ROOT) + [favorite], ROOT)
                        st.success(f"Đã lưu {favorite}. Watchlist có {len(saved)} mã.")
                    except OSError:
                        st.error("Không ghi được Watchlist. Kiểm tra quyền thư mục data/user.")
                st.caption("Danh sách được lưu trên máy này và dùng chung cho bản cài đặt cục bộ.")
            explain_one_score(good)
        st.download_button("⬇ Xuất danh sách đã lọc (CSV)",
            good.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"AURA_Screener_{meta.as_of}.csv", mime="text/csv")

        excluded = data.loc[data["Trạng thái"].ne("Đủ dữ liệu")].copy()
        with st.expander(f"Vì sao {len(excluded):,} mã chưa được xếp hạng?"):
            st.caption("Mã không đủ dữ liệu KHÔNG được gán điểm 0. "
                       "Mã không có nến đúng ngày chốt có thể ít giao dịch hoặc dừng giao dịch.")
            # AURA_FIX_KEYERROR_NHOM_DU_LIEU_V2
            # Bổ sung nhóm lý do CHỈ cho bảng mã thiếu dữ liệu, giữ nguyên phân nhóm sẵn có.
            if "Nhóm dữ liệu" not in excluded.columns:
                excluded["Nhóm dữ liệu"] = ""
            _aura_reason = (excluded["Lý do"].astype("string").fillna("").str.lower()
                            if "Lý do" in excluded.columns
                            else pd.Series("", index=excluded.index, dtype="string"))
            def _aura_group_reason(reason):
                reason = str(reason)
                if "chưa có file ohlcv" in reason or "file not found" in reason or "no such file" in reason:
                    return "Chưa có file giá OHLCV"
                if "thiếu 200 phiên" in reason or "không đủ phiên" in reason or "ít hơn 200 phiên" in reason:
                    return "Chưa đủ 200 phiên"
                if "không có nến ngày chốt" in reason or "không có nến" in reason:
                    return "Thiếu nến ngày chốt"
                if any(term in reason for term in (
                    "thiếu cột", "csv chứa sai mã", "dữ liệu trống", "sai kiểu",
                    "ngày bị trùng", "không hợp lệ", "không nhất quán",
                    "duplicate", "parsererror", "could not convert")):
                    return "Dữ liệu giá cần kiểm tra"
                if not reason.strip():
                    return "Chưa rõ nguyên nhân"
                return "Lỗi khác / cần kiểm tra"
            _aura_previous_group = excluded["Nhóm dữ liệu"].astype("string").fillna("").str.strip()
            excluded["Nhóm dữ liệu"] = _aura_previous_group.where(
                _aura_previous_group.ne(""), _aura_reason.map(_aura_group_reason)
            )
            group_counts = (excluded["Nhóm dữ liệu"].value_counts()
                            .rename_axis("Nguyên nhân").reset_index(name="Số mã"))
            display_table(group_counts, 205)
            kind = st.selectbox("Xem nguyên nhân", ["Tất cả"] + group_counts["Nguyên nhân"].tolist(),
                                key="excluded_kind")
            if kind != "Tất cả":
                excluded = excluded.loc[excluded["Nhóm dữ liệu"].eq(kind)]
            text_query = st.text_input("Tìm trong mã chưa đủ dữ liệu", key="excluded_search")
            if text_query:
                excluded = excluded.loc[excluded["Mã"].str.contains(text_query, regex=False, case=False)]
            display_table(numeric_view(excluded, ["Mã", "Sàn", "Ngành", "Số phiên", "Ngày dữ liệu",
                                                  "Nhóm dữ liệu", "Lý do"]), 330)
            st.download_button("Xuất danh sách chưa đủ dữ liệu (CSV)",
                excluded.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"AURA_Excluded_{meta.as_of}.csv", mime="text/csv")

with tab_watch:
    st.subheader("Danh sách theo dõi & so sánh cổ phiếu")
    st.caption("Lưu mã theo dõi tại `data/user/watchlist.json` của máy đang chạy Streamlit. "
               "Không phải tài khoản đồng bộ đám mây; trên server công khai cần cơ chế lưu riêng từng người.")
    watch = load_watchlist(ROOT)
    w1, w2 = st.columns([2, 1])
    allowed = [x for x in sorted(eq) if x not in watch]
    if allowed:
        to_add = w1.selectbox("Thêm mã SSI vào Watchlist", allowed, key="watch_picker")
        if w2.button("+ Thêm mã", key="watch_add_button"):
            try:
                watch = save_watchlist(watch + [to_add], ROOT)
                st.success(f"Đã lưu {to_add}")
            except OSError:
                st.error("Không thể lưu Watchlist vào ổ đĩa.")
    if not watch:
        st.info("Watchlist đang trống. Hãy thêm mã từ danh mục ở trên hoặc tab Bộ lọc.")
    else:
        st.caption(f"Đang theo dõi {len(watch)} mã: " + ", ".join(watch[:25]) + ("…" if len(watch) > 25 else ""))
        remove_col, remove_btn = st.columns([2, 1])
        removing = remove_col.multiselect("Chọn mã cần xóa", watch,
                                            placeholder="Chọn mã...", key="watch_remove")
        if remove_btn.button("Xoá mã đã chọn", disabled=not removing, key="watch_remove_button"):
            try:
                watch = save_watchlist([x for x in watch if x not in removing], ROOT)
                st.success(f"Đã xóa {len(removing)} mã.")
            except OSError:
                st.error("Không thể cập nhật Watchlist.")
        if watch:
            scan = st.session_state.get("batday_scan_result")
            if scan:
                frame, meta = scan
                watched = frame.loc[frame["Mã"].isin(watch)].copy()
                sort_order = {name: i for i, name in enumerate(watch)}
                watched["_order"] = watched["Mã"].map(sort_order)
                watched = watched.sort_values("_order")
                cols = ["Mã", "Tên doanh nghiệp", "Sàn", "Ngành", "Trạng thái", "Nhóm dữ liệu",
                        "Smart Rating /10", "Thứ hạng", "Giá (VND)", "Lợi suất 63 phiên (%)",
                        "GTGD 20 phiên (tỷ VND)", "Ngày dữ liệu", "Lý do"]
                view_watch = numeric_view(watched, cols).rename(columns={"Smart Rating /10": "Điểm kỹ thuật /10"})
                display_table(view_watch, 290)
                st.download_button("⬇ Xuất Watchlist và điểm kỹ thuật", view_watch.to_csv(index=False).encode("utf-8-sig"),
                                   "AURA_Watchlist.csv", mime="text/csv")
            else:
                st.caption("Quét dữ liệu ở tab Bộ lọc để xem điểm và thứ hạng tương ứng từng mã trong Watchlist.")
            st.markdown("**So sánh biến động giá (chuẩn hóa về 100 tại ngày đầu chung)**")
            selected = st.multiselect("Chọn 2–5 mã", watch, default=watch[:min(3, len(watch))],
                                      max_selections=5, placeholder="Chọn cổ phiếu...", key="compare_symbols")
            if len(selected) < 2:
                st.info("Chọn ít nhất 2 mã để so sánh diễn biến giá.")
            else:
                series = []
                invalid = []
                for sym in selected:
                    try:
                        d = get_ohlcv(sym)
                        if d.empty:
                            invalid.append(sym)
                            continue
                        data_s = d.set_index("date")["close"].rename(sym)
                        series.append(data_s)
                    except (ValueError, OSError, pd.errors.ParserError, KeyError):
                        invalid.append(sym)
                if invalid:
                    st.warning("Không đọc được giá của: " + ", ".join(invalid))
                if len(series) < 2:
                    st.info("Chưa đủ 2 mã có dữ liệu giá để vẽ biểu đồ.")
                else:
                    joined = pd.concat(series, axis=1, join="inner").dropna().tail(250)
                    if len(joined) < 2 or joined.iloc[0].le(0).any():
                        st.info("Các mã được chọn chưa có đủ ngày giao dịch chung để so sánh.")
                    else:
                        indexed = joined.div(joined.iloc[0]).mul(100)
                        st.line_chart(indexed, height=360)
                        st.caption(f"{len(joined)} ngày chung · Từ {joined.index[0]:%d/%m/%Y} "
                                   f"đến {joined.index[-1]:%d/%m/%Y}. "
                                   "Mốc 100 để so sánh biến động, không phải giá VND; chưa gồm cổ tức và phí.")

with tab_rating:
    # AURA_SMART_RATING_V7
    # AURA_V8_7_PRACTICAL_RESEARCH_VIEW: use existing technical + provisional BCTC.
    # Verified V7 source file is preserved for later independent audit.
    from core.aura_research_score_v87 import render_research_rating
    render_research_rating(ROOT, st.session_state.get('batday_scan_result'))

    # AURA_V8_3_3_DEDUP_RATING
    st.divider()
    st.markdown("#### BCTC 5 năm · 2021–2025")
    try:
        financial_mtime = FIN_PATH.stat().st_mtime_ns
    except OSError:
        financial_mtime = None
    financial = financial_annual(financial_mtime)
    catalogue = catalogue_cached()
    universe = (catalogue.loc[catalogue["asset_class"].eq("EQUITY"), "symbol"].astype(str).tolist()
                if "asset_class" in catalogue and "symbol" in catalogue else [])
    all_equities = len(set(universe))

    # The journal records extension ATTEMPTS; it does not certify all five years.
    history_log = ROOT / "data" / "fundamentals" / "financial_5y_status.csv"
    if history_log.is_file():
        try:
            log = pd.read_csv(history_log, encoding="utf-8-sig", dtype=str)
            if {"symbol", "status"}.issubset(log.columns):
                st.caption(f"Nhật ký mở rộng 2021–2022: đã ghi nhận {log['symbol'].nunique():,} mã / "
                           f"{all_equities:,} mã trong danh mục. "
                           "`EXTENDED` nghĩa là đã bổ sung file nguồn; chưa chứng nhận đủ chỉ tiêu cả 5 năm.")
        except (OSError, ValueError, pd.errors.ParserError):
            st.caption("Chưa đọc được nhật ký BCTC 5 năm; dữ liệu đã tải không bị thay đổi.")

    if financial.empty:
        st.warning("Chưa có bảng chỉ tiêu BCTC đã xử lý. Khi đồng bộ hoàn tất, hãy tính lại "
                   "bảng tỷ số tài chính bằng lệnh bên dưới.")
        st.code(r".\.venv\Scripts\python.exe .\build_financial_features.py", language="powershell")
    else:
        annual = prepare_annual(financial)
        coverage_year = coverage_by_year(annual, universe)
        year_options = sorted(set(annual["year"].dropna().astype(int)) & set(range(2021, 2026)))
        selected_year = st.selectbox("Năm BCTC", year_options, index=len(year_options)-1,
                                     key="aura_financial_year") if year_options else 2025
        current = provisional_rows(annual, selected_year)
        if universe:
            current = current.loc[current["symbol"].isin(set(universe))]
        verified_count = int(annual.loc[annual["year"].eq(selected_year) &
                                        annual["score_eligible"].astype(str).str.upper().eq("YES"),
                                        "symbol"].nunique()) if "score_eligible" in annual else 0
        five_years = five_years_with_ratios(annual, universe)
        # aura_extreme_eps_notice: data-quality warning only; don't alter raw figures.
        if "eps_growth_pct_provisional" in current:
            eps_series = pd.to_numeric(current["eps_growth_pct_provisional"], errors="coerce")
            outliers = int(eps_series.abs().gt(1000).sum())
            if outliers:
                st.caption(f"Kiểm tra dữ liệu: {outliers:,} mã có tăng trưởng EPS tuyệt đối vượt 1.000%. "
                           "Có thể do mẫu số EPS kỳ trước rất nhỏ; chưa tự động kết luận sai.")

        y1, y2, y3, y4 = st.columns(4)
        y1.metric(f"Có tỷ số sơ bộ {selected_year}", f"{current['symbol'].nunique():,}/{all_equities:,}")
        y2.metric("Có chỉ tiêu ở cả 5 năm", f"{five_years:,}",
                  help="Có ít nhất một tỷ số sơ bộ mỗi năm; KHÔNG đồng nghĩa đủ ba báo cáo được xác minh")
        y3.metric(f"Đủ kiểm chứng {selected_year}", f"{verified_count:,}")
        y4.metric("Phạm vi", "2021–2025", help="Chưa bao gồm BCTC bán niên 2026")
        st.caption("Chỉ đếm mã có tỷ số đọc được, KHÔNG đếm các dòng placeholder, "
                   "không coi thiếu dữ liệu là 0 điểm. BCTC bán niên 2026 chưa tích hợp.")

        with st.expander("Xem độ phủ chỉ tiêu theo từng năm", expanded=False):
            display_table(coverage_year, 240)
            st.caption("Các tỷ lệ trên không phải tỷ lệ doanh nghiệp có đủ 3 báo cáo gốc hoặc "
                       "đã xác minh ngày công bố.")

        filter_col1, filter_col2 = st.columns([1, 2])
        choices = sorted(current["company_type"].dropna().astype(str).unique().tolist()) if "company_type" in current else []
        groups = filter_col1.multiselect("Nhóm doanh nghiệp", choices,
                                         placeholder="Tất cả nhóm", key="aura_financial_group")
        symbols = sorted(current["symbol"].drop_duplicates().tolist())
        codes = filter_col2.multiselect("Mã cổ phiếu muốn xem", symbols,
                                       placeholder="Gõ mã để tìm (để trống = tất cả)", key="aura_financial_codes")
        filtered = provisional_rows(annual, selected_year, symbols=codes, groups=groups)
        if universe:
            filtered = filtered.loc[filtered["symbol"].isin(set(universe))]
        if filtered.empty:
            st.info("Không có chỉ tiêu phù hợp bộ lọc. Chọn năm khác, nhóm khác hoặc bỏ chọn mã.")
        else:
            st.markdown(f"**Bảng tỷ số tài chính sơ bộ · {selected_year} · {len(filtered):,} mã**")
            display_table(preview_display(filtered), 390)
            # Keep export numeric so the figures are useful in Excel, while the UI stays readable.
            export_cols = [c for c in ("symbol", "year", "company_type", "roe_pct_provisional",
                             "roa_pct_provisional", "eps_growth_pct_provisional",
                             "net_margin_pct_provisional", "gross_margin_pct_provisional",
                             "liabilities_to_equity_provisional", "balance_identity_pass", "score_eligible",
                             "status", "issues") if c in filtered]
            st.download_button("Xuất bảng BCTC sơ bộ (CSV)",
                               filtered[export_cols].to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"AURA_BCTC_SoBo_{selected_year}.csv", mime="text/csv",
                               key="download_bctc_provisional")

        # Compare within a SINGLE company only. Missing years are not interpolated.
        companies = sorted(annual.loc[annual["_has_candidate"] if "_has_candidate" in annual else
                                      annual["status"].eq("PROVISIONAL_REVIEW_REQUIRED"),
                                      "symbol"].drop_duplicates().tolist())
        if companies:
            st.markdown("#### Xu hướng tài chính của từng cổ phiếu")
            first = "FPT" if "FPT" in companies else companies[0]
            chosen = st.selectbox("Chọn mã để so sánh 5 năm", companies,
                                   index=companies.index(first), key="aura_financial_compare")
            trend = trend_for_symbol(annual, chosen)
            if trend.empty:
                st.caption("Chưa có chỉ tiêu cho mã đã chọn.")
            else:
                st.caption("ROE, ROA và tăng trưởng EPS ở đây là tỷ số sơ bộ; "
                           "các năm thiếu được để trống, không nội suy hay gán 0.")
                series = [x for x in ("ROE (%)", "ROA (%)") if x in trend and trend[x].notna().any()]
                if series:
                    st.line_chart(trend.set_index("Năm")[series], height=260)
                display_table(preview_display(annual.loc[annual["symbol"].eq(chosen)].sort_values("year")), 260)
                company_type = annual.loc[annual["symbol"].eq(chosen), "company_type"]
                if not company_type.empty and str(company_type.iloc[-1]) in ("BANK", "FINANCIAL_OTHER"):
                    st.caption("Ngân hàng/chứng khoán: không so sánh biên lợi nhuận hay tỷ lệ nợ "
                               "với doanh nghiệp sản xuất như cùng một nhóm chuẩn.")
                company_issues = annual.loc[annual["symbol"].eq(chosen) & annual["year"].eq(selected_year), "issues"]
                if not company_issues.empty and pd.notna(company_issues.iloc[0]) and str(company_issues.iloc[0]).strip():
                    with st.expander("Chi tiết vấn đề dữ liệu cần xem lại"):
                        st.code(str(company_issues.iloc[0]), language="text")

        with st.expander("Kiểm tra file nguồn và cách cập nhật", expanded=False):
            coverage_path = ROOT / "data" / "fundamentals" / "processed" / "financial_feature_coverage.csv"
            if coverage_path.is_file():
                try:
                    file_coverage = pd.read_csv(coverage_path, encoding="utf-8-sig")
                    if {"symbol", "statement_files_present"}.issubset(file_coverage.columns):
                        count_file = pd.to_numeric(file_coverage["statement_files_present"], errors="coerce")
                        st.caption(f"Mã có ≥1 file nguồn BCTC: {int(count_file.gt(0).sum()):,}; "
                                   f"có 3 loại file: {int(count_file.eq(3).sum()):,}. "
                                   "Một file có thể gồm nhiều năm nhưng không chứng nhận đủ dữ liệu mỗi năm.")
                except (OSError, ValueError, pd.errors.ParserError):
                    st.caption("Không đọc được bảng độ phủ nguồn tại thời điểm này.")
            st.code(r".\.venv\Scripts\python.exe .\build_financial_features.py", language="powershell")
            st.caption("Chạy lệnh này **sau khi** hoàn tất tải BCTC 5 năm; "
                       "không chạy đồng thời hai chương trình ghi file BCTC.")

    st.caption("Phạm vi 2021–2025 là báo cáo **năm**. Chưa bổ sung bán niên 2026; "
               "chưa xác minh ngày công bố và hồ sơ gốc. "
               "Không dùng số liệu công bố sau ngày chốt để hồi kiểm (look-ahead bias).")

    # AURA 3.9 - add financial data quality panel, no changes to rating formulas
    from core.aura_financial_quality import render_financial_quality_panel
    render_financial_quality_panel(ROOT)

with tab_data:
    st.subheader("Minh bạch dữ liệu & phương pháp")
    st.markdown("**Nguồn thị trường:** SSI FastConnect V3 · OHLCV EOD lưu cục bộ. "
                "Chỉ trang Tra cứu mới có thể tải một mã khi bạn chủ động bấm cập nhật. "
                "WebSocket SSI Worker là nguồn riêng, không sửa nến EOD hoặc điểm kỹ thuật.")
    st.markdown("**Phạm vi:** `EQUITY` được xác nhận trong danh mục SSI; "
                "`EQUITY_CANDIDATE` tra cứu được nhưng không xếp hạng mặc định; "
                "CW/ETF/trái phiếu/phái sinh không đưa vào mẫu cổ phiếu.")
    st.markdown("**Ngày chốt:** ngày nến EOD mới nhất có trong tập dữ liệu hợp lệ. "
                "Các mã thiếu file, thiếu 200 phiên hoặc không có nến đúng ngày chốt được liệt kê "
                "riêng; điểm của chúng để trống, không coi là cổ phiếu xấu.")
    if LEDGER_PATH.is_file():
        try:
            ledger = pd.read_csv(LEDGER_PATH, encoding="utf-8-sig", keep_default_na=False)
            if "status" in ledger:
                counts = ledger["status"].value_counts().rename_axis("Trạng thái đồng bộ").reset_index(name="Số mã")
                st.markdown("**Nhật ký Market Sync cục bộ**")
                display_table(counts, 195)
                st.caption("`OK` chỉ là lần gọi SSI đã thành công; không có nghĩa mã được xếp hạng. "
                           "`NO_BARS` và `ERROR` phải xem riêng nếu còn thiếu file giá.")
        except (OSError, ValueError, pd.errors.ParserError):
            st.caption("Nhật ký đồng bộ chưa đọc được.")
    st.markdown("**Khi có dữ liệu EOD mới:** cập nhật ngoài Terminal, sau đó bấm Quét / làm mới xếp hạng.")
    st.code("python scripts/market_sync.py --mode stale --limit 1518 --pause 1.5\n"
            "python scripts/market_sync.py --mode missing --limit 1518 --pause 1.5", language="bash")
    st.caption("Market Sync có cooldown: hàng đợi = 0 không chứng minh dữ liệu của tất cả 1.518 mã đã đầy đủ.")
    st.markdown("**Trọng số điểm kỹ thuật /10**")
    factor_labels = {"trend": "Xu hướng MA", "momentum": "Động lượng", "liquidity": "Thanh khoản",
                     "rsi_macd": "RSI/MACD", "risk": "Rủi ro", "breakout": "Vượt đỉnh"}
    display_table(pd.DataFrame([{"Thành phần": factor_labels[k], "Trọng số (%)": 100*v}
                                for k, v in WEIGHTS.items()]), 270)
    st.caption("Giả thuyết điểm tổng hợp: kỹ thuật 50%, cơ bản 35%, định giá 15%; "
               "chỉ tính khi đủ bằng chứng nguồn/ngày công bố và chỉ tiêu đúng thời điểm. "
               "Điểm xếp hạng là công cụ nghiên cứu, không phải khuyến nghị đầu tư.")
    with st.expander("Danh mục SSI và phân loại chứng khoán"):
        cols = [c for c in ("symbol", "name", "board", "sector", "asset_class") if c in cat]
        st.dataframe(cat[cols], hide_index=True, use_container_width=True, height=340)


# AURA H1 2026 PANEL V9.1
from core.aura_h1_2026_panel import render_h1_panel
render_h1_panel()
