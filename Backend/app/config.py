import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load biến môi trường từ file .env
load_dotenv()

class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLAMA_CLOUD_API_KEY: str = os.getenv("LLAMA_CLOUD_API_KEY", "")
    
    # --- LLM & EMBEDDING CONFIG ---
    # OpenAI Models: gpt-4o-mini, gpt-4o, gpt-4-turbo, gpt-3.5-turbo
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    # OpenAI Embedding: text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    
    # --- QUERY TRANSFORMATION CONFIG ---
    # Bật/tắt Query Transformation Pipeline
    USE_QUERY_TRANSFORMATION: bool = os.getenv("USE_QUERY_TRANSFORMATION", "true").lower() == "true"
    
    # Chiến lược transformation: "rewrite", "decompose", "multi_query", "hyde", "full"
    QUERY_TRANSFORM_STRATEGY: str = os.getenv("QUERY_TRANSFORM_STRATEGY", "rewrite")
    
    # Số lượng top chunks sau khi merge từ multiple queries
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "8"))
    
    # Số chunks ban đầu cho mỗi query
    SIMILARITY_TOP_K: int = int(os.getenv("SIMILARITY_TOP_K", "5"))
    
    # --- RE-RANKING CONFIG ---
    # Bật/tắt Re-ranking
    USE_RERANKING: bool = os.getenv("USE_RERANKING", "true").lower() == "true"
    
    # Loại reranker: "cross-encoder", "llm", "cohere", "none"
    RERANKER_TYPE: str = os.getenv("RERANKER_TYPE", "cross-encoder")
    
    # Model cho Cross-Encoder: "multilingual-large", "multilingual-small", "english-large"
    RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "multilingual-large")
    
    # Số nodes giữ lại sau reranking (None = giữ tất cả)
    RERANKER_TOP_N: int = int(os.getenv("RERANKER_TOP_N", "5"))
    
    # Cohere API Key (chỉ cần nếu dùng Cohere reranker)
    COHERE_API_KEY: str = os.getenv("COHERE_API_KEY", "")
    
    # --- LOGGING CONFIG ---
    # Log level: "DEBUG", "INFO", "WARNING", "ERROR"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Log file path
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/app.log")
    
    # Log to console
    LOG_TO_CONSOLE: bool = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"
    
    # Log rotation settings
    LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10MB
    LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    # --- METRICS CONFIG ---
    # Bật/tắt metrics collection
    METRICS_ENABLED: bool = os.getenv("METRICS_ENABLED", "true").lower() == "true"
    
    # Số giờ giữ metrics trong memory
    METRICS_RETENTION_HOURS: int = int(os.getenv("METRICS_RETENTION_HOURS", "24"))
    
    # --- REDIS CACHE CONFIG ---
    # Bật/tắt Redis caching
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "false").lower() == "true"
    
    # Redis connection settings
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    
    # Cache TTL settings (in seconds)
    REDIS_TTL: int = int(os.getenv("REDIS_TTL", "3600"))  # 1 hour default
    REDIS_TRANSFORM_TTL: int = int(os.getenv("REDIS_TRANSFORM_TTL", "3600"))  # 1 hour
    REDIS_RETRIEVAL_TTL: int = int(os.getenv("REDIS_RETRIEVAL_TTL", "1800"))  # 30 minutes
    REDIS_RESPONSE_TTL: int = int(os.getenv("REDIS_RESPONSE_TTL", "7200"))  # 2 hours
    
    # --- SESSION CONFIG ---
    # Session TTL in minutes (how long a conversation stays active)
    SESSION_TTL_MINUTES: int = int(os.getenv("SESSION_TTL_MINUTES", "60"))
    
    # Token limit for chat memory per session
    MEMORY_TOKEN_LIMIT: int = int(os.getenv("MEMORY_TOKEN_LIMIT", "3000"))
    
    # Maximum concurrent sessions
    MAX_SESSIONS: int = int(os.getenv("MAX_SESSIONS", "1000"))
    
    # --- RATE LIMITING CONFIG ---
    # Enable/disable rate limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    
    # Requests per minute per IP
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    
    # Requests per hour per IP
    RATE_LIMIT_PER_HOUR: int = int(os.getenv("RATE_LIMIT_PER_HOUR", "500"))
    
    # Burst limit (max requests per second)
    RATE_LIMIT_BURST: int = int(os.getenv("RATE_LIMIT_BURST", "5"))

settings = Settings() 