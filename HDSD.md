# Huong Dan Cho Nguoi Nhan File Zip Chay Giong May Local

## Nguoi nhan can lam gi de chay duoc nhu local

### 4.1. Yeu cau tren may nguoi nhan

- Docker Desktop da cai va dang chay
- Con trong o dia (goi co the lon neu giu `mongo_data` va `qdrant_data`)

### 4.2. Nhan va giai nen

Nguoi nhan giai nen vao duong dan khong dau, vi du:

`D:\RAG Chatbot`

### 4.3. Sua key bat buoc

- Mo `Backend/.env`
- Dien `OPENAI_API_KEY` cua may ho (neu key khac)
- Giu nguyen hoac doi `JWT_SECRET_KEY`
- Neu can, doi `ADMIN_USERNAME` va `ADMIN_PASSWORD`

### 4.4. Chay he thong

Mo terminal tai thu muc goc du an va chay:

```bash
docker compose up -d --build
```

### 4.5. Truy cap sau khi chay

- Frontend: `http://localhost`
- Backend API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- MongoDB host port: `localhost:27018`
- Qdrant: `http://localhost:6333`

### 4.6. Dung he thong khi khong su dung

```bash
docker compose down
```

## 5. Neu khong can du lieu cu

Ban co 2 lua chon:

- Xoa `mongo_data/` va `qdrant_data/` truoc khi nen de goi nhe hon.
- Hoac giu nguyen thu muc nhung xoa tren may dich neu muon reset du lieu.

Khi do he thong se tao du lieu moi sau khi chay lai, nhung ket qua retrieval co the khac so voi may local cu.

## 6. Kiem tra nguoi nhan da chay dung chua

1. Truy cap `http://localhost:8000/health` phai tra ve trang thai hoat dong.
2. Mo `http://localhost`, gui 1 cau hoi de test chat.
3. Dang nhap admin bang tai khoan trong `Backend/.env`.
4. Neu nguoi gui da gui kem `mongo_data` va `qdrant_data`, ket qua phai gan giong may local.

## 7. Loi thuong gap khi nguoi nhan mo tren may ho

### 7.1. Backend bao loi thieu API key

- Kiem tra `Backend/.env` da co `OPENAI_API_KEY` chua.
- Chay lai: `docker compose up -d --build`.

### 7.2. Khong ket noi duoc Mongo/Qdrant

- Kiem tra container co dang chay: `docker compose ps`.
- Neu loi data cu, thu `docker compose down` roi `docker compose up -d --build`.

### 7.3. Frontend khong goi duoc backend

- Kiem tra backend da len tai `http://localhost:8000/health`.
- Kiem tra container `uni_frontend` va `uni_backend` co `Up`.

### 7.4. Bao loi port da duoc su dung

- Neu may nguoi nhan dang dung cong 80/8000/27018/6333 cho app khac, can tat app xung dot hoac doi port trong `docker-compose.yml`.

## 8. Mau tin nhan gui kem file zip (de copy dung nhanh)

Nguoi gui co the gui kem doan nay cho nguoi nhan:

```text
Ban giai nen file vao D:\RAG Chatbot, mo Docker Desktop truoc.
Sau do mo terminal tai thu muc goc du an va chay:
docker compose up -d --build

Cho 1-2 phut roi mo:
- Frontend: http://localhost
- Backend health: http://localhost:8000/health

Neu can, sua OPENAI_API_KEY trong Backend/.env truoc khi chay.
Khi dung he thong thi chay:
docker compose down
```

## 9. Checklist ngan truoc khi gui file nen

- Co `docker-compose.yml`.
- Co `Backend/.env` (da dien key can thiet).
- Co/khong co `mongo_data`, `qdrant_data` theo nhu cau giu du lieu.
- Khong dong goi `.venv`, `node_modules`, `__pycache__`.
- Da test local bang `docker compose up -d --build` thanh cong.
