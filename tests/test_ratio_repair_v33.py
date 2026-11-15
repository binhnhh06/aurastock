import unittest
import pandas as pd
from core.ratio_repair_v33 import normalize_ratio


def table(years,quarter,typ):
    cols=[str(years[0])] + [f'{years[0]}.{i}' for i in range(1,len(years))]
    rows=[]
    for name,vals in [('year',years),('quarter',quarter),('ratioType',typ),
                      ('roe',[0.11]*len(years)),('pe_ratio',[12]*len(years))]:
        rows.append(dict(item_id=name,**dict(zip(cols,vals))))
    return pd.DataFrame(rows)

class TestRepair(unittest.TestCase):
    def test_repeated_2018_blocked(self):
        df=table([2018]*4,[1,2,3,4],['RATIO_TTM']*4)
        periods,candidates=normalize_ratio(df,'FPT')
        self.assertEqual(len(candidates),0)
        self.assertTrue((periods.status=='STALE').all())
    def test_exact_duplicate_blocked(self):
        df=table([2025,2025],[4,4],['RATIO_TTM']*2)
        periods,candidates=normalize_ratio(df,'TCB')
        self.assertEqual(len(candidates),0)
        self.assertTrue((periods.status=='DUPLICATE_PERIOD').all())
    def test_annual_quarter5_accepted_only_as_candidate(self):
        df=table([2024,2025],[5,5],['RATIO_YEAR']*2)
        periods,candidates=normalize_ratio(df,'TCB')
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates.iloc[0]['period'],'2025')
        self.assertEqual(candidates.iloc[0]['eligible_for_backtest'],'NO')
    def test_ttm_recent_unique(self):
        df=table([2025,2026],[4,1],['RATIO_TTM']*2)
        periods,candidates=normalize_ratio(df,'SSI')
        self.assertEqual(len(candidates),2)
        self.assertEqual(set(candidates.period),{'2025-Q4','2026-Q1'})
    def test_missing_metadata_not_parsed(self):
        df=pd.DataFrame({'item_id':['roe'],'2025':[0.1]})
        periods,candidates=normalize_ratio(df,'SSI')
        self.assertEqual(periods.iloc[0].status,'MISSING_METADATA')
        self.assertTrue(candidates.empty)

if __name__=='__main__': unittest.main()


class TestRealDuplicateColumnNames(unittest.TestCase):
    """Regression for 54x19 raw Vnstock DataFrame with repeated '2018'."""
    def test_exact_duplicate_columns_do_not_raise_valueerror(self):
        names = ['item', 'item_en', 'item_id'] + ['2018'] * 16
        rows = []
        fields = [('year', [2018] * 16),
                  ('quarter', [1, 2, 3, 4] * 4),
                  ('ratioType', ['RATIO_TTM'] * 16),
                  ('roe', [.1] * 16),
                  ('pe_ratio', [12.] * 16)]
        for key, values in fields:
            rows.append([key, key, key] + values)
        df = pd.DataFrame(rows, columns=names)
        periods, candidates = normalize_ratio(df, 'FPT')
        self.assertEqual(len(periods), 16)
        self.assertTrue((periods.status == 'DUPLICATE_PERIOD').all())
        self.assertTrue(candidates.empty)
        self.assertEqual(list(periods.column_position), list(range(3, 19)))

    def test_duplicate_labels_with_distinct_metadata_never_shift_year(self):
        # Two physically distinct period columns, both called '2018'.
        df = pd.DataFrame([
            ['year', 2025, 2026],
            ['quarter', 4, 1],
            ['ratioType', 'RATIO_TTM', 'RATIO_TTM'],
            ['roe', 0.12, 0.14],
        ], columns=['item_id', '2018', '2018'])
        periods, candidates = normalize_ratio(df, 'FPT')
        self.assertEqual(set(periods.period), {'2025-Q4', '2026-Q1'})
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates.set_index('period').loc['2026-Q1', 'roe'], 0.14)
        self.assertTrue((candidates.eligible_for_backtest == 'NO').all())
