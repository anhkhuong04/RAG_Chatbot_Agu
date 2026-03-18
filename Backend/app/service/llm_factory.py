import os
from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from app.core.config import get_settings

# Load environment variables
load_dotenv()

def init_settings():
    app_settings = get_settings()
    llm_cfg = app_settings.llm

    # Configure LLM (for chat/generation)
    Settings.llm = OpenAI(
        model=llm_cfg.llm_model,
        api_key=llm_cfg.openai_api_key or os.getenv("OPENAI_API_KEY"),
        temperature=llm_cfg.llm_temperature
    )
    
    # Configure Embedding model (for vector search)
    Settings.embed_model = OpenAIEmbedding(
        model=llm_cfg.embedding_model,
        dimensions=llm_cfg.embedding_dimension,
        api_key=llm_cfg.openai_api_key or os.getenv("OPENAI_API_KEY")
    )
    
    # Configure chunking defaults
    Settings.chunk_size = 1024
    Settings.chunk_overlap = 200
    
    print(f"LlamaIndex Settings initialized ({llm_cfg.llm_model} + {llm_cfg.embedding_model}, dim={llm_cfg.embedding_dimension})")


def get_llm():
    if Settings.llm is None:
        init_settings()
    return Settings.llm


def get_embed_model():
    if Settings.embed_model is None:
        init_settings()
    return Settings.embed_model
