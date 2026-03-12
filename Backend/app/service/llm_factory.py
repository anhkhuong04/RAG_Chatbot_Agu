import os
from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding

# Load environment variables
load_dotenv()

def init_settings():
    """
    Initialize LlamaIndex global settings with OpenAI LLM and Embeddings.
    Call this once at application startup.
    """
    # Configure LLM (for chat/generation)
    Settings.llm = OpenAI(
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.1
    )
    
    # Configure Embedding model (for vector search)
    Settings.embed_model = OpenAIEmbedding(
        model="text-embedding-3-small",
        api_key=os.getenv("OPENAI_API_KEY")
    )
    
    # Configure chunking defaults
    Settings.chunk_size = 1024
    Settings.chunk_overlap = 200
    
    print("✅ LlamaIndex Settings initialized (OpenAI GPT-4o-mini + text-embedding-3-small)")


def get_llm():
    """Get the configured LLM instance"""
    if Settings.llm is None:
        init_settings()
    return Settings.llm


def get_embed_model():
    """Get the configured embedding model"""
    if Settings.embed_model is None:
        init_settings()
    return Settings.embed_model
