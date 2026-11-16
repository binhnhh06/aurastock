"""Lưu lịch sử giá SSI WebSocket theo ngày để làm bằng chứng thu thập dữ liệu (≥ 5–10 phiên).

Worker gọi `LiveArchive.capture(state)` định kỳ (mặc định mỗi 60 giây). Mỗi lần chỉ ghi
những mã có tick MỚI kể từ lần ghi trước → không nhân bản dữ liệu cũ.
File: data/ssi_cache/live_archive/YYYY-MM-DD.csv (giờ Việt Nam), sự kiện kết nối ở
YYYY-MM-DD_events.csv. Dữ liệu này KHÔNG dùng để tính chỉ báo/điểm.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "data" / "ssi_cache" / "live_archive"
FIELDS = ["captured_at", "kind", "symbol", "price", "quantity", "change", "change_percent",
          "trading_time", "received_at", "connection"]
EVENT_FIELDS = ["at", "connection", "detail"]


def _append(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


class LiveArchive:
    def __init__(self, folder: Path = ARCHIVE_DIR):
        self.folder = Path(folder)
        self._seen: dict[tuple[str, str], str] = {}
        self._last_conn = None

    def capture(self, state: dict, now: datetime | None = None) -> int:
        """Ghi các tick mới trong `state` (snapshot của worker). Trả về số dòng đã ghi."""
        now = (now or datetime.now(timezone.utc)).astimezone(VN)
        conn = str(state.get("connection", ""))
        if conn != self._last_conn:
            self.event(conn, "", now)
        rows = []
        for kind, group in (("STOCK", state.get("quotes") or {}), ("INDEX", state.get("indices") or {})):
            for symbol, rec in group.items():
                if not isinstance(rec, dict) or rec.get("price") in (None, ""):
                    continue
                received = str(rec.get("received_at") or "")
                if self._seen.get((kind, symbol)) == received:
                    continue  # chưa có tick mới
                self._seen[(kind, symbol)] = received
                rows.append({"captured_at": now.isoformat(timespec="seconds"), "kind": kind,
                             "symbol": symbol, "connection": conn, **rec})
        if rows:
            _append(self.folder / f"{now:%Y-%m-%d}.csv", FIELDS, rows)
        return len(rows)

    def event(self, connection: str, detail: str = "", now: datetime | None = None):
        now = (now or datetime.now(timezone.utc)).astimezone(VN)
        self._last_conn = connection
        _append(self.folder / f"{now:%Y-%m-%d}_events.csv", EVENT_FIELDS,
                [{"at": now.isoformat(timespec="seconds"), "connection": connection, "detail": detail}])


def summarize(folder: Path = ARCHIVE_DIR):
    """Tóm tắt dữ liệu đã thu theo ngày: số dòng, số mã, phút có dữ liệu, sự kiện mất kết nối."""
    import pandas as pd
    folder = Path(folder)
    out = []
    for f in sorted(folder.glob("????-??-??.csv")):
        try:
            d = pd.read_csv(f, encoding="utf-8-sig")
        except (OSError, ValueError, pd.errors.EmptyDataError):
            continue
        if d.empty:
            continue
        t = pd.to_datetime(d["captured_at"], errors="coerce")
        minutes = t.dt.floor("min").nunique()
        stock = d.loc[d["kind"].eq("STOCK")]
        ev = folder / f"{f.stem}_events.csv"
        disconnects = 0
        if ev.exists():
            e = pd.read_csv(ev, encoding="utf-8-sig")
            disconnects = int(e["connection"].astype(str).str.contains("DISCONNECTED|ERROR", regex=True).sum())
        out.append({
            "Ngày": f.stem, "Số dòng": len(d), "Số mã cổ phiếu": stock["symbol"].nunique(),
            "Số chỉ số": d.loc[d["kind"].eq("INDEX"), "symbol"].nunique(),
            "Phút có dữ liệu": int(minutes),
            "Từ": t.min().strftime("%H:%M") if t.notna().any() else "",
            "Đến": t.max().strftime("%H:%M") if t.notna().any() else "",
            "Giá trùng/không hợp lệ": int(pd.to_numeric(d["price"], errors="coerce").le(0).sum()
                                         + d.duplicated(["kind", "symbol", "received_at"]).sum()),
            "Lần mất kết nối": disconnects,
        })
    return pd.DataFrame(out)
