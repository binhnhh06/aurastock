
import os
import time
import argparse
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv
from ssi_sdk import Auth, Config, Data
from ssi_sdk.enums import Timeframe

# =====================================================
# BATDAY SSI - HISTORICAL DATA DOWNLOADER
# SSI FastConnect V3 / Python SDK 3.3.2
# =====================================================

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)

CACHE = ROOT / "data" / "ssi_cache"
OUTPUT = CACHE / "ohlcv"
OUTPUT.mkdir(parents=True, exist_ok=True)

SYMBOLS_FILE = CACHE / "vn30_symbols.csv"

# Khoang thoi gian co dinh de tai lap nghien cuu
FROM_DATE = "2024/01/01 00:00:00"
TO_DATE = "2026/11/09 23:59:59"

COLUMNS = [
    "symbol", "date", "open", "high",
    "low", "close", "volume"
]


def get_config():
    keys = [
        "SSI_CLIENT_ID",
        "SSI_API_KEY",
        "SSI_API_SECRET",
    ]

    missing = [k for k in keys if not os.getenv(k, "").strip()]
    if missing:
        raise RuntimeError("Thieu cau hinh: " + ", ".join(missing))

    return Config(
        client_id=os.environ["SSI_CLIENT_ID"].strip(),
        api_key=os.environ["SSI_API_KEY"].strip(),
        api_secret=os.environ["SSI_API_SECRET"].strip(),
    )


def load_symbols():
    if not SYMBOLS_FILE.exists():
        raise FileNotFoundError("Khong tim thay vn30_symbols.csv")

    df = pd.read_csv(SYMBOLS_FILE, dtype=str)

    if "symbol" not in df.columns:
        raise ValueError("Thieu cot symbol")

    symbols = (
        df["symbol"]
        .dropna()
        .str.strip()
        .str.upper()
        .drop_duplicates()
        .tolist()
    )

    if not symbols:
        raise ValueError("Danh sach co phieu rong")

    return symbols


def normalize_ohlcv(bars, symbol):
    rows = []

    for bar in bars:
        rows.append({
            "symbol": symbol,
            "date": getattr(bar, "trading_date", None),
            "open": getattr(bar, "open_price", None),
            "high": getattr(bar, "high_price", None),
            "low": getattr(bar, "low_price", None),
            "close": getattr(bar, "close_price", None),
            "volume": getattr(bar, "volume", None),
        })

    raw_count = len(rows)
    df = pd.DataFrame(rows, columns=COLUMNS)

    if df.empty:
        return df, {
            "raw_rows": 0,
            "duplicate_rows": 0,
            "invalid_rows": 0,
            "valid_rows": 0,
        }

    df["date"] = pd.to_datetime(
        df["date"], errors="coerce"
    )

    numeric_cols = [
        "open", "high", "low", "close", "volume"
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(
            df[col], errors="coerce"
        )

    # Kiem tra logic gia OHLC
    invalid = (
        df["date"].isna()
        | df[numeric_cols].isna().any(axis=1)
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (df["volume"] < 0)
        | (df["high"] < df["low"])
        | (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
    )

    invalid_count = int(invalid.sum())

    # Bao cao so dong loi, chi giu du lieu hop le
    df = df.loc[~invalid].copy()

    duplicate_count = int(
        df.duplicated(["symbol", "date"]).sum()
    )

    df = (
        df.drop_duplicates(
            ["symbol", "date"], keep="last"
        )
        .sort_values("date")
        .reset_index(drop=True)
    )

    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    stats = {
        "raw_rows": raw_count,
        "duplicate_rows": duplicate_count,
        "invalid_rows": invalid_count,
        "valid_rows": len(df),
    }

    return df, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--all",
        action="store_true",
        help="Tai tat ca ma trong danh sach"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="So ma thu nghiem (mac dinh 3)"
    )
    args = parser.parse_args()

    symbols = load_symbols()

    if not args.all:
        symbols = symbols[:max(1, args.limit)]

    print("=" * 60)
    print("BATDAY SSI - DOWNLOAD HISTORICAL OHLCV")
    print("=" * 60)
    print("Khoang:", FROM_DATE, "den", TO_DATE)
    print("So ma can xu ly:", len(symbols))

    report = []

    with Auth(get_config()) as auth:
        auth.authenticate()
        print("[OK] SSI Authentication")

        with Data(auth) as data:
            for i, symbol in enumerate(symbols, 1):
                print(f"\n[{i}/{len(symbols)}] {symbol}")

                filepath = OUTPUT / f"{symbol}.csv"

                # Khong tai lai file da co neu khong can
                if filepath.exists() and filepath.stat().st_size > 0:
                    cached = pd.read_csv(filepath)

                    print("[CACHE] Da co du lieu:", len(cached))

                    report.append({
                        "symbol": symbol,
                        "status": "CACHED",
                        "valid_rows": len(cached),
                        "invalid_rows": None,
                        "duplicate_rows": None,
                        "first_date": (
                            cached["date"].iloc[0]
                            if len(cached) else None
                        ),
                        "last_date": (
                            cached["date"].iloc[-1]
                            if len(cached) else None
                        ),
                    })
                    continue

                try:
                    bars = data.market_data.get_ohlc_all(
                        symbol=symbol,
                        timeframe=Timeframe.DAY_1,
                        from_date=FROM_DATE,
                        to_date=TO_DATE,
                        size=1000,
                        ascending=True,
                    )

                    df, stats = normalize_ohlcv(
                        bars or [], symbol
                    )

                    if df.empty:
                        print("[WARNING] Khong co du lieu hop le")
                        status = "EMPTY"
                    else:
                        # Ghi an toan, khong de file CSV do dang
                        temp_file = filepath.with_suffix(".tmp")
                        df.to_csv(
                            temp_file,
                            index=False,
                            encoding="utf-8-sig",
                        )
                        temp_file.replace(filepath)

                        print("[OK] So phien:", len(df))
                        print(
                            "Khoang:",
                            df["date"].iloc[0],
                            "->",
                            df["date"].iloc[-1],
                        )

                        if len(df) < 200:
                            print(
                                "[WARNING] Chua du 200 phien "
                                "de tinh MA200"
                            )

                        status = "OK"

                    report.append({
                        "symbol": symbol,
                        "status": status,
                        **stats,
                        "first_date": (
                            df["date"].iloc[0]
                            if len(df) else None
                        ),
                        "last_date": (
                            df["date"].iloc[-1]
                            if len(df) else None
                        ),
                    })

                except Exception as exc:
                    print("[ERROR]", type(exc).__name__)
                    print(
                        "HTTP:",
                        getattr(exc, "status_code", None),
                        "Code:",
                        getattr(exc, "code", None),
                    )

                    report.append({
                        "symbol": symbol,
                        "status": "ERROR",
                        "valid_rows": 0,
                        "error_type": type(exc).__name__,
                    })

                # Nghi giua cac ma, tranh goi API lien tuc
                time.sleep(0.6)

    summary = pd.DataFrame(report)

    summary.to_csv(
        CACHE / "ohlcv_quality.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print("\n" + "=" * 60)
    print("BAO CAO CHAT LUONG DU LIEU")
    print("=" * 60)

    print(
        summary[
            ["symbol", "status", "valid_rows"]
        ].to_string(index=False)
    )

    print("\nFile luu tai:", OUTPUT)
    print("Bao cao:", CACHE / "ohlcv_quality.csv")
    print(
        "Thoi diem kiem tra:",
        datetime.now(
            ZoneInfo("Asia/Ho_Chi_Minh")
        ).isoformat()
    )


if __name__ == "__main__":
    main()
