# 📋 BÁO CÁO TRIỂN KHAI: Dynamic Prompt Management

**Ngày thực hiện:** 06/03/2026  
**Tính năng:** Quản lý Prompt động qua MongoDB + Admin Dashboard  
**Trạng thái:** ✅ Hoàn thành

---

## 1. Tổng Quan

Tính năng cho phép quản trị viên chỉnh sửa prompt cho từng loại câu hỏi (intent) trực tiếp trên Admin Dashboard mà không cần redeploy code. Prompt được lưu trong MongoDB collection `prompts` và được cache trong bộ nhớ để đảm bảo hiệu suất.

### Kiến trúc

```
┌─────────────────────────────────────────────────────┐
│              Admin Dashboard (React)                 │
│         PromptEditor Component                       │
│    Select Intent → Edit Template → Save              │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP (axios)
┌──────────────────────▼──────────────────────────────┐
│              FastAPI Backend                         │
│  GET  /api/v1/admin/prompts        → List all        │
│  GET  /api/v1/admin/prompts/{name} → Get one         │
│  PUT  /api/v1/admin/prompts/{name} → Update          │
│  POST /api/v1/admin/prompts        → Create new      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              PromptService (Singleton)                │
│  ┌────────────────────────────────────────────────┐  │
│  │  In-Memory Cache (thread-safe, lazy loading)   │  │
│  │  { "general": "...", "diem_chuan": "...", ... } │  │
│  └────────────────────┬───────────────────────────┘  │
│                       │ invalidate_cache()            │
│  ┌────────────────────▼───────────────────────────┐  │
│  │  MongoDB: university_db.prompts                │  │
│  │  Auto-seed from hardcoded INTENT_PROMPTS       │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              ChatService                              │
│  _get_intent_prompt(intent) → PromptService          │
│  Fallback → hardcoded INTENT_PROMPTS                 │
└──────────────────────────────────────────────────────┘
```

---

## 2. Danh Sách File Đã Thay Đổi / Tạo Mới

### 🆕 File Mới (4 files)

| #   | File                                             | Mô tả                                                              |
| --- | ------------------------------------------------ | ------------------------------------------------------------------ |
| 1   | `Backend/app/models/__init__.py`                 | Package init cho Pydantic models                                   |
| 2   | `Backend/app/models/prompt.py`                   | Pydantic schemas: `PromptRecord`, `PromptUpdate`, `PromptResponse` |
| 3   | `Backend/app/service/prompt_service.py`          | `PromptService` với in-memory caching + CRUD + auto-seed           |
| 4   | `Frontend/src/components/admin/PromptEditor.tsx` | React component cho giao diện chỉnh sửa prompt                     |

### ✏️ File Đã Sửa (6 files)

| #   | File                                     | Thay đổi                                                                                                   |
| --- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| 1   | `Backend/app/api/v1/endpoints/admin.py`  | Thêm 4 endpoints quản lý prompt + import PromptService                                                     |
| 2   | `Backend/app/service/chat_service.py`    | Thay `INTENT_PROMPTS` dict → `PromptService`, thêm `_get_intent_prompt()` helper, cập nhật `clear_cache()` |
| 3   | `Frontend/src/services/adminAPI.ts`      | Thêm types + API functions cho prompt (getPrompts, updatePrompt)                                           |
| 4   | `Frontend/src/hooks/useAdmin.ts`         | Thêm prompt state + actions (fetchPrompts, handleUpdatePrompt)                                             |
| 5   | `Frontend/src/components/admin/index.ts` | Export `PromptEditor` component                                                                            |
| 6   | `Frontend/src/pages/AdminPage.tsx`       | Tích hợp `PromptEditor` vào Admin Dashboard                                                                |

---

## 3. Chi Tiết Kỹ Thuật

### 3.1 MongoDB Schema (`prompts` collection)

```javascript
{
  intent_name: "diem_chuan",        // Unique index
  system_prompt: "",                 // Reserved for future use
  user_template: "Bạn là chuyên viên...", // Prompt template chính
  description: "Prompt cho câu hỏi về điểm chuẩn",
  is_active: true,
  updated_at: ISODate("2026-03-06T..."),
  created_at: ISODate("2026-03-06T...")
}
```

### 3.2 Cơ Chế Cache

- **Lazy loading**: Cache chỉ load lần đầu khi `get_intent_prompt()` được gọi
- **Thread-safe**: Sử dụng `threading.Lock()` (consistent với `_index_lock` trong ChatService)
- **Auto-invalidate**: Cache tự invalidate khi admin cập nhật prompt qua API
- **Fallback**: Nếu MongoDB lỗi → tự động dùng hardcoded `INTENT_PROMPTS`

### 3.3 Auto-Seeding

Khi `PromptService` khởi tạo lần đầu:

1. Kiểm tra collection `prompts` có dữ liệu chưa
2. Nếu trống → copy toàn bộ 4 prompt từ `intent_prompts.py` sang MongoDB
3. Nếu đã có dữ liệu → không ghi đè (bảo toàn thay đổi của admin)

### 3.4 API Endpoints

| Method | Endpoint                              | Mô tả                            |
| ------ | ------------------------------------- | -------------------------------- |
| `GET`  | `/api/v1/admin/prompts`               | Liệt kê tất cả prompts           |
| `GET`  | `/api/v1/admin/prompts/{intent_name}` | Lấy 1 prompt theo tên intent     |
| `PUT`  | `/api/v1/admin/prompts/{intent_name}` | Cập nhật prompt (partial update) |
| `POST` | `/api/v1/admin/prompts`               | Tạo prompt mới                   |

### 3.5 ChatService Integration

6 vị trí sử dụng `INTENT_PROMPTS` đã được thay thế:

| Vị trí | Method                           | Thay đổi                                                                       |
| ------ | -------------------------------- | ------------------------------------------------------------------------------ |
| 1      | `_handle_career_advice()`        | `INTENT_PROMPTS["career_advice"]` → `self._get_intent_prompt("career_advice")` |
| 2      | `_handle_career_advice_stream()` | Tương tự                                                                       |
| 3      | `_synthesize_response_stream()`  | `INTENT_PROMPTS.get(intent, ...)` → `self._get_intent_prompt(intent)`          |
| 4      | `_handle_pandas_query()`         | Tương tự                                                                       |
| 5      | `_handle_pandas_query_stream()`  | Tương tự                                                                       |
| 6      | `_synthesize_response()`         | Tương tự                                                                       |

---

## 4. Backward Compatibility

| Yếu tố                   | Đảm bảo                                        |
| ------------------------ | ---------------------------------------------- |
| File `intent_prompts.py` | ✅ Không thay đổi, giữ nguyên làm fallback     |
| Khi MongoDB lỗi          | ✅ Tự động fallback về hardcoded prompts       |
| Lần chạy đầu tiên        | ✅ Auto-seed từ hardcoded → MongoDB            |
| Không có breaking change | ✅ Tất cả import/export hiện tại vẫn hoạt động |

---

## 5. Hướng Dẫn Sử Dụng

### Admin Dashboard

1. Truy cập **Admin Dashboard** → cuộn xuống phần **"Quản lý Prompt"**
2. Chọn intent từ dropdown (Tổng quát, Điểm chuẩn, Học phí, Tư vấn nghề nghiệp)
3. Chỉnh sửa nội dung prompt trong textarea
4. Nhấn **"Lưu thay đổi"** → prompt được cập nhật ngay lập tức, không cần restart server

### Lưu ý

- Giữ placeholder `{context_str}` trong template nếu cần RAG context
- Có thể tắt prompt bằng cách set `is_active: false`
- Cache tự động refresh khi nhấn **"Clear Cache"** trên Admin Dashboard

---

## 6. Kết Quả Kiểm Tra

- ✅ **0 lỗi compile** trên tất cả 10 files (Backend + Frontend)
- ✅ Tương thích với cấu trúc code hiện tại
- ✅ Tuân thủ pattern hiện có (Pydantic models, FastAPI router, React hooks, Tailwind CSS)
