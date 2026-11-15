#!/usr/bin/env python3
"""Conservative read-only H1/2026 source readiness audit."""
import argparse,csv,json,re,sys
from pathlib import Path
from datetime import datetime

REQUIRED=('symbol','report_period','period_end','publication_date','scope','source_url')
TARGET=Path('data/fundamentals/processed/bctc_h1_2026.csv')

def audit(root,as_of='2026-11-13'):
 root=Path(root).resolve(); path=root/TARGET
 data={'as_of':as_of,'target_relative':str(TARGET),'status':'MISSING','rows':0,'valid_rows':0,'symbols':0,'invalid':[],'candidates':[]}
 # Indicate nearby files with H1 or 6T 2026 in name; don't equate year=2026 with H1.
 base=root/'data'/'fundamentals'
 if base.is_dir():
  for f in base.rglob('*'):
   if f.is_file() and re.search(r'(?:2026.*(?:h1|6m|6t|ban.?nien)|(?:h1|6m|6t|ban.?nien).*2026)',f.name,re.I):
    data['candidates'].append(str(f.relative_to(root)))
 if path.is_file():
  try:
   with path.open(encoding='utf-8-sig',newline='') as fp:
    rd=csv.DictReader(fp); columns=rd.fieldnames or []
    missing=[x for x in REQUIRED if x not in columns]
    if missing:
     data['status']='MISSING_COLUMNS';data['invalid']=['Missing: '+','.join(missing)]
    else:
     valid=set()
     for i,row in enumerate(rd,2):
      data['rows']+=1
      ok=(row.get('report_period','').upper() in ('6T/2026','H1/2026','6M/2026')
        and row.get('period_end')=='2026-06-30' and row.get('publication_date','') <= as_of
        and re.fullmatch(r'\d{4}-\d{2}-\d{2}',row.get('publication_date',''))
        and row.get('scope','').upper() in ('CONSOLIDATED','SEPARATE')
        and row.get('source_url','').startswith(('http://','https://')) and bool(row.get('symbol','')))
      if ok:valid.add(row['symbol'].upper());data['valid_rows']+=1
      else:
       if len(data['invalid'])<20:data['invalid'].append(f'row {i}: wrong period, date, scope or source')
     data['symbols']=len(valid);data['status']='CANDIDATES_FOUND_NOT_VERIFIED' if data['valid_rows'] else 'NO_ELIGIBLE_ROWS'
  except Exception as e:
   data['status']='READ_ERROR';data['invalid']=[type(e).__name__]
 out=root/'reports'/'aura_h1_2026_readiness';out.mkdir(parents=True,exist_ok=True)
 (out/'status.json').write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
 print(f"=== AURA | BCTC BAN NIEN 6T/2026 — READ ONLY ===")
 print(f"[STATUS] {data['status']} | rows={data['rows']} | valid metadata={data['valid_rows']} | symbols={data['symbols']}")
 print(f"[CANDIDATE_FILES] {len(data['candidates'])} (file name only; not evidence of complete 6M)")
 print(f"[REPORT] {out/'status.json'}")
 print("[NOTE] No automatic verification and no 2026 yearly Smart Rating/Backtest")
 return 0

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--as-of',default='2026-11-13');a=p.parse_args();sys.exit(audit(a.root,a.as_of))
