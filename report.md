# 📋 BÁO CÁO THAY ĐỔI: Dynamic Schema Extraction & Agentic Routing

> **Ngày:** 25/02/2026  
> **Phạm vi:** Nạp dữ liệu (Ingestion) · Quản lý dữ liệu (Storage) · Truy xuất & Trả lời (Retrieval & Response)

---

## 1. NẠP DỮ LIỆU (Ingestion Pipeline)

### 1.1. LlamaParse Prompts — Chuyển sang Dynamic Schema

**File:** `Backend/app/service/ingestion_service.py`

| Trước | Sau |
|---|---|
| `ADMISSION_SCORE_INSTRUCTION` ép cứng 11 cột (`TT, MaNganh, NganhHoc...`) | Giữ nguyên số lượng cột gốc PDF, gộp header đa tầng (VD: `PT1_ĐT2_3`, `PT3_Nhom1`) |
| `TUITION_FEE_INSTRUCTION` ép cứng 5-6 cột, thêm cột Thạc sĩ/Tiến sĩ | Giữ nguyên cột gốc, **KHÔNG thêm cột Thạc sĩ/Tiến sĩ**, trích xuất hệ số nhân ở cuối file |

**Thay đổi chính:**
- Điểm chuẩn: LlamaParse trích xuất bảng nguyên bản + chú thích dạng bullet points
- Học phí: Trích xuất **2 bảng riêng biệt** (DH26 và DH25) + **nguyên văn quy tắc hệ số** (1.2, 1.3, 1.4, 1.7, 1.8)

### 1.2. CSV Extraction — Lưu riêng từng bảng

**File:** `Backend/app/service/ingestion_service.py` → `_extract_table_to_csv()`

| Trước | Sau |
|---|---|
| `pd.concat(frames)` → 1 file CSV duy nhất | Logic rẽ nhánh theo category |

**Logic mới:**
- **Điểm chuẩn** → `diem_chuan_2025.csv` (concat tất cả bảng)
- **Học phí** → `hoc_phi_bang_1_2025.csv` + `hoc_phi_bang_2_2025.csv` (mỗi bảng 1 file riêng, tránh lỗi schema khác nhau)

**Lý do:** Bảng DH26 và DH25 có **số cột khác nhau**. `pd.concat` sẽ tạo ra NaN và làm hỏng dữ liệu.

---

## 2. QUẢN LÝ DỮ LIỆU (Storage & Classification)

### 2.1. Phân loại Intent — 4 nhánh

**Files:** `constants.py`, `__init__.py`, `chat_service.py`

| Trước (2 nhánh) | Sau (4 nhánh) |
|---|---|
| `CHITCHAT` / `QUERY` | `CHITCHAT` / `QUERY_DOCS` / `QUERY_SCORES` / `QUERY_FEES` |

**Keyword lists mới trong `constants.py`:**
```python
SCORE_INDICATORS = ["điểm chuẩn", "điểm trúng tuyển", "điểm xét tuyển", ...]
FEE_INDICATORS   = ["học phí", "mức phí", "chi phí học", "tín chỉ", ...]
```

**Thứ tự ưu tiên trong `_classify_intent()`:**
1. `SCORE_INDICATORS` → `QUERY_SCORES`
2. `FEE_INDICATORS` → `QUERY_FEES`
3. `QUERY_INDICATORS` → `QUERY_DOCS`
4. Tin nhắn dài → `QUERY_DOCS`
5. `CHITCHAT_KEYWORDS` + tin nhắn ngắn → `CHITCHAT`
6. Mặc định → `QUERY_DOCS`

### 2.2. Data Dictionary — Từ điển dữ liệu

**File:** `chat_service.py` → `AGU_DATA_DICTIONARY`

Hằng số chứa:
- **Từ điển Điểm chuẩn:** PT1 (Xét tuyển thẳng), PT2 (ĐGNL), PT3 (Thi THPT)
- **Từ điển Học phí:** Bang_1 = Khóa Mới DH26, Bang_2 = Khóa Cũ DH25
- **Hệ số nhân:** Thạc sĩ/Tiến sĩ/VLVH = Đại học × hệ số (1.2–1.8)

Được inject vào `PandasQueryEngine.instruction_str` cùng với `df.columns.tolist()` (Dynamic Schema).

---

## 3. TRUY XUẤT & TRẢ LỜI (Retrieval & Response)

### 3.1. PandasQueryEngine Integration

**File:** `chat_service.py`

**Khởi tạo:**
- `_init_pandas_engines()` → gọi trong `__init__()`
- `_load_csv_engine()` → cho Điểm chuẩn (1 file CSV)
- `_load_multi_csv_engine()` → cho Học phí (N file CSV, merge + tag cột `bang`)

**Mỗi engine nhận:**
```
instruction_str = AGU_DATA_DICTIONARY + Dynamic Schema (columns list + row count)
```

### 3.2. Agentic Routing trong luồng Stream

**Files:** `chat_service.py` → `process_message_stream()`, `chat.py` → `_sse_generator()`

```
User Query
    │
    ▼
_classify_intent()
    │
    ├─ CHITCHAT ──────────► LLM Direct (astream_chat)
    │
    ├─ QUERY_SCORES ──────► PandasQueryEngine (diem_chuan CSV)
    │                           │
    │                           ▼
    │                       Raw pandas output → LLM format → stream tokens
    │
    ├─ QUERY_FEES ────────► PandasQueryEngine (hoc_phi CSV)
    │                           │
    │                           ▼
    │                       Raw pandas output → LLM format → stream tokens
    │
    └─ QUERY_DOCS ────────► HybridRetriever (Qdrant + BM25)
                                │
                                ▼
                            Reranker → LLM synthesize → stream tokens
```

**Tất cả nhánh đều stream qua SSE:**
```
event: metadata  → {"session_id": "...", "intent": "QUERY_SCORES"}
event: sources   → ["Truy xuất từ Bảng điểm chuẩn"]
event: token     → từng chunk text
event: done      → [DONE]
```

### 3.3. Fallback & Error Handling

- Nếu `PandasQueryEngine` chưa init (thiếu CSV) → **fallback sang QUERY_DOCS** (Qdrant RAG)
- Nếu query pandas lỗi → stream thông báo lỗi + fallback RAG
- `clear_cache()` → reload cả Qdrant index **và** CSV engines

---

## 4. DEPENDENCIES MỚI

**File:** `Backend/requirements.txt`

```diff
+ llama-index-experimental   # PandasQueryEngine
+ pandas                     # DataFrame processing
```

---

## 5. DANH SÁCH FILE ĐÃ SỬA

| File | Thay đổi |
|---|---|
| `ingestion_service.py` | LlamaParse prompts, CSV extraction logic, split save |
| `chat_service.py` | Imports, AGU_DATA_DICTIONARY, _classify_intent 4-way, PandasQueryEngine init/load/query/stream, process_message 4-way, clear_cache |
| `constants.py` | Thêm SCORE_INDICATORS, FEE_INDICATORS |
| `prompts/__init__.py` | Export constants mới |
| `chat.py` | SSE generator 4-way routing |
| `requirements.txt` | llama-index-experimental, pandas |
