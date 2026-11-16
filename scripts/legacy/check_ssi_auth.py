import sys as _aura_sys
from pathlib import Path as _AuraPath
_aura_sys.path.insert(0, str(_AuraPath(__file__).resolve().parents[2]))  # gốc dự án (file đã chuyển vào scripts/legacy)


import os
from pathlib import Path

from dotenv import load_dotenv
from ssi_sdk import Auth, Config
from ssi_sdk.exceptions import AuthenticationError, SSIError

# Đọc file .env của dự án
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path, override=True)

keys = [
    "SSI_CLIENT_ID",
    "SSI_API_KEY",
    "SSI_API_SECRET"
]

print("=" * 50)
print("KIEM TRA XAC THUC SSI FASTCONNECT V3")
print("=" * 50)

# Chỉ kiểm tra có cấu hình hay không
# Không in bất kỳ khóa bí mật nào
missing = []

for key in keys:
    value = os.getenv(key, "")
    valid = bool(value.strip()) and not value.strip().startswith("DIEN_")
    print(f"{key}: {'OK' if valid else 'THIEU'}")

    if not valid:
        missing.append(key)

if missing:
    print("\nVui long kiem tra file .env")
    raise SystemExit(1)

config = Config(
    client_id=os.environ["SSI_CLIENT_ID"].strip(),
    api_key=os.environ["SSI_API_KEY"].strip(),
    api_secret=os.environ["SSI_API_SECRET"].strip()
)

print("\nDang thu xac thuc...")

try:
    with Auth(config) as auth:
        auth.authenticate()

    print("XAC THUC THANH CONG!")
    print("SSI credentials da duoc chap nhan.")

except AuthenticationError as e:
    print("\nXAC THUC THAT BAI")
    print("Loai loi: AuthenticationError")
    print("HTTP status:", e.status_code)
    print("SSI error code:", e.code)
    print("Thong bao:", e.message)

except SSIError as e:
    print("\nLOI SSI SDK")
    print("Loai loi:", type(e).__name__)
    print("HTTP status:", e.status_code)
    print("SSI error code:", e.code)
    print("Thong bao:", e.message)

except Exception as e:
    print("\nLOI KHAC")
    print("Loai loi:", type(e).__name__)
    print("Khong in chi tiet de tranh lo thong tin nhay cam.")
