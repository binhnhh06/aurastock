import sys as _aura_sys
from pathlib import Path as _AuraPath
_aura_sys.path.insert(0, str(_AuraPath(__file__).resolve().parents[2]))  # gốc dự án (file đã chuyển vào scripts/legacy)

import pandas as pd

src = r"C:\Users\binh1\vn-annual-report-miner\src\arminer\data\fixtures\fiinpro_icb_companies.csv"
d = pd.read_csv(src, encoding="utf-8-sig")
o = d[['Mã CK','Tên Doanh Nghiệp','Sàn giao dịch','Ngành ICB Cấp 1 (Industry)','Ngành ICB Cấp 2 (Supersector)','Ngành ICB Cấp 3 (Sector)']].copy()
o.columns = ['ma','ten','san','icb1','icb2','icb3']
o['ma'] = o['ma'].astype(str).str.upper().str.strip()
o.drop_duplicates('ma').sort_values('ma').to_csv('data/icb_companies.csv', index=False, encoding='utf-8-sig')
print("Xong:", len(o), "mã")