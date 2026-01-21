"""
Debug Script: Test parsing và chunking trước khi ingest
Giúp xác định vấn đề với data
"""
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from llama_parse import LlamaParse
from llama_index.core import SimpleDirectoryReader
from app.config import settings


def test_llama_parse_connection():
    """Test kết nối LlamaParse API"""
    print("=" * 60)
    print("🔍 TEST 1: LlamaParse API Connection")
    print("=" * 60)
    
    if not settings.LLAMA_CLOUD_API_KEY:
        print("❌ LLAMA_CLOUD_API_KEY is empty!")
        return False
    
    print(f"✅ API Key found: {settings.LLAMA_CLOUD_API_KEY[:10]}...")
    return True


def test_file_parsing(file_path: str, use_premium: bool = False):
    """Test parsing một file cụ thể"""
    print("\n" + "=" * 60)
    print(f"🔍 TEST 2: Parse File")
    print(f"   File: {file_path}")
    print(f"   Premium Mode: {use_premium}")
    print("=" * 60)
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return None
    
    # Create parser
    if use_premium:
        parser = LlamaParse(
            api_key=settings.LLAMA_CLOUD_API_KEY,
            result_type="markdown",
            language="vi",
            # Sử dụng system_prompt thay vì parsing_instruction (deprecated)
            system_prompt="Trích xuất toàn bộ nội dung bảng và văn bản. Giữ nguyên cấu trúc.",
            # Chỉ dùng premium_mode - KHÔNG dùng gpt4o_mode cùng lúc
            premium_mode=True,
            verbose=True
        )
    else:
        parser = LlamaParse(
            api_key=settings.LLAMA_CLOUD_API_KEY,
            result_type="markdown",
            language="vi",
            verbose=True
        )
    
    try:
        # Parse file
        print("\n📄 Parsing...")
        
        reader = SimpleDirectoryReader(
            input_files=[file_path],
            file_extractor={".pdf": parser, ".docx": parser}
        )
        
        docs = reader.load_data()
        
        print(f"\n✅ Parsed {len(docs)} document(s)")
        
        for i, doc in enumerate(docs):
            print(f"\n{'='*40}")
            print(f"📝 Document {i+1}:")
            print(f"   Length: {len(doc.text)} characters")
            print(f"   Preview (first 1500 chars):")
            print("-" * 40)
            print(doc.text[:1500] if doc.text else "[EMPTY]")
            print("-" * 40)
            
            # Check for common issues
            if not doc.text or len(doc.text) < 50:
                print("⚠️ WARNING: Document is very short or empty!")
            
            if "| " not in doc.text and "bảng" in file_path.lower():
                print("⚠️ WARNING: No table markers found (expected for table document)")
            
        return docs
        
    except Exception as e:
        print(f"\n❌ Error parsing: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_chunking(docs, chunk_size: int = 512, chunk_overlap: int = 50):
    """Test chunking strategy"""
    print("\n" + "=" * 60)
    print(f"🔍 TEST 3: Chunking")
    print(f"   Chunk size: {chunk_size}")
    print(f"   Overlap: {chunk_overlap}")
    print("=" * 60)
    
    if not docs:
        print("❌ No documents to chunk!")
        return None
    
    from llama_index.core.node_parser import SentenceSplitter
    
    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separator="\n\n"
    )
    
    nodes = splitter.get_nodes_from_documents(docs)
    
    print(f"\n✅ Created {len(nodes)} chunks")
    
    for i, node in enumerate(nodes[:5]):  # Show first 5
        print(f"\n📦 Chunk {i+1} ({len(node.text)} chars):")
        print("-" * 40)
        print(node.text[:500] if len(node.text) > 500 else node.text)
        print("-" * 40)
    
    if len(nodes) > 5:
        print(f"\n... and {len(nodes) - 5} more chunks")
    
    return nodes


def test_embedding_connection():
    """Test embedding model connection"""
    print("\n" + "=" * 60)
    print("🔍 TEST 4: Embedding Connection")
    print("=" * 60)
    
    try:
        from app.core.llm import setup_llm_settings
        from llama_index.core import Settings
        
        setup_llm_settings()
        
        # Test embedding
        test_text = "Đây là văn bản test để kiểm tra embedding tiếng Việt."
        embedding = Settings.embed_model.get_text_embedding(test_text)
        
        print(f"✅ Embedding successful!")
        print(f"   Dimension: {len(embedding)}")
        print(f"   First 5 values: {embedding[:5]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Embedding error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_qdrant_connection():
    """Test Qdrant vector store connection"""
    print("\n" + "=" * 60)
    print("🔍 TEST 5: Qdrant Connection")
    print("=" * 60)
    
    try:
        from app.core.vector_store import get_vector_store
        
        storage_context = get_vector_store()
        client = storage_context.vector_store.client
        
        # Get collections
        collections = client.get_collections()
        
        print(f"✅ Qdrant connected!")
        print(f"   Collections: {len(collections.collections)}")
        
        for col in collections.collections:
            print(f"   - {col.name}")
            
            # Get collection info
            try:
                info = client.get_collection(col.name)
                print(f"     Points: {info.points_count}")
                print(f"     Vectors: {info.vectors_count}")
            except:
                pass
        
        return True
        
    except Exception as e:
        print(f"❌ Qdrant error: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_full_diagnostics():
    """Run all diagnostic tests"""
    print("\n" + "=" * 80)
    print("🔬 RAG INGESTION DIAGNOSTICS")
    print("=" * 80)
    
    # Test 1: API Connection
    api_ok = test_llama_parse_connection()
    
    # Test 2: Parse a sample file
    data_path = os.path.join(parent_dir, "data")
    sample_files = []
    
    for folder in os.listdir(data_path):
        folder_path = os.path.join(data_path, folder)
        if os.path.isdir(folder_path):
            for f in os.listdir(folder_path):
                if f.endswith(('.pdf', '.docx')):
                    sample_files.append((os.path.join(folder_path, f), folder))
    
    if sample_files:
        print(f"\n📁 Found {len(sample_files)} files to test")
        
        for file_path, folder in sample_files:
            print(f"\n{'#'*80}")
            print(f"Testing: {os.path.basename(file_path)} ({folder})")
            print(f"{'#'*80}")
            
            # Use premium for Diem Chuan
            use_premium = folder == "Diem Chuan"
            
            docs = test_file_parsing(file_path, use_premium=use_premium)
            
            if docs:
                # Test chunking
                nodes = test_chunking(docs, chunk_size=800, chunk_overlap=100)
    
    # Test 4: Embedding
    embed_ok = test_embedding_connection()
    
    # Test 5: Qdrant
    qdrant_ok = test_qdrant_connection()
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 DIAGNOSTIC SUMMARY")
    print("=" * 80)
    print(f"   LlamaParse API: {'✅' if api_ok else '❌'}")
    print(f"   Embedding Model: {'✅' if embed_ok else '❌'}")
    print(f"   Qdrant Storage: {'✅' if qdrant_ok else '❌'}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="RAG Ingestion Diagnostics")
    parser.add_argument("--file", type=str, help="Test specific file")
    parser.add_argument("--premium", action="store_true", help="Use premium mode")
    parser.add_argument("--full", action="store_true", help="Run full diagnostics")
    
    args = parser.parse_args()
    
    if args.file:
        test_file_parsing(args.file, use_premium=args.premium)
    elif args.full:
        run_full_diagnostics()
    else:
        # Default: run embedding and qdrant tests
        test_llama_parse_connection()
        test_embedding_connection()
        test_qdrant_connection()
