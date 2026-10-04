# Hướng Dẫn Cài Đặt Và Sử Dụng

## 1. Yêu cầu hệ thống & Cài đặt môi trường

### Bước 1: Cài đặt Python
* Tải và cài đặt **Python** (phiên bản 3.9 trở lên) tại: [python.org/downloads](https://www.python.org/downloads/)
* ⚠️ **Lưu ý quan trọng khi cài đặt (dành cho Windows):** Trong quá trình bấm Install, bạn **BẮT BUỘC** phải tích chọn ô **"Add Python to PATH"** ở ngay màn hình đầu tiên.

### Bước 2: Tạo file `.env`
* Trong thư mục dự án, tìm file `.env.example`.
* Copy file này và đổi tên thành `.env`.

### Bước 3: Cài đặt các thư viện Python
1. Mở cửa sổ dòng lệnh (Terminal trên Mac/Linux hoặc Command Prompt / PowerShell trên Windows) tại thư mục dự án.
2. Gõ lệnh sau và nhấn **Enter** để tự động cài đặt tất cả thư viện có trong `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## 2. MongoDB & Backup / Restore

MongoDB dùng để lưu dữ liệu của ứng dụng.

### 2.1. Cấu hình MongoDB Atlas

#### Bước 1: Tạo MongoDB Atlas

Truy cập [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) và đăng nhập.

1. Tạo một Cluster mới.
2. Có thể chọn gói **Free (M0)**.

#### Bước 2: Tạo tài khoản Database

Vào:

**Database Access → Add New Database User**

Tạo:

* **Username**
* **Password**

Hãy lưu lại thông tin này.

#### Bước 3: Cho phép kết nối

Vào:

**Network Access → Add IP Address**

Chọn:

**Allow Access From Anywhere → Confirm**

#### Bước 4: Lấy Connection String

Vào:

**Database → Connect → Drivers**

Copy Connection String có dạng:

```text
mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/
```

#### Bước 5: Cấu hình ứng dụng

Copy:

```text
.env.example
```

thành:

```text
.env
```

Mở `.env` và điền:

```env
MONGODB_URI=mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/
```

---

### 2.2. Cài đặt MongoDB Database Tools

Để sử dụng **Backup / Restore**, cần cài [MongoDB Database Tools](https://www.mongodb.com/try/download/database-tools)


Chọn:

* **Platform:** Windows x86_64
* **Package:** msi

Sau khi cài đặt, mở CMD và kiểm tra:

```cmd
mongodump --version
```

và:

```cmd
mongorestore --version
```

Nếu cả hai lệnh hiển thị phiên bản là đã cài đặt thành công.

---

### 2.3. Backup

Trong ứng dụng, chọn:

```text
Backup
```

Hệ thống sẽ tự động tạo thư mục:

```text
backups/
└── 20261004_174442/
    └── recruitment_crawler/
        ├── jobs.bson
        └── jobs.metadata.json
```

Nếu xuất hiện:

```text
Database backup completed: backups\20261004_174442
```

thì Backup đã thành công.

---

### 2.4. Restore

Để kiểm tra hoặc khôi phục Backup, sử dụng file:

```text
jobs.bson
```

Ví dụ:

```text
backups/20261004_174442/recruitment_crawler/jobs.bson
```

Mở CMD và chạy:

```cmd
mongorestore --uri="MONGODB_CONNECTION_STRING" --db=recruitment_crawler_test "PATH_TO_BACKUP\jobs.bson"
```

Ví dụ:

```cmd
mongorestore --uri="mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/" --db=recruitment_crawler_test "d:\workspace\job-crawler\backups\20261004_174442\recruitment_crawler\jobs.bson"
```

Backup sẽ được khôi phục vào:

```text
recruitment_crawler_test
└── jobs
```

> Nên Restore vào `recruitment_crawler_test` để kiểm tra trước, không ảnh hưởng đến Database đang sử dụng.

Nếu xuất hiện:

```text
1102 document(s) restored successfully. 0 document(s) failed to restore.
```

thì Restore thành công.

## 3. Hướng Dẫn Cấu Hình Scraper (`config.py`)

Tài liệu này hướng dẫn cách lấy mã tỉnh/thành phố và mã ngành nghề từ đường link (URL) của các trang tuyển dụng, giúp bạn dễ dàng chỉnh sửa và mở rộng cấu hình cào dữ liệu trong file `config.py`.

### 3.1. Nguyên lý chung
Mỗi trang tuyển dụng sẽ quản lý tỉnh/thành phố và ngành nghề bằng các mã ID riêng trên đường link (URL). Để lấy được các mã này:
1. Truy cập trang web tuyển dụng trên trình duyệt.
2. Chọn bộ lọc **Địa điểm** và **Ngành nghề** bạn muốn cào.
3. Nhìn lên thanh địa chỉ (URL) của trình duyệt để copy các mã tương ứng điền vào file `config.py`.

### 3.2. Cách lấy mã từ URL từng trang

#### A. VietnamWorks (`VIETNAMWORKS_SEARCHES`)
* **URL mẫu:** `https://www.vietnamworks.com/viec-lam?l=24.29.28&j=5`
* **Cách lấy mã:**
  * **Mã địa điểm (`city_ids`):** Nhìn sau `l=`. Các mã phân cách bằng dấu chấm.
    * *Ví dụ:* `l=24.29.28` → điền `[24, 29, 28]` (24: Hà Nội, 29: TP.HCM, 28: Hải Phòng).
  * **Mã ngành nghề (`job_function_ids`):** Nhìn sau `j=` (hoặc `g=`).
    * *Ví dụ:* `j=5` → điền `[5]` (5: CNTT / Viễn thông).

#### B. CareerLink (`CAREERLINK_SEARCHES`)
* **URL mẫu:** `https://www.careerlink.vn/tim-viec-lam-tai/hai-phong/HP?category_ids=19%2C130`
* **Cách lấy mã:**
  * **Mã địa điểm (`province_codes`):** Nhìn phần chữ in hoa ở cuối đường dẫn (trước dấu `?`).
    * *Ví dụ:* `/hai-phong/HP` → điền `["HP"]` (HP: Hải Phòng, HN: Hà Nội).
  * **Mã ngành nghề (`category_ids`):** Nhìn sau `category_ids=`. Mã `%2C` chính là dấu phẩy.
    * *Ví dụ:* `category_ids=19%2C130` → điền `[19, 130]` (19: Phần mềm, 130: Phần cứng).

#### C. TopCV (`TOPCV_SEARCHES`)
* **URL mẫu:** `https://www.topcv.vn/tim-viec-lam-software-engineering-tai-hai-phong-l9cr257cb258?type_keyword=1&sba=1&category_family=r257~b258_b259&locations=l9`
* **Cách lấy mã:**
  * **Đường dẫn tìm kiếm (`search_url`):** Copy toàn bộ link gốc phía trước dấu `?`.
  * **Mã địa điểm (`locations`):** Nhìn sau `locations=`.
    * *Ví dụ:* `locations=l9` → điền `["l9"]` (`l9` là Hải Phòng).
  * **Chuỗi nhóm ngành (`category_family`):** Copy đoạn mã sau `category_family=`.
    * *Ví dụ:* `category_family: "r257~b258_b259"`
  * **Tham số lọc (`params`):** Giữ nguyên các tham số cố định thu được từ URL (`type_keyword`, `disable_auto_detect_type_keyword`, `sba`, `saturday_status`).