import os
from dotenv import load_dotenv

load_dotenv()

# MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI is not configured")

if not MONGODB_DATABASE:
    raise ValueError("MONGODB_DATABASE is not configured")

# VietnamWorks
# https://www.vietnamworks.com/viec-lam?l=2.4.5&g=5&j=35.28.27.31.25.29.36.34.30.33.26.32.37
VIETNAMWORKS_SEARCH_URL = "https://ms.vietnamworks.com/job-search/v1.0/search"
VIETNAMWORKS_SEARCHES = {
    "it": {
        "city_ids": [
            28, # Hai Phong
            70, # Quoc te
            24, # Ha Noi
            # 29, # Ho Chi Minh
            # 17, # Da Nang
            # 15, # Can Tho
            # 3, # Ba Ria - Vung Tau
            # 2, # An Giang
            # 4, # Bac Can
            # 5, # Bac Giang
            # 6, # Bac Lieu
            # 7, # Bac Ninh
            # 8, # Ben Tre
            # 10, # Binh Dinh
            # 11, # Binh Duong
            # 12, # Binh Phuoc
            # 13, # Binh Thuan
            # 14, # Ca Mau
            # 16, # Cao Bang
            # 73, Dac Nong
            # 18, # Dak Lak
            # 71, # DBSCL
            # 69, # Dien Bien
            # 19, # Dong Nai
            # 20, # Dong Thap
            # 21, # Gia Lai
            # 22, # Ha Giang
            # 23, # Ha Nam
            # 26, # Ha Tinh
            # 27, # Hai Duong
            # 72, # Hau Giang
            # 30, # Hoa Binh
            # 32, # Hung Yen
            # 33, # Khanh Hoa
            # 34, # Kon Tum
            # 35, # Lai Chau 
            # 36, # Lam Dong
        ],
        "job_function_ids": [
            5,   # Cong nghe thong tin / Vien thong
            # 29, # CEO / General Management
        ],
    }
}
# CareerLink
# https://www.careerlink.vn/tim-viec-lam-tai/hai-phong/HP?category_ids=19%2C130
CAREERLINK_BASE_URL = "https://www.careerlink.vn"
CAREERLINK_SEARCHES = {
    "it": {
        "category_ids": [
            19,     # CNTT - Phần mềm
            # 130     # CNTT - Phần cứng, mạng
        ],
        "province_codes": [
            "HP", 
            "HN",
            "HCM",
            # "DN",
        ],
    },

}
# TopCV
TOPCV_BASE_URL = "https://www.topcv.vn"
# https://www.topcv.vn/tim-viec-lam-software-engineering-tai-hai-phong-l9cr257cb258?type_keyword=1&disable_auto_detect_type_keyword=1&sba=1&category_family=r257~b258_b259_b260_b261_b262_b263_b264_b265_b266_b268_b269&locations=l9&saturday_status=0
TOPCV_SEARCHES = {
    "it": {
        "search_url": "https://www.topcv.vn/tim-viec-lam-software-engineering-tai-hai-phong-l9cr257cb258",
        "locations": ["l9"],
        "category_family": "r257~b258_b259_b260_b261_b262_b263_b264_b265_b266_b268_b269",
        "params": {
            "type_keyword": 1,
            "disable_auto_detect_type_keyword": 1,
            "sba": 1,
            "saturday_status": 0
        }
    }
}

# ---------------- Re-check ----------------
RECHECK_MIN_AGE_DAYS = 3          # < 7 ngày: job mới, bỏ qua
RECHECK_MAX_AGE_DAYS = 30         # > 30 ngày: ngừng re-check
RECHECK_EXPIRY_BUFFER_DAYS = 1    # sắp hết hạn trong N ngày: ngừng re-check
RECHECK_INTERVAL_DAYS = 7         # 1 job chỉ re-check tối đa 1 lần / N ngày
RECHECK_BATCH_SIZE = 10           # số job xử lý song song mỗi đợt

# Field so sánh để phát hiện thay đổi
RECHECK_TRACKED_FIELDS = (
    "description", 
    "requirements", 
    "benefits", 
    "contact", 
    "salary", 
    "location", 
    "address", 
    "expired_at", 
    # "specifications",
)
# Trang chi tiết trả mã này thì coi như tin đã bị gỡ
RECHECK_CLOSED_STATUS_CODES = (404, 410)