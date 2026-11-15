"""Upload annual financial candidate ratios to a SEPARATE private R2 prefix.

No financial CSVs or keys are written to GitHub. Never modifies score flags.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from core.aura_r2_market import client, enabled, prefix, setting
from core.aura_r2_financial_v98 import _validate_annual, _archive_files


def _sample_bytes(df):
    return df.to_csv(index=False).encode('utf-8-sig')


def build_package(root: Path):
    path = root / 'data/fundamentals/processed/financial_features_annual.csv'
    if not path.is_file():
        raise RuntimeError('FINANCIAL_ANNUAL_CSV_MISSING')
    annual = path.read_bytes()
    info = _validate_annual(annual)
    df = pd.read_csv(io.BytesIO(annual), encoding='utf-8-sig', low_memory=False)
    # Derived quality summaries calculated offline, never mark a candidate as verified.
    from core.aura_financial_quality import audit_tables
    universe = None
    catalogue = root / 'data/ssi_cache/market_symbols.csv'
    if catalogue.is_file():
        c = pd.read_csv(catalogue, encoding='utf-8-sig', keep_default_na=False, low_memory=False)
        if {'symbol', 'asset_class'}.issubset(c):
            universe = sorted(set(c.loc[c['asset_class'].astype(str).str.upper().eq('EQUITY'), 'symbol'].astype(str).str.upper()) - {''})
    years, companies, issues = audit_tables(df, universe)
    records = {
        'financial_features_annual.csv': annual,
        'aura_quality_by_year.csv': _sample_bytes(years),
        'aura_quality_by_symbol.csv': _sample_bytes(companies),
        'aura_quality_issues.csv': _sample_bytes(issues),
    }
    h1 = root / 'data/fundamentals/processed/bctc_h1_2026.csv'
    if h1.is_file():
        hdf = pd.read_csv(h1, encoding='utf-8-sig', dtype=str).fillna('')
        needed = {'symbol','report_period','period_end','publication_date','scope','source_url'}
        if not needed.issubset(hdf):
            raise ValueError('H1_2026_MISSING_PROVENANCE_COLUMNS')
        valid = (
            hdf['report_period'].str.upper().isin(['6T/2026','H1/2026','6M/2026'])
            & hdf['period_end'].eq('2026-06-30')
            & hdf['publication_date'].str.fullmatch(r'\d{4}-\d{2}-\d{2}', na=False)
            & hdf['source_url'].str.match(r'^https?://', na=False)
            & hdf['scope'].str.upper().isin(['CONSOLIDATED','SEPARATE'])
        )
        if bool(valid.any()):
            records['bctc_h1_2026.csv'] = _sample_bytes(hdf.loc[valid])
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode='w', compression=zipfile.ZIP_DEFLATED, compresslevel=8) as z:
        for name, raw in records.items(): z.writestr(name, raw)
    blob = mem.getvalue()
    sha = hashlib.sha256(blob).hexdigest()
    _archive_files(blob, sha)
    return blob, sha, info, sorted(records)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(ROOT))
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    root = Path(args.root).resolve()
    blob, sha, info, names = build_package(root)
    print('[FIN-CHECK]', json.dumps({**info, 'archive_bytes': len(blob), 'files': names}, ensure_ascii=False))
    if args.dry_run:
        print('[OK] Dry-run: khong ket noi R2, khong upload.')
        return
    if not enabled(): raise RuntimeError('R2_UPLOADER_NOT_CONFIGURED_IN_THIS_POWERSHELL_SESSION')
    s3, bucket, base = client(), setting('AURA_R2_BUCKET'), prefix() + '/financial'
    key = f'{base}/snapshots/{sha}.zip'
    print('[FIN-UPLOAD] Private financial candidate snapshot, separate from EOD. No GitHub data.')
    s3.put_object(Bucket=bucket, Key=key, Body=blob, ContentType='application/zip')
    manifest = {
        'schema_version': '9.8', 'sha256': sha, 'zip_key': key,
        'rows': info['rows'], 'symbols': info['symbols'], 'source_verified_rows': info['source_verified_rows'],
        'score_eligible_rows': info['score_eligible_rows'], 'files': names,
        'published_at': datetime.now(timezone.utc).isoformat(),
        'note': 'ANNUAL CANDIDATE/PROVISIONAL, NOT AUDITED FINANCIAL STATEMENTS OR AUTOMATIC SMART RATING',
    }
    s3.put_object(Bucket=bucket, Key=base + '/current.json',
                  Body=json.dumps(manifest, ensure_ascii=False).encode('utf-8'),
                  ContentType='application/json', CacheControl='no-store')
    print('[FIN-UPLOADED] Private R2 financial: ', info['symbols'], 'symbols,', info['rows'], 'rows,', len(blob), 'bytes')
    print('[SAFETY] Data NOT added to GitHub; no score flags changed.')


if __name__ == '__main__':
    try: main()
    except Exception as e:
        print('[SAFE]', type(e).__name__, str(e)[:130])
        raise SystemExit(2)
