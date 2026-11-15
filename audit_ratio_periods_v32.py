"""Audit Vnstock ratio exports before any financial or valuation scoring.

Does NOT change source CSVs or create any scores. Periods are taken from
metadata rows (year, quarter, ratioType), NEVER inferred from pandas' .1 suffixes.
"""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import pandas as pd

META_COLS = {'item', 'item_en', 'item_id', 'Unnamed: 0'}
SAMPLE_IDS = ('year', 'quarter', 'ratioType', 'pe_ratio', 'pb_ratio', 'roe', 'roa')


def _metadata(df: pd.DataFrame, field: str):
    if 'item_id' not in df.columns:
        return None
    matches = df.loc[df['item_id'].astype(str).str.strip().eq(field)]
    return matches.iloc[0] if len(matches) == 1 else None


def _year(value):
    v = pd.to_numeric(value, errors='coerce')
    if pd.isna(v) or int(v) != float(v) or not 1990 <= int(v) <= 2100:
        return None
    return int(v)


def _quarter(value):
    v = pd.to_numeric(value, errors='coerce')
    return int(v) if pd.notna(v) and int(v) == float(v) else None


def audit_one(path: Path, min_recent_year: int = 2025):
    df = pd.read_csv(path, encoding='utf-8-sig', low_memory=False)
    symbol = path.stem.replace('_ratios', '').upper()
    fields = {name: _metadata(df, name) for name in ('year','quarter','ratioType')}
    if not all(v is not None for v in fields.values()):
        return [{'symbol':symbol, 'source_column':'', 'period':'', 'status':'BLOCK_METADATA_MISSING',
                 'year':None,'quarter':None,'ratio_type':'','duplicate_period':False}], None

    cols = [c for c in df.columns if c not in META_COLS]
    periods=[]
    for c in cols:
        yr=_year(fields['year'][c]); q=_quarter(fields['quarter'][c])
        kind=str(fields['ratioType'][c]).strip().upper()
        if yr is None:
            period=''; status='BLOCK_INVALID_YEAR'
        elif 'YEAR' in kind and 'TTM' not in kind:
            period=f'{yr}'; status='STRUCTURE_OK'
        elif q in {1,2,3,4}:
            period=f'{yr}-Q{q}'; status='STRUCTURE_OK'
        else:
            period=''; status='BLOCK_INVALID_QUARTER_OR_TYPE'
        if yr is not None and yr < min_recent_year and status == 'STRUCTURE_OK':
            status='BLOCK_STALE_PERIOD'
        periods.append({'symbol':symbol,'source_column':str(c),'year':yr,'quarter':q,
                        'ratio_type':kind,'period':period,'status':status,
                        'duplicate_period':False})
    counts=Counter((r['period'],r['ratio_type']) for r in periods if r['period'])
    for r in periods:
        if r['period'] and counts[(r['period'],r['ratio_type'])]>1:
            r['duplicate_period']=True
            if r['status']=='STRUCTURE_OK': r['status']='BLOCK_DUPLICATE_PERIOD'

    # Extract sample metric values solely for audit; NO scores or current-period assumptions.
    samples=[]
    for field in SAMPLE_IDS:
        row=_metadata(df, field)
        if row is None: continue
        for rec in periods:
            c=rec['source_column']
            samples.append({'symbol':symbol,'source_column':c,'period':rec['period'],
                            'item_id':field,'raw_value':str(row[c]),'period_status':rec['status']})
    return periods, samples


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--staging', type=Path, default=Path('data/fundamentals/staging'))
    p.add_argument('--out',type=Path,default=Path('data/fundamentals/mapping_review'))
    p.add_argument('--min-recent-year',type=int,default=2025)
    a=p.parse_args()
    files=sorted(a.staging.glob('*_ratios.csv'))
    if not files: raise SystemExit(f'Khong tim thay *_ratios.csv trong {a.staging}')
    a.out.mkdir(parents=True,exist_ok=True)
    all_periods=[]; all_samples=[]; summaries=[]
    for path in files:
        periods,samples=audit_one(path,a.min_recent_year)
        all_periods.extend(periods)
        all_samples.extend(samples or [])
        years=sorted({r['year'] for r in periods if r['year'] is not None})
        codes=Counter(r['status'] for r in periods)
        duplicate_count=sum(r['duplicate_period'] for r in periods)
        recent_ok=sum(r['status']=='STRUCTURE_OK' for r in periods)
        summaries.append({'symbol':periods[0]['symbol'],'ratio_columns':len(periods),
                          'metadata_years':','.join(map(str,years)),
                          'duplicate_period_columns':duplicate_count,
                          'recent_structure_ok_columns':recent_ok,
                          'eligible_for_smart_rating':'NO - unverified publication date and source',
                          'status_counts':'; '.join(f'{k}:{v}' for k,v in sorted(codes.items()))})
    pd.DataFrame(all_periods).to_csv(a.out/'ratio_period_diagnostics_v32.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(all_samples).to_csv(a.out/'ratio_sample_values_v32.csv',index=False,encoding='utf-8-sig')
    summary=pd.DataFrame(summaries)
    summary.to_csv(a.out/'ratio_audit_summary_v32.csv',index=False,encoding='utf-8-sig')
    print('=== RATIO PERIOD AUDIT V3.2 ===')
    print(summary[['symbol','ratio_columns','metadata_years','duplicate_period_columns','recent_structure_ok_columns']].to_string(index=False))
    print('\nDữ liệu tỷ số CHƯA được đưa vào Smart Rating. Không suy luận năm từ hậu tố .1, .2.')
    print('Đã lưu 3 CSV kiểm tra vào:',a.out.resolve())

if __name__ == '__main__': main()
