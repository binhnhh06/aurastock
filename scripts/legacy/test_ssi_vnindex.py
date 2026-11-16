import sys as _aura_sys
from pathlib import Path as _AuraPath
_aura_sys.path.insert(0, str(_AuraPath(__file__).resolve().parents[2]))  # gốc dự án (file đã chuyển vào scripts/legacy)


import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from ssi_sdk import Auth, Config, Data
from ssi_sdk.enums import Timeframe

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)

OUTPUT = ROOT / "data" / "ssi_cache"
OUTPUT.mkdir(parents=True, exist_ok=True)


def show_error(exc):
    print("Loai loi:", type(exc).__name__)
    print("HTTP:", getattr(exc, "status_code", None))
    print("SSI code:", getattr(exc, "code", None))


def main():
    print("=" * 55)
    print("BATDAY SSI - KIEM TRA DU LIEU VNINDEX")
    print("=" * 55)

    config = Config(
        client_id=os.environ["SSI_CLIENT_ID"].strip(),
        api_key=os.environ["SSI_API_KEY"].strip(),
        api_secret=os.environ["SSI_API_SECRET"].strip(),
    )

    with Auth(config) as auth:
        auth.authenticate()
        print("[OK] Authentication")

        with Data(auth) as data:

            # 1. Lay thong tin VNINDEX
            try:
                print("\n[1] VNINDEX SUMMARY")

                summary = (
                    data.market_data
                    .get_index_summary("VNINDEX")
                )

                if summary is None:
                    print("Khong co summary.")
                else:
                    fields = [
                        "index_value",
                        "index_change",
                        "index_change_percent",
                        "total_match",
                        "total_match_value",
                        "total_advance_stock",
                        "total_decline_stock",
                    ]

                    for field in fields:
                        print(
                            field,
                            ":",
                            getattr(summary, field, None)
                        )

            except Exception as exc:
                show_error(exc)

            # 2. Thu lay nen lich su VNINDEX
            try:
                print("\n[2] VNINDEX HISTORICAL OHLC")

                bars = data.market_data.get_ohlc_all(
                    symbol="VNINDEX",
                    timeframe=Timeframe.DAY_1,
                    from_date="2025/01/01 00:00:00",
                    to_date="2026/11/09 23:59:59",
                    size=1000,
                    ascending=True,
                )

                rows = []

                for bar in bars or []:
                    rows.append({
                        "time": getattr(
                            bar, "trading_date", None
                        ),
                        "open": getattr(
                            bar, "open_price", None
                        ),
                        "high": getattr(
                            bar, "high_price", None
                        ),
                        "low": getattr(
                            bar, "low_price", None
                        ),
                        "close": getattr(
                            bar, "close_price", None
                        ),
                        "volume": getattr(
                            bar, "volume", None
                        ),
                    })

                df = pd.DataFrame(rows)

                if df.empty:
                    print("SSI khong tra ve OHLC VNINDEX.")
                    return

                df["time"] = pd.to_datetime(
                    df["time"], errors="coerce"
                )

                cols = [
                    "open", "high", "low",
                    "close", "volume"
                ]

                for col in cols:
                    df[col] = pd.to_numeric(
                        df[col], errors="coerce"
                    )

                invalid = (
                    df.isna().any(axis=1)
                    | (df[["open", "high", "low", "close"]] <= 0)
                      .any(axis=1)
                    | (df["volume"] < 0)
                    | (df["high"] < df[["open", "low", "close"]].max(axis=1))
                    | (df["low"] > df[["open", "high", "close"]].min(axis=1))
                )

                print("So nen nhan duoc:", len(df))
                print("So nen khong hop le:", int(invalid.sum()))
                print(
                    "Ngay trung:",
                    int(df["time"].duplicated().sum())
                )

                if invalid.any() or df["time"].duplicated().any():
                    print("Can ra soat, chua luu du lieu.")
                    return

                df = df.sort_values("time")

                if len(df) < 60:
                    print("Chua du 60 phien, khong luu.")
                    return

                df.to_csv(
                    OUTPUT / "vnindex_ohlcv_ssi.csv",
                    index=False,
                    encoding="utf-8-sig",
                )

                print("\n5 phien gan nhat:")
                print(df.tail(5).to_string(index=False))
                print("\n[OK] Da luu VNINDEX SSI")

            except Exception as exc:
                print("Khong lay duoc OHLC lich su.")
                show_error(exc)


if __name__ == "__main__":
    main()
