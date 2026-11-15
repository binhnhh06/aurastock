"""BatDayStox: safe corrections for equity-only default scanning.
Run from project root: python marketwide_safe_patch.py.
Does NOT modify data files, secrets, scores, or app.py.
"""
from __future__ import annotations
import ast
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
PATCHES = [
    (
        'core/ssi_universe.py',
        "    typ = str(getattr(item, 'stock_type', None) or '').strip().upper()\n",
        "    typ = str(getattr(item, 'stock_type', None) or '').strip().upper()\n"
        "    # An explicit underlying security means the record is a warrant,\n"
        "    # even if the stock_type field is inconsistent.\n"
        "    if _has_text(getattr(item, 'cw_underlying_symbol', None)):\n"
        "        return 'NON_EQUITY'\n",
    ),
    (
        'core/smart_screener.py',
        '    symbols = screener_symbols(root)\n',
        '    symbols = screener_symbols(root, include_candidates=False)\n',
    ),
    (
        'scripts/ssi_fetch_symbol.py',
        'else screener_symbols()[a.offset:a.offset+a.batch]',
        'else screener_symbols(include_candidates=False)[a.offset:a.offset+a.batch]',
    ),
]


def main():
    prepared = []
    for rel, old, new in PATCHES:
        path = ROOT / rel
        if not path.is_file():
            raise SystemExit(f'MISSING: {path}; no files changed')
        source = path.read_text(encoding='utf-8-sig')
        if new in source:
            print(f'ALREADY_PATCHED: {rel}')
            continue
        if source.count(old) != 1:
            raise SystemExit(f'UNEXPECTED_SOURCE: {rel}; no files changed')
        updated = source.replace(old, new)
        ast.parse(updated, filename=str(path))
        prepared.append((path, updated, rel))
    if not prepared:
        print('ALL_PATCHED: no changes needed')
        return
    backup = ROOT / 'backups' / ('marketwide_safe_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True, exist_ok=True)
    for path, updated, rel in prepared:
        target = backup / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for path, updated, rel in prepared:
        path.write_text(updated, encoding='utf-8')
        print('PATCHED:', rel)
    print('BACKUP:', backup)
    print('Default scan: EQUITY only; candidates still searchable')


if __name__ == '__main__':
    main()
