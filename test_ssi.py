
from core.ssi_client import get_ssi_ohlcv


def main():
    print("=" * 55)
    print("BATDAY SSI PROJECT - KIEM TRA KET NOI API")
    print("=" * 55)

    try:
        df = get_ssi_ohlcv(
            symbol="SSI",
            from_date="2026/09/01 00:00:00",
            to_date="2026/11/09 23:59:59",
        )

        if df.empty:
            print("API ket noi nhung khong tra ve du lieu.")
            return

        print("\nKET NOI VA LAY DU LIEU THANH CONG")
        print("So dong:", len(df))
        print("So dong trung:", df.duplicated(
            subset=["symbol", "time"]
        ).sum())

        print("\n5 dong du lieu dau:")
        print(df.head(5).to_string(index=False))

        print("\nGia tri thieu:")
        print(df.isna().sum().to_string())

        print("\nKiem tra logic OHLC:")
        invalid = df[
            (df["high"] < df["low"])
            | (df["high"] < df["open"])
            | (df["high"] < df["close"])
            | (df["low"] > df["open"])
            | (df["low"] > df["close"])
        ]
        print("So dong OHLC bat hop ly:", len(invalid))

    except Exception as exc:
        # Không in traceback có thể chứa dữ liệu nhạy cảm.
        print("KIEM TRA THAT BAI")
        print("Loai loi:", type(exc).__name__)
        print("Kiem tra .env, quyen Market Data va ket noi mang.")


if __name__ == "__main__":
    main()
