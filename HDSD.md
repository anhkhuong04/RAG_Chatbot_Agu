# Hướng Dẫn Cài Đặt và Sử Dụng Dự Án RAG Chatbot

Tài liệu này giúp người dùng clone dự án từ GitHub và chạy được đầy đủ chức năng giống môi trường local

## 1. Yêu cầu hệ thống

- [Git](https://git-scm.com/downloads)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Python 3.11+](https://www.python.org/downloads/)
- [Node.js 20+](https://nodejs.org/)

## 2. Clone dự án

```bash
git clone <repo-url>
cd RAG_Chatbot_Agu
```

## 3. Thiết lập biến môi trường

### Backend

Tạo file `Backend/.env` (repo hiện tại chưa có `.env.example`) với nội dung tối thiểu:

```env
# Bắt buộc để chatbot trả lời
OPENAI_API_KEY=your_openai_api_key

# Khuyên dùng để token admin không bị mất sau mỗi lần restart
JWT_SECRET_KEY=your_strong_secret_key

# Tùy chọn (mặc định nếu không set)
ADMIN_USERNAME=Admin
ADMIN_PASSWORD=123456
MONGO_URI=mongodb://admin:admin123@localhost:27018/?authSource=admin
QDRANT_URL=http://localhost:6333
```

### Frontend (chỉ cần khi chạy dev mode)

Tạo file `Frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
```

## 4. Cách chạy dự án: Chạy thông qua Docker

Đây là cách sát nhất với local hiện tại, vì `docker-compose.yml` đã mount dữ liệu có sẵn từ `mongo_data/` và `qdrant_data/`.

```bash
docker compose up -d --build
```

Sau khi chạy:

- Frontend: http://localhost
- Backend API: http://localhost:8000
- MongoDB: localhost:27018
- Qdrant: localhost:6333

## 5. Kiểm tra nhanh sau khi chạy

- Mở `http://localhost:8000/health`, kết quả phải là trạng thái healthy.
- Mở giao diện chat (Docker mode: `http://localhost`, Dev mode: `http://localhost:5173`).
- Gửi 1 câu hỏi tuyển sinh để kiểm tra luồng RAG.
- Đăng nhập admin bằng tài khoản mặc định `Admin / 123456` nếu bạn chưa đổi trong `.env`.

## 6. Cách dừng hệ thống

Nếu chạy full Docker:

```bash
docker compose down
```

## 7. Lưu ý quan trọng về dữ liệu nạp sẵn

- Dữ liệu được lấy từ 2 thư mục trong repo:
  - `mongo_data/`
  - `qdrant_data/`
- Không xóa hai thư mục này nếu muốn giữ trạng thái dữ liệu giống local.
- Tránh dùng lệnh xóa volume dữ liệu nếu bạn không muốn reset data.
