# AURA Stock — Hệ thống phân tích và sàng lọc cổ phiếu Việt Nam

> **Đồ án FinTech / nguyên mẫu nghiên cứu học thuật** · SSI FastConnect V3 · Python · Streamlit · Cloudflare R2
> **Trạng thái:** đang hoàn thiện kiểm thử. Tín hiệu kỹ thuật đã được kiểm chứng bằng backtest ở hai cấp độ — event study (mục 8.4) và danh mục (mục 8.5), kết quả chi tiết kèm giới hạn phương pháp trình bày đầy đủ ở mục 8. Đây là công cụ hỗ trợ nghiên cứu, sàng lọc và giải thích dữ liệu — không phải hệ thống khuyến nghị đầu tư hay đặt lệnh giao dịch.

**Website:** https://aura-stock-filter.streamlit.app/
**Mã nguồn:** https://github.com/binhnhh06/aurastock

## 1. Giới thiệu và mục tiêu

AURA Stock hỗ trợ nghiên cứu cổ phiếu Việt Nam theo một quy trình thống nhất: **quan sát thị trường → lựa chọn khẩu vị → phân tích mã → kiểm tra kỹ thuật và tài chính → xem thiết lập giao dịch → theo dõi danh mục mô phỏng**. Mục tiêu là hỗ trợ sinh viên và nhà đầu tư cá nhân **sàng lọc, giải thích và so sánh điều kiện đầu tư** từ dữ liệu có nguồn, không thay thế thẩm định tài chính hoặc tư vấn đầu tư cá nhân.

Các câu hỏi nghiên cứu chính:

1. Có thể tích hợp dữ liệu SSI EOD, chỉ số thị trường và BCTC vào cùng một giao diện dễ sử dụng không?
2. Bộ lọc theo khẩu vị, xu hướng, breakout, pullback và giá trị hỗ trợ phát hiện **ứng viên để nghiên cứu** như thế nào?
3. Khi dữ liệu tài chính chưa được kiểm chứng, hệ thống có thể **tách tín hiệu kỹ thuật khỏi xác nhận cơ bản** để tránh kết luận quá mức không?
4. Kết quả chiến lược có bền vững khi tính đến chi phí giao dịch, biến động thị trường và dữ liệu ngoài mẫu không? **Đã kiểm chứng ở mục 8.4 và 8.5, và câu trả lời là chưa: xét từng lần mua riêng lẻ, tín hiệu cho lời; nhưng khi gộp lại thành một danh mục theo dõi liên tục qua các kỳ (giai đoạn ngoài mẫu 24/11/2025–15/10/2026), danh mục theo tín hiệu AURA lại lỗ nhiều, mức lời không bù được rủi ro đã bỏ ra (Sharpe -1,98), và thua cả VN-Index lẫn danh mục không lọc (baseline) — tức ở quy mô cả danh mục, tín hiệu chưa bền vững trong giai đoạn kiểm thử này.**

## 2. Chức năng chính

| Nhóm | Mô tả | Trạng thái xác minh |
|---|---|---|
| Toàn cảnh thị trường | VN-Index, VN30, HNX-Index, UPCoM-Index: điểm, biến động, KLGD, GTGD, ngày phiên | Đã có bản tin SSI EOD trên R2, có lịch tự động cập nhật hằng ngày (mục 7); mới triển khai 24/11/2026, chưa qua nhiều phiên để xác nhận ổn định |
| Phân tích cổ phiếu | Giá SSI EOD, các đường MA, RSI, đồ thị đa khung | Đã hiển thị; cần rà soát giá điều chỉnh/corporate actions |
| Hợp khẩu vị | Bộ tiêu chí và ngưỡng theo hồ sơ người dùng; phân biệt Đạt / Không đạt / N/A | Có chức năng; cần soát nhất quán điểm dữ liệu |
| Báo cáo tài chính | Bảng cân đối kế toán, KQKD, lưu chuyển tiền tệ nhiều năm, lọc chỉ tiêu | Đã thấy trên website; chưa xác minh với bản công bố chính thức |
| Tỷ số tài chính | Các tỷ số tính từ BCTC và đồ thị | Hiển thị dưới dạng **tham khảo** khi nguồn chưa xác minh |
| Quét thị trường | Sàng lọc các mã theo bộ tiêu chí đang chọn | Có chức năng; đã backtest (mục 8.4–8.5) — hiệu quả dương ở mức sự kiện riêng lẻ, nhưng không vượt trội ở cấp danh mục ngoài mẫu |
| Vĩ mô & Chính sách | Dữ liệu thị trường/khối ngoại EOD và tin/chính sách có nguồn | Khối ngoại đã đồng bộ lên R2 (hiện chỉ VN30 + 10 phiên gần nhất), chưa chứng minh bao phủ toàn thị trường |
| Hiểu doanh nghiệp | Hồ sơ, ngành, chỉ tiêu tài chính, bối cảnh và định giá khi đủ đầu vào | Có chức năng; một số trường có thể N/A |
| Theo dõi danh mục | Lưu danh sách và tính lãi/lỗ mô phỏng theo cấu hình đang có | Cần kiểm thử độ bền lưu trữ và phân tách người dùng trên Cloud |

> **Về phạm vi BCTC:** log kiểm kê ngày 15/11/2026 ghi nhận 1.518 mã trong danh sách hợp nhất, 1.515 mã được xử lý R2 (681 đầy đủ theo bộ kiểm tra, 834 thiếu một phần); 3 mã BCG, PSH, VE8 cần xác minh upload độc lập. Các con số này là **snapshot kiểm kê**, không phải cam kết dữ liệu đầy đủ hoặc được kiểm toán.

## 3. Kiến trúc

```text
SSI FastConnect V3 (OHLCV, chỉ số, khối ngoại)
            │
            ▼
    Bộ đồng bộ Python (local / job có kiểm soát)
            │
            ├── Cache dữ liệu EOD local (không commit)
            └── Cloudflare R2 private (snapshot hợp lệ, tách quyền)
                            │
BCTC từ nguồn đã thu thập ──┤  (đánh dấu chưa xác minh)
                            ▼
                 Streamlit Cloud / AURA
                ├── Tổng quan & biểu đồ
                ├── Khẩu vị và sàng lọc
                ├── BCTC & tỷ số tham khảo
                ├── Cơ hội mua / cảnh báo rủi ro
                └── Theo dõi danh mục mô phỏng
```

**Phân tách quan trọng:** giá EOD dùng cho chỉ báo khác với tick realtime; BCTC sơ bộ không được nâng thành dữ liệu đã công bố; dữ liệu giao dịch khối ngoại không thể suy ra từ chỉ số thị trường. Không công khai API key, dữ liệu hạn chế phân phối hoặc danh mục cá nhân trên GitHub.

## 4. Phương pháp đánh giá

### 4.1. Chỉ báo kỹ thuật

- **SMA(n)** là trung bình đóng cửa của `n` phiên; ứng dụng sử dụng các cửa sổ như 20, 50 và 200 phiên.
- **RSI(14)** mô tả động lượng giá trong khoảng 0–100.
- Các điều kiện xu hướng, breakout, pullback dựa trên quan hệ giá–MA, độ dốc xu hướng, động lượng và khối lượng.
- Lớp đánh giá chính sách còn kiểm tra độ mới EOD, dữ liệu giá bất thường, thanh khoản, xu hướng VN-Index cùng phiên và cảnh báo rủi ro. Ngưỡng trong code là **giả thuyết nghiên cứu**, chưa được tối ưu hóa hay kiểm định hiệu quả.

### 4.2. Phân loại ứng viên

- **Ứng viên nghiên cứu:** thiết lập được bộ xác nhận hiện tại chấp thuận, *không phải lệnh mua*.
- **Theo dõi:** có cấu trúc kỹ thuật hoặc điều kiện sơ bộ nhưng thiếu xác nhận.
- **Cảnh báo:** xu hướng giảm, sụt giảm đáng kể hoặc điểm tổng hợp thấp; *không phải lệnh bán tự động*.
- **N/A:** không có dữ liệu đủ tin cậy để đánh giá điều kiện. **N/A không được tính là Đạt hoặc Không đạt.**

### 4.3. Phân tích cơ bản và BCTC

Bảng BCTC trên R2 được chuyển từ kho dữ liệu nghiên cứu và có thể thiếu báo cáo/năm. Tỷ số ROE, biên lợi nhuận, Nợ/VCSH, P/E, P/B và tăng trưởng chỉ được trình bày khi có đủ đầu vào. Muốn dùng cho **đánh giá giá trị đã xác minh**, cần thêm nguồn báo cáo công bố, ngày công bố, đơn vị số liệu và kiểm tra điều chỉnh hồi tố. Không suy diễn rằng có BCTC trên R2 đồng nghĩa đã kiểm chứng nguồn.

### 4.4. Mô hình điểm

Ứng dụng có các điểm kỹ thuật/cơ bản và kết quả phân loại theo ngưỡng. Trong đồ án, gọi chung là **“Điểm đánh giá”**, không dùng tên nội bộ của thuật toán trên màn hình. Điểm này là thước đo điều kiện nghiên cứu, **không phải xác suất tăng giá hay xác suất thắng**.

### 4.5. Cơ sở lựa chọn ngưỡng và trọng số (bổ sung)

- **Ngưỡng điểm đánh giá tổng hợp (≥80/100):** mới nâng từ ≥60 lên ≥80, theo quy ước của Validea — đơn vị nghiên cứu định lượng mô phỏng chiến lược các nhà đầu tư nổi tiếng (Warren Buffett, Benjamin Graham, Peter Lynch, Joel Greenblatt...), nơi điểm ≥80/100 được họ gọi là "có quan tâm" và ≥90/100 là "quan tâm mạnh". Hướng này cũng phù hợp với Piotroski F-Score (Đại học Stanford, công bố năm 2000 trên *Journal of Accounting Research*), nơi điểm 8–9/9 (~89–100%) được coi là cổ phiếu giá trị tốt. **Đã cập nhật:** backtest ở mục 8.4–8.5 được chạy lại với ngưỡng ≥80 mới (24/11/2026). Kết quả: event study không còn lợi thế rõ ràng như ở ngưỡng ≥60 cũ (lẫn lộn giữa hai giai đoạn), và backtest danh mục ngoài mẫu còn xấu hơn một chút về Sharpe (-2,14 so với -1,98 cũ) do tỷ lệ kỳ thắng giảm còn 8,3%. Tức nâng ngưỡng theo nguồn uy tín hơn **không tự động cải thiện** hiệu quả chiến lược — xem chi tiết và diễn giải nguyên nhân ở mục 8.4–8.5.
- **Trọng số kỹ thuật/cơ bản/định giá trong Smart Rating V7 (sơ bộ, chưa dùng đặt lệnh):** đổi từ 50/35/15 (không có căn cứ) sang chia đều ~33/33/34, theo nguyên tắc "đa dạng hóa ngây thơ" (naive diversification, 1/N) của DeMiguel, Garlappi & Uppal (2009, *Review of Financial Studies*) — nghiên cứu cho thấy trọng số chia đều thường ổn định hơn ngoài mẫu so với trọng số tự chọn khi chưa có đủ dữ liệu để ước lượng trọng số tối ưu đáng tin cậy.
- **Ngưỡng thanh khoản GTGD TB20 ≥ 2 tỷ đồng/phiên:** thấp hơn có chủ đích so với tiêu chí thanh khoản chính thức của HOSE cho rổ VN30 (tối thiểu 10 tỷ đồng/ngày theo bộ chỉ số phiên bản 3.1, nâng lên 30 tỷ đồng/ngày từ phiên bản 4.0 có hiệu lực tháng 1/2025). Lý do: AURA là công cụ sàng lọc **ứng viên nghiên cứu diện rộng** (gồm cả mã vốn hóa vừa/nhỏ), không phải tiêu chí chọn cổ phiếu blue-chip vào chỉ số — nên cố ý đặt ngưỡng thấp hơn để không bỏ sót mã có tín hiệu. Đây là lựa chọn phạm vi có chủ đích, không tương đương với ngưỡng của HOSE.
- **RSI(14) và cặp MA50/MA200:** chu kỳ RSI 14 theo đúng công bố gốc của J. Welles Wilder Jr. (*New Concepts in Technical Trading Systems*, 1978). Cặp MA50/MA200 (dùng trong bộ lọc chế độ VN-Index ≥ MA50) theo đúng cấu hình "golden cross/death cross" phổ biến nhất trong phân tích kỹ thuật, cân bằng giữa độ nhạy (~2 tháng) và độ ổn định (~10 tháng); một số nguồn (ví dụ Fisher Investments) ghi nhận thẳng rằng bản thân con số 50/200 chỉ là quy ước phổ biến, chưa có chứng minh toán học là tối ưu — AURA kế thừa quy ước này như phần lớn công cụ kỹ thuật khác, không tự phát minh ra con số riêng.
- **Trọng số 0,2 (cơ bản) / 0,8 (kỹ thuật) trong công thức điểm tổng hợp chính (`core/strategy.py`):** đây là lựa chọn heuristic riêng của nhóm, hiện **chưa có nguồn đối chiếu bên ngoài** và chưa được kiểm định thống kê — khác với trọng số Smart Rating V7 nói trên. Nêu rõ ở đây để tránh gây hiểu nhầm là đã có căn cứ học thuật cho toàn bộ mô hình điểm.

## 5. Hướng dẫn sử dụng website

1. Truy cập **[AURA Stock](https://aura-stock-filter.streamlit.app/)**.
2. Chọn **khẩu vị đầu tư**, có thể mở *Tùy chỉnh tiêu chí lọc* để thay các ngưỡng.
3. Nhập mã cổ phiếu (ví dụ FPT, HPG, VNM) và chọn thời gian giá cùng số năm BCTC.
4. Nhấn **Phân tích**. Quan sát **Tổng quan → Hợp khẩu vị → Kỹ thuật → BCTC → Tỷ số → Vĩ mô → Hiểu doanh nghiệp**.
5. Đọc phần **Điều kiện để xem xét mua**, **Cảnh báo rủi ro** và giải thích. Không hiểu N/A là tín hiệu bán; không hiểu “Đạt” là lệnh mua.
6. Nếu cần, mở trang quét thị trường, danh mục theo dõi hoặc xuất báo cáo/CSV ở nơi ứng dụng hỗ trợ.

> Dữ liệu EOD có ngày phiên riêng. Ngày nghỉ không có phiên mới. Realtime chỉ được công bố nếu hệ thống có bản tin tick hợp lệ.

## 6. Chạy trên máy (Windows PowerShell)

Yêu cầu: Python 3.12, Git và môi trường được cấp quyền truy cập dữ liệu. Không cần đưa API key lên mã nguồn.

```powershell
git clone https://github.com/binhnhh06/aurastock.git
cd aurastock

# Khi chưa tạo .venv:
py -3.12 -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Mã nguồn công khai chưa chứa kho cache giá EOD, BCTC private, secrets và dữ liệu cá nhân. Nếu clone từ GitHub, phải cấu hình nguồn và quyền dữ liệu riêng trước khi kỳ vọng hiển thị đầy đủ mọi chức năng. Không commit `.env`, `.streamlit/secrets.toml`, dữ liệu BCTC có giới hạn quyền, CSV SSI riêng hoặc cơ sở dữ liệu danh mục.

## 7. Đồng bộ dữ liệu và triển khai Cloud

- **Dữ liệu giá / chỉ số / khối ngoại:** chạy các script SSI theo cấu hình đã được kiểm tra; xác minh số bản tin, ngày phiên, đơn vị, tỷ lệ lỗi, sau đó mới upload ảnh chụp R2 private.
  - **4 chỉ số** (VN-Index, VN30, HNX-Index, UPCoM-Index): `scripts/ssi_refresh_indices.py` (lấy EOD qua REST `indexSummary`) → `scripts/aura_upload_index_summary.py` (đẩy lên R2, key `index_summary/v103/{MÃ}.json`).
  - **Toàn bộ mã cổ phiếu** (OHLCV, ~1.560 mã): `scripts/aura_fullmarket_snapshot.py sync --mode stale` → `scripts/aura_fullmarket_snapshot.py upload` (đóng gói snapshot zip, đẩy lên R2). Có cơ chế tự chặn upload nếu số mã có dữ liệu giảm bất thường so với bản đang có trên R2, để tránh vô tình làm mất dữ liệu; trường hợp giảm hợp lệ (ví dụ 1 mã hủy niêm yết) xử lý thủ công qua `scripts/aura_force_upload_snapshot.py` sau khi xác minh.
  - **Khối ngoại:** `scripts/aura_sync_foreign.py --days 10 --vn30` → `scripts/aura_upload_foreign_flow.py` (đẩy lên R2, key `foreign_flow/v1/foreign_flow_eod.csv`). Hiện chỉ đồng bộ rổ VN30, chưa phủ toàn thị trường.
- **BCTC:** chỉ đẩy dữ liệu có quyền lưu trữ và hiển thị, giữ metadata nguồn và trạng thái kiểm chứng.
- **Website:** Streamlit Community Cloud từ repo `binhnhh06/aurastock`, nhánh `main`, entrypoint `app.py`.
- **Secrets:** đặt trong **Streamlit Cloud → App settings → Secrets**, không thêm vào GitHub. Đồng nhất endpoint, bucket, prefix, quyền R2 với bộ upload local. Khóa trong Streamlit Cloud Secrets là **khóa chỉ-đọc** (chỉ để app hiển thị); các script upload ở trên chạy trên máy cá nhân cần một khóa R2 **Read & Write** riêng, không dùng chung với khóa chỉ-đọc.
- **Lịch tự động EOD:** đã cài qua Windows Task Scheduler — `scripts/windows/install_eod_refresh.ps1`, chạy đủ cả 3 pipeline ở trên (4 chỉ số + toàn bộ mã + khối ngoại), vào 21:00 các ngày thứ 2–6, log tại `logs/eod_full_refresh.log`. **Cài đặt và chạy thử lần đầu ngày 24/11/2026; mới xác nhận chạy đúng 1 lần, chưa có chuỗi log nhiều ngày liên tục để coi là đã kiểm thử ổn định** — phụ thuộc máy cá nhân phải đang bật đúng giờ đã đặt lịch; chưa có cơ chế cảnh báo khi lịch không chạy được (ví dụ máy tắt/ngủ).

## 8. Kiểm thử và backtest

### 8.1. Kiểm thử tự động (tái hiện được, không cần API key)

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q tests
```

Bộ test dùng dữ liệu tổng hợp, không gọi SSI. Nội dung chính: chuẩn hóa OHLCV (giá âm, high/low sai, trùng phiên, thiếu cột), fallback sang cache khi SSI lỗi, chấm điểm X10 (khoảng điểm, không gán điểm cơ bản giả định khi thiếu BCTC, độ mới dữ liệu theo giờ Việt Nam), RSI chấm điểm trùng RSI biểu đồ, giới hạn tần suất REST, danh mục toàn thị trường không bị ghi đè bởi snapshot thiếu.

### 8.2. Nhật ký và giới hạn tần suất

- `core/aura_log.py` ghi log theo giờ Việt Nam ra stderr (Streamlit Cloud → *Manage app → Logs*) và `logs/aura.log` (không commit). Không ghi key/secret/token.
- Mọi lần gọi SSI REST trong `core/ssi_adapter.py` cách nhau tối thiểu `SSI_MIN_INTERVAL_SEC` giây (mặc định 1). Lỗi API, lần chuyển sang cache và số phiên tải được đều có log.
- Từ điển dữ liệu và danh sách nhóm API: `docs/DATA_DICTIONARY.md`.

### 8.3. Giá realtime trên bản online (chỉ hiển thị)

- **Tính toán:** MA, RSI, điểm, xếp hạng, backtest luôn dùng nến **SSI EOD**. Giá realtime **không** đi vào bất kỳ phép tính nào.
- **Hiển thị:** máy cá nhân chạy `scripts/ssi_live_worker.py` trong giờ giao dịch (Task Scheduler, xem `scripts/windows/install_live_worker.ps1`). Worker giữ SSI WebSocket, ghi `data/ssi_cache/live_market.json` và đẩy bản sao lên R2 (`<AURA_R2_PREFIX>/live/live_market.json`) mỗi `AURA_LIVE_R2_PUSH_SEC` giây (mặc định 5).
- Streamlit Cloud đọc snapshot từ R2 bằng khóa chỉ-đọc, cache 5 giây. Snapshot cũ hơn 30 giây hoặc tick cũ hơn 120 giây → thẻ giá ghi rõ “Giá khớp cuối” hoặc quay về “Giá đóng cửa (EOD)”.
- Worker luôn theo dõi `AURA_LIVE_SYMBOLS` + VN30 + các mã thanh khoản cao nhất (tối đa `AURA_LIVE_MAX`, mặc định 60) và thêm mã người dùng đang xem trên máy chạy worker. Mã ngoài danh sách hiển thị giá EOD.
- **Lưu trữ WebSocket (bằng chứng ≥ 5–10 phiên):** worker ghi các tick mới mỗi 60 giây vào `data/ssi_cache/live_archive/YYYY-MM-DD.csv` (giờ VN) và sự kiện kết nối vào `..._events.csv`. Tóm tắt: `python scripts/live_archive_summary.py` → `docs/evidence/live_archive_summary.csv`.
- Chi phí R2: khoảng 4.500 lần ghi/ngày giao dịch, nằm trong hạn mức miễn phí (1 triệu Class A, 10 triệu Class B/tháng).

### 8.4. Event study (kiểm chứng điểm kỹ thuật)

```powershell
.\.venv\Scripts\python.exe scripts\aura_backtest_event.py            # toàn bộ mã trong data/ssi_cache/ohlcv
.\.venv\Scripts\python.exe scripts\aura_backtest_event.py --limit 200 # chạy thử nhanh
```

- Quy tắc đóng băng theo `core/strategy.py`: điểm kỹ thuật ≥ 60, ≥ 200 phiên, GTGD TB20 ≥ 2 tỷ, VN-Index ≥ MA50 tại đóng cửa phiên t.
- Vào lệnh giá mở cửa t+1, thoát đóng cửa t+5/t+10/t+20, trừ chi phí khứ hồi 0,40%; lấy mẫu mỗi 5 phiên; 60% thời gian đầu là trong mẫu, phần còn lại ngoài mẫu.
- So sánh với VN-Index cùng cửa sổ và với toàn bộ mã đủ điều kiện cùng ngày (baseline); t-stat tính trên chuỗi trung bình theo ngày.
- Kết quả: `docs/evidence/backtest_summary.csv`, `backtest_buckets.csv/.png`. Giới hạn: giá chưa điều chỉnh (loại cửa sổ có biến động 1 ngày > 30%), survivorship bias, cửa sổ 20 phiên chồng lấp, không kiểm định điểm cơ bản vì BCTC chưa có ngày công bố.

### 8.5. Backtest danh mục (đã thực hiện — 24/11/2026)

Khác với event study ở mục 8.4 (đo lợi suất trung bình của TỪNG sự kiện riêng lẻ, không nối theo thời gian), mục này dựng DANH MỤC và nối các kỳ tái cân bằng liên tiếp **không chồng lấp** thành một đường equity curve, để tính các thước đo chuẩn của quản lý danh mục.

- Quy tắc: tái cân bằng mỗi 20 phiên (~1 tháng), equal-weight, đã trừ chi phí khứ hồi 0,40%. 3 danh mục so sánh: (1) **Tín hiệu AURA** — chỉ giữ mã đạt điểm ≥ 60 tại đầu kỳ; không có mã nào đạt tín hiệu thì coi như giữ tiền mặt (lợi suất kỳ = 0%); (2) **Baseline** — equal-weight toàn bộ mã đủ điều kiện dữ liệu/thanh khoản, không lọc theo điểm; (3) **VN-Index** mua và giữ.
- Dữ liệu 16/07/2024–15/10/2026 (29 kỳ không chồng lấp, 17 trong mẫu / 12 ngoài mẫu, ngoài mẫu từ 24/11/2025). Script tái lập: `scripts/aura_backtest_portfolio.py` (tái dùng đúng logic tín hiệu và chi phí của `core/aura_backtest.py`).

| Giai đoạn | Chiến lược | CAGR | Sharpe (rf=0) | Max Drawdown | Tỷ lệ kỳ thắng |
|---|---|---|---|---|---|
| Trong mẫu | Tín hiệu AURA | -9,13% | -0,43 | 11,73% | 35,3% |
| Trong mẫu | Baseline | +0,80% | 0,14 | 12,57% | 64,7% |
| Trong mẫu | VN-Index | +22,42% | 1,23 | 9,08% | 64,7% |
| Ngoài mẫu | Tín hiệu AURA | -17,19% | -1,98 | 18,06% | 16,7% |
| Ngoài mẫu | Baseline | -19,86% | -1,68 | 21,21% | 41,7% |
| Ngoài mẫu | VN-Index | +0,43% | 0,13 | 12,52% | 50,0% |

**Kết luận trung thực (cập nhật sau khi nâng ngưỡng từ ≥60 lên ≥80, 24/11/2026):** nâng ngưỡng điểm lên mức đối chiếu được với nguồn uy tín (mục 4.5) **không khắc phục được vấn đề cốt lõi**. Ở cấp độ danh mục, tín hiệu AURA (≥80) vẫn không tạo ra giá trị vượt trội so với VN-Index. So với baseline, CAGR ngoài mẫu nhỉnh hơn một chút (-19,37% so với -19,86%) nhưng Sharpe lại xấu hơn (-2,14 so với -1,68), vì tỷ lệ kỳ thắng giảm mạnh (chỉ 8,3%, tức 1/12 kỳ, so với 41,7% của baseline) — ngưỡng càng khắt khe, số kỳ có mã đạt tín hiệu càng ít, và phần lớn các kỳ đó lại là kỳ thua. Khả năng do: (a) VN-Index là chỉ số vốn hóa, bị chi phối bởi nhóm blue-chip tăng mạnh giai đoạn này, trong khi danh mục equal-weight (đa số mã vốn hóa vừa/nhỏ) chịu bất lợi hệ thống không liên quan đến chất lượng tín hiệu; (b) mẫu chỉ 29 kỳ không chồng lấp, ngoài mẫu chỉ 12 kỳ — cỡ mẫu nhỏ, phương sai cao, Sharpe âm không có ý nghĩa thống kê mạnh; (c) ngay cả ở ngưỡng ≥80, tín hiệu đơn ngưỡng vẫn chưa phân biệt mức độ tin cậy theo xếp hạng (không chọn top-N) — khi ít mã đạt ngưỡng hơn, rủi ro tập trung vào nhóm biên (vừa đủ 80 điểm) lại tăng thay vì giảm.

**Giới hạn:** giá chưa điều chỉnh cổ tức/chia tách (kế thừa từ 8.4); không có chi phí trượt giá ngoài phí khứ hồi cố định; không mô phỏng quản lý rủi ro trong kỳ (stop-loss); Sharpe ratio giả định lãi suất phi rủi ro = 0%/năm (Sharpe thô, không trừ lãi suất tiền gửi); survivorship bias như 8.4. Kết quả này **không phải khuyến nghị đầu tư**.

## 9. Giới hạn và đạo đức sử dụng

- BCTC tổng hợp chưa được chứng minh là dữ liệu công bố đã kiểm toán, có thể thiếu 2021–2022 ở một số mã.
- Kho SSI EOD cần kiểm tra điều chỉnh giá, thanh khoản, hủy niêm yết, dữ liệu lỗi/nghỉ lễ.
- Các ngưỡng đang dùng không phải tham số được backtest tối ưu hay kiểm chứng ngoài mẫu.
- Ngưỡng điểm tổng hợp đã nâng từ ≥60 lên ≥80/100 (xem mục 4.5); backtest ở mục 8.4–8.5 đã được chạy lại với ngưỡng ≥80 mới (24/11/2026) nên số liệu trong README phản ánh đúng ngưỡng hiện hành.
- Số liệu lãi/lỗ mô phỏng không bao gồm đầy đủ chi phí, thuế và hạn chế khớp lệnh nếu chưa cấu hình.
- Cần kiểm tra lưu trữ danh mục Cloud có cơ chế xác thực, phân quyền và bền vững trước khi cho nhiều người sử dụng.
- Dữ liệu lịch sử và kết quả sàng lọc không bảo đảm lợi nhuận tương lai.

## 10. Tài liệu và nguồn tham khảo

1. **SSI Developer Portal:** [FastConnect API — Tổng quan](https://developers.ssi.com.vn/en/docs/getting-started); [Market Data](https://developers.ssi.com.vn/docs/faq/market-data). Xác thực, dữ liệu chỉ số, OHLCV, và các giới hạn kênh REST/WebSocket.
2. **Streamlit:** [Community Cloud deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app); [Secrets management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).
3. **Cloudflare:** [R2 S3-compatible API](https://developers.cloudflare.com/r2/get-started/s3/). Lưu và đọc ảnh chụp dữ liệu trong bucket private.
4. **CFA Institute (2026):** [Backtesting and Simulation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation). Walk-forward, look-ahead bias, survivorship bias và giới hạn của mô phỏng.
5. **Nguồn sơ cấp cần đối chiếu từng mã:** BCTC và thuyết minh từ trang quan hệ nhà đầu tư doanh nghiệp; công bố thông tin HOSE, HNX/UPCoM. Nguồn nào chưa đối chiếu phải giữ nhãn *chưa xác minh*.
6. **Wilder, J. Welles Jr. (1978):** *New Concepts in Technical Trading Systems*. Trend Research. Nguồn gốc chỉ báo RSI, chu kỳ mặc định 14.
7. **Piotroski, J. (2000):** "Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers", *Journal of Accounting Research*, 38. Căn cứ cho ngưỡng điểm 8–9/9 ở cổ phiếu giá trị tốt.
8. **DeMiguel, V., Garlappi, L., & Uppal, R. (2009):** "Optimal Versus Naive Diversification: How Inefficient is the 1/N Portfolio Strategy?", *Review of Financial Studies*, 22(5). Căn cứ cho việc chia đều trọng số khi chưa đủ dữ liệu ước lượng tối ưu.
9. **Validea:** [Guru Stock Screener User Guide](https://zeusnew.validea.com/aboutus/gurustockscreeneruserguide.pdf). Quy ước điểm ≥80/100 ("có quan tâm") và ≥90/100 ("quan tâm mạnh") mô phỏng chiến lược các nhà đầu tư huyền thoại.
10. **HOSE (Sở Giao dịch Chứng khoán TP.HCM):** HOSE-Index Methodology phiên bản 3.1 và 4.0 (hiệu lực 01/2025). Tiêu chí thanh khoản tối thiểu rổ VN30: GTGD khớp lệnh ≥10 tỷ đồng/ngày (bản 3.1) → ≥30 tỷ đồng/ngày (bản 4.0).

## 11. Cấu trúc thư mục chính

```text
app.py                      # Trang phân tích chính
pages/                      # Các trang phụ: sàng lọc, danh mục (tùy bản triển khai)
core/                       # SSI adapters, BCTC, chỉ báo, bộ lọc, hiển thị
scripts/                    # Đồng bộ dữ liệu, worker realtime, backtest, kiểm kê
scripts/windows/            # PowerShell: cài worker realtime (install_live_worker.ps1) + lịch EOD tự động (install_eod_refresh.ps1), runbook nộp bài
scripts/legacy/             # Script một lần thời phát triển (không dùng trong sản phẩm)
docs/evidence/              # Bằng chứng kiểm chứng: backtest, tóm tắt dữ liệu WebSocket
requirements.txt            # Phụ thuộc Python
README.md                   # Hướng dẫn dự án
docs/DATA_DICTIONARY.md     # Nhóm API SSI, trường dữ liệu, kiểm tra chất lượng
tests/                      # Kiểm thử tự động (pytest)
```

**Nguyên tắc phát hành:** Chỉ ghi “hoàn thiện” khi giao diện, tính toàn vẹn dữ liệu, quy trình đồng bộ, kiểm thử hồi quy và backtest đều có log chứng minh. README này là **bản soạn cho lần phát hành**; các trạng thái phải được cập nhật theo log mới nhất trước khi nộp đồ án.
