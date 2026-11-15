from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_release_structure():
    for p in ['app.py','requirements.txt','.env.example','.gitignore','docs/ARCHITECTURE.md','docs/CLOUD_READINESS.md']:
        assert (ROOT/p).is_file(), p
    assert not (ROOT/'.env').exists()
    assert not (ROOT/'data'/'ssi_cache').exists()
    assert not list(ROOT.rglob('*.sqlite'))
if __name__=='__main__':
    test_release_structure(); print('[OK] Release files and privacy gates')
