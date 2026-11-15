"""AURA V9.9: display-only parity with BCTC returned by the local app.

Uploads are per-symbol private R2 objects, never Github files. No score changes.
The source BCTC is not automatically an officially verified disclosure.
"""
from __future__ import annotations

import gzip
import io
import json
import math
import re
from datetime import datetime, timezone
from typing import Dict

import pandas as pd

_SYMBOL = re.compile(r"[A-Z0-9]{2,12}\Z")
_SCHEMA = "aura_original_bctc_v1"
_NAMES = {"balance_sheet": "Bảng cân đối kế toán", "income_statement": "Kết quả kinh doanh", "cash_flow": "Lưu chuyển tiền tệ"}
_MAX_SIZE = 5 * 1024 * 1024
_MAX_ROWS = 6000


def _symbol(value: str) -> str:
    value = str(value or "").strip().upper()
    if not _SYMBOL.fullmatch(value):
        raise ValueError("INVALID_SYMBOL")
    return value


def _value(x):
    if pd.isna(x):
        return None
    try:
        f = float(x)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError, OverflowError):
        return None


def build_document(symbol: str, statements: Dict[str, pd.DataFrame], *, captured_at=None):
    """Serialize exactly the three item-by-year tables local `lay_bctc` returned."""
    symbol = _symbol(symbol)
    result = {}
    count = 0
    for kind in _NAMES:
        frame = statements.get(kind)
        if frame is None or frame.empty:
            continue
        years = [int(x) for x in frame.columns]
        if not years or len(years) > 8 or len(set(years)) != len(years) or any(y < 2016 or y > 2030 for y in years):
            raise ValueError("INVALID_YEARS")
        rows = []
        for item, values in frame.iterrows():
            label = str(item).strip()
            if not label or len(label) > 300:
                continue
            rows.append({"item": label, "values": [_value(v) for v in values.to_list()]})
        count += len(rows)
        if rows:
            result[kind] = {"years": years, "rows": rows}
    if not result or count > _MAX_ROWS:
        raise ValueError("INVALID_BCTC_ROWS")
    return {"schema": _SCHEMA, "symbol": symbol,
            "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
            "source": "Local AURA financial providers (vnfinancialdata / vnstock)",
            "source_verified": False, "published_at": None,
            "statements": result}


def encode_document(document: dict) -> bytes:
    raw = json.dumps(document, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > _MAX_SIZE:
        raise ValueError("DOCUMENT_TOO_LARGE")
    return gzip.compress(raw, compresslevel=8, mtime=0)


def decode_document(blob: bytes, expected_symbol: str):
    expected_symbol = _symbol(expected_symbol)
    if len(blob) > _MAX_SIZE:
        raise ValueError("BLOB_TOO_LARGE")
    # Bounded decompression, including for unexpectedly high gzip compression ratios.
    with gzip.GzipFile(fileobj=io.BytesIO(blob), mode="rb") as z:
        raw = z.read(_MAX_SIZE + 1)
        if len(raw) > _MAX_SIZE:
            raise ValueError("DECOMPRESSED_TOO_LARGE")
    data = json.loads(raw)
    if data.get("schema") != _SCHEMA or data.get("symbol") != expected_symbol:
        raise ValueError("UNEXPECTED_SCHEMA_OR_SYMBOL")
    if data.get("source_verified") is not False or data.get("published_at") is not None:
        raise ValueError("UNVERIFIED_SOURCE_METADATA_CHANGED")
    statements = data.get("statements")
    if not isinstance(statements, dict) or not 1 <= len(statements) <= 3:
        raise ValueError("INVALID_STATEMENTS")
    frames, rows_total = {}, 0
    for kind, info in statements.items():
        if kind not in _NAMES or not isinstance(info, dict):
            raise ValueError("INVALID_KIND")
        years = info.get("years")
        rows = info.get("rows")
        if (not isinstance(years, list) or len(years) == 0 or len(years) > 8 or
                len(set(map(str, years))) != len(years) or
                not all(type(y) is int and 2016 <= y <= 2030 for y in years) or
                not isinstance(rows, list)):
            raise ValueError("INVALID_DATA_STRUCTURE")
        labels, values = [], []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("item"), str):
                raise ValueError("INVALID_ROW")
            if not 0 < len(row["item"]) <= 300 or not isinstance(row.get("values"), list) or len(row["values"]) != len(years):
                raise ValueError("INVALID_ROW_SIZE")
            if not all(v is None or (type(v) in (int, float) and math.isfinite(v)) for v in row["values"]):
                raise ValueError("INVALID_NUMERIC_VALUES")
            labels.append(row["item"])
            values.append(row["values"])
        rows_total += len(rows)
        frames[kind] = pd.DataFrame(values, index=labels, columns=years, dtype=float)
    if rows_total == 0 or rows_total > _MAX_ROWS:
        raise ValueError("UNEXPECTED_ROW_COUNT")
    return frames, {"captured_at": str(data.get("captured_at") or ""), "source": str(data.get("source") or "")}


def object_key(symbol: str, prefix: str = "aura-eod") -> str:
    symbol = _symbol(symbol)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_/-]{0,120}", prefix) or ".." in prefix:
        raise ValueError("INVALID_PREFIX")
    return prefix.rstrip("/") + "/financial_original/v1/" + symbol + ".json.gz"


def _retrieve(symbol: str):
    """Network reads only when requested; failures never break the EOD app."""
    from core.aura_r2_market import enabled, client, prefix, setting
    if not enabled():
        return None
    key = object_key(symbol, prefix())
    try:
        response = client().get_object(Bucket=setting("AURA_R2_BUCKET"), Key=key)
        data = response["Body"].read(_MAX_SIZE + 1)
        return decode_document(data, symbol)
    except Exception:
        # Do not leak S3 paths, authentication information, or headers to visitors.
        return None


def load_original(symbol: str):
    import streamlit as st
    @st.cache_data(ttl=1800, show_spinner=False, max_entries=150)
    def _cached(symbol_key):
        return _retrieve(symbol_key)
    try:
        return _cached(_symbol(symbol))
    except Exception:
        return None


def render_original_statements(symbol: str) -> bool:
    import streamlit as st
    result = load_original(symbol)
    if not result:
        return False
    statements, metadata = result
    st.subheader("BCTC 2021–2025 · bảng chỉ tiêu như bản local")
    st.warning("Dữ liệu gốc do ứng dụng local lấy từ nguồn tài chính bên ngoài và sao lưu vào R2 riêng tư. "
               "**Chưa xác minh BCTC công bố, thời điểm công bố hoặc phạm vi hợp nhất**; "
               "không dùng để chấm điểm cơ bản hay backtest.")
    st.caption("Nguồn hiển thị: bản sao dữ liệu local · Thời điểm lưu: " + metadata.get("captured_at", "chưa rõ"))
    for kind, label in _NAMES.items():
        if kind not in statements:
            continue
        frame = statements[kind]
        st.subheader(label)
        keyword = st.text_input("Lọc chỉ tiêu (" + label + ")", key="v99_local_filter_" + symbol + "_" + kind,
                                placeholder="vd: lãi, tài sản, nợ...")
        selected = frame.loc[frame.index.astype(str).str.contains(keyword, case=False, regex=False)] if keyword else frame
        st.dataframe(selected.style.format("{:,.0f}"), use_container_width=True, height=380)
    return True


def render_original_ratios(symbol: str) -> bool:
    import streamlit as st
    result = load_original(symbol)
    if not result:
        return False
    statements, metadata = result
    from core.analysis import tinh_ty_so
    ratios = tinh_ty_so(statements)
    if ratios.empty:
        return False
    st.subheader("Tỷ số tài chính · tính từ cùng BCTC bản local")
    st.warning("Các tỷ số được **tính lại từ BCTC local đã sao lưu** để kết quả đồng nhất giữa máy và Cloud. "
               "Nguồn chưa đối chiếu báo cáo công bố, không sử dụng để chấm Smart Rating / điểm cơ bản.")
    st.dataframe(ratios.style.format("{:,.2f}"), use_container_width=True, height=380)
    chosen = st.selectbox("Xem biểu đồ tỷ số", list(ratios.index), key="v99_local_ratio_" + symbol)
    series = pd.to_numeric(ratios.loc[chosen], errors="coerce").dropna()
    if len(series):
        st.bar_chart(pd.DataFrame({chosen: series.to_numpy()}, index=series.index.map(str)), height=280)
    return True
