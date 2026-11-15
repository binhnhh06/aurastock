
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from ssi_sdk import Auth, Config, Data
from ssi_sdk.enums import Timeframe


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def get_ssi_config():
    """Đọc thông tin xác thực từ biến môi trường."""
    client_id = os.getenv("SSI_CLIENT_ID")
    api_key = os.getenv("SSI_API_KEY")
    api_secret = os.getenv("SSI_API_SECRET")

    missing = [
        name for name, value in {
            "SSI_CLIENT_ID": client_id,
            "SSI_API_KEY": api_key,
            "SSI_API_SECRET": api_secret,
        }.items()
        if not value or value.startswith("DIEN_")
    ]

    if missing:
        raise RuntimeError(
            "Thiếu cấu hình SSI: " + ", ".join(missing)
        )

    return Config(
        client_id=client_id,
        api_key=api_key,
        api_secret=api_secret,
    )


def get_ssi_ohlcv(
    symbol="SSI",
    from_date="2026/09/01 00:00:00",
    to_date="2026/11/09 23:59:59",
):
    """
    Lấy dữ liệu OHLCV ngày qua SSI FastConnect V3.
    Chỉ đọc dữ liệu, không thực hiện giao dịch.
    """
    config = get_ssi_config()

    with Auth(config) as auth:
        auth.authenticate()

        with Data(auth) as data:
            candles = data.market_data.get_ohlc_all(
                symbol=symbol.upper(),
                timeframe=Timeframe.DAY_1,
                from_date=from_date,
                to_date=to_date,
                ascending=True,
            )

    columns = [
        "symbol", "time", "open",
        "high", "low", "close", "volume"
    ]

    records = []

    for candle in candles:
        records.append({
            "symbol": candle.symbol,
            "time": candle.trading_date,
            "open": candle.open_price,
            "high": candle.high_price,
            "low": candle.low_price,
            "close": candle.close_price,
            "volume": candle.volume,
        })

    df = pd.DataFrame(records, columns=columns)

    if df.empty:
        return df

    # Chuẩn hóa kiểu dữ liệu
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Loại bản ghi lặp theo mã và thời điểm
    df = df.drop_duplicates(
        subset=["symbol", "time"],
        keep="last"
    ).reset_index(drop=True)

    return df
