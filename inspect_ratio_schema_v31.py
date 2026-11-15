"""Local-only, read-only diagnostic of Vnstock ratios CSV layout.

Never assigns a year or financial metric based on a CSV column name alone.
"""
from pathlib import Path
import argparse
import pandas as pd

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--staging', type=Path, default=ROOT/'data'/'fundamentals'/'staging')
    parser.add_argument('--out', type=Path, default=ROOT/'data'/'fundamentals'/'mapping_review')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    reports=[]
    for path in sorted(args.staging.glob('*_ratios.csv')):
        df=pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
        symbol=path.name.split('_')[0].upper()
        print(f'\n{symbol}: {len(df)} rows / {len(df.columns)} columns')
        print('  Columns:', ', '.join(map(str,df.columns)))
        for _, row in df.iterrows():
            name=str(row.get('item_id','')).strip()
            if name in {'year','quarter','ratioType','pe_ratio','pb_ratio','roe','roa','dividend_yield','market_cap'}:
                cells = []
                for c in df.columns:
                    if c not in ('Unnamed: 0','item','item_en','item_id'):
                        val=row[c]
                        if pd.notna(val):
                            cells.append(f'{c}={str(val)[:25]}')
                print(' ',name,' | ', ' ; '.join(cells[:9]))
            reports.append({
                'symbol': symbol, 'item_id': str(row.get('item_id','')),
                'item_label': str(row.get('item','')),
                'source_file': path.name, 'all_columns': '|'.join(map(str,df.columns)),
            })
    if reports:
        pd.DataFrame(reports).to_csv(args.out/'ratio_items_catalog.csv',index=False,encoding='utf-8-sig')
        print('\nSaved ratio_items_catalog.csv (names only; no scores generated)')
    else:
        print('No *ratios.csv found; check --staging path')

if __name__=='__main__': main()
