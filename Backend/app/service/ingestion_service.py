import os
import re
import uuid
import logging
from datetime import datetime
from pymongo import MongoClient
from qdrant_client import QdrantClient
from llama_index.core import VectorStoreIndex, StorageContext, SimpleDirectoryReader, Settings, PromptTemplate
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_parse import LlamaParse
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from striprtf.striprtf import rtf_to_text

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Import LLM settings
from app.service.llm_factory import init_settings


# ============================================
# PYDANTIC SCHEMAS — Structured Output for LLM Extraction
# ============================================

# --- Admission Scores (Điểm chuẩn) ---
class AdmissionRecord(BaseModel):
    ma_nganh: str = Field(description="Mã ngành đào tạo (Ví dụ: 7480201)")
    ten_nganh: str = Field(description="Tên ngành đào tạo (Ví dụ: Công nghệ thông tin)")
    to_hop_mon: str = Field(description="Danh sách tổ hợp môn xét tuyển, phân cách bằng dấu phẩy (VD: 'A00, A01, C01, D01, D07'). Ghi đúng theo tài liệu gốc.")
    pt1_dt23: Optional[float] = Field(default=None, description="Điểm chuẩn Phương thức 1 - Đối tượng 2,3 (xét tuyển thẳng). Null nếu không có.")
    pt1_dt4: Optional[float] = Field(default=None, description="Điểm chuẩn Phương thức 1 - Đối tượng 4 (xét tuyển thẳng, có chứng chỉ ngoại ngữ). Null nếu không có.")
    pt2: Optional[float] = Field(default=None, description="Điểm chuẩn Phương thức 2 - xét kết quả kỳ thi Đánh giá năng lực (ĐGNL) ĐHQG TP.HCM, thang điểm ~1200. Null nếu không xét.")
    pt3_nhom1: Optional[float] = Field(default=None, description="Điểm chuẩn Phương thức 3 Nhóm 1 - xét kết quả thi tốt nghiệp THPT, tổ hợp nhóm 1. Null nếu không xét.")
    pt3_nhom2: Optional[float] = Field(default=None, description="Điểm chuẩn Phương thức 3 Nhóm 2 - xét kết quả thi tốt nghiệp THPT, tổ hợp nhóm 2 (C00). Null nếu không xét.")
    pt3_nhom3: Optional[float] = Field(default=None, description="Điểm chuẩn Phương thức 3 Nhóm 3 - xét kết quả thi tốt nghiệp THPT, tổ hợp nhóm 3. Null nếu không xét.")

# Column mapping for CSV export
ADMISSION_SCORE_COLUMNS = ["pt1_dt23", "pt1_dt4", "pt2", "pt3_nhom1", "pt3_nhom2", "pt3_nhom3"]

class AdmissionTableExtraction(BaseModel):
    records: List[AdmissionRecord] = Field(description="Danh sách điểm chuẩn của các ngành có trong trang tài liệu này")
    metadata_notes: List[str] = Field(description="Danh sách các câu chú thích, giải thích từ viết tắt (PT1, PT2, ĐT2...) xuất hiện ở phần đầu hoặc cuối bảng/trang.")

# --- Tuition Fees (Học phí) ---
class TuitionRecord(BaseModel):
    nganh_dao_tao: str = Field(description="Tên ngành, nhóm ngành hoặc khối ngành")
    hoc_phi_hk1: Optional[float] = Field(description="Học phí học kỳ 1 (kiểu số nguyên/thực, đã bỏ dấu chấm ngàn)")
    hoc_phi_hk2: Optional[float] = Field(description="Học phí học kỳ 2 (kiểu số nguyên/thực, đã bỏ dấu chấm ngàn)")

class TuitionTableExtraction(BaseModel):
    doi_tuong_ap_dung: str = Field(description="Đối tượng khóa học áp dụng (VD: 'Khóa 2026', 'Khóa 2025 trở về trước')")
    records: List[TuitionRecord] = Field(description="Danh sách học phí của các ngành")
    metadata_notes: List[str] = Field(description="Các ghi chú về quy định nhân hệ số học phí cho Thạc sĩ, Tiến sĩ, VLVH nếu có.")


class IngestionService:
    """Service for processing documents and indexing into vector database"""
    
    # Supported file extensions
    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.docx', '.rtf', '.jpg', '.jpeg', '.png'}
    
    # Extensions that use LlamaParse (PDF for better table parsing)
    LLAMAPARSE_EXTENSIONS = {'.pdf'}
    
    # Categories that should be extracted to CSV instead of Qdrant
    CSV_CATEGORIES = {"điểm chuẩn", "học phí"}
    
    # Directory for structured CSV data
    STRUCTURED_DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "structured"
    )
    
    # Parsing method identifiers for metadata tracking
    PARSE_METHOD_LLAMA = "llama_parse"
    PARSE_METHOD_LLAMA_CUSTOM = "llama_parse_custom"  # Category-specific instructions
    PARSE_METHOD_SIMPLE = "simple_directory_reader"
    
    # Default parsing instruction for general Vietnamese academic documents
    DEFAULT_PARSING_INSTRUCTION = """
        BẠN LÀ CHUYÊN GIA TRÍCH XUẤT DỮ LIỆU TỪ TÀI LIỆU HỌC THUẬT VÀ QUY CHẾ ĐẠI HỌC.
        Nhiệm vụ của bạn là chuyển đổi tài liệu thành định dạng Markdown chuẩn, sạch sẽ và giữ nguyên cấu trúc ngữ nghĩa.

        ====================
        1. BẢO TOÀN CẤU TRÚC PHÁP LÝ
        ====================
        - Tài liệu thường chứa các quy định. Bạn BẮT BUỘC PHẢI giữ nguyên chữ và định dạng nổi bật (bôi đậm hoặc dùng thẻ Heading) cho các cấp độ: CHƯƠNG, MỤC, ĐIỀU.
        - Việc này giúp hệ thống nhận diện ngữ cảnh chính xác. Không được viết liền các Điều vào nhau.

        ====================
        2. XỬ LÝ DỮ LIỆU BẢNG BIỂU VÀ DANH SÁCH
        ====================
        - Mọi bảng biểu xuất hiện trong tài liệu phải được chuyển thành định dạng Markdown Table chuẩn (`| Cột 1 | Cột 2 |`). 
        - KHÔNG bỏ sót bất kỳ hàng hay cột nào. Nếu ô trống, hãy để rỗng `| |`.
        - Các phần liệt kê (Khoản a, b, c hoặc dấu gạch đầu dòng) phải được format bằng Markdown List (`- ` hoặc `1. `) rõ ràng, mỗi ý một dòng.

        ====================
        3. LỌC NHIỄU VÀ LÀM SẠCH (DATA CLEANING)
        ====================
        - TUYỆT ĐỐI LOẠI BỎ: Số trang, header/footer lặp lại ở mỗi trang, dòng chữ ký, dấu mộc đỏ.
        - Không để lại các ký tự ngắt dòng vô nghĩa giữa một câu văn (do lỗi PDF xuống dòng). Hãy nối chúng lại thành câu hoàn chỉnh.

        ====================
        4. BẢO TOÀN NỘI DUNG VÀ NGÔN NGỮ
        ====================
        - Tuyệt đối giữ nguyên tiếng Việt. KHÔNG dịch bất kỳ từ nào sang tiếng Anh.
        - Giữ nguyên 100% độ chính xác của: Tên riêng, Mã ngành, Số điện thoại, Email, Địa chỉ, Đường link (URL), Ngày tháng, Tỉ lệ phần trăm (%) và Số tiền.
    """

    # Category-specific parsing instructions for complex tables
    ADMISSION_SCORE_INSTRUCTION = """
        BẠN LÀ HỆ THỐNG TRÍCH XUẤT DỮ LIỆU ĐIỂM CHUẨN ĐẠI HỌC TỪ PDF.
        YÊU CẦU:
        1. Trích xuất toàn bộ dữ liệu dưới dạng bảng Markdown (`| Cột 1 | Cột 2 |`).
        2. Giữ nguyên toàn bộ nội dung, không tự ý gộp cột hay xóa cột.
        3. Tuyệt đối KHÔNG bỏ sót các dòng ghi chú, chú thích (VD: PT1, PT2, ĐT2...) nằm ở phần cuối của bảng hoặc cuối trang. Hãy giữ chúng lại dưới dạng văn bản bình thường (Text) bên dưới bảng Markdown.
    """

    TUITION_FEE_INSTRUCTION = """
        BẠN LÀ HỆ THỐNG TRÍCH XUẤT DỮ LIỆU HỌC PHÍ TỪ PDF.
        YÊU CẦU:
        1. Trích xuất các bảng học phí dưới dạng bảng Markdown (`| Cột 1 | Cột 2 |`).
        2. Các dòng phân nhóm (Ví dụ: "Khối ngành I:", "Khối ngành III:") hãy để trên một hàng riêng biệt của bảng.
        3. QUAN TRỌNG: Ở phần cuối tài liệu thường có các quy định về việc nhân hệ số học phí (Ví dụ: Thạc sĩ nhân 1.2, Tiến sĩ nhân 1.4...). PHẢI trích xuất nguyên văn khối text này giữ lại ở cuối file Markdown.
    """

    def __init__(self):
        # Initialize LlamaIndex settings (LLM + Embeddings)
        init_settings()
        
        # Connect to MongoDB
        self.mongo_client = MongoClient(os.getenv("MONGO_URI"))
        self.db = self.mongo_client["university_db"]
        self.doc_collection = self.db["documents"]
        
        # Connect to Qdrant
        self.qdrant_client = QdrantClient(url=os.getenv("QDRANT_URL"))
        
        # Collection name for vectors
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME", "university_knowledge")
        
        # LlamaParse API key for PDF processing
        self.llama_api_key = os.getenv("LLAMA_CLOUD_API_KEY")

    @staticmethod
    def is_supported_file(filename: str) -> bool:
        ext = os.path.splitext(filename.lower())[1]
        return ext in IngestionService.SUPPORTED_EXTENSIONS
    
    @staticmethod
    def get_file_extension(filename: str) -> str:
        return os.path.splitext(filename.lower())[1]

    def process_file(self, file_path: str, metadata: dict) -> str | None:
        filename = os.path.basename(file_path)
        ext = self.get_file_extension(filename)
        
        # Validate file extension
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file format: {ext}. Supported: {self.SUPPORTED_EXTENSIONS}")
        
        doc_uuid = str(uuid.uuid4())
        print(f"🔄 Processing file: {filename} (ID: {doc_uuid})...")

        # --- STEP 1: SAVE METADATA TO MONGODB (PENDING) ---
        doc_record = {
            "doc_uuid": doc_uuid,
            "filename": metadata.get("original_filename", filename),
            "metadata": {
                "year": metadata.get("year"),
                "category": metadata.get("category"),
                "description": metadata.get("description")
            },
            "status": "PENDING",
            "created_at": datetime.now()
        }
        self.doc_collection.insert_one(doc_record)

        try:
            # --- STEP 2: LOAD DOCUMENT BASED ON FILE TYPE ---
            # Pass category for category-specific parsing instructions (PDF only)
            category = metadata.get("category")
            documents, parsing_method = self._load_documents(file_path, ext, category)
            
            if not documents:
                raise ValueError(f"No content extracted from file: {filename}")
            
            print(f"📄 Loaded {len(documents)} document(s) from {ext} file (method: {parsing_method})")
            
            # Add parsing method to metadata for tracking
            metadata["parsing_method"] = parsing_method

            # --- STEP 3: BRANCH — CSV for structured data, Qdrant for text ---
            year = metadata.get("year")
            if category and category.lower().strip() in self.CSV_CATEGORIES:
                # Structured data path: extract tables to CSV, skip Qdrant
                csv_path, row_count = self._extract_table_to_csv(documents, category, year)
                
                if csv_path is None:
                    raise ValueError(f"Failed to extract tables from {filename} for category '{category}'")
                
                # Update MongoDB with CSV info
                self.doc_collection.update_one(
                    {"doc_uuid": doc_uuid},
                    {"$set": {
                        "status": "INDEXED",
                        "storage_type": "csv",
                        "csv_path": csv_path,
                        "row_count": row_count,
                        "parsing_method": parsing_method,
                        "indexed_at": datetime.now()
                    }}
                )
                
                print(f"✅ Successfully extracted to CSV: {csv_path} ({row_count} rows)")
            else:
                # Text data path: chunk, embed, index to Qdrant
                chunk_count = self._index_nodes(documents, metadata, doc_uuid)
                
                self.doc_collection.update_one(
                    {"doc_uuid": doc_uuid},
                    {"$set": {
                        "status": "INDEXED",
                        "storage_type": "qdrant",
                        "chunk_count": chunk_count,
                        "parsing_method": parsing_method,
                        "indexed_at": datetime.now()
                    }}
                )
                
                print(f"✅ Successfully indexed to Qdrant: {filename} ({chunk_count} chunks)")
            
            return doc_uuid

        except Exception as e:
            # Update MongoDB with error status
            print(f"❌ Error: {str(e)}")
            self.doc_collection.update_one(
                {"doc_uuid": doc_uuid},
                {"$set": {
                    "status": "FAILED",
                    "error": str(e)
                }}
            )
            return None
    
    def _load_documents(self, file_path: str, ext: str, category: str = None) -> tuple[list, str]:
        if ext in self.LLAMAPARSE_EXTENSIONS:
            # --- PDF: Use LlamaParse with category-specific instructions ---
            return self._load_with_llama_parse(file_path, category)
        elif ext == '.rtf':
            # --- RTF: Convert to plain text using striprtf ---
            return self._load_rtf(file_path)
        else:
            # --- TXT, DOCX, Images: Use SimpleDirectoryReader ---
            return self._load_with_simple_reader(file_path)
    
    def _get_parsing_instruction(self, category: str) -> tuple[str, bool]:
        if not category:
            return self.DEFAULT_PARSING_INSTRUCTION, False
        
        # Normalize category for comparison (handle variations)
        category_lower = category.lower().strip()
        
        # Admission Scores: "Điểm chuẩn" or "Tuyển sinh" (contains score tables)
        if any(keyword in category_lower for keyword in ["điểm chuẩn", "diem chuan"]):
            logger.info(f"🎯 Using ADMISSION_SCORE_INSTRUCTION for category: {category}")
            return self.ADMISSION_SCORE_INSTRUCTION, True
        
        # Tuition Fees: "Học phí"
        if any(keyword in category_lower for keyword in ["học phí", "hoc phi"]):
            logger.info(f"💰 Using TUITION_FEE_INSTRUCTION for category: {category}")
            return self.TUITION_FEE_INSTRUCTION, True
        
        # Default instruction for other categories
        logger.info(f"📄 Using DEFAULT_PARSING_INSTRUCTION for category: {category}")
        return self.DEFAULT_PARSING_INSTRUCTION, False
    
    def _load_with_llama_parse(self, file_path: str, category: str = None) -> tuple[list, str]:
        try:
            # Get category-specific parsing instruction
            instruction, is_custom = self._get_parsing_instruction(category)
            
            # Create LlamaParse instance with appropriate instruction
            parser = LlamaParse(
                api_key=self.llama_api_key,
                result_type="markdown",
                parsing_instruction=instruction,
                verbose=True
            )
            
            parse_method = self.PARSE_METHOD_LLAMA_CUSTOM if is_custom else self.PARSE_METHOD_LLAMA
            
            logger.info(f"📊 Using LlamaParse for PDF: {os.path.basename(file_path)} (custom={is_custom})")
            print(f"🔄 Parsing PDF with {'CUSTOM' if is_custom else 'DEFAULT'} instruction for category: {category or 'None'}")
            
            documents = parser.load_data(file_path)
            
            if documents:
                # Add parsing strategy metadata to each document
                for doc in documents:
                    doc.metadata['parsing_strategy'] = parse_method
                    doc.metadata['parsing_category'] = category or 'general'
                
                logger.info(f"✅ LlamaParse successfully extracted {len(documents)} document(s)")
                return documents, parse_method
            else:
                raise ValueError("LlamaParse returned empty documents")
                
        except Exception as e:
            # Fallback to SimpleDirectoryReader if LlamaParse fails
            logger.warning(f"⚠️ LlamaParse failed: {str(e)}. Fallback to standard parser.")
            print(f"⚠️ Fallback to standard parser due to: {str(e)}")
            return self._load_with_simple_reader(file_path)
    
    def _load_rtf(self, file_path: str) -> tuple[list, str]:
        logger.info(f"📄 Loading RTF file: {os.path.basename(file_path)}")
        with open(file_path, 'r', encoding='utf-8') as f:
            rtf_content = f.read()
        plain_text = rtf_to_text(rtf_content)
        doc = Document(text=plain_text, metadata={"file_name": os.path.basename(file_path)})
        return [doc], self.PARSE_METHOD_SIMPLE

    def _load_with_simple_reader(self, file_path: str) -> tuple[list, str]:
        logger.info(f"📄 Using SimpleDirectoryReader for: {os.path.basename(file_path)}")
        reader = SimpleDirectoryReader(
            input_files=[file_path],
            filename_as_id=True
        )
        documents = reader.load_data()
        return documents, self.PARSE_METHOD_SIMPLE
    
    def _index_nodes(self, documents, metadata: dict, doc_uuid: str) -> int:
        filename = metadata.get("original_filename", "unknown")
        parsing_method = metadata.get("parsing_method", self.PARSE_METHOD_SIMPLE)
        
        # Add metadata to each document for filtering
        for doc in documents:
            doc.metadata["doc_uuid"] = doc_uuid
            doc.metadata["filename"] = filename
            doc.metadata["year"] = metadata.get("year")
            doc.metadata["category"] = metadata.get("category")
            doc.metadata["parsing_method"] = parsing_method
            # Exclude technical fields from LLM context but keep filename
            doc.excluded_llm_metadata_keys = ["doc_uuid", "parsing_method"]
            doc.excluded_embed_metadata_keys = ["doc_uuid", "parsing_method"]

        # Chunk documents with context-aware splitting
        # chunk_size=2048: Đủ lớn để chứa bảng biểu phức tạp (điểm chuẩn, học phí)
        # chunk_overlap=400: Đủ để giữ context giữa các chunk (~20%)
        splitter = SentenceSplitter(
            chunk_size=2048,
            chunk_overlap=400,
            paragraph_separator="\n\n",
        )
        nodes = splitter.get_nodes_from_documents(documents)
        
        # Enrich nodes with section context
        nodes = self._enrich_nodes_with_context(nodes, metadata)
        
        print(f"Split into {len(nodes)} chunks")

        # Index to Qdrant
        vector_store = QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=self.collection_name
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        # This will automatically: Embed -> Index -> Upload
        VectorStoreIndex(nodes, storage_context=storage_context)
        
        return len(nodes)
    
    def _enrich_nodes_with_context(self, nodes, metadata):
        chapter_pattern = re.compile(r'(Chương\s+[IVXLCDM\d]+[.:]\s*[^\n]+)', re.IGNORECASE)
        article_pattern = re.compile(r'(Điều\s+\d+[.:]\s*[^\n]+)', re.IGNORECASE)
        section_pattern = re.compile(r'(Mục\s+\d+[.:]\s*[^\n]+)', re.IGNORECASE)
        
        current_chapter = ""
        current_article = ""
        current_section = ""
        
        for node in nodes:
            text = node.text
            
            # Detect chapter
            chapter_match = chapter_pattern.search(text)
            if chapter_match:
                current_chapter = chapter_match.group(1).strip()
            
            # Detect article
            article_match = article_pattern.search(text)
            if article_match:
                current_article = article_match.group(1).strip()
            
            # Detect section
            section_match = section_pattern.search(text)
            if section_match:
                current_section = section_match.group(1).strip()
            
            # Build context prefix
            context_parts = []
            if current_chapter:
                context_parts.append(current_chapter)
            if current_section:
                context_parts.append(current_section)
            if current_article:
                context_parts.append(current_article)
            
            # Add context to node metadata
            if context_parts:
                node.metadata["section_context"] = " > ".join(context_parts)
            
            # Add document info to metadata
            node.metadata["source_doc"] = metadata.get("original_filename", "")
            node.metadata["category"] = metadata.get("category", "")
            node.metadata["year"] = metadata.get("year", "")
        
        return nodes
    
    def _extract_table_to_csv(self, documents, category: str, year: int) -> tuple[str | None, int]:
        os.makedirs(self.STRUCTURED_DATA_DIR, exist_ok=True)
        category_lower = category.lower().strip()
        
        if "điểm chuẩn" in category_lower:
            return self._extract_admission_scores(documents, year)
        elif "học phí" in category_lower:
            return self._extract_tuition_fees(documents, year)
        
        return None, 0
    
    def _extract_admission_scores(self, documents, year: int) -> tuple[str | None, int]:
        all_records: List[AdmissionRecord] = []
        all_notes: set = set()
        
        extraction_prompt = PromptTemplate(
            "Hãy đọc nội dung tài liệu tuyển sinh sau và trích xuất điểm chuẩn "
            "thành cấu trúc JSON nghiêm ngặt theo schema được cung cấp.\n"
            "- Mỗi ngành là 1 record gồm: ma_nganh, ten_nganh, to_hop_mon, và các điểm chuẩn.\n"
            "- to_hop_mon: ghi đầy đủ danh sách tổ hợp môn xét tuyển.\n"
            "- pt1_dt23, pt1_dt4: điểm xét tuyển thẳng (PT1) theo đối tượng.\n"
            "- pt2: điểm Đánh giá năng lực (ĐGNL) ĐHQG TP.HCM, thang ~1200.\n"
            "- pt3_nhom1, pt3_nhom2, pt3_nhom3: điểm xét thi tốt nghiệp THPT theo nhóm tổ hợp.\n"
            "- Nếu ngành không xét phương thức nào đó, để null.\n"
            "- Gom tất cả ghi chú, giải thích viết tắt (PT1, PT2, PT3, ĐT2, ĐT3, ĐT4, Nhóm 1/2/3...) vào metadata_notes.\n\n"
            "NỘI DUNG TÀI LIỆU:\n{doc_content}"
        )
        
        for i, doc in enumerate(documents):
            content = doc.get_content()
            if not content or not content.strip():
                continue
            
            try:
                logger.info(f"🔍 Extracting admission scores from document node {i+1}/{len(documents)}")
                
                # Use LLM structured prediction with Pydantic schema
                extraction = Settings.llm.structured_predict(
                    AdmissionTableExtraction,
                    extraction_prompt,
                    doc_content=content,
                )
                
                if extraction.records:
                    all_records.extend(extraction.records)
                    logger.info(f"  ✅ Extracted {len(extraction.records)} records from node {i+1}")
                
                if extraction.metadata_notes:
                    all_notes.update(extraction.metadata_notes)
                    
            except Exception as e:
                logger.warning(f"⚠️ Failed to extract from node {i+1}: {e}")
                continue
        
        if not all_records:
            logger.warning("❌ No admission records extracted from any node")
            return None, 0
        
        # Flatten records to tabular format
        flat_data = []
        for record in all_records:
            row = {
                "MaNganh": record.ma_nganh,
                "NganhHoc": record.ten_nganh,
                "ToHopMon": record.to_hop_mon,
            }
            # Map fixed score fields to CSV columns
            for col in ADMISSION_SCORE_COLUMNS:
                row[col.upper()] = getattr(record, col, None)
            flat_data.append(row)
        
        df = pd.DataFrame(flat_data)
        
        # Save CSV
        csv_path = os.path.join(self.STRUCTURED_DATA_DIR, f"diem_chuan_{year}.csv")
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        logger.info(f"📊 Saved {len(df)} rows to {csv_path}")
        print(f"📊 Saved {len(df)} rows to {csv_path}")
        
        # Save metadata notes
        if all_notes:
            notes_path = os.path.join(self.STRUCTURED_DATA_DIR, f"diem_chuan_{year}_metadata.txt")
            with open(notes_path, 'w', encoding='utf-8') as f:
                for note in sorted(all_notes):
                    f.write(f"- {note}\n")
            logger.info(f"📝 Saved {len(all_notes)} metadata notes to {notes_path}")
            print(f"📝 Saved {len(all_notes)} notes to {notes_path}")
        
        return csv_path, len(df)
    
    def _extract_tuition_fees(self, documents, year: int) -> tuple[str | None, int]:
        # Group by doi_tuong_ap_dung
        groups: Dict[str, List[TuitionRecord]] = {}
        all_notes: set = set()
        
        extraction_prompt = PromptTemplate(
            "Hãy đọc nội dung tài liệu học phí sau và trích xuất thông tin học phí "
            "thành cấu trúc JSON nghiêm ngặt theo schema được cung cấp.\n"
            "- doi_tuong_ap_dung: Ghi rõ đối tượng khóa.\n"
            "- Mỗi ngành/nhóm ngành là 1 record với nganh_dao_tao, hoc_phi_hk1, hoc_phi_hk2.\n"
            "- Số tiền phải là kiểu số (bỏ dấu chấm ngàn). VD: 404000 thay vì '404.000'.\n"
            "- Gom tất cả ghi chú về quy tắc nhân hệ số (Thạc sĩ, Tiến sĩ, VLVH) vào metadata_notes.\n\n"
            "NỘI DUNG TÀI LIỆU:\n{doc_content}"
        )
        
        for i, doc in enumerate(documents):
            content = doc.get_content()
            if not content or not content.strip():
                continue
            
            try:
                logger.info(f"🔍 Extracting tuition fees from document node {i+1}/{len(documents)}")
                
                # Use LLM structured prediction with Pydantic schema
                extraction = Settings.llm.structured_predict(
                    TuitionTableExtraction,
                    extraction_prompt,
                    doc_content=content,
                )
                
                doi_tuong = extraction.doi_tuong_ap_dung or f"Bang_{i+1}"
                
                if extraction.records:
                    if doi_tuong not in groups:
                        groups[doi_tuong] = []
                    groups[doi_tuong].extend(extraction.records)
                    logger.info(f"  ✅ Extracted {len(extraction.records)} records for '{doi_tuong}' from node {i+1}")
                
                if extraction.metadata_notes:
                    all_notes.update(extraction.metadata_notes)
                    
            except Exception as e:
                logger.warning(f"⚠️ Failed to extract from node {i+1}: {e}")
                continue
        
        if not groups:
            logger.warning("❌ No tuition records extracted from any node")
            return None, 0
        
        # Save each group as separate CSV
        saved_paths = []
        total_rows = 0
        
        for idx, (doi_tuong, records) in enumerate(groups.items(), start=1):
            flat_data = [
                {
                    "NganhDaoTao": r.nganh_dao_tao,
                    "HocPhi_HK1": r.hoc_phi_hk1,
                    "HocPhi_HK2": r.hoc_phi_hk2,
                }
                for r in records
            ]
            
            df = pd.DataFrame(flat_data)
            csv_path = os.path.join(self.STRUCTURED_DATA_DIR, f"hoc_phi_bang_{idx}_{year}.csv")
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            saved_paths.append(csv_path)
            total_rows += len(df)
            logger.info(f"📊 Saved {len(df)} rows to {csv_path} (đối tượng: {doi_tuong})")
            print(f"📊 Saved {len(df)} rows to {csv_path} (đối tượng: {doi_tuong})")
        
        # Save metadata notes (hệ số Thạc sĩ, Tiến sĩ, VLVH...)
        if all_notes:
            notes_path = os.path.join(self.STRUCTURED_DATA_DIR, f"hoc_phi_{year}_metadata.txt")
            with open(notes_path, 'w', encoding='utf-8') as f:
                for note in sorted(all_notes):
                    f.write(f"- {note}\n")
            logger.info(f"📝 Saved {len(all_notes)} metadata notes to {notes_path}")
            print(f"📝 Saved {len(all_notes)} notes to {notes_path}")
        
        if saved_paths:
            return saved_paths[0], total_rows
        return None, 0
    
    def get_all_documents(self):
        return list(self.doc_collection.find({}, {"_id": 0}))
    
    def get_document_by_id(self, doc_uuid: str):
        return self.doc_collection.find_one({"doc_uuid": doc_uuid}, {"_id": 0})
    
    def delete_document(self, doc_uuid: str) -> bool:
        result = self.doc_collection.delete_one({"doc_uuid": doc_uuid})
        return result.deleted_count > 0