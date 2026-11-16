# AURA Stock — Hệ thống phân tích và sàng lọc cổ phiếu Việt Nam

> **Đồ án FinTech / nguyên mẫu nghiên cứu học thuật** · SSI FastConnect V3 · Python · Streamlit · Cloudflare R2
> **Trạng thái:** bản demo đang hoàn thiện kiểm thử; **chưa có kết quả backtest chính thức**; không phải hệ thống tư vấn hoặc đặt lệnh giao dịch.

**Website demo:** https://aura-stock-filter.streamlit.app/
**Mã nguồn:** https://github.com/binhnhh06/aurastock

## 1. Giới thiệu và mục tiêu

AURA Stock hỗ trợ nghiên cứu cổ phiếu Việt Nam theo một quy trình thống nhất: **quan sát thị trường → lựa chọn khẩu vị → phân tích mã → kiểm tra kỹ thuật và tài chính → xem thiết lập giao dịch → theo dõi danh mục mô phỏng**. Mục tiêu là hỗ trợ sinh viên và nhà đầu tư cá nhân **sàng lọc, giải thích và so sánh điều kiện đầu tư** từ dữ liệu có nguồn, không thay thế thẩm định tài chính hoặc tư vấn đầu tư cá nhân.

Các câu hỏi nghiên cứu chính:

1. Có thể tích hợp dữ liệu SSI EOD, chỉ số thị trường và BCTC vào cùng một giao diện dễ sử dụng không?
2. Bộ lọc theo khẩu vị, xu hướng, breakout, pullback và giá trị hỗ trợ phát hiện **ứng viên để nghiên cứu** như thế nào?
3. Khi dữ liệu tài chính chưa được kiểm chứng, hệ thống có thể **tách tín hiệu kỹ thuật khỏi xác nhận cơ bản** để tránh kết luận quá mức không?
4. Kết quả chiến lược có bền vững khi xét chi phí, chế độ thị trường và dữ liệu ngoài mẫu không? (**Sẽ trả lời sau backtest.**)

## 2. Chức năng chính

| Nhóm | Mô tả | Trạng thái xác minh |
|---|---|---|
| Toàn cảnh thị trường | VN-Index, VN30, HNX-Index, UPCoM-Index: điểm, biến động, KLGD, GTGD, ngày phiên | Đã có bản tin SSI EOD trên R2; cần giám sát cập nhật hằng phiên |
| Phân tích cổ phiếu | Giá SSI EOD, các đường MA, RSI, đồ thị đa khung | Đã hiển thị; cần rà soát giá điều chỉnh/corporate actions |
| Hợp khẩu vị | Bộ tiêu chí và ngưỡng theo hồ sơ người dùng; phân biệt Đạt / Không đạt / N/A | Có chức năng; cần soát nhất quán điểm dữ liệu |
| Báo cáo tài chính | Bảng cân đối kế toán, KQKD, lưu chuyển tiền tệ nhiều năm, lọc chỉ tiêu | Đã thấy trên website; chưa xác minh với bản công bố chính thức |
| Tỷ số tài chính | Các tỷ số tính từ BCTC và đồ thị | Hiển thị dưới dạng **tham khảo** khi nguồn chưa xác minh |
| Quét thị trường | Sàng lọc các mã theo bộ tiêu chí đang chọn | Có chức năng; hiệu quả chiến lược chưa backtest |
| Vĩ mô & Chính sách | Dữ liệu thị trường/khối ngoại EOD và tin/chính sách có nguồn | Khối ngoại đã đồng bộ lên R2, chưa chứng minh bao phủ toàn thị trường |
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
- **BCTC:** chỉ đẩy dữ liệu có quyền lưu trữ và hiển thị, giữ metadata nguồn và trạng thái kiểm chứng.
- **Website:** Streamlit Community Cloud từ repo `binhnhh06/aurastock`, nhánh `main`, entrypoint `app.py`.
- **Secrets:** đặt trong **Streamlit Cloud → App settings → Secrets**, không thêm vào GitHub. Đồng nhất endpoint, bucket, prefix, quyền R2 với bộ upload local.
- **Lịch tự động EOD:** chưa xác nhận đã được triển khai và giám sát; chỉ ghi “tự động cập nhật” sau khi có job, retry, log và kiểm thử sau lỗi.

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

### 8.5. Backtest danh mục (chưa thực hiện)

**Trạng thái hiện tại:** chưa có báo cáo backtest chính thức. Quy trình dự kiến (chi tiết ở `docs/AURA_BACKTEST_PROTOCOL.md`):

1. Đóng băng phiên bản quy tắc và tập mã nghiên cứu.
2. Làm sạch dữ liệu OHLCV, kiểm tra đơn vị và quyền/cổ tức; ghi nhận mã hủy niêm yết để hạn chế survivorship bias.
3. Phát tín hiệu tại **đóng cửa ngày t**, mô phỏng khớp **không sớm hơn ngày t+1**; ghi chi phí, thuế, trượt giá và điều kiện thanh khoản.
4. So sánh chiến lược theo phong cách (xu hướng, breakout, pullback) với mua–nắm giữ, VN-Index, và thử ngoài mẫu / walk-forward.
5. Báo cáo CAGR, lợi nhuận tổng, biến động, Sharpe (giả định lãi suất phi rủi ro rõ ràng), max drawdown, số lệnh, tỷ lệ thắng và kiểm tra nhạy cảm tham số.
6. Chỉ đưa kết quả lên README khi đã chạy và kiểm tra dữ liệu thực tế; **không tự điền tỷ lệ thắng hoặc hiệu suất**.

## 9. Giới hạn và đạo đức sử dụng

- BCTC tổng hợp chưa được chứng minh là dữ liệu công bố đã kiểm toán, có thể thiếu 2021–2022 ở một số mã.
- Kho SSI EOD cần kiểm tra điều chỉnh giá, thanh khoản, hủy niêm yết, dữ liệu lỗi/nghỉ lễ.
- Các ngưỡng đang dùng không phải tham số được backtest tối ưu hay kiểm chứng ngoài mẫu.
- Số liệu lãi/lỗ mô phỏng không bao gồm đầy đủ chi phí, thuế và hạn chế khớp lệnh nếu chưa cấu hình.
- Cần kiểm tra lưu trữ danh mục Cloud có cơ chế xác thực, phân quyền và bền vững trước khi cho nhiều người sử dụng.
- Dữ liệu lịch sử và kết quả sàng lọc không bảo đảm lợi nhuận tương lai.

## 10. Tài liệu và nguồn tham khảo

1. **SSI Developer Portal:** [FastConnect API — Tổng quan](https://developers.ssi.com.vn/en/docs/getting-started); [Market Data](https://developers.ssi.com.vn/docs/faq/market-data). Xác thực, dữ liệu chỉ số, OHLCV, và các giới hạn kênh REST/WebSocket.
2. **Streamlit:** [Community Cloud deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app); [Secrets management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).
3. **Cloudflare:** [R2 S3-compatible API](https://developers.cloudflare.com/r2/get-started/s3/). Lưu và đọc ảnh chụp dữ liệu trong bucket private.
4. **CFA Institute (2026):** [Backtesting and Simulation](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/backtesting-and-simulation). Walk-forward, look-ahead bias, survivorship bias và giới hạn của mô phỏng.
5. **Nguồn sơ cấp cần đối chiếu từng mã:** BCTC và thuyết minh từ trang quan hệ nhà đầu tư doanh nghiệp; công bố thông tin HOSE, HNX/UPCoM. Nguồn nào chưa đối chiếu phải giữ nhãn *chưa xác minh*.

## 11. Cấu trúc thư mục chính

```text
app.py                      # Trang phân tích chính
pages/                      # Các trang phụ: sàng lọc, danh mục (tùy bản triển khai)
core/                       # SSI adapters, BCTC, chỉ báo, bộ lọc, hiển thị
scripts/                    # Đồng bộ dữ liệu và tác vụ kiểm tra
requirements.txt            # Phụ thuộc Python
README.md                   # Hướng dẫn dự án
docs/DATA_DICTIONARY.md     # Nhóm API SSI, trường dữ liệu, kiểm tra chất lượng
tests/                      # Kiểm thử tự động (pytest)
```

**Nguyên tắc phát hành:** Chỉ ghi “hoàn thiện” khi giao diện, tính toàn vẹn dữ liệu, quy trình đồng bộ, kiểm thử hồi quy và backtest đều có log chứng minh. README này là **bản soạn cho lần phát hành**; các trạng thái phải được cập nhật theo log mới nhất trước khi nộp đồ án.
