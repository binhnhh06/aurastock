
from pathlib import Path
import pandas as pd

from core.data import lay_ratio, lay_bctc

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "fundamentals" / "staging"
OUT.mkdir(parents=True, exist_ok=True)

# Ba loại hình doanh nghiệp khác nhau
SYMBOLS = ["FPT", "TCB", "SSI"]


def save_data(df, filename):
    if not isinstance(df, pd.DataFrame) or df.empty:
        print("  Khong co du lieu:", filename)
        return

    result = df.copy()

    if isinstance(result.columns, pd.MultiIndex):
        result.columns = [
            " | ".join(map(str, col))
            for col in result.columns
        ]

    result.to_csv(
        OUT / filename,
        encoding="utf-8-sig",
        index=True
    )

    print(
        "  Da luu:", filename,
        "| Shape:", result.shape
    )
    print("  Cot:", list(map(str, result.columns[:12])))


def main():
    print("=" * 60)
    print("BATDAY SSI - AUDIT NGUON DU LIEU TAI CHINH")
    print("=" * 60)

    for symbol in SYMBOLS:
        print(f"\n===== {symbol} =====")

        try:
            ratios = lay_ratio(symbol)
            save_data(
                ratios,
                f"{symbol}_ratios.csv"
            )
        except Exception as exc:
            print("Ratio error:", type(exc).__name__)

        try:
            statements = lay_bctc(symbol, 3)

            if not isinstance(statements, dict):
                print("BCTC khong phai dict")
                continue

            for statement_name, frame in statements.items():
                save_data(
                    frame,
                    f"{symbol}_{statement_name}.csv"
                )

        except Exception as exc:
            print("BCTC error:", type(exc).__name__)

    print("\nHOAN THANH KIEM TRA")
    print("Thu muc:", OUT)


if __name__ == "__main__":
    main()
