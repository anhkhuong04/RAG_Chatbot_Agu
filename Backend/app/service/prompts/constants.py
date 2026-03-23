CHITCHAT_KEYWORDS = [
    "hello", "hi", "hey", "thank", "thanks", "bye", "goodbye",
    "xin chào", "chào", "cảm ơn", "tạm biệt", "chào bạn", "ok", "tư vấn"
]

# --- Score-specific indicators (→ QUERY_SCORES) ---
SCORE_INDICATORS = [
    "điểm chuẩn", "điểm trúng tuyển", "điểm đầu vào", "điểm đậu",
    "diem chuan", "diem trung tuyen", "diem dau vao", "diem dau",
]

# --- Fee-specific indicators (→ QUERY_FEES) ---
FEE_INDICATORS = [
    "học phí", "hoc phi", "đóng tiền", "tín chỉ", "mức thu",
    "chi phí học", "aun-qa", "kiểm định",
]

# --- General query indicators (→ QUERY_DOCS) ---
# Score/fee keywords removed — they are now in their own lists above
QUERY_INDICATORS = [
    # Tuyển sinh chung
    "xét tuyển", "tuyển sinh", "đăng ký", "phương thức", "tính điểm xét tuyển",
    "tổ hợp", "khối", "ngành", "chuyên ngành", "mã ngành", "ngưỡng đầu vào",
    "ưu tiên xét tuyển", "điểm ưu tiên", "điểm cộng", "điểm khuyến khích", "chỉ tiêu", "học phí dự kiến",

    # Thông tin chung
    "thông tin", "yêu cầu", "điều kiện", "hồ sơ", "thủ tục",
    "chương trình", "đào tạo", "cơ sở", "địa chỉ", "liên hệ",
    # Câu hỏi
    "bao nhiêu", "như thế nào", "là gì", "ở đâu", "khi nào",
    "có những", "danh sách", "làm sao", "cách nào", "tại sao",
    "có không", "được không", "cần gì", "gồm những",
]

# --- Career advice indicators (→ CAREER_ADVICE) ---
CAREER_INDICATORS = [
    "cơ hội việc làm", "hướng nghiệp", "ra trường", "làm nghề gì",
    "lương", "giỏi toán", "học khó không", "tư vấn giúp",
    "có nên học", "tương lai", "ra làm gì", "việc làm",
    "nghề nghiệp", "công việc", "triển vọng", "học cntt",

]

CHITCHAT_MAX_WORDS=20 