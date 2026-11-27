"""AURA: source-linked company news and regulatory discovery.

Uses public Google News RSS search as discovery (NOT a verified news API),
plus official Vietnamese legal portals as authoritative verification links.
Headlines alone never determine recommendation direction, legal force, or scores.
No authentication/API keys; no background monitoring; HTTP capped by timeout.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape
from pathlib import Path
import re
import unicodedata
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st

VN_TZ = timezone(timedelta(hours=7))

# Topics are qualitative possibilities, never an automatic company valuation.
TOPICS = (
    (("lãi suất", "tín dụng", "trái phiếu", "vay vốn", "huy động vốn", "lãi vay"),
     "Chi phí vốn", "Đối chiếu mức vay nợ, lãi suất thả nổi và khả năng tiếp cận tín dụng của doanh nghiệp."),
    (("lợi nhuận", "doanh thu", "kết quả kinh doanh", "báo cáo tài chính", "biên lợi nhuận"),
     "Kết quả kinh doanh", "Kiểm tra báo cáo kỳ gốc, lợi nhuận bất thường và mức độ đóng góp của hoạt động cốt lõi."),
    (("cổ tức", "chia tách", "phát hành", "esop", "cổ phiếu thưởng"),
     "Cơ cấu vốn & quyền cổ đông", "Đối chiếu ngày chốt quyền, tỷ lệ thực hiện, pha loãng và điều chỉnh giá cổ phiếu."),
    (("dự án", "nhà máy", "hợp đồng", "đầu tư", "mở rộng", "đơn hàng", "khai trương"),
     "Doanh thu & công suất", "Kiểm tra tiến độ, vốn đầu tư, thời điểm ghi nhận doanh thu và chi phí triển khai."),
    (("thuế", "thuế suất", "thuế quan", "thuế nhập khẩu", "thuế xuất khẩu"),
     "Thuế & biên lợi nhuận", "Xác minh đối tượng áp dụng, thời điểm có hiệu lực và tỷ trọng doanh thu/chi phí liên quan."),
    (("đất đai", "nhà ở", "bất động sản", "quy hoạch", "giấy phép", "pháp lý"),
     "Pháp lý dự án", "Kiểm tra phạm vi điều chỉnh, pháp lý từng dự án và thời điểm đủ điều kiện triển khai."),
    (("tỷ giá", "usd", "ngoại tệ", "xuất khẩu", "nhập khẩu", "logistics"),
     "Tỷ giá & thương mại", "Đối chiếu tỷ lệ doanh thu/chi phí ngoại tệ và chính sách phòng ngừa rủi ro tỷ giá."),
    (("nghị định", "thông tư", "luật", "quyết định", "nghị quyết", "chính sách", "quy định"),
     "Chính sách & tuân thủ", "Đọc văn bản gốc để xác nhận ngành, đối tượng áp dụng, ngày hiệu lực và quy định chuyển tiếp."),
    (("sáp nhập", "mua lại", "thoái vốn", "bán vốn", "m&a"),
     "Sở hữu & giao dịch", "Đối chiếu tỷ lệ sở hữu, giá trị thương vụ, thời điểm hoàn tất và nghĩa vụ công bố thông tin."),
)

OFFICIAL_PORTALS = (
    ("Cơ sở dữ liệu quốc gia về pháp luật", "https://vbpl.vn"),
    ("Hệ thống văn bản Chính phủ", "https://vanban.chinhphu.vn/he-thong-van-ban?classid=1"),
    ("Ngân hàng Nhà nước Việt Nam", "https://www.sbv.gov.vn"),
)


def _clean(value: object, max_chars=150) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:max_chars]


def _deaccent(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").replace("đ", "d")


def _short_company(name: str) -> str:
    text = _clean(name, 120)
    text = re.sub(r"^\s*(công ty|ngân hàng)\s+(cổ phần|thương mại cổ phần|tnhh|tập đoàn)\s+", "", text, flags=re.I)
    return text[:85]


def company_meta(symbol: str, sector: str = "", company: str = "") -> tuple[str, str]:
    """Prefer the existing industry table, fallback to SSI catalogue if present."""
    symbol = _clean(symbol, 12).upper()
    company, sector = _clean(company, 120), _clean(sector, 80)
    if company and sector:
        return company, sector
    try:
        from core import industry
        info = industry.thong_tin(symbol)
        company = company or _clean(info.get("ten"), 120)
        sector = sector or _clean(info.get("icb2") or info.get("icb1"), 80)
    except (ImportError, AttributeError, OSError, KeyError, ValueError):
        pass
    if company and sector:
        return company, sector
    try:
        from core.ssi_universe import load_catalogue
        root = Path(__file__).resolve().parent.parent
        d = load_catalogue(root)
        one = d[d["symbol"].astype(str).str.upper().eq(symbol)]
        if not one.empty:
            company = company or _clean(one.iloc[0].get("name"), 120)
            sector = sector or _clean(one.iloc[0].get("sector"), 80)
    except (ImportError, OSError, KeyError, ValueError, TypeError):
        pass
    return company, sector


def sector_topic(sector: str) -> tuple[str, str]:
    """Map industry labels to broad public-policy search topics (not applicability)."""
    s = _deaccent(_clean(sector, 100))
    rows = (
        (("ngan hang", "tin dung", "tai chinh", "bao hiem"), "ngân hàng tín dụng bảo hiểm", "Lãi suất, an toàn vốn, thanh toán, quản trị rủi ro"),
        (("chung khoan", "dau tu tai chinh"), "chứng khoán thị trường vốn", "Công bố thông tin, giao dịch, huy động vốn"),
        (("bat dong san", "xay dung", "vat lieu", "ha tang"), "bất động sản đất đai xây dựng", "Đất đai, nhà ở, phê duyệt dự án, đầu tư công"),
        (("cong nghe", "phan mem", "vien thong", "cntt"), "công nghệ thông tin chuyển đổi số", "Dữ liệu, an ninh mạng, chuyển đổi số, viễn thông"),
        (("dien", "nang luong", "dau khi", "than"), "năng lượng điện dầu khí", "Cơ chế giá, quy hoạch, năng lượng tái tạo"),
        (("duoc", "y te", "benh vien"), "dược phẩm y tế", "Cấp phép, đấu thầu, đăng ký và giá thuốc"),
        (("nong nghiep", "thuc pham", "thuy san", "cao su"), "nông nghiệp thủy sản thực phẩm", "Tiêu chuẩn xuất khẩu, kiểm dịch, an toàn thực phẩm"),
        (("van tai", "logistics", "hang khong", "cang"), "vận tải logistics", "Hạ tầng, thuế phí, thương mại, vận tải"),
        (("det may", "da giay", "xuat khau"), "dệt may xuất khẩu", "Thuế quan, xuất xứ hàng hóa, thị trường xuất khẩu"),
    )
    for keys, topic, channel in rows:
        if any(key in s for key in keys):
            return topic, channel
    return (_clean(sector, 65) or "doanh nghiệp Việt Nam", "Lãi suất, thuế, lao động, thương mại và tuân thủ")


def topic_impact(title: str) -> tuple[str, str]:
    lower = _deaccent(_clean(title, 260))
    for keys, label, reasoning in TOPICS:
        if any(_deaccent(k) in lower for k in keys):
            return label, reasoning
    return "Cần đọc nội dung", "Chưa đủ bằng chứng từ tiêu đề để xác định cơ chế tác động. Kiểm tra nội dung bài báo và mức độ liên quan."


def _item_date(value: str):
    try:
        parsed = parsedate_to_datetime(value)
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(VN_TZ)
    except (ValueError, TypeError, IndexError):
        return None


def _rss_search(query: str, limit=12) -> list[dict]:
    """Bounded remote read; RSS links are discovery pointers, not verified facts."""
    if not query.strip():
        return []
    url = "https://news.google.com/rss/search?q=" + quote(query[:330], safe="") + "&hl=vi&gl=VN&ceid=VN:vi"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AURA-StockResearch/1.0)"})
        # AURA_V115_RSS_TIMEOUT: 4s là quá ngắn cho mã được đưa tin nhiều (vd FPT) -
        # payload RSS lớn hơn hẳn các mã khác nên hay bị timeout và rơi vào nhánh
        # "không tìm được tin" dù nguồn vẫn có dữ liệu. Nới lên 9s, vẫn có giới hạn.
        with urlopen(req, timeout=9) as response:
            if getattr(response, "status", 200) != 200:
                return []
            payload = response.read(650_001)
        if len(payload) > 650_000:
            return []
        root = ET.fromstring(payload)
    except (OSError, ValueError, ET.ParseError, TimeoutError):
        return []
    records = []
    now = datetime.now(VN_TZ)
    for item in root.findall(".//channel/item")[:70]:
        title = _clean(item.findtext("title"), 220)
        link = _clean(item.findtext("link"), 800)
        if not title or not link:
            continue
        parsed_link = urlparse(link)
        if parsed_link.scheme != "https" or parsed_link.hostname not in ("news.google.com", "www.google.com"):
            continue
        pub = _item_date(item.findtext("pubDate") or "")
        if pub and (pub > now + timedelta(days=1) or pub < now - timedelta(days=370)):
            continue
        source = _clean(item.findtext("source"), 70)
        if not source and " - " in title:
            source = _clean(title.rsplit(" - ", 1)[-1], 70)
        records.append({"title": title, "link": link, "source": source or "Google News RSS",
                        "date": pub, "label": topic_impact(title)[0]})
        if len(records) >= limit:
            break
    return records


def _distinct(records: list[dict], limit: int) -> list[dict]:
    seen, output = set(), []
    for rec in sorted(records, key=lambda x: x.get("date") or datetime(1970,1,1,tzinfo=VN_TZ), reverse=True):
        key = _deaccent(rec["title"].rsplit(" - ",1)[0]).strip()
        if key in seen:
            continue
        seen.add(key);output.append(rec)
        if len(output) >= limit:
            break
    return output


@st.cache_data(ttl=1800, show_spinner=False)
def company_news(symbol: str, company: str, *, max_items=8):
    symbol = re.sub(r"[^A-Z0-9]", "", symbol.upper())[:10]
    name = _short_company(company)
    terms = [f'"{symbol}" ("cổ phiếu" OR "lợi nhuận" OR "doanh nghiệp" OR "cổ tức") when:120d']
    if name and _deaccent(name) != _deaccent(symbol):
        terms.append(f'"{name}" ("lợi nhuận" OR "dự án" OR "cổ tức" OR "kinh doanh") when:120d')
    with ThreadPoolExecutor(max_workers=min(2,len(terms))) as pool:
        all_items = []
        for batch in pool.map(_rss_search, terms):
            all_items.extend(batch)
    # Keep high-confidence symbol/name title mentions, not generic sector headlines.
    matches = []
    company_norm = _deaccent(name)
    for item in all_items:
        t = _deaccent(item["title"])
        symbol_match = bool(re.search(r"(?<![a-z0-9])" + re.escape(symbol.lower()) + r"(?![a-z0-9])",t))
        name_match = len(company_norm) >= 5 and company_norm in t
        # Company feed focuses on the last 120 days, when dates are provided.
        recent = item.get("date") is None or item["date"] >= datetime.now(VN_TZ) - timedelta(days=120)
        if recent and (symbol_match or name_match):
            matches.append(item)
    return _distinct(matches, max_items)



# Strict title-based discovery. These are *relevance gates*, NOT assertions
# that a legal text applies to the company or that a proposed rate change happened.
_REGULATORY_WORDS = (
    "thong tu", "nghi dinh", "luat", "nghi quyet", "quyet dinh",
    "quy dinh", "chinh sach", "co che", "quy hoach", "du thao",
    "cap phep", "xu phat", "bo sung", "ban hanh", "hieu luc",
)
_AUTHORITY_WORDS = (
    "chinh phu", "quoc hoi", "ngan hang nha nuoc", "nhnn", "bo tai chinh",
    "bo cong thuong", "bo khoa hoc", "bo nong nghiep", "bo xay dung",
    "bo y te", "bo thong tin", "ubnd", "thu tuong", "co quan quan ly",
    "uy ban chung khoan", "bo tu phap", "bo noi vu", "bo van hoa",
)
_RATE_WORDS = (
    "lai suat dieu hanh", "lai suat tai cap von", "lai suat tai chiet khau",
    "lai suat omo", "lai suat thi truong mo", "lai suat du tru bat buoc",
    "ty le du tru bat buoc", "tran lai suat huy dong", "nghiep vu thi truong mo",
)
_RATE_ACTIONS = (
    "dieu chinh", "thay doi", "tang", "giam", "giu nguyen", "cong bo",
    "quyet dinh", "ban hanh", "ap dung", "an dinh", "duy tri",
)
_SPECULATIVE = ("de xuat", "kien nghi", "du kien", "co the", "tin don", "du bao", "lo ngai")

# Source sector label -> focused domain phrases -> why it could matter.
# No unclassified fallback: a generic policy is not automatically sector relevant.
_SECTOR_RULES = (
    (("ngan hang", "tin dung", "bao hiem", "dich vu tai chinh"),
     "ngân hàng tín dụng bảo hiểm", ("an toan von", "phan loai no", "ty le du tru", "han muc tin dung", "tin dung", "bao hiem", "thanh toan khong dung tien mat", "ngan hang", "nghiep vu ngan hang"),
     "Vốn, tín dụng, chi phí tuân thủ hoặc điều kiện kinh doanh trong lĩnh vực ngân hàng/bảo hiểm."),
    (("chung khoan", "dau tu tai chinh", "thi truong von"),
     "chứng khoán thị trường vốn", ("chung khoan", "giao dich ky quy", "cong bo thong tin", "trai phieu doanh nghiep", "thi truong von", "niem yet"),
     "Giao dịch, huy động vốn và nghĩa vụ công bố thông tin của công ty chứng khoán."),
    (("bat dong san", "xay dung", "vat lieu", "ha tang"),
     "bất động sản xây dựng", ("dat dai", "nha o", "bat dong san", "quy hoach do thi", "cap phep xay dung", "dau tu cong", "xay dung", "vat lieu xay dung", "du an nha o"),
     "Pháp lý dự án, đầu tư công, cung/cầu bất động sản hoặc chi phí xây dựng."),
    (("cong nghe", "phan mem", "vien thong", "cntt", "dich vu cong nghe", "so hoa"),
     "công nghệ thông tin chuyển đổi số", ("an ninh mang", "bao ve du lieu", "du lieu ca nhan", "cong nghe thong tin", "chuyen doi so", "vien thong", "ha tang so", "dien toan dam may", "trung tam du lieu", "cong nghiep ban dan", "cong nghe so", "tri tue nhan tao"),
     "Điều kiện dữ liệu/an ninh mạng, đầu tư hạ tầng số và nhu cầu dịch vụ công nghệ."),
    (("dien", "nang luong", "dau khi", "than", "khai khoang"),
     "điện năng lượng dầu khí", ("gia dien", "nang luong", "dau khi", "dien gio", "dien mat troi", "dien luc", "xang dau", "khai khoang", "khi thien nhien", "quy hoach dien"),
     "Giá bán, cơ chế mua điện, quy hoạch hoặc chi phí nguyên nhiên liệu."),
    (("duoc", "y te", "benh vien", "cham soc suc khoe"),
     "dược phẩm y tế", ("dau thau thuoc", "dang ky thuoc", "duoc pham", "giay phep luu hanh", "bao hiem y te", "thiet bi y te", "benh vien"),
     "Đấu thầu, giá, cấp phép và tiếp cận thị trường dược/y tế."),
    (("nong nghiep", "thuc pham", "thuy san", "cao su", "chan nuoi"),
     "nông nghiệp thực phẩm thủy sản", ("kiem dich", "an toan thuc pham", "thuy san", "nong san", "chan nuoi", "bao ve thuc vat", "xuat khau gao", "thuc pham", "cao su"),
     "Kiểm dịch, tiêu chuẩn xuất khẩu, nguyên liệu và quy chuẩn chất lượng."),
    (("van tai", "logistics", "hang khong", "cang", "kho bai"),
     "vận tải logistics hàng không", ("van tai", "logistics", "hang khong", "cang bien", "phi cang", "thu phi duong bo", "ha tang giao thong", "hang hai"),
     "Cước vận tải, phí hạ tầng, năng lực khai thác hoặc luồng hàng hóa."),
    (("det may", "da giay", "xuat khau", "hang tieu dung"),
     "dệt may xuất khẩu", ("det may", "da giay", "xuat xu hang hoa", "thue quan", "thue xuat khau", "hang may mac", "thi truong xuat khau"),
     "Thuế quan, xuất xứ và yêu cầu tuân thủ tại thị trường xuất khẩu."),
    (("ban le", "thuong mai", "phan phoi"),
     "bán lẻ thương mại", ("ban le", "phan phoi", "thuong mai dien tu", "bao ve nguoi tieu dung", "thue gia tri gia tang", "gia ban le"),
     "Thuế bán hàng, nhu cầu tiêu dùng, kênh phân phối hoặc tuân thủ thương mại."),
)


def _term_in_title(normalized_title: str, word: str) -> bool:
    word = _deaccent(word)
    return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", normalized_title) is not None


def _has_any(title: str, terms) -> bool:
    return any(_term_in_title(title, term) for term in terms)


def _sector_rule(sector: str):
    s = _deaccent(sector)
    for keys, query, keywords, impact in _SECTOR_RULES:
        if any(k in s for k in keys):
            return query, keywords, impact
    return None


def _is_rate_policy(title: str) -> bool:
    t = _deaccent(title)
    # Narrow to an actual monetary-policy interest-rate/OMO measure by NHNN.
    authority = _has_any(t, ("ngan hang nha nuoc", "nhnn"))
    rate = _has_any(t, _RATE_WORDS) or (_term_in_title(t, "lai suat") and _has_any(t, ("dieu hanh", "tai cap von", "tai chiet khau")))
    return authority and rate and _has_any(t, _RATE_ACTIONS) and not _has_any(t, _SPECULATIVE)


def _is_company_policy(title: str, symbol: str, company: str) -> bool:
    t = _deaccent(title)
    sym = re.sub(r"[^A-Z0-9]", "", symbol.upper())[:10].lower()
    short = _deaccent(_short_company(company))
    # Reject headlines only mentioning ticker as part of an unrelated word.
    company_ref = (len(sym) >= 2 and _term_in_title(t, sym)) or (len(short) >= 5 and short in t)
    return bool(company_ref and _has_any(t, _REGULATORY_WORDS) and _has_any(t, _AUTHORITY_WORDS))


def _is_sector_policy(title: str, rule) -> bool:
    if rule is None:
        return False
    t = _deaccent(title)
    _, keywords, _ = rule
    # Both a real industry-specific term and a state/regulatory term are required.
    return _has_any(t, keywords) and _has_any(t, _REGULATORY_WORDS)


def _policy_item(item: dict, category: str, *, sector_rule=None):
    entry = dict(item)
    if category == "direct":
        entry["policy_label"] = "Có nhắc doanh nghiệp & cơ quan quản lý"
        entry["policy_reason"] = "Tin có nhắc doanh nghiệp cùng thông tin quản lý; phải đọc văn bản gốc để kiểm tra đối tượng áp dụng và tác động thực tế."
    elif category == "sector":
        entry["policy_label"] = "Chính sách đúng ngành"
        entry["policy_reason"] = (sector_rule[2] if sector_rule else "Cần kiểm tra phạm vi áp dụng.") + " Cần đối chiếu ngày hiệu lực và văn bản gốc."
    else:
        entry["policy_label"] = "Lãi suất điều hành / tiền tệ"
        entry["policy_reason"] = "Có thể truyền dẫn qua mặt bằng lãi suất, chi phí vốn và định giá thị trường; chưa xác định mức tác động hoặc hướng tăng/giảm của cổ phiếu."
    return entry


@st.cache_data(ttl=3600, show_spinner=False)
def relevant_policy_news(symbol: str, company: str, sector: str, *, per_group=5):
    """Discover only headline matches to company, sector rule, or NHNN policy rates.

    Source = Google News RSS discovery; no assertion of legal force/actual impact.
    """
    sym = re.sub(r"[^A-Z0-9]", "", symbol.upper())[:10]
    name = _short_company(company)
    rule = _sector_rule(sector)
    queries = [
        ("direct", f'"{sym}" ("thông tư" OR "nghị định" OR "quyết định" OR "quy định") when:240d'),
        ("rates", '"Ngân hàng Nhà nước" ("lãi suất điều hành" OR "tái cấp vốn" OR "tái chiết khấu" OR "thị trường mở") when:365d'),
        ("rates", '"NHNN" ("lãi suất điều hành" OR "lãi suất tái cấp vốn") ("điều chỉnh" OR "tăng" OR "giảm") when:365d'),
    ]
    if name and len(name) >= 5:
        queries.append(("direct", f'"{name}" ("luật" OR "thông tư" OR "nghị định" OR "quyết định") when:240d'))
    if rule:
        queries.extend([
            ("sector", f'{rule[0]} ("thông tư" OR "nghị định" OR "quyết định" OR "luật") when:365d'),
            ("sector", f'{rule[0]} ("quy định" OR "chính sách" OR "cơ chế") when:240d'),
        ])
    grouped = {"direct": [], "sector": [], "rates": []}
    def _get(pair):
        key, query = pair
        return key, _rss_search(query, limit=30)
    with ThreadPoolExecutor(max_workers=min(5, len(queries))) as pool:
        for key, batch in pool.map(_get, queries):
            for item in batch:
                title = item.get("title", "")
                is_rate = _is_rate_policy(title)
                is_direct = _is_company_policy(title, sym, company)
                is_sector = _is_sector_policy(title, rule)
                # The regulatory category takes precedence; don't blend broad news.
                category = "direct" if is_direct else "rates" if is_rate else "sector" if is_sector else None
                if category:
                    grouped[category].append(_policy_item(item, category, sector_rule=rule))
    seen = set()
    output = {}
    # Avoid duplicate stories appearing in multiple groups.
    for category in ("direct", "sector", "rates"):
        output[category] = []
        for item in _distinct(grouped[category], 50):
            key = _deaccent(item["title"].rsplit(" - ", 1)[0]).strip()
            if key not in seen:
                seen.add(key)
                output[category].append(item)
            if len(output[category]) >= per_group:
                break
    return output


def _news_html(item: dict, *, policy=False) -> str:
    label, reason = topic_impact(item["title"])
    if policy:
        label = item.get("policy_label", label)
        reason = item.get("policy_reason", reason)
    when = item["date"].strftime("%d/%m/%Y") if item.get("date") else "Chưa xác định ngày"
    title = escape(item["title"])
    link = escape(item["link"],quote=True)
    meta = f"{escape(item['source'])} · {escape(when)}"
    return f'''<article class="aura-story">
      <div class="aura-story-top"><span class="aura-story-tag">{escape(label)}</span>
       <span class="aura-story-meta">{meta}</span></div>
      <a class="aura-story-link" href="{link}" target="_blank" rel="noopener noreferrer nofollow">{title}</a>
      <p class="aura-story-note"><b>{"Hướng tác động cần kiểm chứng" if policy else "Kênh tác động tiềm năng"}:</b> {escape(reason)}</p>
    </article>'''


def _styles():
    st.markdown("""<style>
    .aura-context{padding:15px 19px;border:2px solid #8F47E6;border-radius:18px;
      background:linear-gradient(115deg,#E4D4FF,#FFDEF0);box-shadow:4px 5px 0 #24113D;
      margin:7px 4px 23px 0;color:#2C1949;line-height:1.7}
    .aura-story{background:#fff;border:2px solid #B387F5;border-radius:18px;padding:15px 18px;
      margin:10px 4px 16px 0;box-shadow:4px 4px 0 #261048}
    .aura-story-top{display:flex;align-items:center;justify-content:space-between;
      flex-wrap:wrap;gap:9px;margin-bottom:9px}
    .aura-story-tag{background:linear-gradient(105deg,#7D37F1,#C13FD8);border:1px solid #27123C;color:#fff;
      font-size:11px;font-weight:850;border-radius:999px;padding:5px 11px}
    .aura-story-meta{font-size:11px;font-weight:600;color:#76648B}
    .aura-story-link{color:#32144D!important;font-weight:800;font-size:15px;
      line-height:1.65;text-decoration:none}
    .aura-story-link:hover{color:#7332E0!important;text-decoration:underline}
    .aura-story-note{font-size:12px;line-height:1.65;color:#5C516E;margin:9px 0 0}
    </style>""", unsafe_allow_html=True)


def render_company_news(symbol: str, *, company="", sector=""):
    symbol = re.sub(r"[^A-Z0-9]","",symbol.upper())[:10]
    company,sector=company_meta(symbol,sector,company)
    _styles()
    st.subheader("Tin tức & sự kiện liên quan doanh nghiệp")
    st.markdown(f'''<div class="aura-context"><b>{escape(symbol)}</b> · {escape(company or "Chưa có tên doanh nghiệp")}
    <div style="font-size:12px">Tin được khám phá từ Google News RSS theo mã/tên công ty; phần “kênh tác động” chỉ là
    <b>gợi ý câu hỏi nghiên cứu theo tiêu đề</b>, không phải kết luận bài báo hay tín hiệu mua/bán.</div></div>''', unsafe_allow_html=True)
    with st.spinner("Đang tìm tin doanh nghiệp từ nguồn công khai..."):
        items=company_news(symbol,company)
    if not items:
        st.info("Chưa tìm được bài báo phù hợp hoặc nguồn RSS tạm thời không phản hồi. Có thể tra cứu trực tiếp ở liên kết dưới.")
    else:
        st.caption(f"{len(items)} tin gần đây · Nguồn/đường dẫn theo bài đăng · Nội dung bài chưa được xác minh độc lập")
        for item in items:
            st.markdown(_news_html(item),unsafe_allow_html=True)
    search=quote(f'"{symbol}" {company or "cổ phiếu"}',safe="")
    st.link_button("Mở Google News để tìm thêm tin về " + symbol,
                   f"https://news.google.com/search?q={search}&hl=vi&gl=VN&ceid=VN:vi")
    st.caption("Các tin trên không được dùng làm đầu vào tự động cho điểm đánh giá và không đồng nghĩa tác động tích cực/tiêu cực đã được kiểm chứng.")



def render_policy_page(symbol: str, *, sector="", company=""):
    """Focused legal/macro feed; no general policy headlines slipped into this UI."""
    symbol = re.sub(r"[^A-Z0-9]", "", symbol.upper())[:10]
    company, sector = company_meta(symbol, sector, company)
    rule = _sector_rule(sector)
    _styles()
    st.subheader("Vĩ mô & Chính sách liên quan")
    industry_text = sector or "Chưa phân loại"
    st.markdown(f"""<div class="aura-context"><b>{escape(symbol)}</b> · {escape(company or "Chưa có tên doanh nghiệp")}
      <div>Ngành: <b>{escape(industry_text)}</b></div>
      <div style="font-size:12px">AURA chỉ hiển thị tin có <b>liên hệ đến chính doanh nghiệp, lĩnh vực hoạt động</b>
      hoặc <b>lãi suất điều hành của Ngân hàng Nhà nước</b>. Không tự suy luận tăng/giảm giá cổ phiếu hay hiệu lực văn bản.</div></div>""", unsafe_allow_html=True)
    with st.spinner("Đang sàng lọc tin chính sách theo doanh nghiệp, ngành và NHNN..."):
        groups = relevant_policy_news(symbol, company, sector)
    sections = (
        ("direct", "Liên quan trực tiếp đến doanh nghiệp", "Tin có nhắc chính doanh nghiệp và cơ quan quản lý nhà nước."),
        ("sector", "Quy định liên quan đến ngành", "Chỉ chọn tin vừa có nội dung quản lý vừa nhắc đúng lĩnh vực của công ty."),
        ("rates", "Lãi suất điều hành & tác động thị trường", "Chỉ theo dõi các tin về thay đổi/quyết định lãi suất chính sách, OMO, tái cấp vốn hoặc tái chiết khấu của NHNN."),
    )
    total = sum(len(v) for v in groups.values())
    st.caption(f"{total} tin phù hợp theo bộ lọc tiêu đề · Nguồn khám phá: Google News RSS · Tin có thể là tường thuật, không phải bản gốc pháp luật")
    for key, heading, description in sections:
        if key == "sector" and not rule:
            st.caption("Chưa xác định được nhóm ngành chuyên biệt để đối chiếu chính sách; không hiển thị tin ngành chung chung.")
            continue
        st.markdown("#### " + heading)
        st.caption(description)
        if not groups.get(key):
            st.info("Chưa tìm thấy tin đủ liên quan trong nguồn đang tra cứu. AURA không chèn các bài chính sách chung để lấp chỗ trống.")
        else:
            for item in groups[key]:
                st.markdown(_news_html(item, policy=True), unsafe_allow_html=True)
    st.divider()
    st.markdown("**Kiểm tra văn bản gốc và hiệu lực**")
    a, b = st.columns(2)
    with a:
        st.link_button("Cơ sở dữ liệu pháp luật", "https://vbpl.vn", use_container_width=True)
    with b:
        st.link_button("Hệ thống văn bản Chính phủ", "https://vanban.chinhphu.vn/he-thong-van-ban?classid=1", use_container_width=True)
    st.link_button("Ngân hàng Nhà nước Việt Nam", "https://www.sbv.gov.vn")
    st.caption("Bộ lọc dựa trên tiêu đề tin và từ khóa ngành. Bài báo có thể mô tả dự thảo, đề xuất hoặc văn bản đã ban hành."
               " Việc áp dụng cho doanh nghiệp và tình trạng hiệu lực phải được kiểm tra tại nguồn chính thức.")
