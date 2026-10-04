## Overview

Python crawler thu thập tin tuyển dụng từ TopCV, CareerLink và VietnamWorks, chuẩn hóa dữ liệu rồi lưu vào MongoDB. Runtime là Python 3; HTTP dùng `httpx` async, parse HTML bằng BeautifulSoup và persistence dùng PyMongo.

## Common Commands

Chạy từ thư mục `crawler/` (PowerShell):

| Việc cần làm | Lệnh |
|---|---|
| Tạo môi trường | `python -m venv .venv` |
| Kích hoạt môi trường | `.\.venv\Scripts\Activate.ps1` |
| Cài dependencies | `python -m pip install -r requirements.txt` |
| Chạy crawler hiện tại | `python src/main.py` |
| Kiểm tra cú pháp/compile | `python -m compileall -q src` |
| Test toàn bộ | Chưa có test suite hoặc pytest trong repository. |
| Test một file | Chưa có test runner; nếu thêm pytest, dùng `python -m pytest path\to\test_file.py`. |
| Lint / format | Chưa cấu hình công cụ lint hoặc formatter. |
| Database migrations | Không có migration framework; MongoDB index được tạo khi khởi tạo `JobRepository`. |

Runtime cần `.env` với `MONGODB_URI` và `MONGODB_DATABASE`. Không đưa giá trị bí mật vào tài liệu hoặc commit.

## Project Structure & Architecture

```text
crawler/
├── src/
│   ├── main.py                 # Entry point, asyncio.run
│   ├── config.py               # .env và search config theo site
│   ├── core/                   # HTTP client, pipeline, site fetcher/enricher
│   ├── parsers/                # Parse listing/detail thành dữ liệu chuẩn
│   ├── models/                 # Job dataclass
│   ├── database/               # MongoDB connection, repository, backup
│   └── ui/                     # Tkinter UI cũ; không phải luồng chạy mặc định
│       ├── components/
│       ├── views/
│       └── main_window.py
├── requirements.txt
└── .env                        # Local secrets/config; không commit
```

Kiến trúc modular, dùng chung pipeline producer/consumer và Strategy interfaces (`ListFetcher`, `DetailEnricher`); mỗi site cung cấp fetcher, enricher và parser riêng. `CrawlPipeline` lọc job đã tồn tại theo từng trang rồi enrich song song; `JobRepository` lưu vào collection `jobs`.

## Code Style & Conventions

- Python: module/file, hàm và biến `snake_case`; class `PascalCase`; constants `UPPER_SNAKE_CASE`.
- Giữ mỗi site trong module riêng; cấu hình truy vấn đặt tại `config.py`, logic HTTP/paging ở `core/`, chuyển đổi HTML/JSON ở `parsers/`.
- Dùng `async`/`await` cho crawl và `AsyncHttpClient` như async context manager. Dùng client chung để giữ concurrency, delay và retry nhất quán.
- Giữ schema job trong `models/job.py`; khóa duy nhất MongoDB là cặp `(source, source_id)`.
- Logging hiện dùng `print`, chưa có logging framework. HTTP retry tập trung trong `AsyncHttpClient`; pipeline ghi lỗi từng job và tiếp tục, entry point xử lý `KeyboardInterrupt`/lỗi cấp cao.

## Important Rules & Caveats (Do's and Don'ts)

- Thêm site mới bằng `ListFetcher` + `DetailEnricher` và parser tương ứng; tái sử dụng `CrawlPipeline`/`AsyncHttpClient`.
- Thêm/chỉnh tiêu chí tìm kiếm trong `*_SEARCHES` ở `config.py`; giữ `source` ổn định vì dedup và unique index phụ thuộc giá trị này.
- Giữ việc ghi PyMongo đồng bộ ngoài event loop như hiện tại (`asyncio.to_thread` trong consumer).
- Không hardcode Mongo credentials, API secrets hoặc thông tin môi trường; không commit `.env`.
- Không tạo HTTP client riêng cho từng request hoặc bỏ qua retry/rate limiting của `AsyncHttpClient`.
- Không đổi tên field `Job`, collection `jobs` hay khóa `(source, source_id)` nếu chưa xử lý tương thích dữ liệu đã lưu.
- `run_all()` hiện chỉ chạy TopCV; CareerLink và VietnamWorks đang bị comment. Cần bật rõ ràng trong `src/core/run.py` nếu muốn chạy.
- `database/backup.py` cần MongoDB Database Tools (`mongodump`) cài riêng; đây không phải migration.
