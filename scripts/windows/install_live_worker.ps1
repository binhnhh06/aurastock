<#
AURA - Cài worker giá realtime SSI chạy tự động trong giờ giao dịch (Windows Task Scheduler)

Worker giữ SSI WebSocket trên máy này và đẩy snapshot lên Cloudflare R2 mỗi 5 giây.
Bản online (Streamlit Cloud) đọc snapshot đó để HIỂN THỊ giá; mọi chỉ báo vẫn tính bằng EOD.

Chạy (PowerShell thường, không cần Admin):
    powershell -ExecutionPolicy Bypass -File .\install_live_worker.ps1 -Project "C:\Users\binh1\Projects\batday_ssi_project"
Tùy chọn:
    -RunNow       Chạy thử worker ngay (Ctrl+C để dừng), không tạo lịch
    -Uninstall    Gỡ lịch đã tạo
#>
param(
    [Parameter(Mandatory = $true)][string]$Project,
    [string]$TaskName = "AURA SSI Live Worker",
    [string]$StartTime = "08:50",
    [switch]$RunNow,
    [switch]$Uninstall
)
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
function Fail($m) { Write-Host "[DỪNG] $m" -ForegroundColor Red; exit 1 }

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Đã gỡ lịch '$TaskName'."; exit 0
}

$py = Join-Path $Project ".venv\Scripts\python.exe"
$worker = Join-Path $Project "scripts\ssi_live_worker.py"
$envFile = Join-Path $Project ".env"
if (-not (Test-Path $py)) { Fail "Không thấy $py" }
if (-not (Test-Path $worker)) { Fail "Không thấy $worker" }
if (-not (Test-Path (Join-Path $Project "data\ssi_cache\market_symbols.csv"))) {
    Fail "Thiếu data\ssi_cache\market_symbols.csv (danh mục SSI). Hãy chạy đồng bộ SSI trước."
}

# Chỉ kiểm tra TÊN biến, không in giá trị.
$need = "SSI_CLIENT_ID","SSI_API_KEY","SSI_API_SECRET","AURA_R2_ENDPOINT","AURA_R2_BUCKET","AURA_R2_ACCESS_KEY_ID","AURA_R2_SECRET_ACCESS_KEY"
$have = @()
if (Test-Path $envFile) { $have = Get-Content $envFile -Encoding UTF8 | ForEach-Object { ($_ -split "=",2)[0].Trim() } }
$missing = $need | Where-Object { ($have -notcontains $_) -and -not [Environment]::GetEnvironmentVariable($_) }
if ($missing) {
    Write-Host "[CẢNH BÁO] .env thiếu: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host "  Thiếu SSI_* thì worker không chạy; thiếu AURA_R2_* thì chỉ ghi file local, bản online không có giá realtime."
    if ((Read-Host "Vẫn tiếp tục? (y/N)") -ne "y") { exit 1 }
}

New-Item -ItemType Directory -Force -Path (Join-Path $Project "logs") | Out-Null

if ($RunNow) {
    Write-Host "Chạy thử worker (Ctrl+C để dừng). Xem dòng 'R2_LIVE' và 'WATCHLIST_CO_DINH'..." -ForegroundColor Cyan
    Set-Location $Project
    & $py $worker
    exit $LASTEXITCODE
}

$log = Join-Path $Project "logs\live_worker.log"
$cmd = "Set-Location -LiteralPath '$Project'; & '$py' -u '$worker' *>> '$log'"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command `"$cmd`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $StartTime
# Tự dừng sau 6 giờ 20 phút (08:50 → 15:10, hết phiên ATC 14:45) và tự khởi động lại nếu worker lỗi.
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 6 -Minutes 20) `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 2) -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "AURA: SSI WebSocket -> R2 (chỉ hiển thị giá realtime), thứ 2-6 trong giờ giao dịch" -Force | Out-Null

Write-Host "[XONG] Đã tạo lịch '$TaskName': thứ 2-6 lúc $StartTime, tự dừng sau 6h20." -ForegroundColor Green
Write-Host "  Log: $log"
Write-Host "  Chạy ngay để kiểm tra: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Gỡ lịch: powershell -ExecutionPolicy Bypass -File .\install_live_worker.ps1 -Project '$Project' -Uninstall"
Write-Host "  Lưu ý: máy phải bật (không Sleep) trong giờ giao dịch thì bản online mới có giá realtime."
