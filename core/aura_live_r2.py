"""Giá realtime cho bản online qua Cloudflare R2 (CHỈ HIỂN THỊ).

Luồng: máy cá nhân chạy scripts/ssi_live_worker.py (giữ SSI WebSocket) → mỗi vài giây
ghi live_market.json lên R2 (khóa ghi chỉ nằm trên máy cá nhân) → Streamlit Cloud đọc
bằng khóa R2 chỉ-đọc, cache vài giây.

Không tham gia tính MA/RSI/điểm/xếp hạng: mọi chỉ báo vẫn tính trên nến SSI EOD.
Không ghi key/secret/URL vào log.
"""
from __future__ import annotations

import json
import os
import threading
import time

from core.aura_log import get_logger

log = get_logger("aura.live_r2")
_LOCK = threading.Lock()
_CACHE = {"at": 0.0, "data": {}}
MAX_BYTES = 2 * 1024 * 1024


def _ttl() -> float:
    try:
        return max(1.0, float(os.getenv("AURA_LIVE_R2_CACHE_SEC", "5")))
    except ValueError:
        return 5.0


def live_key() -> str:
    from core.aura_r2_market import prefix
    return f"{prefix()}/live/live_market.json"


def enabled() -> bool:
    try:
        from core.aura_r2_market import enabled as r2_enabled
        return bool(r2_enabled())
    except Exception:  # noqa: BLE001 - thiếu boto3/secrets thì coi như tắt
        return False


def push_snapshot(state: dict, cli=None) -> bool:
    """Worker gọi: ghi đè một object JSON nhỏ (1 thao tác Class A)."""
    from core.aura_r2_market import client, setting
    body = json.dumps(state, ensure_ascii=False, allow_nan=False, default=str).encode("utf-8")
    if len(body) > MAX_BYTES:
        log.warning("Snapshot realtime quá lớn (%d bytes), bỏ qua lần đẩy này", len(body))
        return False
    (cli or client()).put_object(Bucket=setting("AURA_R2_BUCKET"), Key=live_key(), Body=body,
                                 ContentType="application/json", CacheControl="no-store")
    return True


def fetch_snapshot(cli=None, *, now=None) -> dict:
    """App gọi: đọc snapshot từ R2, cache AURA_LIVE_R2_CACHE_SEC giây; lỗi → {}."""
    now = time.monotonic() if now is None else now
    with _LOCK:
        if now - _CACHE["at"] < _ttl():
            return _CACHE["data"]
        _CACHE["at"] = now
    data = {}
    if cli is not None or enabled():
        try:
            from core.aura_r2_market import client, setting
            obj = (cli or client()).get_object(Bucket=setting("AURA_R2_BUCKET"), Key=live_key())
            raw = obj["Body"].read(MAX_BYTES + 1)
            if len(raw) <= MAX_BYTES:
                parsed = json.loads(raw.decode("utf-8"))
                data = parsed if isinstance(parsed, dict) else {}
        except Exception as exc:  # noqa: BLE001 - mất kết nối/không có object: hiển thị EOD
            log.info("Chưa đọc được giá realtime từ R2: %s", type(exc).__name__)
    with _LOCK:
        _CACHE["data"] = data
    return data


class R2Pusher:
    """Luồng nền trong worker: đẩy bản sao trạng thái mỗi `interval` giây."""

    def __init__(self, get_state, interval: float | None = None, push=push_snapshot):
        if interval is None:
            try:
                interval = float(os.getenv("AURA_LIVE_R2_PUSH_SEC", "5"))
            except ValueError:
                interval = 5.0
        self.interval = max(2.0, interval)
        self._get_state, self._push = get_state, push
        self._stop = threading.Event()
        self.pushed = 0
        self.failures = 0

    def run_once(self) -> bool:
        try:
            ok = bool(self._push(self._get_state()))
        except Exception as exc:  # noqa: BLE001 - lỗi mạng không được làm rớt WebSocket
            self.failures += 1
            if self.failures == 1 or self.failures % 20 == 0:
                log.warning("Đẩy snapshot lên R2 lỗi (%d lần): %s", self.failures, type(exc).__name__)
            return False
        if ok:
            self.pushed += 1
            if self.failures:
                log.info("Đẩy snapshot R2 đã phục hồi")
                self.failures = 0
        return ok

    def _loop(self):
        while not self._stop.wait(self.interval):
            self.run_once()

    def start(self):
        threading.Thread(target=self._loop, name="aura-r2-pusher", daemon=True).start()
        return self

    def stop(self):
        self._stop.set()
