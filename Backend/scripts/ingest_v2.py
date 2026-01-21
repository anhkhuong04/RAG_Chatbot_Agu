"""
Advanced RAG Ingestion Pipeline v2.0
Cải thiện chunking, context preservation, và table handling
"""
import os
import sys
import time
import re
import hashlib
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from llama_parse import LlamaParse
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, Document
from llama_index.core.schema import BaseNode, TextNode, NodeRelationship, RelatedNodeInfo
from llama_index.core.node_parser import SentenceSplitter, SemanticSplitterNodeParser
from app.core.llm import setup_llm_settings
from app.core.vector_store import get_vector_store
from app.config import settings


# ==========================================
# CONFIGURATION
# ==========================================

@dataclass
class ChunkingConfig:
    """Configuration cho từng loại document"""
    chunk_size: int
    chunk_overlap: int
    preserve_tables: bool = False
    add_context_header: bool = True
    use_semantic_chunking: bool = False


# Config theo loại folder
FOLDER_CONFIGS: Dict[str, ChunkingConfig] = {
    "Diem Chuan": ChunkingConfig(
        chunk_size=1500,      # Lớn hơn để giữ context bảng
        chunk_overlap=200,
        preserve_tables=True,  # Quan trọng!
        add_context_header=True,
        use_semantic_chunking=False  # Bảng không cần semantic
    ),
    "Hoc Phi": ChunkingConfig(
        chunk_size=1000,
        chunk_overlap=150,
        preserve_tables=True,
        add_context_header=True,
        use_semantic_chunking=False
    ),
    "Quy Che": ChunkingConfig(
        chunk_size=800,
        chunk_overlap=100,
        preserve_tables=False,
        add_context_header=True,
        use_semantic_chunking=True  # Văn bản dài nên dùng semantic
    ),
    "Tong Quan": ChunkingConfig(
        chunk_size=800,
        chunk_overlap=100,
        preserve_tables=False,
        add_context_header=True,
        use_semantic_chunking=True
    ),
}

DEFAULT_CONFIG = ChunkingConfig(
    chunk_size=512,
    chunk_overlap=50,
    preserve_tables=False,
    add_context_header=True
)


# ==========================================
# PARSING INSTRUCTIONS (Cải thiện)
# ==========================================

INSTRUCTION_TABLE = """
Bạn là chuyên gia số hóa bảng điểm tuyển sinh đại học Việt Nam.

NHIỆM VỤ: Trích xuất CHÍNH XÁC thông tin từ bảng điểm chuẩn sang định dạng có cấu trúc.

QUY TẮC BẮT BUỘC:
1. MỖI NGÀNH = MỘT KHỐI THÔNG TIN RIÊNG
   Định dạng cho mỗi ngành:
   ```
   ## [Tên Ngành] (Mã ngành: [Mã])
   - Điểm chuẩn: [Điểm]
   - Tổ hợp xét tuyển: [A00, A01, D01, ...]
   - Chỉ tiêu: [Số lượng] (nếu có)
   - Ghi chú: [Ghi chú] (nếu có)
   ```

2. GIỮ NGUYÊN SỐ LIỆU
   - Số thập phân giữ nguyên (VD: 23.50, không làm tròn)
   - Nếu có nhiều phương thức xét tuyển, liệt kê riêng biệt

3. BỔ SUNG NGỮ CẢNH
   - Đầu mỗi trang ghi: "Năm: [Năm], Phương thức: [Tên phương thức]"
   - Nếu bảng bị ngắt trang, lặp lại thông tin năm/phương thức

4. KHÔNG BỎ SÓT
   - Trích xuất TẤT CẢ các ngành, kể cả ngành có điểm thấp
   - Ghi rõ nếu ô trống: "Không có thông tin"
"""

INSTRUCTION_FEE = """
Bạn là chuyên gia số hóa tài liệu học phí đại học.

NHIỆM VỤ: Trích xuất thông tin học phí theo cấu trúc rõ ràng.

ĐỊNH DẠNG OUTPUT:
```
## Học phí [Năm học]

### [Tên ngành/Khoa]
- Học phí/tín chỉ: [Số tiền] VNĐ
- Học phí/năm (ước tính): [Số tiền] VNĐ
- Áp dụng cho: [Khóa/Đối tượng]
- Ghi chú: [Ghi chú nếu có]
```

QUY TẮC:
1. Giữ nguyên số tiền, không làm tròn
2. Phân biệt rõ học phí theo tín chỉ vs theo năm
3. Ghi chú đối tượng áp dụng (sinh viên chính quy, liên thông, etc.)
"""

INSTRUCTION_REGULATION = """
Bạn là chuyên gia số hóa văn bản quy chế đại học.

NHIỆM VỤ: Chuyển đổi văn bản quy chế sang Markdown có cấu trúc.

QUY TẮC:
1. Giữ nguyên cấu trúc điều/khoản/mục
2. Dùng heading (#, ##, ###) cho điều/khoản
3. Dùng list (-) cho các mục con
4. Loại bỏ header/footer lặp lại (số trang, tên văn bản ở góc)
5. Giữ nguyên các từ viết tắt và định nghĩa

ĐỊNH DẠNG:
# Chương [Số]: [Tên chương]
## Điều [Số]: [Tên điều]
### Khoản [Số]
- Mục a: [Nội dung]
- Mục b: [Nội dung]
"""

INSTRUCTION_GENERAL = """
Bạn là trợ lý số hóa tài liệu giáo dục.

NHIỆM VỤ: Chuyển đổi tài liệu sang Markdown sạch sẽ, dễ tìm kiếm.

QUY TẮC:
1. Sử dụng heading (#) cho các phần lớn
2. Sử dụng bold (**) cho từ khóa quan trọng
3. Giữ nguyên danh sách và bảng
4. Loại bỏ nội dung không liên quan (header/footer lặp)
5. Thêm context nếu thiếu (VD: nếu nói "năm nay" -> thêm năm cụ thể)
"""


def get_instruction_for_folder(folder_name: str) -> str:
    """Lấy instruction phù hợp theo loại folder"""
    instructions = {
        "Diem Chuan": INSTRUCTION_TABLE,
        "Hoc Phi": INSTRUCTION_FEE,
        "Quy Che": INSTRUCTION_REGULATION,
    }
    return instructions.get(folder_name, INSTRUCTION_GENERAL)


# ==========================================
# PARSER FACTORY
# ==========================================

def get_parser(folder_name: str) -> LlamaParse:
    """
    Tạo parser phù hợp với loại document
    """
    instruction = get_instruction_for_folder(folder_name)
    config = FOLDER_CONFIGS.get(folder_name, DEFAULT_CONFIG)
    
    # Folders cần Premium mode (bảng phức tạp)
    needs_premium = folder_name in ["Diem Chuan", "Hoc Phi"]
    
    if needs_premium:
        print(f"📊 [Premium Mode] Parser cho: {folder_name}")
        return LlamaParse(
            api_key=settings.LLAMA_CLOUD_API_KEY,
            result_type="markdown",
            language="vi",
            # Sử dụng system_prompt thay vì parsing_instruction (deprecated)
            system_prompt=instruction,
            # Chỉ dùng premium_mode - KHÔNG dùng gpt4o_mode cùng lúc
            premium_mode=True,
            verbose=True,
            # Cải thiện cho bảng
            skip_diagonal_text=True,
            do_not_unroll_columns=True,
        )
    else:
        print(f"📄 [Standard Mode] Parser cho: {folder_name}")
        return LlamaParse(
            api_key=settings.LLAMA_CLOUD_API_KEY,
            result_type="markdown",
            language="vi",
            system_prompt=instruction,
            verbose=True
        )


# ==========================================
# ADVANCED CHUNKING
# ==========================================

class TableAwareChunker:
    """
    Chunker thông minh: giữ nguyên bảng, chunk văn bản hợp lý
    """
    
    def __init__(self, config: ChunkingConfig):
        self.config = config
        self.sentence_splitter = SentenceSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separator="\n\n"
        )
    
    def _extract_tables(self, text: str) -> List[Tuple[int, int, str]]:
        """
        Tìm và trích xuất các bảng Markdown
        Returns: List of (start_pos, end_pos, table_content)
        """
        tables = []
        lines = text.split('\n')
        
        in_table = False
        table_start = 0
        table_lines = []
        current_pos = 0
        
        for i, line in enumerate(lines):
            # Detect table row (starts with |)
            is_table_line = line.strip().startswith('|') and '|' in line[1:]
            
            if is_table_line and not in_table:
                # Start of table
                in_table = True
                table_start = current_pos
                table_lines = [line]
            elif is_table_line and in_table:
                # Continue table
                table_lines.append(line)
            elif not is_table_line and in_table:
                # End of table
                in_table = False
                table_content = '\n'.join(table_lines)
                tables.append((table_start, current_pos, table_content))
                table_lines = []
            
            current_pos += len(line) + 1  # +1 for newline
        
        # Handle table at end of document
        if in_table and table_lines:
            table_content = '\n'.join(table_lines)
            tables.append((table_start, current_pos, table_content))
        
        return tables
    
    def _extract_sections(self, text: str) -> List[Tuple[str, str]]:
        """
        Trích xuất các section dựa trên heading ##
        Returns: List of (heading, content)
        """
        sections = []
        current_heading = "Tổng quan"
        current_content = []
        
        for line in text.split('\n'):
            if line.startswith('## '):
                # Save previous section
                if current_content:
                    sections.append((current_heading, '\n'.join(current_content)))
                current_heading = line[3:].strip()
                current_content = []
            else:
                current_content.append(line)
        
        # Save last section
        if current_content:
            sections.append((current_heading, '\n'.join(current_content)))
        
        return sections
    
    def chunk_document(self, doc: Document) -> List[TextNode]:
        """
        Chunk document với table awareness
        """
        text = doc.text
        metadata = doc.metadata.copy()
        nodes = []
        
        if self.config.preserve_tables:
            # Strategy 1: Section-based chunking cho bảng điểm
            sections = self._extract_sections(text)
            
            for heading, content in sections:
                if not content.strip():
                    continue
                
                # Tạo node cho mỗi section
                node = TextNode(
                    text=content,
                    metadata={
                        **metadata,
                        "section_heading": heading,
                        "chunk_type": "section"
                    }
                )
                nodes.append(node)
        else:
            # Strategy 2: Semantic/Sentence chunking cho văn bản thường
            temp_doc = Document(text=text, metadata=metadata)
            nodes = self.sentence_splitter.get_nodes_from_documents([temp_doc])
            
            # Add chunk type metadata
            for node in nodes:
                node.metadata["chunk_type"] = "sentence"
        
        return nodes


class HierarchicalChunker:
    """
    Chunker phân cấp: Parent chunks (context) + Child chunks (detail)
    Giúp retrieval tốt hơn bằng cách có cả overview và chi tiết
    """
    
    def __init__(self, config: ChunkingConfig):
        self.config = config
        # Parent chunks: lớn hơn, cho context
        self.parent_splitter = SentenceSplitter(
            chunk_size=config.chunk_size * 2,
            chunk_overlap=config.chunk_overlap
        )
        # Child chunks: nhỏ hơn, cho chi tiết
        self.child_splitter = SentenceSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap
        )
    
    def chunk_document(self, doc: Document) -> List[TextNode]:
        """
        Tạo hierarchical chunks
        """
        metadata = doc.metadata.copy()
        
        # 1. Tạo parent chunks
        parent_nodes = self.parent_splitter.get_nodes_from_documents([doc])
        
        all_nodes = []
        
        for i, parent in enumerate(parent_nodes):
            parent_id = f"{metadata.get('file_name', 'doc')}_{i}"
            parent.id_ = parent_id
            parent.metadata["node_type"] = "parent"
            parent.metadata["chunk_index"] = i
            all_nodes.append(parent)
            
            # 2. Tạo child chunks từ parent
            child_doc = Document(text=parent.text, metadata=metadata)
            child_nodes = self.child_splitter.get_nodes_from_documents([child_doc])
            
            for j, child in enumerate(child_nodes):
                child.id_ = f"{parent_id}_child_{j}"
                child.metadata["node_type"] = "child"
                child.metadata["parent_id"] = parent_id
                child.metadata["chunk_index"] = j
                
                # Link to parent
                child.relationships[NodeRelationship.PARENT] = RelatedNodeInfo(
                    node_id=parent_id
                )
                
                all_nodes.append(child)
        
        return all_nodes


# ==========================================
# CONTEXT INJECTION
# ==========================================

def inject_context(node: TextNode, folder_name: str, doc_metadata: Dict) -> TextNode:
    """
    Inject context vào node để cải thiện retrieval
    """
    # Build context header
    file_name = doc_metadata.get('file_name', 'Unknown')
    year = doc_metadata.get('year', 'Unknown')
    
    context_parts = [
        f"📁 LOẠI TÀI LIỆU: {folder_name}",
        f"📄 TÊN FILE: {file_name}",
        f"📅 NĂM: {year}",
    ]
    
    # Add folder-specific context
    folder_context = {
        "Diem Chuan": "📊 NỘI DUNG: Thông tin điểm chuẩn trúng tuyển đại học",
        "Hoc Phi": "💰 NỘI DUNG: Thông tin học phí và chi phí học tập",
        "Quy Che": "📜 NỘI DUNG: Quy chế, quy định của trường",
        "Tong Quan": "🏫 NỘI DUNG: Thông tin tổng quan về trường",
    }
    
    if folder_name in folder_context:
        context_parts.append(folder_context[folder_name])
    
    # Section heading if available
    if "section_heading" in node.metadata:
        context_parts.append(f"📌 MỤC: {node.metadata['section_heading']}")
    
    context_header = "\n".join(context_parts)
    separator = "\n" + "="*50 + "\n"
    
    # Inject vào text
    node.text = context_header + separator + node.text
    
    return node


# ==========================================
# DEDUPLICATION
# ==========================================

def compute_chunk_hash(text: str) -> str:
    """Compute hash để detect duplicate"""
    # Normalize text before hashing
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return hashlib.md5(normalized.encode()).hexdigest()


def deduplicate_nodes(nodes: List[TextNode]) -> List[TextNode]:
    """
    Loại bỏ duplicate nodes
    """
    seen_hashes = set()
    unique_nodes = []
    
    for node in nodes:
        chunk_hash = compute_chunk_hash(node.text)
        
        if chunk_hash not in seen_hashes:
            seen_hashes.add(chunk_hash)
            unique_nodes.append(node)
        else:
            print(f"   ⚠️ Duplicate detected, skipping...")
    
    return unique_nodes


# ==========================================
# MAIN INGESTION PIPELINE
# ==========================================

def process_folder(
    folder_path: str, 
    folder_name: str,
    config: ChunkingConfig
) -> List[TextNode]:
    """
    Xử lý một folder: Parse -> Chunk -> Inject Context
    """
    print(f"\n{'='*60}")
    print(f"📂 Processing: {folder_name}")
    print(f"{'='*60}")
    
    all_nodes = []
    
    try:
        # 1. Setup parser
        parser = get_parser(folder_name)
        
        # 2. Setup metadata extractor
        def get_metadata(file_path: str) -> Dict:
            file_name = os.path.basename(file_path)
            
            # Extract year from filename
            year_match = re.search(r'20\d{2}', file_name)
            year = year_match.group() if year_match else "Không rõ năm"
            
            return {
                "category": folder_name,
                "file_name": file_name,
                "year": year,
                "source_path": file_path,
            }
        
        # 3. Load documents
        print(f"   📖 Loading documents...")
        reader = SimpleDirectoryReader(
            input_dir=folder_path,
            file_extractor={
                ".pdf": parser,
                ".docx": parser,
                ".png": parser,
                ".jpg": parser,
                ".jpeg": parser,
            },
            file_metadata=get_metadata,
            recursive=True
        )
        
        documents = reader.load_data()
        print(f"   ✅ Loaded {len(documents)} documents")
        
        if not documents:
            print(f"   ⚠️ No documents found in {folder_name}")
            return []
        
        # 4. Debug: Show parsed content preview
        for doc in documents:
            preview = doc.text[:500] if doc.text else "EMPTY"
            print(f"\n   📝 Preview of {doc.metadata.get('file_name', 'unknown')}:")
            print(f"   {preview}...")
            print(f"   Total length: {len(doc.text)} chars")
        
        # 5. Chunk documents
        print(f"\n   ✂️ Chunking with config: chunk_size={config.chunk_size}, overlap={config.chunk_overlap}")
        
        if config.preserve_tables:
            chunker = TableAwareChunker(config)
        else:
            chunker = TableAwareChunker(config)  # Can switch to HierarchicalChunker
        
        for doc in documents:
            if not doc.text or len(doc.text.strip()) < 10:
                print(f"   ⚠️ Skipping empty document: {doc.metadata.get('file_name')}")
                continue
                
            nodes = chunker.chunk_document(doc)
            print(f"   📦 {doc.metadata.get('file_name')}: {len(nodes)} chunks")
            
            # 6. Inject context
            if config.add_context_header:
                nodes = [inject_context(node, folder_name, doc.metadata) for node in nodes]
            
            all_nodes.extend(nodes)
        
        # 7. Deduplicate
        print(f"\n   🔍 Deduplicating...")
        original_count = len(all_nodes)
        all_nodes = deduplicate_nodes(all_nodes)
        print(f"   ✅ {original_count} -> {len(all_nodes)} unique chunks")
        
    except Exception as e:
        print(f"   ❌ Error processing {folder_name}: {e}")
        import traceback
        traceback.print_exc()
    
    return all_nodes


def save_to_vector_store(nodes: List[TextNode], max_retries: int = 3) -> bool:
    """
    Lưu nodes vào Qdrant vector store
    """
    if not nodes:
        print("❌ No nodes to save!")
        return False
    
    for attempt in range(max_retries):
        try:
            print(f"\n{'='*60}")
            print(f"💾 Saving {len(nodes)} nodes to Qdrant (attempt {attempt + 1}/{max_retries})")
            print(f"{'='*60}")
            
            # Get storage context
            storage_context = get_vector_store()
            
            # Create index
            index = VectorStoreIndex(
                nodes=nodes,
                storage_context=storage_context,
                show_progress=True
            )
            
            print(f"\n✅ Successfully saved {len(nodes)} nodes!")
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if "quota" in error_msg or "rate" in error_msg or "429" in error_msg:
                wait_time = (attempt + 1) * 60  # Exponential backoff
                print(f"\n⚠️ Rate limit hit! Waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"\n❌ Error: {e}")
                if attempt == max_retries - 1:
                    import traceback
                    traceback.print_exc()
                    return False
                time.sleep(10)
    
    return False


def run_ingestion():
    """
    Main ingestion pipeline
    """
    print("\n" + "="*80)
    print("🚀 ADVANCED RAG INGESTION PIPELINE v2.0")
    print("="*80)
    
    # 1. Setup LLM settings (for embedding)
    print("\n⚙️ Setting up LLM...")
    setup_llm_settings()
    
    # 2. Get data path
    base_path = os.path.join(parent_dir, "data")
    if not os.path.exists(base_path):
        print(f"❌ Data folder not found: {base_path}")
        return
    
    # 3. Get all folders
    folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
    print(f"\n📁 Found {len(folders)} folders: {folders}")
    
    # 4. Process each folder
    all_nodes: List[TextNode] = []
    
    for folder in folders:
        folder_path = os.path.join(base_path, folder)
        config = FOLDER_CONFIGS.get(folder, DEFAULT_CONFIG)
        
        nodes = process_folder(folder_path, folder, config)
        all_nodes.extend(nodes)
    
    # 5. Summary
    print("\n" + "="*80)
    print("📊 INGESTION SUMMARY")
    print("="*80)
    print(f"   Total chunks: {len(all_nodes)}")
    
    # Breakdown by folder
    folder_counts = {}
    for node in all_nodes:
        cat = node.metadata.get("category", "Unknown")
        folder_counts[cat] = folder_counts.get(cat, 0) + 1
    
    for folder, count in folder_counts.items():
        print(f"   - {folder}: {count} chunks")
    
    # 6. Save to vector store
    if all_nodes:
        success = save_to_vector_store(all_nodes)
        
        if success:
            print("\n" + "="*80)
            print("🎉 INGESTION COMPLETED SUCCESSFULLY!")
            print("="*80)
        else:
            print("\n❌ Ingestion failed!")
    else:
        print("\n⚠️ No data to ingest!")


def test_single_file(file_path: str):
    """
    Test ingestion cho một file
    """
    print(f"\n🧪 Testing single file: {file_path}")
    
    setup_llm_settings()
    
    folder_name = os.path.basename(os.path.dirname(file_path))
    config = FOLDER_CONFIGS.get(folder_name, DEFAULT_CONFIG)
    
    parser = get_parser(folder_name)
    
    def get_meta(fp):
        return {"file_name": os.path.basename(fp), "category": folder_name, "year": "2025"}
    
    reader = SimpleDirectoryReader(
        input_files=[file_path],
        file_extractor={".pdf": parser},
        file_metadata=get_meta
    )
    
    docs = reader.load_data()
    print(f"\n📄 Parsed content ({len(docs)} docs):")
    
    for doc in docs:
        print(f"\n{'='*60}")
        print(doc.text[:2000] if doc.text else "EMPTY")
        print(f"\n... (total {len(doc.text)} chars)")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Advanced RAG Ingestion")
    parser.add_argument("--test", type=str, help="Test single file path")
    args = parser.parse_args()
    
    if args.test:
        test_single_file(args.test)
    else:
        run_ingestion()
