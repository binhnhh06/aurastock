"""Safely install the unified Streamlit tabbed page. Run from project root.

Dry-run: python install_two_pages.py --dry-run
Apply:   python install_two_pages.py
"""
from __future__ import annotations
import sys as _aura_sys
from pathlib import Path as _AuraPath
_aura_sys.path.insert(0, str(_AuraPath(__file__).resolve().parents[2]))  # gốc dự án (file đã chuyển vào scripts/legacy)


import argparse
import ast
from datetime import datetime
from pathlib import Path
import shutil
import sys

ROOT = Path.cwd()
SOURCE = ROOT / 'ui_two_pages' / '01_Tram_loc_thi_truong.py'
DEST = ROOT / 'pages' / '01_Tram_loc_thi_truong.py'
OLD = [
    '01_Bo_loc_SSI_Thong_minh.py',
    '02_SSI_Smart_Rating_Da_nhan_to.py',
    '03_Tra_cuu_toan_thi_truong.py',
]


def plan(root=ROOT):
    if not (root / 'app.py').is_file():
        raise FileNotFoundError('Không thấy app.py. Hãy chạy trong thư mục batday_ssi_project.')
    src = root / 'ui_two_pages' / '01_Tram_loc_thi_truong.py'
    if not src.is_file():
        raise FileNotFoundError('Thiếu file trang mới trong thư mục ui_two_pages/.')
    ast.parse(src.read_text(encoding='utf-8-sig'))
    pages = root / 'pages'
    moves = [pages / name for name in OLD if (pages / name).is_file()]
    target = pages / '01_Tram_loc_thi_truong.py'
    if target.is_file():
        moves.append(target)
    return moves, target


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    try:
        originals, target = plan(ROOT)
    except (FileNotFoundError, SyntaxError) as exc:
        print('ABORT:', exc)
        sys.exit(1)
    print('Ứng dụng gốc: app.py (KHÔNG THAY ĐỔI)')
    print('Trang đích:', target)
    print('Trang sao lưu:', *[p.name for p in originals], sep='\n  - ')
    if args.dry_run:
        print('DRY RUN: chưa thay đổi file nào.')
        return
    backup = ROOT / 'backups' / f'unified_ui_{datetime.now():%Y%m%d_%H%M%S}' / 'pages'
    backup.mkdir(parents=True, exist_ok=False)
    for old in originals:
        shutil.move(str(old), str(backup / old.name))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, target)
    print('INSTALLED:', target)
    print('BACKUP:', backup.parent)
    print('OK: app.py, core/strategy.py, core/data.py và dữ liệu SSI không bị sửa.')


if __name__ == '__main__':
    main()
