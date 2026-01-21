from llama_index.core import Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from app.config import settings

def setup_llm_settings():
    """
    Cấu hình LLM và Embedding Model sử dụng OpenAI
    
    Supported LLM models:
        - gpt-4o-mini (recommended - fast & cheap)
        - gpt-4o (best quality)
        - gpt-4-turbo
        - gpt-3.5-turbo
    
    Supported Embedding models:
        - text-embedding-3-small (recommended - good balance)
        - text-embedding-3-large (best quality)
        - text-embedding-ada-002 (legacy)
    """
    # 1. Cấu hình LLM (GPT-4o-mini)
    Settings.llm = OpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.1,
        # Giảm max_tokens để tiết kiệm chi phí output (đắt gấp 4 lần input)
        # 1024 tokens = ~750 từ tiếng Anh hoặc ~500 từ tiếng Việt
        max_tokens=1024
    )

    # 2. Cấu hình Embedding Model
    Settings.embed_model = OpenAIEmbedding(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.OPENAI_API_KEY,
        # Batch size cho embedding requests
        embed_batch_size=100
    )
    
    # LƯU Ý: Không set node_parser global vì mỗi loại dữ liệu cần chunking khác nhau
    # node_parser sẽ được set riêng trong ingest.py và engine.py
    
    print(f"✅ Đã cấu hình LLM ({settings.LLM_MODEL}) & Embedding ({settings.EMBEDDING_MODEL})")

# Gọi hàm setup
setup_llm_settings()