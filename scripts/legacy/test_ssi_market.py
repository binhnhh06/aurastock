import sys as _aura_sys
from pathlib import Path as _AuraPath
_aura_sys.path.insert(0, str(_AuraPath(__file__).resolve().parents[2]))  # gốc dự án (file đã chuyển vào scripts/legacy)


import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from ssi_sdk import Auth, Config, Data

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)

OUTPUT = ROOT / "data" / "ssi_cache"
OUTPUT.mkdir(parents=True, exist_ok=True)


def show_error(exc):
    # Không in token hoặc thông tin xác thực.
    print("Loai loi:", type(exc).__name__)
    print("HTTP:", getattr(exc, "status_code", None))
    print("SSI code:", getattr(exc, "code", None))


def main():
    print("=" * 55)
    print("BATDAY SSI - KIEM TRA MARKET DATA")
    print("=" * 55)

    config = Config(
        client_id=os.environ["SSI_CLIENT_ID"].strip(),
        api_key=os.environ["SSI_API_KEY"].strip(),
        api_secret=os.environ["SSI_API_SECRET"].strip(),
    )

    with Auth(config) as auth:
        auth.authenticate()
        print("\n[OK] Xac thuc thanh cong")

        with Data(auth) as data:

            # 1. Kiem tra danh sach VN30
            try:
                print("\n[1] Lay danh sach VN30...")
                vn30 = data.market_data.get_securities_info_by_index(
                    "VN30"
                )

                symbols = [
                    sec.symbol for sec in (vn30 or [])
                ]

                print("So ma nhan duoc:", len(symbols))
                print("Danh sach:", ", ".join(symbols))

                if symbols:
                    pd.DataFrame({
                        "symbol": symbols
                    }).to_csv(
                        OUTPUT / "vn30_symbols.csv",
                        index=False,
                        encoding="utf-8-sig",
                    )
                    print("[OK] Da luu vn30_symbols.csv")

            except Exception as exc:
                print("[LOI] Khong lay duoc VN30")
                show_error(exc)

            # 2. Kiem tra OHLCV lich su
            try:
                print("\n[2] Lay du lieu OHLCV ma SSI...")

                bars = data.market_data.get_ohlc_1day_historical(
                    symbol="SSI",
                    from_date="2026/06/01 00:00:00",
                    to_date="2026/11/09 23:59:59",
                    page=1,
                    size=1000,
                )

                rows = []
                for bar in bars or []:
                    rows.append({
                        "symbol": "SSI",
                        "time": str(bar.trading_date),
                        "open": bar.open_price,
                        "high": bar.high_price,
                        "low": bar.low_price,
                        "close": bar.close_price,
                        "volume": bar.volume,
                    })

                df = pd.DataFrame(rows)

                if df.empty:
                    print("[CANH BAO] Khong co du lieu OHLCV")
                else:
                    df = df.drop_duplicates(
                        subset=["symbol", "time"]
                    ).sort_values("time")

                    print("So phien:", len(df))
                    print("\n5 phien gan nhat:")
                    print(df.tail(5).to_string(index=False))

                    df.to_csv(
                        OUTPUT / "ssi_ohlcv.csv",
                        index=False,
                        encoding="utf-8-sig",
                    )
                    print("\n[OK] Da luu ssi_ohlcv.csv")

            except Exception as exc:
                print("[LOI] Khong lay duoc OHLCV")
                show_error(exc)

    print("\nHOAN THANH KIEM TRA MARKET DATA")


if __name__ == "__main__":
    main()
