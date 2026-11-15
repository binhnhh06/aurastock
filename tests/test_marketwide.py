import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace, ModuleType
from unittest.mock import patch

import pandas as pd
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from core.ssi_universe import classify, save_catalogue, screener_symbols, load_catalogue, validate_symbol
from scripts.install_marketwide import transform
from scripts.ssi_fetch_symbol import persist

class TestCatalogue(unittest.TestCase):
    def test_equity_vs_warrant(self):
        self.assertEqual(classify(SimpleNamespace(stock_type='stock', listed_shares=1)), 'EQUITY')
        self.assertEqual(classify(SimpleNamespace(stock_type='STOCK', cw_underlying_symbol='FPT')), 'NON_EQUITY')
        self.assertEqual(classify(SimpleNamespace(stock_type='unknown', listed_shares=123)), 'EQUITY_CANDIDATE')
        self.assertEqual(classify(SimpleNamespace(stock_type='ETF')), 'NON_EQUITY')

    def test_full_market_fallback(self):
        with TemporaryDirectory() as td:
            path=Path(td)/'data/ssi_cache'
            path.mkdir(parents=True)
            pd.DataFrame({'symbol':['FPT','SSI']}).to_csv(path/'vn30_symbols.csv',index=False)
            self.assertEqual(screener_symbols(td),['FPT','SSI'])
            df=pd.DataFrame({'symbol':['FPT','VGI','E1VFVN30'],'board':['HOSE','UPCOM','HOSE'],
                             'name':['FPT','VGI','ETF'],'sector':['IT','IT','Fund'],
                             'asset_class':['EQUITY','EQUITY_CANDIDATE','NON_EQUITY'],
                             'equity_scan':[True,True,False]})
            save_catalogue(df,path/'market_symbols.csv')
            self.assertEqual(screener_symbols(td),['FPT','VGI'])
            self.assertEqual(validate_symbol('vgi',td),'VGI')
            with self.assertRaises(ValueError): validate_symbol('../escape',td)

    def test_installer_no_guess(self):
        a='''def scan_cached_universe(root):\n    universe_file = root / "data" / "ssi_cache" / "vn30_symbols.csv"\n    prices_dir = 1\n    symbols = pd.read_csv(universe_file, encoding="utf-8-sig")["symbol"].dropna().astype(str).str.strip().str.upper().drop_duplicates().tolist()\n    return symbols\n'''
        b,changed=transform(a)
        self.assertTrue(changed)
        self.assertIn('screener_symbols(root)',b)
        self.assertFalse(transform(b)[1])
        with self.assertRaises(ValueError): transform('x = 1\n')

    def test_persist_merges_and_excludes_future(self):
        with TemporaryDirectory() as td:
            path=Path(td)/'FPT.csv'
            a=pd.DataFrame({'symbol':['FPT'],'date':['2026-11-10'],'open':[100], 'high':[101],
                            'low':[99], 'close':[100], 'volume':[100]})
            b=pd.DataFrame({'symbol':['FPT','FPT'],'date':['2026-11-10','2026-11-12'],'open':[105,108],
                            'high':[108,110],'low':[100,107],'close':[106,109],'volume':[300,400]})
            persist('FPT',a,path,'2026-11-11')
            self.assertEqual(persist('FPT',b,path,'2026-11-11'),1)
            c=pd.read_csv(path)
            self.assertEqual(float(c.close.iloc[-1]),106.)
            self.assertEqual(len(c),1)

    def test_partial_board_failure_is_not_saved(self):
        class FakeBoard:
            HOSE='HOSE'; HNX='HNX'; UPCOM='UPCOM'
        fake=ModuleType('ssi_sdk.enums')
        fake.Board=FakeBoard
        from core.ssi_universe import collect_market_catalogue
        svc=SimpleNamespace(get_securities_info_by_board=lambda board:
                            (_ for _ in ()).throw(RuntimeError('fail')) if board=='UPCOM' else [SimpleNamespace(symbol='FPT',stock_type='STOCK',symbol_name_vi='FPT')])
        with patch.dict(sys.modules, {'ssi_sdk.enums':fake}):
            with self.assertRaises(RuntimeError):collect_market_catalogue(svc)

if __name__=='__main__': unittest.main()
