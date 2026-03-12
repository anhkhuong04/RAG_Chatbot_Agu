# 📊 HƯỚNG DẪN LƯU TRỮ DỮ LIỆU - RAG CHATBOT

## 🗄️ TỔNG QUAN 2 DATABASE

Hệ thống sử dụng **2 database** với vai trò khác nhau:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RAG CHATBOT DATABASE                              │
├─────────────────────────────────┬───────────────────────────────────────────┤
│           MONGODB               │                QDRANT                     │
│     (Document Metadata)         │           (Vector Storage)                │
├─────────────────────────────────┼───────────────────────────────────────────┤
│ • Thông tin file đã upload      │ • Vectors embedding của text chunks       │
│ • Trạng thái xử lý              │ • Nội dung text của từng chunk            │
│ • Lịch sử chat sessions         │ • Metadata để filter khi search           │
│ • Không dùng cho RAG search     │ • Nguồn chính cho RAG retrieval           │
└─────────────────────────────────┴───────────────────────────────────────────┘
```

---

## 📁 MONGODB - Document Metadata Storage

### Database: `university_db`

### Collection 1: `documents`

Lưu **metadata** của các file đã upload (KHÔNG lưu nội dung).

```javascript
{
    "_id": ObjectId("..."),
    "doc_uuid": "550e8400-e29b-41d4-a716-446655440000",  // Liên kết với Qdrant
    "filename": "diem_chuan_2025.pdf",
    "metadata": {
        "year": 2025,
        "category": "Điểm chuẩn",
        "description": "Điểm chuẩn tuyển sinh năm 2025"
    },
    "status": "INDEXED",           // PENDING | INDEXED | FAILED
    "chunk_count": 15,             // Số chunks đã tạo trong Qdrant
    "parsing_method": "llama_parse_custom",
    "created_at": ISODate("2026-01-30T10:00:00Z"),
    "indexed_at": ISODate("2026-01-30T10:01:30Z"),
    "error": null                  // Lỗi nếu status = FAILED
}
```

**Mục đích:**

- Hiển thị danh sách documents trên Admin UI
- Theo dõi trạng thái xử lý file
- Audit trail (ai upload, khi nào)

---

### Collection 2: `chat_sessions`

Lưu **lịch sử chat** của từng session.

```javascript
{
    "_id": ObjectId("..."),
    "session_id": "user-session-abc123",
    "messages": [
        {
            "role": "user",
            "content": "Điểm chuẩn ngành CNTT?",
            "timestamp": ISODate("2026-01-30T14:30:00Z")
        },
        {
            "role": "assistant",
            "content": "Điểm chuẩn ngành CNTT năm 2025 là 25.5...",
            "sources": ["diem_chuan_2025.pdf (2025)"],
            "timestamp": ISODate("2026-01-30T14:30:05Z")
        }
    ],
    "created_at": ISODate("2026-01-30T14:30:00Z"),
    "last_activity": ISODate("2026-01-30T14:35:00Z")
}
```

**Mục đích:**

- Lưu lịch sử hội thoại
- Context cho chitchat (chào hỏi)
- **KHÔNG dùng cho RAG retrieval**

---

## 🔍 QDRANT - Vector Storage

### Collection: `university_knowledge`

Lưu **vectors và nội dung text** của từng chunk.

```javascript
{
    "id": "point-uuid-12345",
    "vector": [0.0123, -0.0456, 0.0789, ...],  // 1536 dimensions (OpenAI)
    "payload": {
        // Nội dung text gốc
        "_node_content": "{\"text\": \"Ngành Công nghệ thông tin...\", ...}",

        // Metadata để filter
        "doc_uuid": "550e8400-e29b-41d4-a716-446655440000",
        "filename": "diem_chuan_2025.pdf",
        "year": 2025,
        "category": "Điểm chuẩn",

        // Context từ document structure
        "section_context": "Chương I > Điều 3: Điểm chuẩn",
        "file_name": "diem_chuan_2025.pdf"
    }
}
```

**Mục đích:**

- **Nguồn chính cho RAG retrieval**
- Dense vector search (semantic similarity)
- Metadata filtering (year, category)
- Text content cho BM25 search

---

## 🗑️ KHI XÓA FILE TỪ ADMIN

### ✅ NHỮNG GÌ ĐƯỢC XÓA (Đã implement)

| Database    | Dữ liệu bị xóa                        | Cách xóa                                        |
| ----------- | ------------------------------------- | ----------------------------------------------- |
| **MongoDB** | Record trong `documents` collection   | `collection.delete_one({"doc_uuid": doc_uuid})` |
| **Qdrant**  | Tất cả vectors có `doc_uuid` matching | `qdrant_client.delete(filter: doc_uuid=...)`    |

### Code thực hiện xóa:

```python
# Backend/app/api/v1/endpoints/admin.py

@router.delete("/documents/{doc_uuid}")
async def delete_document(doc_uuid: str):
    # Step 1: Delete vectors from Qdrant
    qdrant_client.delete(
        collection_name="university_knowledge",
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="doc_uuid",
                    match=MatchValue(value=doc_uuid)
                )
            ]
        )
    )

    # Step 2: Delete from MongoDB
    collection.delete_one({"doc_uuid": doc_uuid})
```

---

### ⚠️ NHỮNG GÌ CHƯA ĐƯỢC XÓA

| Dữ liệu                                 | Lý do                                                      | Giải pháp            |
| --------------------------------------- | ---------------------------------------------------------- | -------------------- |
| **In-memory cache** trong `ChatService` | `_all_nodes`, `_hybrid_retriever` được cache khi khởi động | **Restart backend**  |
| **Chat history** trong `chat_sessions`  | Lịch sử chat là độc lập với documents                      | Xóa thủ công nếu cần |
| **File gốc** trên server (nếu có)       | Chưa implement auto-delete                                 | Xóa thủ công         |

---

## 🔄 LUỒNG DỮ LIỆU KHI XÓA

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         DELETE DOCUMENT FLOW                               │
└────────────────────────────────────────────────────────────────────────────┘

  Admin UI                     Backend                      Databases
     │                            │                             │
     │ Click "Xóa"                │                             │
     ├───────────────────────────►│                             │
     │ DELETE /documents/{uuid}   │                             │
     │                            │                             │
     │                            │ 1. Find doc in MongoDB      │
     │                            ├────────────────────────────►│ MongoDB
     │                            │◄────────────────────────────┤ ✓ Found
     │                            │                             │
     │                            │ 2. Delete vectors by uuid   │
     │                            ├────────────────────────────►│ Qdrant
     │                            │◄────────────────────────────┤ ✅ Deleted
     │                            │                             │
     │                            │ 3. Delete MongoDB record    │
     │                            ├────────────────────────────►│ MongoDB
     │                            │◄────────────────────────────┤ ✅ Deleted
     │                            │                             │
     │◄───────────────────────────┤ Response: success           │
     │                            │                             │
     │                            │                             │
     ├─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─
     │     ⚠️ CACHE VẪN CÒN!     │ _all_nodes[] cached         │
     │                            │ _hybrid_retriever cached    │
     │                            │                             │
     │ User hỏi RAG              │                             │
     ├───────────────────────────►│                             │
     │                            │ Dùng cache cũ! ❌            │
     │◄───────────────────────────┤ Vẫn trả lời từ cache       │
     │                            │                             │
     └────────────────────────────┴─────────────────────────────┘

     ✅ FIX: Restart Backend sau khi xóa để clear cache
```

---

## 📋 TÓM TẮT

### MongoDB lưu gì?

- **documents**: Metadata file upload (filename, year, category, status)
- **chat_sessions**: Lịch sử chat (messages, timestamps)

### Qdrant lưu gì?

- **Vectors**: Embedding 1536 chiều của mỗi text chunk
- **Payload**: Text content + metadata (doc_uuid, year, category)

### Khi xóa từ Admin:

| Bước | Hành động                  | Trạng thái             |
| ---- | -------------------------- | ---------------------- |
| 1    | Xóa Qdrant vectors         | ✅ Đã implement        |
| 2    | Xóa MongoDB record         | ✅ Đã implement        |
| 3    | Clear in-memory cache      | ⚠️ Cần restart backend |
| 4    | Xóa chat history liên quan | ❌ Chưa implement      |

### Khuyến nghị:

```bash
# Sau khi xóa documents, restart backend để clear cache
# PowerShell
Ctrl+C  # Stop uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🔧 CẢI TIẾN ĐỀ XUẤT

### 1. Auto-refresh cache sau khi xóa

```python
# Thêm vào delete_document endpoint
def delete_document(doc_uuid: str):
    # ... existing code ...

    # Invalidate ChatService cache
    chat_service.refresh_hybrid_retriever()
```

### 2. Endpoint để clear cache thủ công

```python
@router.post("/admin/clear-cache")
async def clear_cache():
    chat_service._hybrid_retriever = None
    chat_service._all_nodes = []
    chat_service._index = None
    return {"status": "cache_cleared"}
```

---

_Document Version: 1.0_  
_Last Updated: January 30, 2026_
