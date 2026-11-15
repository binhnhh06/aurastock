"""Bổ sung lịch sử nến ngày SSI cũ cho MỘT mã, không thay đổi nguồn X10.

Sử dụng: python scripts/ssi_backfill_history.py FPT --years 10

Tải theo cửa sổ tối đa 700 ngày lịch, tránh giới hạn 1.000 nến / request.
Chỉ lấy giai đoạn trước file hiện có, ghép theo ngày và ghi atomically sau
khi mọi request thành công. Không truy cập dịch vụ đặt lệnh.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.ssi_fetch_symbol import from_ohlc, persist
from core.ssi_universe import validate_symbol

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
OUT = ROOT / "data" / "ssi_cache" / "ohlcv"


def backfill(symbol: str, years: int) -> None:
    from ssi_sdk import Auth, Config, Data
    from ssi_sdk.enums import Timeframe

    symbol = validate_symbol(symbol, ROOT)
    now = datetime.now(TZ)
    target = now.date() if (now.hour, now.minute) >= (15, 30) else (now - timedelta(days=1)).date()
    start = (pd.Timestamp(target) - pd.DateOffset(years=years)).date()
    csv = OUT / f"{symbol}.csv"
    last_old_date = None
    if csv.is_file():
        old = pd.to_datetime(pd.read_csv(csv, usecols=["date"])["date"], errors="coerce").dropna()
        if not old.empty:
            oldest = old.min().date()
            last_old_date = oldest - timedelta(days=1)
    if last_old_date is not None and last_old_date < start:
        print(f"{symbol}: dữ liệu đã có từ {oldest}; không cần bổ sung trước {start}.")
        return
    end = min(target, last_old_date) if last_old_date is not None else target
    if end < start:
        print(f"{symbol}: không còn giai đoạn cũ cần tải.")
        return

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass
    keys = ("SSI_CLIENT_ID", "SSI_API_KEY", "SSI_API_SECRET")
    if any(not os.environ.get(k) for k in keys):
        raise RuntimeError("Thiếu thông tin SSI trong .env")

    cfg = Config(client_id=os.environ["SSI_CLIENT_ID"],
                 api_key=os.environ["SSI_API_KEY"],
                 api_secret=os.environ["SSI_API_SECRET"])
    parts = []
    with Auth(cfg) as auth:
        auth.authenticate()
        with Data(auth) as client:
            window_start = start
            index = 0
            while window_start <= end:
                index += 1
                window_end = min(window_start + timedelta(days=699), end)
                print(f"[{index}] {symbol}: {window_start} -> {window_end}", flush=True)
                candles = client.market_data.get_ohlc_all(
                    symbol=symbol,
                    timeframe=Timeframe.DAY_1,
                    from_date=window_start.strftime("%Y/%m/%d 00:00:00"),
                    to_date=window_end.strftime("%Y/%m/%d 23:59:59"),
                    size=1000,
                    ascending=True,
                )
                fetched = from_ohlc(symbol, candles)
                if len(fetched) >= 1000:
                    raise RuntimeError("API đạt giới hạn 1000 nến trong một cửa sổ: không ghi dữ liệu thiếu.")
                print(f"     Nhận {len(fetched)} nến", flush=True)
                if not fetched.empty:
                    parts.append(fetched)
                window_start = window_end + timedelta(days=1)

    if not parts:
        print("SSI chưa trả nến lịch sử cũ hơn. File hiện có được giữ nguyên.")
        return
    new = pd.concat(parts, ignore_index=True)
    total = persist(symbol, new, csv, target)
    data = pd.read_csv(csv, usecols=["date"])
    dates = pd.to_datetime(data["date"], errors="coerce").dropna()
    print(f"HOÀN TẤT {symbol}: {total:,} nến ngày; từ {dates.min().date()} đến {dates.max().date()}.")
    print("Mở lại biểu đồ Năm/Tháng để xem lịch sử được bổ sung.")
    print("Lưu ý: dữ liệu SSI chưa được xác minh là giá đã điều chỉnh các sự kiện doanh nghiệp.")


def main():
    parser = argparse.ArgumentParser(description="Bổ sung nến SSI cũ hơn cho một cổ phiếu")
    parser.add_argument("symbol", help="Mã cổ phiếu (ví dụ FPT)")
    parser.add_argument("--years", type=int, default=10, help="Tải lùi bao nhiêu năm (3..20)")
    a = parser.parse_args()
    if not 3 <= a.years <= 20:
        parser.error("--years phải từ 3 đến 20")
    backfill(a.symbol, a.years)


if __name__ == "__main__":
    main()
