import os
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from qdrant_client import QdrantClient

# Load biến môi trường từ file .env trong cùng thư mục với script
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

def check_connections():
    print("Đang kiểm tra kết nối hệ thống...")
    
    mongo_uri = os.getenv("MONGO_URI")
    print(f"MONGO_URI: {mongo_uri}")

    # 1. Kiểm tra MongoDB
    try:
        mongo_client = MongoClient(mongo_uri)
        mongo_client.admin.command('ping')
        print("MongoDB: KẾT NỐI THÀNH CÔNG!")
    except Exception as e:
        print(f"MongoDB: LỖI - {e}")

    # 2. Kiểm tra Qdrant
    try:
        qdrant_url = os.getenv("QDRANT_URL")
        client = QdrantClient(url=qdrant_url)
        collections = client.get_collections()
        print("Qdrant: KẾT NỐI THÀNH CÔNG!")
    except Exception as e:
        print(f"Qdrant: LỖI - {e}")
if __name__ == "__main__":
    check_connections()