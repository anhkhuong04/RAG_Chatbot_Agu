import os
import re
import uuid
import hashlib
import logging
from datetime import datetime
import pandas as pd
from llama_index.core import VectorStoreIndex, StorageContext, SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_parse import LlamaParse
from typing import List, Optional
from striprtf.striprtf import rtf_to_text


# Configure logging
logger = logging.getLogger(__name__)

# Import LLM settings
from app.service.llm_factory import init_settings
from app.core.config import get_settings
from app.db import get_database, get_qdrant_client


class IngestionService:
    """Service for processing documents and indexing into vector database."""

    # ── Supported formats ──────────────────────────────────────────────
    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.docx', '.rtf', '.jpg', '.jpeg', '.png', '.csv'}
    LLAMAPARSE_EXTENSIONS = {'.pdf'}

    # ── CSV chunking ────────────────────────────────────────────────────
    # Number of rows per Document chunk; header is repeated in every chunk.
    ROWS_PER_CSV_CHUNK = 30

    # ── RTF encoding fallback order ─────────────────────────────────────
    RTF_ENCODINGS = ('utf-8', 'cp1252', 'latin1')

    # ── Parse method identifiers ─────────────────────────────────────────
    PARSE_METHOD_LLAMA = "llama_parse"
    PARSE_METHOD_LLAMA_CUSTOM = "llama_parse_custom"
    PARSE_METHOD_SIMPLE = "simple_directory_reader"

    # ── LlamaParse prompts ───────────────────────────────────────────────
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

    ADMISSION_SCORE_INSTRUCTION = """
        BẠN LÀ HỆ THỐNG TRÍCH XUẤT DỮ LIỆU ĐIỂM CHUẨN ĐẠI HỌC TỪ PDF.
        YÊU CẦU:
        1. Trích xuất toàn bộ dữ liệu dưới dạng bảng Markdown (`| Cột 1 | Cột 2 |`).
        2. Giữ nguyên toàn bộ nội dung, không tự ý gộp cột hay xóa cột.
        3. Tuyệt đối KHÔNG bỏ sót các dòng ghi chú, chú thích nằm ở phần cuối của bảng hoặc cuối trang. Hãy giữ chúng lại dưới dạng văn bản bình thường (Text) bên dưới bảng Markdown.
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
        settings = get_settings()

        # Connect to MongoDB
        self.db = get_database("university_db")
        self.doc_collection = self.db["documents"]

        # Connect to Qdrant
        self.qdrant_client = get_qdrant_client()

        # Collection name for vectors
        self.collection_name = settings.database.qdrant_collection_name

        # LlamaParse API key for PDF processing
        self.llama_api_key = os.getenv("LLAMA_CLOUD_API_KEY")

    # ── Static helpers ──────────────────────────────────────────────────

    @staticmethod
    def is_supported_file(filename: str) -> bool:
        ext = os.path.splitext(filename.lower())[1]
        return ext in IngestionService.SUPPORTED_EXTENSIONS

    @staticmethod
    def get_file_extension(filename: str) -> str:
        return os.path.splitext(filename.lower())[1]

    @staticmethod
    def _compute_file_hash(file_path: str) -> str:
        """Compute SHA-256 hash of the file for duplicate detection."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


    # ── Main entry point ────────────────────────────────────────────────

    def process_file(self, file_path: str, metadata: dict) -> str | None:
        filename = os.path.basename(file_path)
        ext = self.get_file_extension(filename)

        # Validate file extension
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file format: {ext}. Supported: {self.SUPPORTED_EXTENSIONS}"
            )

        # ── P0: Deduplication check via SHA-256 hash ────────────────────
        file_hash = self._compute_file_hash(file_path)
        existing_doc = self.doc_collection.find_one(
            {"file_hash": file_hash, "status": "INDEXED"}
        )
        if existing_doc:
            logger.info(
                f"Duplicate file detected (hash={file_hash[:12]}…). "
                f"Returning existing doc_uuid={existing_doc['doc_uuid']} — skipping re-index."
            )
            logger.info(
                f"Duplicate: '{filename}' already indexed as {existing_doc['doc_uuid']}. "
                "Skipping."
            )
            return existing_doc["doc_uuid"]

        doc_uuid = str(uuid.uuid4())
        logger.info(f"Processing file: {filename} (ID: {doc_uuid})...")

        # --- STEP 1: SAVE METADATA TO MONGODB (PENDING) ---
        doc_record = {
            "doc_uuid": doc_uuid,
            "filename": metadata.get("original_filename", filename),
            "file_hash": file_hash,
            "metadata": {
                "year": metadata.get("year"),
                "category": metadata.get("category"),
                "description": metadata.get("description"),
            },
            "status": "PENDING",
            "created_at": datetime.now(),
        }
        self.doc_collection.insert_one(doc_record)

        try:
            # --- STEP 2: LOAD DOCUMENT BASED ON FILE TYPE ---
            category = metadata.get("category")

            # All documents go through the standard Vector RAG path (Qdrant)
            documents, parsing_method = self._load_documents(file_path, ext, category)

            if not documents:
                raise ValueError(f"No content extracted from file: {filename}")

            logger.info(
                f"Loaded {len(documents)} document(s) from {ext} file "
                f"(method: {parsing_method})"
            )

            # Add parsing method to metadata for tracking
            metadata["parsing_method"] = parsing_method

            # --- STEP 3: Index to Qdrant ---
            chunk_count = self._index_nodes(documents, metadata, doc_uuid)

            self.doc_collection.update_one(
                {"doc_uuid": doc_uuid},
                {
                    "$set": {
                        "status": "INDEXED",
                        "storage_type": "qdrant",
                        "chunk_count": chunk_count,
                        "parsing_method": parsing_method,
                        "indexed_at": datetime.now(),
                    }
                },
            )

            logger.info(f"Successfully indexed to Qdrant: {filename} ({chunk_count} chunks)")
            return doc_uuid

        except Exception as e:
            # Update MongoDB with error status
            logger.exception(
                "Error processing file '%s' (doc_uuid=%s)", filename, doc_uuid
            )
            self.doc_collection.update_one(
                {"doc_uuid": doc_uuid},
                {"$set": {"status": "FAILED", "error": str(e)}},
            )
            return None

    # ── Document loading ────────────────────────────────────────────────

    def _load_documents(
        self, file_path: str, ext: str, category: str = None
    ) -> tuple[list, str]:
        if ext in self.LLAMAPARSE_EXTENSIONS:
            return self._load_with_llama_parse(file_path, category)
        elif ext == ".csv":
            return self._load_csv(file_path)
        elif ext == ".rtf":
            return self._load_rtf(file_path)
        else:
            return self._load_with_simple_reader(file_path)

    def _load_csv(self, file_path: str) -> tuple[list, str]:
        logger.info(f"Loading CSV file: {os.path.basename(file_path)}")

        last_error = None
        df = None
        for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin1"):
            try:
                df = pd.read_csv(
                    file_path, encoding=encoding, sep=None, engine="python"
                )
                logger.info(
                    f"CSV parsed with encoding={encoding}, rows={len(df)}"
                )
                break
            except Exception as exc:
                last_error = exc

        if df is None:
            raise ValueError(f"Failed to parse CSV file: {last_error}")
        if df.empty:
            raise ValueError("CSV file is empty")

        # Clean empty rows/cols
        df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
        if df.empty:
            raise ValueError("CSV has no usable rows after cleaning")

        filename = os.path.basename(file_path)
        total_rows = len(df)
        chunk_size = self.ROWS_PER_CSV_CHUNK
        num_chunks = max(1, (total_rows + chunk_size - 1) // chunk_size)

        documents: List[Document] = []
        for i in range(num_chunks):
            batch = df.iloc[i * chunk_size : (i + 1) * chunk_size]
            row_start = i * chunk_size + 1
            row_end = min((i + 1) * chunk_size, total_rows)
            table_md = self._dataframe_to_markdown(batch)

            text = (
                f"Nguồn dữ liệu CSV: {filename}\n"
                f"[Phần {i + 1}/{num_chunks} — hàng {row_start}–{row_end}/{total_rows}]\n\n"
                f"Bảng dữ liệu:\n{table_md}"
            )
            doc = Document(
                text=text,
                metadata={
                    "file_name": filename,
                    "file_type": "csv",
                    "csv_part": i + 1,
                    "csv_total_parts": num_chunks,
                },
            )
            documents.append(doc)

        logger.info(
            f"CSV '{filename}': {total_rows} rows → "
            f"{num_chunks} row-batched document(s) "
            f"({chunk_size} rows/chunk, header repeated in each)"
        )
        return documents, self.PARSE_METHOD_SIMPLE

    @staticmethod
    def _dataframe_to_markdown(df: pd.DataFrame) -> str:
        safe_df = df.fillna("").astype(str)
        headers = [
            h.strip() if isinstance(h, str) else str(h) for h in safe_df.columns
        ]

        def _escape_cell(value: str) -> str:
            return str(value).replace("|", "\\|").replace("\n", " ").strip()

        header_row = "| " + " | ".join(_escape_cell(h) for h in headers) + " |"
        separator_row = "| " + " | ".join(["---"] * len(headers)) + " |"

        data_rows = []
        for _, row in safe_df.iterrows():
            data_rows.append(
                "| " + " | ".join(_escape_cell(v) for v in row.tolist()) + " |"
            )

        return "\n".join([header_row, separator_row, *data_rows])

    def _get_parsing_instruction(self, category: str) -> tuple[str, bool]:
        if not category:
            return self.DEFAULT_PARSING_INSTRUCTION, False

        category_lower = category.lower().strip()

        if any(
            keyword in category_lower for keyword in ["điểm chuẩn", "diem chuan"]
        ):
            logger.info(f"Using ADMISSION_SCORE_INSTRUCTION for category: {category}")
            return self.ADMISSION_SCORE_INSTRUCTION, True

        if any(keyword in category_lower for keyword in ["học phí", "hoc phi"]):
            logger.info(f"Using TUITION_FEE_INSTRUCTION for category: {category}")
            return self.TUITION_FEE_INSTRUCTION, True

        logger.info(f"Using DEFAULT_PARSING_INSTRUCTION for category: {category}")
        return self.DEFAULT_PARSING_INSTRUCTION, False

    def _load_with_llama_parse(
        self, file_path: str, category: str = None
    ) -> tuple[list, str]:
        try:
            instruction, is_custom = self._get_parsing_instruction(category)

            parser = LlamaParse(
                api_key=self.llama_api_key,
                result_type="markdown",
                parsing_instruction=instruction,
                verbose=True,
            )

            parse_method = (
                self.PARSE_METHOD_LLAMA_CUSTOM if is_custom else self.PARSE_METHOD_LLAMA
            )

            logger.info(
                f"Using LlamaParse for PDF: {os.path.basename(file_path)} "
                f"(custom={is_custom})"
            )
            logger.info(
                f"Parsing PDF with {'CUSTOM' if is_custom else 'DEFAULT'} "
                f"instruction for category: {category or 'None'}"
            )

            documents = parser.load_data(file_path)

            if documents:
                for doc in documents:
                    doc.metadata["parsing_strategy"] = parse_method
                    doc.metadata["parsing_category"] = category or "general"

                logger.info(
                    f"LlamaParse successfully extracted {len(documents)} document(s)"
                )
                return documents, parse_method
            else:
                raise ValueError("LlamaParse returned empty documents")

        except Exception as e:
            logger.warning(
                f"LlamaParse failed: {str(e)}. Fallback to standard parser."
            )
            logger.warning(f"Fallback to standard parser due to: {str(e)}")
            return self._load_with_simple_reader(file_path)

    def _load_rtf(self, file_path: str) -> tuple[list, str]:
        logger.info(f"Loading RTF file: {os.path.basename(file_path)}")
        last_error: Optional[Exception] = None

        for enc in self.RTF_ENCODINGS:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    rtf_content = f.read()
                plain_text = rtf_to_text(rtf_content)
                logger.info(f"RTF decoded successfully with encoding={enc}")
                break
            except (UnicodeDecodeError, Exception) as exc:
                last_error = exc
                logger.debug(f"RTF decode failed with encoding={enc}: {exc}")
        else:
            raise ValueError(
                f"Failed to decode RTF file '{os.path.basename(file_path)}' "
                f"with any of {self.RTF_ENCODINGS}. Last error: {last_error}"
            )

        doc = Document(
            text=plain_text,
            metadata={"file_name": os.path.basename(file_path)},
        )
        return [doc], self.PARSE_METHOD_SIMPLE

    def _load_with_simple_reader(self, file_path: str) -> tuple[list, str]:
        logger.info(
            f"Loading file with SimpleDirectoryReader: {os.path.basename(file_path)}"
        )
        reader = SimpleDirectoryReader(
            input_files=[file_path], filename_as_id=True
        )
        documents = reader.load_data()
        return documents, self.PARSE_METHOD_SIMPLE

    # ── Indexing ────────────────────────────────────────────────────────

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
            doc.excluded_llm_metadata_keys = ["doc_uuid", "parsing_method"]
            doc.excluded_embed_metadata_keys = ["doc_uuid", "parsing_method"]

        splitter = SentenceSplitter(
            chunk_size=2048,
            chunk_overlap=400,
            paragraph_separator="\n\n",
        )
        nodes = splitter.get_nodes_from_documents(documents)

        # ── P2: Content validation ──────────────────────────────────────
        if not nodes:
            raise ValueError(
                "Chunking produced zero nodes — document may be empty or unreadable."
            )

        text_lengths = [len(n.text) for n in nodes]
        avg_len = sum(text_lengths) / len(text_lengths)
        short_nodes = sum(1 for l in text_lengths if l < 100)
        empty_nodes = sum(1 for l in text_lengths if l < 10)

        logger.info(
            f"Chunking summary: {len(nodes)} nodes | "
            f"avg_len={avg_len:.0f} chars | "
            f"min={min(text_lengths)} | max={max(text_lengths)} | "
            f"short(<100c)={short_nodes} | empty(<10c)={empty_nodes}"
        )

        if short_nodes > len(nodes) * 0.3:
            logger.warning(
                f"High ratio of short chunks: {short_nodes}/{len(nodes)} "
                f"({100 * short_nodes // len(nodes)}%). "
                "Consider reviewing source document quality or parsing settings."
            )

        if empty_nodes > 0:
            logger.warning(
                f"{empty_nodes} near-empty nodes detected (<10 chars). "
                "They will still be indexed but may add noise."
            )

        # Enrich nodes with section context
        nodes = self._enrich_nodes_with_context(nodes, metadata)

        logger.info(f"Split into {len(nodes)} chunks")

        # Index to Qdrant
        vector_store = QdrantVectorStore(
            client=self.qdrant_client, collection_name=self.collection_name
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # Automatically: Embed → Index → Upload to Qdrant
        VectorStoreIndex(nodes, storage_context=storage_context)

        return len(nodes)

    def _enrich_nodes_with_context(self, nodes, metadata):
        chapter_pattern = re.compile(
            r"(Chương\s+[IVXLCDM\d]+[.:]\s*[^\n]+)", re.IGNORECASE
        )
        article_pattern = re.compile(r"(Điều\s+\d+[.:]\s*[^\n]+)", re.IGNORECASE)
        section_pattern = re.compile(r"(Mục\s+\d+[.:]\s*[^\n]+)", re.IGNORECASE)

        current_chapter = ""
        current_article = ""
        current_section = ""

        for node in nodes:
            text = node.text

            chapter_match = chapter_pattern.search(text)
            if chapter_match:
                current_chapter = chapter_match.group(1).strip()

            article_match = article_pattern.search(text)
            if article_match:
                current_article = article_match.group(1).strip()

            section_match = section_pattern.search(text)
            if section_match:
                current_section = section_match.group(1).strip()

            context_parts = []
            if current_chapter:
                context_parts.append(current_chapter)
            if current_section:
                context_parts.append(current_section)
            if current_article:
                context_parts.append(current_article)

            if context_parts:
                node.metadata["section_context"] = " > ".join(context_parts)

            node.metadata["source_doc"] = metadata.get("original_filename", "")
            node.metadata["category"] = metadata.get("category", "")
            node.metadata["year"] = metadata.get("year", "")

        return nodes

    def get_all_documents(self):
        return list(self.doc_collection.find({}, {"_id": 0}))

    def get_document_by_id(self, doc_uuid: str):
        return self.doc_collection.find_one({"doc_uuid": doc_uuid}, {"_id": 0})