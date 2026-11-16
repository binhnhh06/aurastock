"""Adapter đọc giá SSI FastConnect V3, tương thích đầu vào giá của BatDayStox.

Ưu tiên file CSV đã tải tại data/ssi_cache/ohlcv/{SYMBOL}.csv.
Nếu chưa có cache, gọi SSI SDK V3 để lấy dữ liệu lịch sử rồi lưu lại.
Không dùng API giao dịch. Không đưa thông tin xác thực vào source code.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from core.aura_log import SSI_REST_LIMITER, get_logger

log = get_logger("aura.ssi")

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "ssi_cache" / "ohlcv"
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PRICE_COLS = ("open", "high", "low", "close", "volume")


def _today():
    return datetime.now(VN_TZ).date()


def _validate_symbol(symbol):
    symbol = str(symbol).strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,12}", symbol):
        raise ValueError("Mã chứng khoán không hợp lệ")
    return symbol


def _normalize(raw, symbol):
    """Chuẩn hóa định dạng SSI CSV -> time/open/high/low/close/volume.

    SSI có giá VND và khối lượng cổ phiếu. KHÔNG tự nhân giá 1000.
    Không tự điều chỉnh sự kiện doanh nghiệp.
    """
    if raw is None or raw.empty:
        raise ValueError(f"SSI không có OHLCV cho {symbol}")
    df = raw.copy()
    if "date" in df and "time" not in df:
        df = df.rename(columns={"date": "time"})
    required = ["time", *PRICE_COLS]
    missing = sorted(set(required).difference(df.columns))
    if missing:
        raise ValueError("SSI thiếu cột: " + ", ".join(missing))
    if "symbol" in df:
        bad_symbol = ~df["symbol"].astype(str).str.strip().str.upper().eq(symbol)
        if bad_symbol.any():
            raise ValueError("Dữ liệu SSI chứa mã khác mã yêu cầu")
    # Thời gian nến ngày là thời gian giao dịch VN, không cần UTC conversion.
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    for c in PRICE_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df[required].isna().any().any():
        raise ValueError("Dữ liệu SSI có ngày/giá/khối lượng bị thiếu hoặc sai kiểu")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Dữ liệu SSI chứa giá không dương")
    if (df["volume"] < 0).any():
        raise ValueError("Dữ liệu SSI có khối lượng âm")
    if (df["high"] < df[["open", "low", "close"]].max(axis=1)).any():
        raise ValueError("Dữ liệu SSI có giá cao nhất không hợp lệ")
    if (df["low"] > df[["open", "high", "close"]].min(axis=1)).any():
        raise ValueError("Dữ liệu SSI có giá thấp nhất không hợp lệ")
    # Với dữ liệu hàng ngày, trùng ngày phải được nhận diện thay vì âm thầm mất dữ liệu.
    df["time"] = df["time"].dt.normalize()
    if df["time"].duplicated().any():
        raise ValueError("Dữ liệu SSI trùng phiên, cần rà soát nguồn")
    df = df.sort_values("time").reset_index(drop=True)
    return df[["time", *PRICE_COLS]].copy()


def _get_credentials():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass
    keys = ("SSI_CLIENT_ID", "SSI_API_KEY", "SSI_API_SECRET")
    missing = [k for k in keys if not os.getenv(k, "").strip()]
    if missing:
        raise RuntimeError("Thiếu thông tin SSI (" + ", ".join(missing) + ")")
    return {k: os.environ[k].strip() for k in keys}


def _fetch_live(symbol, days):
    """Chỉ gọi endpoint dữ liệu nến SSI V3, không gọi trading service."""
    try:
        from ssi_sdk import Auth, Config, Data
        from ssi_sdk.enums import Timeframe
    except ImportError as exc:
        raise RuntimeError("Thiếu ssi-sdk: pip install ssi-sdk") from exc

    cred = _get_credentials()
    config = Config(
        client_id=cred["SSI_CLIENT_ID"],
        api_key=cred["SSI_API_KEY"],
        api_secret=cred["SSI_API_SECRET"],
    )
    today = _today()
    since = today - timedelta(days=max(int(days), 400))
    SSI_REST_LIMITER.wait()  # giới hạn tần suất gọi REST
    t0 = time.monotonic()
    try:
        with Auth(config) as auth:
            auth.authenticate()
            with Data(auth) as data:
                bars = data.market_data.get_ohlc_all(
                    symbol=symbol,
                    timeframe=Timeframe.DAY_1,
                    from_date=since.strftime("%Y/%m/%d 00:00:00"),
                    to_date=today.strftime("%Y/%m/%d 23:59:59"),
                    size=1000,
                    ascending=True,
                )
    except Exception as exc:
        # Không in exception body, vì backend/SDK đôi khi chứa chi tiết request.
        status = getattr(exc, "status_code", None)
        code = getattr(exc, "code", None)
        log.error("SSI DailyOhlc %s thất bại: %s HTTP=%s code=%s", symbol, type(exc).__name__, status, code)
        raise RuntimeError(
            f"SSI Market Data thất bại: {type(exc).__name__}, HTTP={status}, code={code}"
        ) from None
    rows = [{
        "symbol": symbol,
        "date": getattr(bar, "trading_date", None),
        "open": getattr(bar, "open_price", None),
        "high": getattr(bar, "high_price", None),
        "low": getattr(bar, "low_price", None),
        "close": getattr(bar, "close_price", None),
        "volume": getattr(bar, "volume", None),
    } for bar in (bars or [])]
    df = _normalize(pd.DataFrame(rows), symbol)
    log.info("SSI DailyOhlc %s: %d phiên, đến %s (%.1fs)", symbol, len(df),
             df["time"].iloc[-1].date(), time.monotonic() - t0)
    # Lưu cache đúng cấu trúc được dùng trong scripts/legacy/download_ssi_history.py.
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    csv = CACHE_DIR / f"{symbol}.csv"
    temp = csv.with_suffix(".tmp")
    to_save = df.rename(columns={"time": "date"}).copy()
    to_save.insert(0, "symbol", symbol)
    try:
        to_save.to_csv(temp, index=False, encoding="utf-8-sig")
        temp.replace(csv)
    except OSError:
        # Cache chỉ là tối ưu, vẫn trả dữ liệu API nếu thư mục readonly.
        if temp.exists():
            temp.unlink(missing_ok=True)
    return df


def lay_gia_ssi(symbol, so_ngay=730, refresh=False):
    """Trả về DataFrame theo đúng contract lay_gia gốc của BatDayStox.

    refresh=False: ưu tiên cache có sẵn. Nếu không có cache sẽ gọi SSI live.
    refresh=True: cố làm mới qua SSI; nếu lỗi và có cache thì dùng cache,
    đồng thời gắn warning trong DataFrame.attrs.
    """
    symbol = _validate_symbol(symbol)
    so_ngay = int(so_ngay)
    if so_ngay <= 0:
        raise ValueError("so_ngay phải lớn hơn 0")
    csv = CACHE_DIR / f"{symbol}.csv"
    cached = None
    cached_error = None
    if csv.is_file():
        try:
            cached = _normalize(pd.read_csv(csv), symbol)
        except Exception as exc:
            cached_error = type(exc).__name__
            log.warning("Cache %s không hợp lệ: %s", csv.name, cached_error)

    if refresh or cached is None:
        try:
            full = _fetch_live(symbol, so_ngay)
            mode = "SSI_API"
            warning = ""
        except Exception as exc:
            if cached is None:
                raise RuntimeError(
                    f"Không thể lấy OHLCV của {symbol} từ SSI "
                    f"(cache={cached_error or 'không có'}, {type(exc).__name__})"
                ) from None
            full = cached
            mode = "SSI_CACHE"
            warning = "Không cập nhật được SSI, đang dùng dữ liệu cache."
            log.warning("%s: SSI lỗi (%s), dùng cache đến %s", symbol, type(exc).__name__,
                        cached["time"].iloc[-1].date())
    else:
        full = cached
        mode = "SSI_CACHE"
        warning = "Đang đọc dữ liệu SSI đã lưu; chưa làm mới trực tiếp từ API."

    cutoff = pd.Timestamp(_today() - timedelta(days=so_ngay))
    data = full[(full["time"] >= cutoff) &
                (full["time"] <= pd.Timestamp(_today()))].copy()
    if len(data) < 60:
        raise ValueError(
            f"{symbol} chỉ có {len(data)} phiên trong {so_ngay} ngày; "
            "cần tối thiểu 60 phiên cho bộ lọc gốc"
        )
    data.attrs["nguon_gia"] = "SSI FastConnect V3"
    data.attrs["che_do"] = mode
    data.attrs["gia_cap_nhat_den"] = data["time"].iloc[-1].strftime("%Y-%m-%d")
    data.attrs["canh_bao"] = warning
    data.attrs["gia_don_vi"] = "VND"
    data.attrs["gia_dieu_chinh"] = "chưa xác minh"
    return data.reset_index(drop=True)
