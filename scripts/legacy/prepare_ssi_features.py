import sys as _aura_sys
from pathlib import Path as _AuraPath
_aura_sys.path.insert(0, str(_AuraPath(__file__).resolve().parents[2]))  # gốc dự án (file đã chuyển vào scripts/legacy)


from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "ssi_cache"
SOURCE = CACHE / "ohlcv"
OUTPUT = CACHE / "features"
OUTPUT.mkdir(parents=True, exist_ok=True)

REQUIRED = [
    "symbol", "date", "open", "high",
    "low", "close", "volume"
]


def prepare_one(symbol):
    path = SOURCE / f"{symbol}.csv"

    if not path.exists():
        raise FileNotFoundError("Missing OHLCV file")

    df = pd.read_csv(path)

    missing = set(REQUIRED) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    df["date"] = pd.to_datetime(
        df["date"], errors="coerce"
    )

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df[REQUIRED].isna().any().any():
        raise ValueError("Missing or invalid values")

    if not df["symbol"].eq(symbol).all():
        raise ValueError("Symbol mismatch")

    if df["date"].duplicated().any():
        raise ValueError("Duplicate trading dates")

    if (
        (df[["open", "high", "low", "close"]] <= 0).any().any()
        or (df["volume"] < 0).any()
        or (df["high"] < df[["open", "low", "close"]].max(axis=1)).any()
        or (df["low"] > df[["open", "high", "close"]].min(axis=1)).any()
    ):
        raise ValueError("Invalid OHLCV")

    df = df.sort_values("date").reset_index(drop=True)

    # Chi bao xu huong
    df["ma20"] = df["close"].rolling(
        20, min_periods=20
    ).mean()

    df["ma50"] = df["close"].rolling(
        50, min_periods=50
    ).mean()

    df["ma200"] = df["close"].rolling(
        200, min_periods=200
    ).mean()

    # Dong luong 63 phien
    df["momentum63"] = (
        df["close"] / df["close"].shift(63) - 1
    )

    # Thanh khoan
    df["volume_ma20"] = df["volume"].rolling(
        20, min_periods=20
    ).mean()

    df["volume_ma60"] = df["volume"].rolling(
        60, min_periods=60
    ).mean()

    denominator = df["volume_ma60"].replace(0, float("nan"))
    df["volume_ratio"] = df["volume_ma20"] / denominator

    # Canh bao bien dong gia lon
    df["daily_return"] = df["close"].pct_change(
        fill_method=None
    )
    large_moves = int(
        (df["daily_return"].abs() > 0.30).sum()
    )

    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    df.to_csv(
        OUTPUT / f"{symbol}.csv",
        index=False,
        encoding="utf-8-sig"
    )

    last = df.iloc[-1]

    return {
        "symbol": symbol,
        "status": "OK",
        "sessions": len(df),
        "first_date": df["date"].iloc[0],
        "last_date": df["date"].iloc[-1],
        "ma200_valid": int(df["ma200"].notna().sum()),
        "momentum63_valid": int(df["momentum63"].notna().sum()),
        "large_moves_30pct": large_moves,
        "latest_close": last["close"],
    }


def main():
    symbols = (
        pd.read_csv(CACHE / "vn30_symbols.csv")["symbol"]
        .astype(str).str.strip().str.upper()
        .drop_duplicates().tolist()
    )

    results = []

    for symbol in symbols:
        try:
            result = prepare_one(symbol)
            results.append(result)
            print(
                f"[OK] {symbol}: "
                f"{result['sessions']} phien"
            )
        except Exception as exc:
            print(f"[ERROR] {symbol}: {type(exc).__name__}")
            results.append({
                "symbol": symbol,
                "status": "ERROR",
                "sessions": 0
            })

    report = pd.DataFrame(results)
    report.to_csv(
        CACHE / "feature_quality.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\n===== FEATURE QUALITY =====")
    print(report.to_string(index=False))

    print("\nSo ma OK:", (report["status"] == "OK").sum())
    print("Tong so ma:", len(report))
    print("Luu tai:", OUTPUT)


if __name__ == "__main__":
    main()
