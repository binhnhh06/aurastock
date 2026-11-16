<#
AURA - Runbook hoàn thiện và nộp đồ án (chạy từng bước theo ngày)

Chạy trong PowerShell (thư mục bất kỳ):
  $rb = "$HOME\aurastock\scripts\windows\aura_runbook.ps1"
  powershell -ExecutionPolicy Bypass -File $rb -Task <tên bước>

Các bước:
  setup        16/11  Tạo/cập nhật bản clone sạch $HOME\aurastock, cài thư viện vào .venv, cài lịch worker
  status       17-19/11 (cuối ngày)  Worker có chạy không, log, số phiên WebSocket đã lưu
  evidence     19/11  Chạy pytest, kiểm kê dữ liệu, backtest, tóm tắt WebSocket → thư mục gửi Claude
  publish      19/11  Commit + push bằng chứng (docs/evidence) lên GitHub (hỏi y/N)
  stopworker   19/11 tối  Dừng và gỡ lịch worker (để bật lại realtime trên web)
  package      20/11  Tạo file nộp MSSV_HoTen_NEOAPI_FinTech.zip từ GitHub (không có khóa/dữ liệu)

Tham số:
  -Project  Dự án có .env + data (mặc định C:\Users\<bạn>\Projects\batday_ssi_project)
  -MSSV -HoTen   Dùng cho bước package (HoTen viết liền không dấu, vd NguyenVanLoc)
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("setup", "status", "evidence", "publish", "stopworker", "package")]
    [string]$Task,
    [string]$Project = "$HOME\Projects\batday_ssi_project",
    [string]$Repo = "$HOME\aurastock",
    [string]$RepoUrl = "https://github.com/binhnhh06/aurastock.git",
    [string]$MSSV = "",
    [string]$HoTen = ""
)
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$TaskName = "AURA SSI Live Worker"
$Py = Join-Path $Project ".venv\Scripts\python.exe"
$Send = Join-Path ([Environment]::GetFolderPath("Desktop")) "AURA_gui_Claude"
function Step($m) { Write-Host "`n=== $m" -ForegroundColor Cyan }
function Ok($m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[CHÚ Ý] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[DỪNG] $m" -ForegroundColor Red; exit 1 }
function Ask($m) { return ((Read-Host "$m (y/N)") -eq "y") }

if (-not (Test-Path $Py)) { Fail "Không thấy $Py. Kiểm tra -Project." }

function Update-Repo {
    if (-not (Test-Path (Join-Path $Repo ".git"))) {
        & git clone $RepoUrl $Repo
        if ($LASTEXITCODE -ne 0) { Fail "Không clone được $RepoUrl" }
    } else {
        Push-Location $Repo
        $dirty = & git status --porcelain
        if ($dirty) { Warn "Bản clone có thay đổi chưa commit, bỏ qua git pull:`n$($dirty -join "`n")" }
        else { & git pull --ff-only origin main }
        Pop-Location
    }
    Ok "Bản clone: $Repo ($((& git -C $Repo log --oneline -1)))"
}

switch ($Task) {

"setup" {
    Step "1. Bản clone sạch từ GitHub"
    Update-Repo
    Step "2. Cài thư viện cho .venv (theo requirements của GitHub) + pytest, matplotlib"
    & $Py -m pip install -q -r (Join-Path $Repo "requirements.txt") pytest matplotlib
    & $Py -c "import pandas; print('pandas', pandas.__version__)"
    Step "3. Chép file worker mới nhất vào dự án (có sao lưu)"
    $files = "core\aura_log.py","core\aura_live_r2.py","core\live_archive.py","core\ssi_market_live.py",
             "scripts\ssi_live_worker.py","scripts\live_archive_summary.py","scripts\windows\install_live_worker.ps1"
    $bk = Join-Path $Project (".aura_backups\runbook_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    foreach ($f in $files) {
        $src = Join-Path $Repo $f; $dst = Join-Path $Project $f
        if (Test-Path $dst) { New-Item -ItemType Directory -Force -Path (Split-Path (Join-Path $bk $f)) | Out-Null; Copy-Item $dst (Join-Path $bk $f) -Force }
        New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
        Copy-Item $src $dst -Force
    }
    Ok "Đã chép $($files.Count) file. Bản cũ: $bk"
    Step "4. Lịch worker thu dữ liệu WebSocket (thứ 2-6, 08:50, tự dừng sau 6h20)"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Project "scripts\windows\install_live_worker.ps1") -Project $Project
    Write-Host ""
    Warn "Nhớ: Streamlit Cloud → Settings → Secrets đặt AURA_LIVE_ENABLED = `"0`" trong các ngày worker chạy."
    Warn "Máy phải bật (không Sleep) từ 8:50 đến 15:10."
}

"status" {
    Step "Lịch worker"
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) { $i = $t | Get-ScheduledTaskInfo; Write-Host "  Trạng thái: $($t.State) · Lần chạy cuối: $($i.LastRunTime) · Kết quả: $($i.LastTaskResult)" }
    else { Warn "Chưa có lịch '$TaskName'. Chạy -Task setup." }
    Step "20 dòng log cuối"
    $log = Join-Path $Project "logs\live_worker.log"
    if (Test-Path $log) { Get-Content $log -Tail 20 } else { Warn "Chưa có $log" }
    Step "Dữ liệu WebSocket đã lưu"
    Push-Location $Project
    & $Py scripts\live_archive_summary.py
    Pop-Location
}

"evidence" {
    Update-Repo
    New-Item -ItemType Directory -Force -Path $Send, (Join-Path $Send "anh_chup") | Out-Null
    $ev = Join-Path $Repo "docs\evidence"
    New-Item -ItemType Directory -Force -Path $ev | Out-Null
    Push-Location $Repo
    Step "1/5 Kiểm thử tự động (pytest)"
    & $Py -m pytest -q tests -p no:cacheprovider 2>&1 | Tee-Object -FilePath (Join-Path $ev "pytest_result.txt")
    Step "2/5 Kiểm kê dữ liệu trên máy"
    & $Py scripts\aura_data_inventory.py --root $Project 2>&1 | Tee-Object -FilePath (Join-Path $ev "data_inventory.txt")
    Step "3/5 Event study (backtest) ~1 phút"
    & $Py scripts\aura_backtest_event.py --data (Join-Path $Project "data\ssi_cache\ohlcv") 2>&1 |
        Where-Object { $_ -notmatch "^\s+\d+/\d+ mã" } | Tee-Object -FilePath (Join-Path $ev "backtest_console.txt")
    Step "4/5 Tóm tắt dữ liệu WebSocket"
    & $Py scripts\live_archive_summary.py --root $Project --out $ev 2>&1 | Tee-Object -FilePath (Join-Path $ev "live_archive_console.txt")
    $events = Get-ChildItem (Join-Path $Project "data\ssi_cache\live_archive") -Filter "*_events.csv" -ErrorAction SilentlyContinue
    if ($events) { $events | Copy-Item -Destination $ev -Force }
    Step "5/5 Lịch sử commit"
    & git log --oneline -40 | Out-File -Encoding utf8 (Join-Path $ev "git_log.txt")
    Pop-Location
    $log = Join-Path $Project "logs\live_worker.log"
    if (Test-Path $log) { Get-Content $log -Tail 200 | Out-File -Encoding utf8 (Join-Path $Send "live_worker_log_tail.txt") }
    Copy-Item (Join-Path $ev "*") $Send -Force
    $zip = Join-Path ([Environment]::GetFolderPath("Desktop")) "AURA_gui_Claude.zip"
    Compress-Archive -Path (Join-Path $Send "*") -DestinationPath $zip -Force
    Ok "Bằng chứng đã nằm ở: $ev (để publish) và $Send"
    Write-Host "  → Bỏ ảnh chụp màn hình vào $Send\anh_chup rồi chạy lại -Task evidence (hoặc nén lại thư mục)."
    Write-Host "  → Gửi Claude file: $zip"
}

"publish" {
    Push-Location $Repo
    & git add -- docs/evidence
    $staged = & git diff --cached --name-only
    if (-not $staged) { Pop-Location; Fail "Không có gì mới trong docs/evidence. Chạy -Task evidence trước." }
    $other = $staged | Where-Object { $_ -notlike "docs/evidence/*" }
    if ($other) { & git reset -q; Pop-Location; Fail "Có file ngoài docs/evidence bị stage: $($other -join ', ')" }
    & git diff --cached --stat
    if (Ask "Commit và push các file bằng chứng trên?") {
        & git commit -m "docs: bằng chứng kiểm chứng (pytest, kiểm kê dữ liệu, event study, WebSocket)"
        & git push origin main
        if ($LASTEXITCODE -eq 0) { Ok "Đã push." } else { Warn "Push lỗi, chạy lại: cd $Repo; git push origin main" }
    } else { & git reset -q; Write-Host "Đã hủy." }
    Pop-Location
}

"stopworker" {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $Py } |
        Where-Object { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -match "ssi_live_worker" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Ok "Đã dừng và gỡ lịch worker."
    Warn "Giờ vào Streamlit Cloud → Settings → Secrets đặt AURA_LIVE_ENABLED = `"1`" → Save → Reboot app."
}

"package" {
    if (-not $MSSV -or -not $HoTen) { Fail "Cần -MSSV và -HoTen, vd: -MSSV K224141234 -HoTen NguyenVanLoc" }
    Update-Repo
    $desk = [Environment]::GetFolderPath("Desktop")
    $name = "${MSSV}_${HoTen}_NEOAPI_FinTech.zip"
    $out = Join-Path $desk $name
    Push-Location $Repo
    & git archive --format=zip --prefix=aurastock/ -o $out HEAD
    Pop-Location
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [System.IO.Compression.ZipFile]::OpenRead($out)
    $bad = $z.Entries | Where-Object { $_.FullName -match '(^|/)\.env$|secrets\.toml|\.sqlite3?$|(^|/)data/ssi_cache/' }
    $count = $z.Entries.Count; $z.Dispose()
    if ($bad) { Remove-Item $out; Fail "File nộp chứa dữ liệu nhạy cảm: $($bad.FullName -join ', ')" }
    Ok "Đã tạo $out ($count mục, không có .env/khóa/dữ liệu riêng)."
    Write-Host "  Kèm theo khi nộp: ${MSSV}_${HoTen}_BaoCao.docx và ${MSSV}_${HoTen}_Demo.mp4 (hoặc link video)."
    Write-Host "  Link sản phẩm: https://aura-stock-filter.streamlit.app/ · Mã nguồn: https://github.com/binhnhh06/aurastock"
}
}
