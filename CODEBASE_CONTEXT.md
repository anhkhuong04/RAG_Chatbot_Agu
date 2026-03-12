# CODEBASE_CONTEXT.md — University RAG Chatbot

> **Mục đích**: System Context cho AI coding assistant. Mô tả kiến trúc, luồng dữ liệu, và interface chính của project.

---

## 1. Tech Stack

| Layer | Technology | Version / Note |
|---|---|---|
| **Backend Framework** | FastAPI + Uvicorn | `python-multipart` for file upload |
| **LLM Orchestration** | LlamaIndex Core | `llama-index`, `llama-index-llms-openai`, `llama-index-embeddings-openai` |
| **LLM** | OpenAI GPT-4o-mini | `temperature=0.1` |
| **Embedding** | OpenAI text-embedding-3-small | 1536-dim |
| **Document Parsing** | LlamaParse (PDF), SimpleDirectoryReader (TXT/DOCX/Images) | `llama-parse`, `python-docx`, `pillow` |
| **Vector DB** | Qdrant | Docker `qdrant/qdrant:latest`, port `6333` |
| **App DB** | MongoDB 7.0 | Docker, port `27018`, db: `university_db` |
| **Hybrid Search** | BM25 + Dense Vector | `llama-index-retrievers-bm25`, `rank-bm25` |
| **Reranking** | Cross-Encoder (sentence-transformers) | Default: `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| **Web Search Fallback** | DuckDuckGo | `ddgs` |
| **Cache** | Redis (optional) | `redis` |
| **Frontend** | React 19 + TypeScript | Vite 7, TailwindCSS 3 |
| **Frontend Libs** | axios, react-markdown, react-router-dom, remark-gfm, lucide-react | |
| **Config** | Pydantic Settings | `.env` driven, nested settings |
| **Infra** | Docker Compose | `docker-compose.yml` (Qdrant + MongoDB) |

---

## 2. Project Structure (depth=3)

```
RAG Chatbot/
├── docker-compose.yml              # Qdrant + MongoDB containers
├── Backend/
│   ├── .env                        # OPENAI_API_KEY, MONGO_URI, QDRANT_URL, LLAMA_CLOUD_API_KEY
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point, CORS, router mount (/api/v1)
│   │   ├── core/
│   │   │   └── config.py           # Pydantic Settings: RetrievalSettings, DatabaseSettings, LLMSettings
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── __init__.py     # APIRouter aggregation (admin + chat)
│   │   │       └── endpoints/
│   │   │           ├── admin.py    # Upload/Delete/List documents, Clear cache
│   │   │           └── chat.py     # Chat (sync + SSE stream), History, Reset session
│   │   └── service/
│   │       ├── llm_factory.py      # init_settings(): LlamaIndex global LLM + Embedding config
│   │       ├── chat_service.py     # Core chat logic: intent routing, RAG pipeline, history
│   │       ├── ingestion_service.py# Document processing: parse → chunk → embed → Qdrant
│   │       ├── prompts/
│   │       │   ├── constants.py    # CHITCHAT_KEYWORDS, QUERY_INDICATORS, CHITCHAT_MAX_WORDS
│   │       │   ├── system_prompts.py # CHITCHAT_SYSTEM_PROMPT, RAG_SYSTEM_PROMPT
│   │       │   └── intent_prompts.py # INTENT_PROMPTS dict (intent → prompt template)
│   │       └── retrieval/
│   │           ├── hybrid_retriever.py  # HybridRetriever: Dense + BM25 with RRF fusion
│   │           ├── reranker.py          # CrossEncoderReranker: sentence-transformers
│   │           ├── metadata_filter.py   # MetadataFilterService: year/category extraction
│   │           └── query_rewriter.py    # QueryRewriter + HyDEQueryExpander
│   ├── data/                       # Local document storage
│   └── tests/
├── Frontend/
│   ├── .env                        # VITE_API_URL
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── src/
│       ├── App.tsx                 # Router (LandingPage, ChatPage, AdminPage)
│       ├── pages/
│       │   ├── ChatPage.tsx
│       │   ├── AdminPage.tsx
│       │   └── LandingPage.tsx
│       ├── components/
│       │   ├── chat/               # Chat UI components (6 files)
│       │   ├── admin/              # Admin UI components (3 files)
│       │   └── landing/            # Landing page components (6 files)
│       ├── services/
│       │   ├── chatAPI.ts          # POST /chat/stream (SSE), POST /chat, history, reset
│       │   └── adminAPI.ts         # POST /admin/upload, GET /admin/documents, DELETE
│       ├── hooks/
│       │   ├── useChat.ts          # Chat state management hook
│       │   └── useAdmin.ts         # Admin state management hook
│       └── types/
│           ├── chat.ts             # Chat TypeScript interfaces
│           └── admin.ts            # Admin TypeScript interfaces
├── mongo_data/                     # MongoDB persistent volume
└── qdrant_data/                    # Qdrant persistent volume
```

---

## 3. Core Data Flows

### 3.1 Luồng Ingestion (Document Upload → Vector DB)

```
Client POST /api/v1/admin/upload (multipart: file, year, category, description)
│
▼ admin.py::upload_document()
├── Validate file extension (SUPPORTED_EXTENSIONS: .pdf .txt .docx .jpg .jpeg .png)
├── Save UploadFile → tempfile
├── Build metadata dict {year, category, description, original_filename}
│
▼ IngestionService.process_file(temp_path, metadata)
├── Generate doc_uuid (UUID4)
├── Insert doc_record into MongoDB "documents" collection (status=PENDING)
├── _load_documents(file_path, ext, category)
│   ├── PDF → _load_with_llama_parse(file_path, category)
│   │       Uses category-specific instructions (Điểm chuẩn, Học phí, Default)
│   │       Fallback → SimpleDirectoryReader if LlamaParse fails
│   └── TXT/DOCX/IMG → _load_with_simple_reader(file_path)
├── _index_nodes(documents, metadata, doc_uuid)
│   ├── Attach metadata to each Document (doc_uuid, filename, year, category)
│   ├── SentenceSplitter(chunk_size=2048, chunk_overlap=400)
│   ├── _enrich_nodes_with_context() — detect Chương/Điều/Mục in Vietnamese legal docs
│   ├── Create QdrantVectorStore + StorageContext
│   └── VectorStoreIndex(nodes, storage_context) — auto embed (OpenAI) + upsert to Qdrant
├── Update MongoDB doc status → INDEXED (or FAILED)
│
▼ Return doc_uuid to client
```

### 3.2 Luồng Chat (RAG Query)

```
Client POST /api/v1/chat/stream  {message, session_id?}
│
▼ chat.py::chat_stream()
├── Get ChatService singleton
├── Generate session_id if not provided
│
▼ _sse_generator() — SSE stream wrapper
├── Classify intent: _classify_intent(message) → "CHITCHAT" | "QUERY"
├── Send SSE event: "metadata" {session_id, intent}
│
├── [If QUERY]:
│   ▼ _retrieve_and_rerank(message)
│   ├── Step 1: QueryRewriter.rewrite(message) — LLM-based query clarification
│   ├── Step 2: MetadataFilterService.extract_filters(message) — regex year/category
│   ├── Step 3: HybridRetriever.retrieve(search_query)
│   │           ├── Dense: VectorStoreIndex.as_retriever(top_k=10)
│   │           ├── Sparse: BM25Retriever(top_k=10)
│   │           └── RRF fusion (alpha=0.5, k=60) → final_top_k results
│   ├── Step 4: CrossEncoderReranker.rerank(query, nodes, top_n=5)
│   └── Step 5: MetadataFilterService.apply_post_filters(nodes, filters)
│   ├── Send SSE event: "sources" [source_strings]
│   │
│   ▼ _synthesize_response_stream(message, nodes)
│       Build context from nodes → LLM prompt (RAG_SYSTEM_PROMPT + INTENT_PROMPTS)
│       Stream via Settings.llm.astream_chat() → SSE "token" events
│
├── [If CHITCHAT]:
│   ▼ _handle_chitchat_stream(history, message)
│       Build messages (CHITCHAT_SYSTEM_PROMPT + history + user msg)
│       Stream via Settings.llm.astream_chat() → SSE "token" events
│
├── Save user msg + full assistant response to MongoDB "chat_sessions"
└── Send SSE event: "done"
```

---

## 4. Core Interfaces

### 4.1 `ChatService` (`app/service/chat_service.py`)

```python
class ChatService:
    """Service for handling RAG-based chat interactions with intent routing"""

    def __init__(self):
        # self.settings: Settings (from config.py)
        # self.mongo_client: MongoClient
        # self.db: university_db
        # self.chat_sessions: Collection "chat_sessions"
        # self.qdrant_client: QdrantClient
        # self.collection_name: str ("university_knowledge")
        # self._index: Optional[VectorStoreIndex] — lazy-loaded, thread-safe
        # self._query_engine: Optional — fallback query engine
        # self._index_lock: threading.Lock
        # self._hybrid_retriever: Optional[HybridRetriever]
        # self._reranker: Optional[CrossEncoderReranker]
        # self._metadata_filter: Optional[MetadataFilterService]
        # self._query_rewriter: Optional[QueryRewriter]
        # self._all_nodes: List[Any] — cached nodes for BM25

    # --- Public Methods ---
    async def process_message(self, session_id: str, message: str) -> Dict:
    async def process_message_stream(self, session_id: str, message: str) -> AsyncGenerator[str, None]:
    def get_session_history(self, session_id: str) -> List[dict]:
    def clear_session(self, session_id: str) -> bool:
    def get_all_sessions(self, limit: int = 20) -> List[dict]:
    def clear_cache(self) -> Dict:

    # --- Private (Key pipeline methods) ---
    def _classify_intent(self, message: str) -> str:  # → "CHITCHAT" | "QUERY"
    async def _retrieve_and_rerank(self, message: str) -> tuple[List[NodeWithScore], List[str]]:
    async def _handle_chitchat_stream(self, history: List[ChatMessage], message: str) -> AsyncGenerator[str, None]:
    async def _synthesize_response_stream(self, query: str, nodes: List[NodeWithScore], intent: str = "general") -> AsyncGenerator[str, None]:
    async def _handle_rag_query(self, message: str) -> tuple[str, List[str]]:
    async def _handle_advanced_rag_query(self, message: str) -> tuple[str, List[str]]:
    async def _handle_basic_rag_query(self, message: str) -> tuple[str, List[str]]:
    async def _handle_chitchat(self, history: List[ChatMessage], message: str) -> str:
    def _load_chat_history(self, session_id: str, limit: int = 5) -> List[ChatMessage]:
    def _save_to_history(self, session_id: str, role: str, content: str, sources: Optional[List[str]] = None):
    def _extract_sources(self, nodes: List[NodeWithScore]) -> List[str]:
```

### 4.2 `IngestionService` (`app/service/ingestion_service.py`)

```python
class IngestionService:
    """Service for processing documents and indexing into vector database"""

    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.docx', '.jpg', '.jpeg', '.png'}
    LLAMAPARSE_EXTENSIONS = {'.pdf'}

    def __init__(self):
        # self.mongo_client: MongoClient
        # self.db: university_db
        # self.doc_collection: Collection "documents"
        # self.qdrant_client: QdrantClient
        # self.collection_name: str ("university_knowledge")
        # self.llama_api_key: str

    # --- Public Methods ---
    @staticmethod
    def is_supported_file(filename: str) -> bool:
    @staticmethod
    def get_file_extension(filename: str) -> str:
    def process_file(self, file_path: str, metadata: dict) -> str | None:  # returns doc_uuid
    def get_all_documents(self) -> list:
    def get_document_by_id(self, doc_uuid: str) -> dict | None:
    def delete_document(self, doc_uuid: str) -> bool:

    # --- Private ---
    def _load_documents(self, file_path: str, ext: str, category: str = None) -> tuple[list, str]:
    def _get_parsing_instruction(self, category: str) -> tuple[str, bool]:
    def _load_with_llama_parse(self, file_path: str, category: str = None) -> tuple[list, str]:
    def _load_with_simple_reader(self, file_path: str) -> tuple[list, str]:
    def _index_nodes(self, documents, metadata: dict, doc_uuid: str) -> int:
    def _enrich_nodes_with_context(self, nodes, metadata) -> list:
```

### 4.3 `HybridRetriever` (`app/service/retrieval/hybrid_retriever.py`)

```python
class HybridRetriever(BaseRetriever):
    """Hybrid Retriever combining Dense (Vector) and Sparse (BM25) search.
    Uses Reciprocal Rank Fusion (RRF) to combine results."""

    def __init__(
        self,
        vector_index: VectorStoreIndex,
        nodes: List[Any],
        alpha: float = 0.5,         # 1.0=dense only, 0.0=sparse only
        dense_top_k: int = 10,
        sparse_top_k: int = 10,
        final_top_k: int = 10,
    ):
        # self.vector_retriever: VectorStoreRetriever
        # self.bm25_retriever: Optional[BM25Retriever]
        # self.alpha, self.dense_top_k, self.sparse_top_k, self.final_top_k

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
    def _reciprocal_rank_fusion(self, dense_nodes: List[NodeWithScore], sparse_nodes: List[NodeWithScore], k: int = 60) -> List[NodeWithScore]:
    def update_bm25_index(self, nodes: List[Any]) -> None:
```

### 4.4 Supporting Retrieval Classes

```python
# --- CrossEncoderReranker (retrieval/reranker.py) ---
class CrossEncoderReranker:
    def __init__(self, model_name: Optional[str] = None, top_n: int = 5, device: Optional[str] = None):
    def rerank(self, query: str, nodes: List[NodeWithScore], top_n: Optional[int] = None) -> List[NodeWithScore]:
    def rerank_with_scores(self, query: str, nodes: List[NodeWithScore]) -> List[tuple]:

# --- MetadataFilterService (retrieval/metadata_filter.py) ---
class MetadataFilterService:
    def __init__(self, default_year: Optional[int] = None):
    def extract_filters(self, query: str) -> Dict[str, Any]:
    def build_qdrant_filters(self, filters: Dict[str, Any]) -> Optional[MetadataFilters]:
    def apply_post_filters(self, nodes: List[NodeWithScore], filters: Dict[str, Any], strict: bool = False) -> List[NodeWithScore]:
    def get_filter_summary(self, filters: Dict[str, Any]) -> str:

# --- QueryRewriter (retrieval/query_rewriter.py) ---
@dataclass
class RewrittenQuery:
    original: str
    rewritten: str
    expanded_queries: List[str]
    extracted_keywords: List[str]
    detected_intent: str

class QueryRewriter:
    def __init__(self, enable_rewrite: bool = True, enable_expansion: bool = True, enable_keywords: bool = True, max_expanded_queries: int = 3):
    def rewrite(self, query: str) -> RewrittenQuery:
    def rewrite_simple(self, query: str) -> str:
    def get_all_queries(self, query: str) -> List[str]:

# --- HyDEQueryExpander (retrieval/query_rewriter.py) ---
class HyDEQueryExpander:
    def __init__(self, enabled: bool = False):  # Experimental, disabled by default
    def generate_hypothetical_document(self, query: str) -> str:
```

---

## 5. Data Models (Database Schema)

### 5.1 MongoDB — Collection: `documents`

```json
{
  "doc_uuid": "uuid4-string",
  "filename": "original_filename.pdf",
  "metadata": {
    "year": 2025,
    "category": "Điểm chuẩn",
    "description": "Điểm chuẩn trúng tuyển năm 2025"
  },
  "status": "PENDING | INDEXED | FAILED",
  "created_at": "ISODate",
  "indexed_at": "ISODate",           // set on success
  "chunk_count": 15,                 // number of chunks indexed
  "parsing_method": "llama_parse | llama_parse_custom | simple_directory_reader",
  "error": "error message"           // set on failure
}
```

### 5.2 MongoDB — Collection: `chat_sessions`

```json
{
  "session_id": "uuid4-string",
  "created_at": "ISODate",
  "last_activity": "ISODate",
  "messages": [
    {
      "role": "user | assistant",
      "content": "message text",
      "timestamp": "ISODate",
      "sources": ["file1.pdf", "file2.pdf"]  // optional, only on assistant RAG responses
    }
  ]
}
```

### 5.3 Qdrant — Collection: `university_knowledge`

Mỗi point trong Qdrant chứa payload metadata như sau:

| Field | Type | Description |
|---|---|---|
| `doc_uuid` | string | UUID liên kết với MongoDB `documents` |
| `filename` | string | Tên file gốc |
| `year` | int | Năm của tài liệu |
| `category` | string | Danh mục (Điểm chuẩn, Học phí, ...) |
| `section_context` | string | Context vị trí (Chương > Mục > Điều) |
| `file_name` | string | Redundant filename from LlamaIndex |
| `parsing_method` | string | Phương pháp parse đã dùng |
| `_node_content` | JSON string | LlamaIndex internal: `{text, metadata, ...}` |

> **Embedding**: `text-embedding-3-small` (1536 dims)
> **Chunking**: `SentenceSplitter(chunk_size=2048, chunk_overlap=400)`

---

## 6. API Endpoints Summary

### Admin (`/api/v1/admin`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/upload` | Upload & process document (multipart) |
| `GET` | `/documents` | List all documents |
| `DELETE` | `/documents/{doc_uuid}` | Delete document (MongoDB + Qdrant) |
| `POST` | `/clear-cache` | Invalidate ChatService in-memory caches |

### Chat (`/api/v1/chat`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/stream` | SSE streaming chat (primary) |
| `POST` | `/` | Synchronous chat (legacy) |
| `POST` | `/reset` | Clear session history |
| `GET` | `/history/{session_id}` | Get session messages |

---

## 7. Configuration Overview (`app/core/config.py`)

```
Settings
├── retrieval: RetrievalSettings (env_prefix="RAG_")
│   ├── enable_hybrid_search: bool = True
│   ├── hybrid_alpha: float = 0.5
│   ├── dense_top_k: int = 10
│   ├── sparse_top_k: int = 10
│   ├── enable_reranking: bool = True
│   ├── rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
│   ├── rerank_top_n: int = 5
│   ├── enable_metadata_filter: bool = True
│   ├── enable_query_rewrite: bool = True
│   ├── enable_query_expansion: bool = False
│   └── enable_keyword_extraction: bool = True
├── database: DatabaseSettings
│   ├── mongo_uri: str
│   ├── qdrant_url: str
│   └── qdrant_collection_name: str = "university_knowledge"
├── llm: LLMSettings
│   ├── openai_api_key: str
│   ├── llm_model: str = "gpt-4o-mini"
│   ├── llm_temperature: float = 0.1
│   └── embedding_model: str = "text-embedding-3-small"
└── api_cors_origins: list = ["http://localhost:5173"]
```
