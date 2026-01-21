import os
import qdrant_client
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import StorageContext

def get_vector_store():
    # Xác định đường dẫn tuyệt đối đến thư mục Backend/storage
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    storage_path = os.path.join(backend_dir, "storage")
    
    # Khởi tạo client Qdrant (Lưu dữ liệu vào thư mục Backend/storage)
    client = qdrant_client.QdrantClient(path=storage_path)
    
    # Tạo Vector Store
    vector_store = QdrantVectorStore(
        client=client, 
        collection_name="admissions_data"
    )
    
    # Thiết lập Storage Context
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return storage_context