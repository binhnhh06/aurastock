"""Nhật ký vận hành AURA (giờ Việt Nam) và bộ giới hạn tần suất gọi SSI REST.

- Log ghi ra stderr (Streamlit Cloud hiển thị trong "Manage app → Logs") và,
  nếu ghi được, file logs/aura.log (thư mục logs/ đã nằm trong .gitignore).
- Không bao giờ ghi API key, secret, token hay nội dung request vào log.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_FORMAT = "%(asctime)s+07:00 | %(levelname)s | %(name)s | %(message)s"


class _VNFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):  # noqa: N802 (API của logging)
        return datetime.fromtimestamp(record.created, VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def get_logger(name: str = "aura") -> logging.Logger:
    """Trả về logger dùng chung; chỉ gắn handler một lần cho mỗi tiến trình."""
    root = logging.getLogger("aura")
    if not root.handlers:
        root.setLevel(os.getenv("AURA_LOG_LEVEL", "INFO").upper())
        fmt = _VNFormatter(_FORMAT)
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        root.addHandler(stream)
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(LOG_DIR / "aura.log", encoding="utf-8")
            file_handler.setFormatter(fmt)
            root.addHandler(file_handler)
        except OSError:
            pass  # Hosting chỉ đọc: vẫn còn log ra stderr.
        root.propagate = False
    return root if name == "aura" else root.getChild(name.removeprefix("aura."))


class RateLimiter:
    """Bảo đảm khoảng cách tối thiểu giữa hai lần gọi REST (an toàn đa luồng).

    Mặc định 1 giây/lần, chỉnh bằng biến môi trường SSI_MIN_INTERVAL_SEC.
    Ưu tiên WebSocket cho dữ liệu thời gian thực thay vì gọi REST dồn dập.
    """

    def __init__(self, min_interval: float | None = None, clock=time.monotonic, sleep=time.sleep):
        if min_interval is None:
            try:
                min_interval = float(os.getenv("SSI_MIN_INTERVAL_SEC", "1.0"))
            except ValueError:
                min_interval = 1.0
        self.min_interval = max(0.0, min_interval)
        self._clock, self._sleep = clock, sleep
        self._last = None
        self._lock = threading.Lock()

    def wait(self) -> float:
        """Chờ nếu cần; trả về số giây đã chờ."""
        with self._lock:
            now = self._clock()
            waited = 0.0
            if self._last is not None:
                waited = max(0.0, self.min_interval - (now - self._last))
                if waited:
                    self._sleep(waited)
            self._last = self._clock()
            return waited


SSI_REST_LIMITER = RateLimiter()
