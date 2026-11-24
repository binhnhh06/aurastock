# scripts/check_r2_manifest.py
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
except ImportError:
    pass
from core.aura_r2_market import client, prefix, setting
s3 = client()
bucket, base = setting('AURA_R2_BUCKET'), prefix()
current = json.loads(s3.get_object(Bucket=bucket, Key=f'{base}/current.json')['Body'].read(8192))
print(json.dumps(current, ensure_ascii=False, indent=2))