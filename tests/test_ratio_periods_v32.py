import tempfile
import unittest
from pathlib import Path
import pandas as pd
from audit_ratio_periods_v32 import audit_one

class TestRatioAudit(unittest.TestCase):
    def save(self, values):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        p=Path(t.name)/'FPT_ratios.csv'
        pd.DataFrame(values).to_csv(p,index=False)
        return p

    def test_repeated_2018_columns_never_become_2019(self):
        p=self.save({'item_id':['year','quarter','ratioType','pe_ratio'],
                     '2018':[2018,1,'RATIO_TTM',8.0],
                     '2018.1':[2018,1,'RATIO_TTM',8.0]})
        periods,_=audit_one(p)
        self.assertEqual({x['year'] for x in periods},{2018})
        self.assertEqual({x['status'] for x in periods},{'BLOCK_STALE_PERIOD'})
        self.assertTrue(all(x['duplicate_period'] for x in periods))

    def test_quarter_5_as_year_not_quarter(self):
        p=self.save({'item_id':['year','quarter','ratioType','roe'],
                     '2018':[2018,5,'RATIO_YEAR',0.20]})
        periods,_=audit_one(p)
        self.assertEqual(periods[0]['period'],'2018')
        self.assertNotEqual(periods[0]['period'],'2018-Q5')

    def test_quarter5_ttm_is_invalid(self):
        p=self.save({'item_id':['year','quarter','ratioType'],
                     '2018':[2025,5,'RATIO_TTM']})
        periods,_=audit_one(p)
        self.assertEqual(periods[0]['status'],'BLOCK_INVALID_QUARTER_OR_TYPE')

    def test_recent_is_not_automatically_scored(self):
        p=self.save({'item_id':['year','quarter','ratioType','roe'],
                     '2025':[2025,4,'RATIO_TTM',0.2]})
        periods,_=audit_one(p)
        self.assertEqual(periods[0]['status'],'STRUCTURE_OK')
        # It is only a structural audit: no scoring output exists.

if __name__ == '__main__':unittest.main()
