"""
Application Configuration using Pydantic Settings
Supports environment variables and .env files
"""
import os
from typing import Optional
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class RetrievalSettings(BaseSettings):
    """Settings for Advanced RAG Retrieval"""
    
    # Hybrid Search
    enable_hybrid_search: bool = Field(
        default=True,
        description="Enable hybrid (dense + sparse) search"
    )
    hybrid_alpha: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight for dense search (0=sparse only, 1=dense only)"
    )
    dense_top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of results from dense retriever"
    )
    sparse_top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of results from sparse (BM25) retriever"
    )
    
    # Reranking
    enable_reranking: bool = Field(
        default=True,
        description="Enable cross-encoder reranking"
    )
    rerank_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder model for reranking"
    )
    rerank_top_n: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of top results after reranking"
    )
    
    # Metadata Filtering
    enable_metadata_filter: bool = Field(
        default=True,
        description="Enable automatic metadata filtering from query"
    )
    default_year: Optional[int] = Field(
        default=None,
        description="Default year for filtering (None = current year)"
    )
    
    # Query Rewriting
    enable_query_rewrite: bool = Field(
        default=True,
        description="Enable LLM-based query rewriting/clarification"
    )
    enable_query_expansion: bool = Field(
        default=False,
        description="Enable multi-query expansion (generates query variants)"
    )
    enable_keyword_extraction: bool = Field(
        default=True,
        description="Enable keyword extraction for BM25 boost"
    )
    max_expanded_queries: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum number of expanded query variants"
    )
    
    class Config:
        env_prefix = "RAG_"
        extra = "ignore"


class DatabaseSettings(BaseSettings):
    """Settings for Database connections"""
    
    mongo_uri: str = Field(
        default="mongodb://admin:admin123@localhost:27018",
        description="MongoDB connection URI"
    )
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant server URL"
    )
    qdrant_collection_name: str = Field(
        default="university_knowledge",
        description="Qdrant collection name"
    )
    
    class Config:
        env_prefix = ""
        extra = "ignore"


class LLMSettings(BaseSettings):
    """Settings for LLM and Embeddings"""
    
    openai_api_key: str = Field(
        default="",
        description="OpenAI API Key"
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="LLM model name"
    )
    llm_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="LLM temperature"
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model name"
    )
    
    class Config:
        env_prefix = ""
        extra = "ignore"


class Settings(BaseSettings):
    """Main application settings"""
    
    # App info
    app_name: str = "University RAG Chatbot API"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False)
    
    # Nested settings
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    
    # API settings
    api_cors_origins: list = Field(
        default=["http://localhost:5173"],
        description="Allowed CORS origins"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to ensure settings are only loaded once.
    
    Returns:
        Settings instance
    """
    return Settings()


# Convenience function to get retrieval settings
def get_retrieval_settings() -> RetrievalSettings:
    """Get retrieval settings"""
    return get_settings().retrieval
