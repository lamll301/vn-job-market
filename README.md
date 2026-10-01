# Hướng Dẫn Cài Đặt Và Sử Dụng

## 1. Yêu cầu hệ thống & Cài đặt môi trường

### Bước 1: Cài đặt Python
* Tải và cài đặt **Python** (phiên bản 3.9 trở lên) tại: [python.org/downloads](https://www.python.org/downloads/)
* ⚠️ **Lưu ý quan trọng khi cài đặt (dành cho Windows):** Trong quá trình bấm Install, bạn **BẮT BUỘC** phải tích chọn ô **"Add Python to PATH"** ở ngay màn hình đầu tiên.

### Bước 2: Tạo file `.env`
* Trong thư mục dự án, tìm file `.env.example`.
* Copy file này và đổi tên thành `.env`.

### Bước 3: Cài đặt các thư viện cần thiết
1. Mở cửa sổ dòng lệnh (Terminal trên Mac/Linux hoặc Command Prompt / PowerShell trên Windows) tại thư mục của dự án.
2. Gõ lệnh sau và nhấn **Enter** để tự động cài đặt tất cả thư viện có trong `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## 2. Cấu hình Database (Lấy MONGODB_URI)

### Bước 1: Tạo tài khoản & Database miễn phí
* Truy cập [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) và đăng nhập bằng tài khoản Google.
* Chọn gói **Free (M0)** và nhấn **Create** để tạo ứng dụng (chờ 1-2 phút).

### Bước 2: Tạo Tên đăng nhập & Mật khẩu
* Chọn mục **Database Access** ở menu bên trái -> Nhấn **Add New Database User**.
* Nhập **Username** (ví dụ: `admin`) và nhập **Password** do bạn tự chọn.
* **Lưu lại Username và Password này để sử dụng ở bước sau.**
* Nhấn **Add User**.

### Bước 3: Mở quyền truy cập IP
* Chọn mục **Network Access** ở menu bên trái -> Nhấn **Add IP Address**.
* Nhấn vào nút **Allow Access From Anywhere** -> Nhấn **Confirm**.

### Bước 4: Sao chép chuỗi kết nối
* Chọn mục **Database** ở menu bên trái -> Nhấn nút **Connect** ở khung Database vừa tạo.
* Chọn mục **Drivers**.
* Sao chép (copy) đoạn mã trong mục **Connection String**. Đoạn mã có dạng:
  `mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`

### Bước 5: Điền mã vào file .env
1. Mở file `.env`.
2. Dán đoạn mã vừa sao chép vào sau dấu `=` của dòng `MONGODB_URI=`.
3. Thay thế thông tin trong đoạn mã:
   * Thay `<username>` bằng Tên đăng nhập đã tạo ở Bước 2.
   * Thay `<password>` bằng Mật khẩu đã tạo ở Bước 2.
     *(Lưu ý: Xóa bỏ cả hai ký tự `<` và `>`)*

---

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

