# scripts/aura_force_upload_snapshot.py
"""Upload snapshot R2 bo qua check 'giam so ma' - CHI dung khi da xac nhan
viec giam la hop le (vd: 1 ma bi huy niem yet), khong phai loi dong bo."""
from __future__ import annotations
import hashlib, json, sys, tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.aura_fullmarket_snapshot import pack, load_dotenv
from core.aura_r2_market import client, prefix, setting

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def main():
    load_dotenv(ROOT)
    s3 = client()
    with tempfile.TemporaryDirectory(prefix="aura_pack_") as td:
        file = Path(td) / "aura_market.zip"
        details = pack(ROOT, file)
        base, bucket = prefix(), setting("AURA_R2_BUCKET")
        key = f"{base}/snapshots/{details['sha256']}.zip"
        s3.upload_file(str(file), bucket, key, ExtraArgs={"ContentType": "application/zip"})
        current = {**details, "zip_key": key,
                   "published_at": datetime.now(TZ).isoformat(timespec="seconds"),
                   "source": "SSI FastConnect EOD; private storage"}
        s3.put_object(Bucket=bucket, Key=f"{base}/current.json",
                      Body=json.dumps(current, ensure_ascii=False).encode("utf-8"),
                      ContentType="application/json", CacheControl="no-store")
        print("[FORCE-UPLOADED]", details["ohlcv_files"], "ma, as_of", details["as_of"])


if __name__ == "__main__":
    main()