"""Run: python scripts/ssi_sync_universe.py  (reads credentials from .env locally)."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.ssi_universe import collect_market_catalogue, save_catalogue


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
    except ImportError:
        pass
    import os
    from ssi_sdk import Auth, Data, Config
    required = ('SSI_CLIENT_ID', 'SSI_API_KEY', 'SSI_API_SECRET')
    if any(not os.getenv(k) for k in required):
        raise SystemExit('Thiếu SSI_CLIENT_ID / SSI_API_KEY / SSI_API_SECRET trong .env')
    config = Config(client_id=os.environ['SSI_CLIENT_ID'], api_key=os.environ['SSI_API_KEY'], api_secret=os.environ['SSI_API_SECRET'])
    with Auth(config) as auth:
        auth.authenticate()
        with Data(auth) as data:
            df = collect_market_catalogue(data.market_data)
    output = save_catalogue(df)
    print('SSI MARKET CATALOGUE:', output)
    print('Tổng số dòng danh mục:', len(df))
    print(df.groupby(['board','asset_class']).size().to_string())
    print('Mã cổ phiếu đủ điều kiện đưa vào danh sách quét:', df[df.equity_scan].symbol.nunique())
    print('UNKNOWN và NON_EQUITY không đưa vào bảng chấm điểm cổ phiếu; vẫn có thể tra cứu.')

if __name__ == '__main__':
    main()
