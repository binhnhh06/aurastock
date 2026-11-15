"""Read SSI listed_shares via vnstock 6; no FHSC credential, no changes to BCTC.

Snapshots are observed-at dates (retrieval dates), not issuer effective dates.
Use a separate vnstock6 venv. With --probe or --dry-run nothing is written.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from importlib.metadata import version as package_version, PackageNotFoundError
from pathlib import Path
import os
import re
import shutil
import sys
import tempfile

import pandas as pd

OUT = Path('data/ssi_cache/reference/ssi_listed_shares.csv')
UNIVERSE = Path('data/ssi_cache/market_symbols.csv')
FIELDS = ['symbol', 'exchange', 'listed_shares', 'observed_at', 'source', 'name']
SOURCE = 'Vnstock 6 / SSI Reference.equity.list'
EXCHANGES = ('HOSE','HNX','UPCOM')
SYMBOL_RE = re.compile(r'^[A-Z0-9]{2,12}$')


def now_vn():
    return datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))


def valid_shares(v):
    num = pd.to_numeric(pd.Series([v]),errors='coerce').iloc[0]
    if not pd.notna(num) or not (0 < float(num) < 1e13):
        return None
    if abs(float(num)-round(float(num))) > 0.01:
        return None
    return int(round(float(num)))


def normalized_frame(raw, expected_exchange):
    if not isinstance(raw,pd.DataFrame) or raw.empty:
        raise ValueError(f'{expected_exchange}: nguồn không trả DataFrame có bản ghi')
    mandatory = {'symbol','listed_shares'}
    if not mandatory.issubset(raw.columns):
        raise ValueError(f'{expected_exchange}: thiếu cột {mandatory-set(raw.columns)}')
    out=[]
    for _, r in raw.iterrows():
        sym = str(r['symbol']).upper().strip()
        exchange = str(r.get('exchange',expected_exchange)).upper().strip()
        if exchange not in ('',expected_exchange):
            continue
        if not SYMBOL_RE.fullmatch(sym):
            continue
        shares = valid_shares(r['listed_shares'])
        if shares is None:
            continue
        out.append({'symbol':sym,'exchange':expected_exchange,'listed_shares':shares,
                    'name':str(r.get('organ_name','')).strip()})
    return pd.DataFrame(out,columns=['symbol','exchange','listed_shares','name'])


def get_universe(root):
    f=root/UNIVERSE
    if not f.is_file():
        raise FileNotFoundError(f'Chưa có danh mục cổ phiếu SSI: {f}')
    raw=pd.read_csv(f,encoding='utf-8-sig',dtype=str,keep_default_na=False)
    if not {'symbol','asset_class'}.issubset(raw.columns):
        raise ValueError('Danh mục thiếu symbol/asset_class')
    return set(raw.loc[raw['asset_class'].str.upper().eq('EQUITY'), 'symbol'].str.upper().str.strip())


def read_existing(dest):
    if not dest.exists():
        return pd.DataFrame(columns=FIELDS)
    existing=pd.read_csv(dest,encoding='utf-8-sig',dtype=str,keep_default_na=False)
    if not set(FIELDS).issubset(existing.columns):
        raise ValueError('CSV cũ thiếu cột; không ghi đè')
    return existing


def atomic_csv(df,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.aura_ssi_listed_',suffix='.csv',dir=dest.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8-sig',newline='') as h:
            df.to_csv(h,index=False)
        os.replace(tmp,dest)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def sync(root,exchanges=EXCHANGES,limit=0,probe='',dry_run=False,fetch=None,observed_at=None):
    root=Path(root).resolve()
    if not (root/'app.py').is_file():
        raise FileNotFoundError('Không tìm thấy app.py trong root AURA')
    existing=read_existing(root/OUT)
    # Probe may be exercised without catalogue; production full sync requires it.
    allowed=get_universe(root)
    observed=observed_at or now_vn().date().isoformat()
    if fetch is None:
        try:
            value=package_version('vnstock')
        except PackageNotFoundError:
            value='not-installed'
        if not value.startswith('6.'):
            raise RuntimeError('Yêu cầu vnstock 6; chạy bằng Python môi trường .venv_aura_vnstock6')
        from vnstock import Reference
        ref=Reference('ssi')
        fetch=lambda exchange: ref.equity.list(exchange=exchange)
    output=[]
    skipped=[]
    for ex in exchanges:
        try:
            frame=normalized_frame(fetch(ex), ex)
            if frame.empty:
                skipped.append(f'{ex}:0 bản ghi hợp lệ')
            else:
                frame=frame.loc[frame['symbol'].isin(allowed)].copy()
                output.extend(frame.to_dict('records'))
                print(f'[SSI] {ex}: {len(frame)} mã cổ phiếu hợp lệ trong danh mục AURA')
        except Exception as exc:
            skipped.append(f'{ex}:{type(exc).__name__}: {str(exc)[:120]}')
            print(f'[WARN] {ex}: {type(exc).__name__}; bỏ qua sàn, không tạo số liệu')
    incoming=pd.DataFrame(output,columns=['symbol','exchange','listed_shares','name'])
    if incoming.empty:
        raise ValueError('Không có dữ liệu cổ phiếu hợp lệ; không ghi CSV. Lỗi: '+' | '.join(skipped))
    conflicts=incoming.groupby('symbol')['listed_shares'].nunique()
    duplicated=conflicts[conflicts.gt(1)]
    if not duplicated.empty:
        print('[WARN] Mã xuất hiện với số CP niêm yết khác nhau giữa sàn: '+','.join(duplicated.index))
        incoming=incoming.loc[~incoming['symbol'].isin(duplicated.index)]
    incoming=incoming.sort_values(['symbol','exchange']).drop_duplicates('symbol',keep='first')
    if probe:
        sym=probe.upper().strip()
        picked=incoming.loc[incoming['symbol'].eq(sym)]
        if picked.empty:
            raise ValueError(f'Không tìm thấy {sym} trong dữ liệu vừa truy vấn')
        print(f'[PROBE] {sym}: {int(picked.iloc[0].listed_shares):,} CP NIÊM YẾT | SSI | snapshot {observed}')
        print('[PROBE] Chưa ghi file; khác CP lưu hành, không phải vốn hóa chính thức.')
        return len(incoming),0,None
    if limit>0:
        incoming=incoming.head(limit)
    incoming['observed_at']=observed
    incoming['source']=SOURCE
    # Do not replace snapshots or manually written values: same-day duplicates are skipped.
    key_existing=set(zip(existing['symbol'].str.upper().str.strip(),existing['observed_at'].str.strip()))
    added=incoming.loc[~incoming.apply(lambda r:(r['symbol'],r['observed_at']) in key_existing,axis=1)].copy()
    print(f'[SSI] Dữ liệu tham chiếu: {len(incoming)} mã | mới: {len(added)} | giữ nguyên: {len(incoming)-len(added)}')
    for item in skipped:
        print('[WARN]',item)
    if dry_run:
        print('[DRY RUN] Không ghi dữ liệu');return len(incoming),len(added),None
    dest=root/OUT
    if added.empty:
        print('[OK] Dữ liệu snapshot đã có, không cập nhật file')
        return len(incoming),0,dest
    if dest.is_file():
        backup=root/'.aura_backups'/('listed_ssi_'+now_vn().strftime('%Y%m%d_%H%M%S_%f')+'.csv')
        backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(dest,backup)
        print('[BACKUP]',backup)
    # Append to existing columns without removing manual columns.
    for col in existing.columns:
        if col not in added:
            added[col]=''
    for col in added.columns:
        if col not in existing:
            existing[col]=''
    combined=pd.concat([existing,added[existing.columns]],ignore_index=True)
    atomic_csv(combined,dest)
    print(f'[OK] SSI CP niêm yết: {len(added)} dòng mới, tổng {len(combined)}. File: {dest}')
    print('[CHÚ Ý] Không ghi market_cap_reference.csv, không thay điểm, không dùng backtest.')
    return len(incoming),len(added),dest


def main():
    p=argparse.ArgumentParser(description='AURA V8.3.2 SSI listed shares, separate from market cap')
    p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--exchanges',nargs='+',default=list(EXCHANGES),choices=EXCHANGES)
    p.add_argument('--limit',type=int,default=0,help='0 = all; applies after SSI queries')
    p.add_argument('--probe',type=str,default='')
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args()
    if args.limit<0:
        p.error('--limit không được âm')
    try:
        sync(args.root,tuple(args.exchanges),args.limit,args.probe,args.dry_run)
        return 0
    except Exception as exc:
        print(f'[SAFE] {type(exc).__name__}: {exc}')
        return 2


if __name__=='__main__':sys.exit(main())
