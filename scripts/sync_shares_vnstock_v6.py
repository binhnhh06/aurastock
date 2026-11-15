"""Optional incremental source-backed outstanding shares from vnstock v6.

This script NEVER modifies original SSI prices/BCTC and never guesses units.
Requires vnstock v6 with FHSC reference listing access (may require plan).
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import os
import time
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'fundamentals' / 'processed' / 'market_cap_reference.csv'
CAT = ROOT / 'data' / 'ssi_cache' / 'market_symbols.csv'
FIELDS = ['symbol', 'as_of', 'source', 'market_cap_vnd', 'shares_outstanding']


def run(limit: int, pause: float):
    if not CAT.is_file():
        raise SystemExit('Chưa có data/ssi_cache/market_symbols.csv')
    try:
        from vnstock import Reference
    except (ImportError, AttributeError):
        raise SystemExit('Công cụ này cần vnstock v6 Reference; KHÔNG nâng cấp trong lúc đồng bộ BCTC.')
    existing = pd.read_csv(OUT, encoding='utf-8-sig', dtype=str) if OUT.is_file() else pd.DataFrame(columns=FIELDS)
    for col in FIELDS:
        if col not in existing:
            existing[col] = ''
    existing['symbol'] = existing['symbol'].astype(str).str.upper().str.strip()
    symbols = pd.read_csv(CAT, encoding='utf-8-sig', dtype=str)
    symbols = symbols.loc[symbols['asset_class'].eq('EQUITY'), 'symbol'].str.upper().str.strip().dropna().drop_duplicates().tolist()
    today = date.today().isoformat()
    done = set(existing.loc[existing['as_of'].eq(today) & existing['shares_outstanding'].notna(), 'symbol'])
    pending = [s for s in symbols if s not in done]
    print(f'AURA vnstock shares (optional) | pending={len(pending)} | batch={min(limit,len(pending))}')
    n_ok = n_error = 0
    for i, symbol in enumerate(pending[:limit], 1):
        try:
            company = Reference('fhsc').company(symbol)
            data = company.listing()
            if isinstance(data, dict):
                data = pd.DataFrame([data])
            if not isinstance(data, pd.DataFrame) or data.empty or 'outstanding_shares' not in data:
                raise ValueError('no outstanding_shares')
            if 'symbol' in data:
                data = data.loc[data['symbol'].astype(str).str.upper().eq(symbol)]
            if data.empty:
                raise ValueError('ticker mismatch')
            n = pd.to_numeric(data['outstanding_shares'], errors='coerce').dropna()
            if n.empty or not (0 < float(n.iloc[0]) < 1e13):
                raise ValueError('invalid shares amount')
            shares = int(round(float(n.iloc[0])))
            row = pd.DataFrame([dict(symbol=symbol,as_of=today,
                      source='vnstock v6 · Reference(fhsc).company.listing',
                      market_cap_vnd='',shares_outstanding=shares)])
            existing = pd.concat([existing, row], ignore_index=True)
            existing = existing.sort_values('as_of').drop_duplicates('symbol', keep='last')
            OUT.parent.mkdir(parents=True, exist_ok=True)
            temp = OUT.with_suffix('.tmp')
            existing[FIELDS].to_csv(temp,index=False,encoding='utf-8-sig')
            os.replace(temp,OUT)
            n_ok += 1
            print(f'[{i}/{min(limit,len(pending))}] {symbol}: OK, outstanding_shares={shares}')
        except Exception as err:
            n_error += 1
            print(f'[{i}/{min(limit,len(pending))}] {symbol}: NO_DATA ({type(err).__name__})')
        time.sleep(max(0,pause))
    print(f'Kết thúc: OK {n_ok} | chưa có dữ liệu {n_error} | lưu {OUT}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Optional company outstanding shares from vnstock v6 FHSC')
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--pause',type=float,default=1.5)
    args=parser.parse_args()
    run(max(1,args.limit),max(0,args.pause))
