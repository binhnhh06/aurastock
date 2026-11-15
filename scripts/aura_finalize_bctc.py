"""One-command finalize BCTC 2021-2025: rebuild features + audit quality.

Does not fetch from internet, touch SSI market data, portfolio DB, or change
score_eligible flags. Only writes under data/fundamentals/processed/.
"""
from __future__ import annotations
import argparse
import os
import sys
import tempfile
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.aura_financial_quality import audit_tables


def _atomic_csv(frame: pd.DataFrame, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.aura_bctc_', suffix='.csv', dir=dest.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8-sig', newline='') as file:
            frame.to_csv(file, index=False)
        os.replace(tmp, dest)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def finalize(root: Path, rebuild: bool = True):
    root = Path(root)
    output = root / 'data' / 'fundamentals' / 'processed'
    staging = root / 'data' / 'fundamentals' / 'staging'
    feature_file = output / 'financial_features_annual.csv'
    if rebuild and feature_file.is_file():
        # Never silently erase manual source reviews entered after the original build.
        existing = pd.read_csv(feature_file, encoding='utf-8-sig', low_memory=False)
        has_review = False
        for flag in ('source_verified', 'score_eligible'):
            if flag in existing and existing[flag].fillna('').astype(str).str.strip().str.upper().eq('YES').any():
                has_review = True
        if 'published_at' in existing and existing['published_at'].fillna('').astype(str).str.strip().ne('').any():
            has_review = True
        if has_review:
            raise RuntimeError('Đã có dòng BCTC được xác minh thủ công. Dùng --report-only để giữ nguyên, '
                               'không tự ghi đè các cột nguồn/ngày công bố.')
    if rebuild:
        if not staging.is_dir():
            raise RuntimeError(f'Chưa có thư mục BCTC đã tải: {staging}')
        import build_financial_features as builder
        if tuple(getattr(builder, 'YEARS', ())) != (2021, 2022, 2023, 2024, 2025):
            raise RuntimeError('build_financial_features.py chưa phải bản 5 năm. Cài bản BCTC 5 năm trước.')
        print('1/2 | Đang tính lại tỷ số 2021-2025 từ file staging; không gọi mạng...', flush=True)
        builder.build(staging, output)
    if not feature_file.exists():
        raise RuntimeError('Chưa có financial_features_annual.csv để kiểm tra.')
    raw = pd.read_csv(feature_file, encoding='utf-8-sig', low_memory=False)
    catalogue_path = root / 'data' / 'ssi_cache' / 'market_symbols.csv'
    universe = None
    if catalogue_path.is_file():
        catalogue = pd.read_csv(catalogue_path, encoding='utf-8-sig', keep_default_na=False, low_memory=False)
        if {'symbol', 'asset_class'}.issubset(catalogue):
            universe = sorted(set(catalogue.loc[catalogue['asset_class'].astype(str).str.upper().eq('EQUITY'), 'symbol'].astype(str).str.upper().str.strip()) - {''})
    print('2/2 | Đang lập kiểm tra độ phủ 5 năm và các chỉ tiêu thiếu...', flush=True)
    year, company, issues = audit_tables(raw, universe)
    for name, df in [('aura_quality_by_year.csv', year),
                     ('aura_quality_by_symbol.csv', company),
                     ('aura_quality_issues.csv', issues)]:
        _atomic_csv(df, output / name)
    print('\n=== AURA | TONG KET BCTC 5 NAM ===')
    print('So ma trong danh muc:', len(company))
    print('Ma co du 5 nam co it nhat mot chi tieu nguon:', int(company.years_source.eq(5).sum()))
    print('Ma co ty so so bo o ca 5 nam:', int(company.years_with_ratio.eq(5).sum()))
    print('Ma du 5 nam duoc xac minh nguon/ngay cong bo:', int(company.years_verified.eq(5).sum()))
    print('So dong can xem lai (loi/ngoai le/doi chieu):', len(issues))
    print(year.to_string(index=False))
    print('Ket qua luu tai:', output)
    print('Luu y: Tai du BCTC != du dieu kien de cham Smart Rating tong hop.')


def main():
    parser = argparse.ArgumentParser(description='AURA - tinh lai BCTC 5 nam va lap kiem tra chat luong')
    parser.add_argument('--report-only', action='store_true', help='Chi kiem tra file da tinh; khong chay lai builder')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    finalize(args.root, rebuild=not args.report_only)


if __name__ == '__main__':
    main()
