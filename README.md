# AI-Powered Admission Counseling Chatbot (Advanced RAG)

Hệ thống chatbot tư vấn tuyển sinh cho Trường Đại học An Giang, sử dụng Advanced RAG để trả lời có ngữ cảnh, giảm hallucination và hỗ trợ truy vấn cả dữ liệu văn bản lẫn dữ liệu bảng.

## Mục tiêu chính

- Tư vấn tuyển sinh tự động theo ngữ cảnh.
- Truy vấn dữ liệu điểm chuẩn/học phí từ nguồn cấu trúc.
- Quản trị tri thức và prompt qua trang Admin.
- Hỗ trợ streaming phản hồi theo thời gian thực.

## Kiến trúc tổng quan

### Backend (FastAPI)

- `app/api`: Endpoint REST/SSE (chat, admin).
- `app/service`: Nghiệp vụ chat, retrieval, ingestion, prompt.
- `app/service/retrieval`: Hybrid retrieval, query rewrite/expansion, reranking, metadata filter.
- `app/db`: Kết nối singleton MongoDB và Qdrant.
- `app/core`: Cấu hình hệ thống, bảo mật.

### Frontend (React + Vite + TypeScript)

- Feature-Sliced Design cho chat/admin/auth.
- React Query để quản lý gọi API.
- Router phía client, Nginx fallback `index.html` cho SPA.

## Công nghệ sử dụng

### Backend

- FastAPI, Uvicorn
- LlamaIndex
- Qdrant
- MongoDB
- OpenAI Embeddings/LLM
- Sentence-Transformers (reranker)

### Frontend

- React 19 + Vite
- TypeScript
- Tailwind CSS
- TanStack React Query

## Chạy nhanh với Docker (khuyến nghị)

### 1. Chuẩn bị biến môi trường

Tạo file `Backend/.env`:

```env
OPENAI_API_KEY=your_openai_api_key
JWT_SECRET_KEY=your_strong_secret_key

ADMIN_USERNAME=Admin
ADMIN_PASSWORD=123456

# Các biến dưới đây thường được docker-compose override trong môi trường container
MONGO_URI=mongodb://admin:admin123@localhost:27018/?authSource=admin
QDRANT_URL=http://localhost:6333
LOG_LEVEL=INFO
```

### 2. Khởi động hệ thống

```bash
docker compose up -d --build
```

### 3. Endpoint sau khi chạy

- Frontend: `http://localhost`
- Backend API: `http://localhost:8000`
- Health backend: `http://localhost:8000/health`
- Swagger: `http://localhost:8000/docs`

### 4. Dừng hệ thống

```bash
docker compose down
```

## Chạy ở chế độ phát triển (local dev)

### 1. Khởi động database bằng Docker

```bash
docker compose up -d mongo qdrant
```

### 2. Chạy backend

```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Chạy frontend

```bash
cd Frontend
npm install
npm run dev
```

## Kiểm thử nhanh

- Backend health: truy cập `http://localhost:8000/health`.
- Gửi câu hỏi trên giao diện chat.
- Đăng nhập admin với tài khoản trong `Backend/.env`.

## Cấu trúc thư mục chính

```text
Backend/
    app/
        api/
        core/
        db/
        service/
    tests/

Frontend/
    src/
        features/
        components/
        pages/
```

## Lưu ý vận hành

- Dữ liệu local được mount từ `mongo_data/` và `qdrant_data/` khi chạy Docker.
- Không xóa hai thư mục dữ liệu này nếu muốn giữ trạng thái index/chat.
- Frontend qua Nginx đã cấu hình proxy `/api` sang backend container.

## Tài liệu bổ sung

- Hướng dẫn sử dụng chi tiết: xem `HDSD.md`.

## License

Dự án phục vụ mục đích nội bộ cho bài toán tư vấn tuyển sinh.
