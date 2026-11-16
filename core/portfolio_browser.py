"""Danh mục trên bản online: lưu RIÊNG trong trình duyệt của từng máy (localStorage).

- Máy chủ chỉ giữ file SQLite tạm cho từng phiên (core/aura_cloud_portfolio.py) → không ai
  thấy danh mục của người khác. Khi mở lại trang, dữ liệu được khôi phục từ trình duyệt.
- Không gửi danh mục lên GitHub/R2/máy chủ khác. Xóa dữ liệu duyệt web = xóa danh mục.
- Có thêm xuất/nhập file JSON để sao lưu hoặc chuyển sang máy khác.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.portfolio_store import PortfolioInputError, _snapshot, connect, normalize_symbol

STORAGE_KEY = "aura_portfolio_v1"
VERSION = 1
MAX_BYTES = 1_000_000
_EMPTY = "__AURA_EMPTY__"
TRADE_FIELDS = ("id", "symbol", "trade_date", "side", "quantity", "price_vnd", "fee_pct", "tax_pct", "created_at")


def export_state(db: Path) -> dict:
    with connect(db) as conn:
        watched = [dict(r) for r in conn.execute("SELECT symbol, added_at FROM watched ORDER BY symbol")]
        trades = [dict(r) for r in conn.execute(
            "SELECT " + ",".join(TRADE_FIELDS) + " FROM trades ORDER BY trade_date, id")]
    return {"version": VERSION, "watched": watched, "trades": trades}


def to_text(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def import_state(db: Path, payload) -> int:
    """Thay toàn bộ danh mục của phiên bằng dữ liệu đã lưu. Kiểm tra hợp lệ trước khi ghi."""
    if isinstance(payload, (str, bytes)):
        if len(payload) > MAX_BYTES:
            raise PortfolioInputError("File danh mục quá lớn.")
        payload = json.loads(payload)
    if not isinstance(payload, dict) or payload.get("version") != VERSION:
        raise PortfolioInputError("File danh mục không đúng định dạng AURA.")
    watched = []
    for w in payload.get("watched") or []:
        watched.append((normalize_symbol(w.get("symbol", "")), str(w.get("added_at") or "")))
    trades = []
    for t in payload.get("trades") or []:
        row = {k: t.get(k) for k in TRADE_FIELDS}
        row["symbol"] = normalize_symbol(row["symbol"])
        row["side"] = str(row["side"]).upper()
        row["quantity"] = int(row["quantity"])
        if row["side"] not in ("BUY", "SELL") or row["quantity"] <= 0:
            raise PortfolioInputError("Giao dịch trong file không hợp lệ.")
        trades.append(row)
    _snapshot(trades)  # sổ lệnh phải hợp lệ (không bán quá số đang có)
    with connect(db) as conn:
        conn.execute("DELETE FROM watched")
        conn.execute("DELETE FROM trades")
        conn.executemany("INSERT OR IGNORE INTO watched(symbol, added_at) VALUES(?,?)", watched)
        conn.executemany(
            "INSERT INTO trades(" + ",".join(TRADE_FIELDS) + ") VALUES (" + ",".join("?" * len(TRADE_FIELDS)) + ")",
            [tuple(r[k] for k in TRADE_FIELDS) for r in trades])
    return len(trades)


def sync_with_browser(db: Path, state, *, js_eval=None) -> str:
    """Gọi ở cuối mỗi lần chạy trang. Trả về trạng thái: 'pending' | 'restored' | 'saved' | 'unchanged' | 'off'.

    1) Lần đầu trong phiên: đọc localStorage; có dữ liệu → nhập vào SQLite của phiên rồi rerun.
    2) Các lần sau: nếu danh mục thay đổi → ghi lại localStorage.
    Chưa đọc xong thì KHÔNG ghi, để không đè dữ liệu cũ bằng danh mục rỗng.
    """
    if js_eval is None:
        try:
            from streamlit_js_eval import streamlit_js_eval as js_eval
        except ImportError:
            return "off"
    if not state.get("_aura_pf_loaded"):
        raw = js_eval(js_expressions=f"localStorage.getItem('{STORAGE_KEY}') ?? '{_EMPTY}'",
                      key="aura_pf_load")
        if raw is None:
            return "pending"
        state["_aura_pf_loaded"] = True
        if raw != _EMPTY:
            try:
                import_state(db, raw)
                state["_aura_pf_saved_hash"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                return "restored"
            except (PortfolioInputError, ValueError, TypeError, KeyError):
                state["_aura_pf_error"] = "Dữ liệu danh mục trong trình duyệt bị lỗi; đã bỏ qua."
    text = to_text(export_state(db))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest == state.get("_aura_pf_saved_hash"):
        return "unchanged"
    js_eval(js_expressions=f"localStorage.setItem('{STORAGE_KEY}', {json.dumps(text)}); 'ok'",
            key=f"aura_pf_save_{digest[:16]}")
    state["_aura_pf_saved_hash"] = digest
    return "saved"
