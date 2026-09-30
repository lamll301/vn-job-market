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
VIETNAMWORKS_SEARCH_URL = "https://ms.vietnamworks.com/job-search/v1.0/search"
VIETNAMWORKS_SEARCHES = {
    "it": {
        "city_ids": [
            28, # Hai Phong
            70, # Quoc te
            24, # Ha Noi
            29, # Ho Chi Minh
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
            # "HCM",
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