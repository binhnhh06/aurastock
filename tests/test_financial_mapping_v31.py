import unittest
import tempfile
from pathlib import Path
import pandas as pd
from core.financial_mapping_v31 import compile_financial_review

class TestFinancialMapping(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        a = self.root / "audit"
        a.mkdir()
        self.out = self.root / "out"
        cand=[]
        for year in (2023, 2024, 2025):
            for metric,label,value,stype in [
                ('total_assets','TONG TAI SAN',100+20*(year-2023),'balance_sheet'),
                ('liabilities','NO',60+12*(year-2023),'balance_sheet'),
                ('equity','VCSH',40+8*(year-2023),'balance_sheet'),
                ('profit_after_tax','LNST',8+2*(year-2023),'income_statement'),
                ('eps','EPS',2+0.5*(year-2023),'income_statement'),
                ('income_tax_expense','THUE',3,'income_statement'),
            ]:
                cand.append(dict(symbol='TCB',year=year,statement=stype,metric=metric,match='exact',row=2,label=label,value=value,source_file='TCB_'+stype+'.csv'))
        cand += [dict(symbol='SSI',year=2025,statement='income_statement',metric='income_tax_expense',match='exact',row=6,label='THUE',value=4,source_file='SSI_income_statement.csv')]
        flags=[dict(symbol='SSI',year=2025,severity='CRITICAL_REVIEW',test='tax_equals_pretax',details='bad')]
        pd.DataFrame(cand).to_csv(a/'financial_line_candidates.csv',index=False)
        pd.DataFrame(flags).to_csv(a/'financial_review_flags.csv',index=False)
        pd.DataFrame([dict(symbol='TCB',type='balance_sheet',file='TCB_balance_sheet.csv',rows=12)]).to_csv(a/'financial_inventory.csv',index=False)
        pd.DataFrame([dict(symbol='TCB',sample='item_id=roe')]).to_csv(a/'ratio_schema_examples.csv',index=False)
        self.audit = a

    def tearDown(self): self.temp.cleanup()

    def test_report_and_no_scored_snapshot(self):
        s=compile_financial_review(self.audit,self.out)
        self.assertEqual(s['ready_for_score'],0)
        self.assertFalse((self.out/'fundamentals_snapshot.csv').exists())
        provisional=pd.read_csv(self.out/'financial_metrics_provisional.csv')
        self.assertTrue(provisional.score_eligible.eq('NO').all())
        self.assertTrue(provisional.published_at.isna().all())

    def test_derived_roe_and_no_2023_roe(self):
        compile_financial_review(self.audit,self.out)
        p=pd.read_csv(self.out/'financial_metrics_provisional.csv')
        self.assertTrue(pd.isna(p[(p.symbol=='TCB') & (p.year==2023)].iloc[0].roe_pct_provisional))
        row=p[(p.symbol=='TCB') & (p.year==2024)].iloc[0]
        self.assertAlmostEqual(row.roe_pct_provisional, 10/44*100)
        self.assertEqual(row.balance_identity_status,'PASS_PRELIMINARY')

    def test_block_tax_critical(self):
        compile_financial_review(self.audit,self.out)
        m=pd.read_csv(self.out/'financial_metric_mapping_review.csv')
        r=m[(m.symbol=='SSI') & (m.metric=='income_tax_expense')].iloc[0]
        self.assertEqual(r.status,'BLOCKED_CRITICAL_TAX_LABEL')
        self.assertTrue(pd.isna(r.value_candidate))

    def test_duplicate_revenue_rejected(self):
        src=self.audit/'financial_line_candidates.csv'
        x=pd.read_csv(src)
        rows=[]
        for num in (5,6):
            rows.append(dict(symbol='SSI',year=2025,statement='income_statement',metric='revenue',match='exact',row=num,label='DOANH THU',value=100,source_file='SSI_income_statement.csv'))
        pd.concat([x,pd.DataFrame(rows)], ignore_index=True).to_csv(src,index=False)
        compile_financial_review(self.audit,self.out)
        m=pd.read_csv(self.out/'financial_metric_mapping_review.csv')
        r=m[(m.symbol=='SSI') & (m.metric=='revenue')].iloc[0]
        self.assertEqual(r.status,'AMBIGUOUS_EXACT')
        self.assertTrue(pd.isna(r.value_candidate))

if __name__=='__main__': unittest.main()
