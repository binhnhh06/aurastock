"""Inspect Vnstock ratio source with position-safe normalization (v3.3.1).

Read-only: does not change source ratio, financial statements, or scores.
"""
import argparse
from pathlib import Path
import pandas as pd
from core.ratio_repair_v33 import normalize_ratio

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'fundamentals' / 'ratio_repair_review'


def get_live(symbol, source):
    from vnstock import Vnstock
    client = Vnstock().stock(symbol=symbol, source=source)
    return client.finance.ratio(period='year', lang='vi')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', nargs='+', default=['FPT'])
    parser.add_argument('--source', default='VCI', choices=['VCI', 'KBS'])
    parser.add_argument('--min-year', type=int, default=2025)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    all_periods, all_candidates = [], []
    for raw in args.symbols:
        symbol = raw.strip().upper()
        if not symbol:
            continue
        print(f'\n[{symbol}] Fresh ratio request | source={args.source} | period=year')
        try:
            df = get_live(symbol, args.source)
        except Exception as exc:
            print('  FETCH_FAILED:', type(exc).__name__)
            all_periods.append(pd.DataFrame([{'symbol': symbol, 'source': args.source,
                                              'status': f'FETCH_FAILED_{type(exc).__name__}'}]))
            continue
        if not isinstance(df, pd.DataFrame):
            print('  PARSE_FAILED: response is not DataFrame')
            all_periods.append(pd.DataFrame([{'symbol': symbol, 'source': args.source,
                                              'status': 'PARSE_FAILED_NOT_DATAFRAME'}]))
            continue
        print(f'  Raw shape: {df.shape}; column class: {type(df.columns).__name__}')
        print('  Raw column samples:', [str(x) for x in list(df.columns)[:7]])
        try:
            periods, candidates = normalize_ratio(df, symbol, args.source, args.min_year)
        except Exception as exc:
            print('  PARSE_FAILED:', type(exc).__name__)
            all_periods.append(pd.DataFrame([{'symbol': symbol, 'source': args.source,
                                              'status': f'PARSE_FAILED_{type(exc).__name__}'}]))
            continue
        print('  Period statuses:', periods['status'].value_counts().to_dict())
        print('  Candidate rows for manual review:', len(candidates))
        all_periods.append(periods)
        if not candidates.empty:
            all_candidates.append(candidates)

    if all_periods:
        period_table = pd.concat(all_periods, ignore_index=True)
        file = OUT / 'live_ratio_period_diagnostics.csv'
        period_table.to_csv(file, index=False, encoding='utf-8-sig')
        print('\nDiagnostic saved:', file)
    if all_candidates:
        verified = pd.concat(all_candidates, ignore_index=True)
        file = OUT / 'unverified_ratio_candidates.csv'
        verified.to_csv(file, index=False, encoding='utf-8-sig')
        print('Unverified candidate data saved:', file)
    print('No scored data, source BCTC, or existing ratio staging file has been changed.')


if __name__ == '__main__':
    main()
