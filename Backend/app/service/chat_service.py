import os
import re
import glob
import logging
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator
from pymongo import MongoClient
from qdrant_client import QdrantClient
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.schema import NodeWithScore
from llama_index.vector_stores.qdrant import QdrantVectorStore
from dotenv import load_dotenv
import pandas as pd

# Load environment variables
load_dotenv()

# Import LLM settings
from app.service.llm_factory import init_settings

# Import Advanced Retrieval components
from app.service.retrieval import (
    HybridRetriever,
    CrossEncoderReranker,
    MetadataFilterService,
    QueryRewriter,
)
from app.core.config import get_settings
from app.service.prompts import (
    CHITCHAT_KEYWORDS,
    QUERY_INDICATORS,
    SCORE_INDICATORS,
    FEE_INDICATORS,
    CAREER_INDICATORS,
    CHITCHAT_MAX_WORDS,
    CHITCHAT_SYSTEM_PROMPT,
    RAG_SYSTEM_PROMPT,
)

# Dynamic Prompt Service (replaces hardcoded INTENT_PROMPTS)
from app.service.prompt_service import get_prompt_service
import asyncio

# PandasQueryEngine (optional — requires llama-index-experimental)
try:
    from llama_index.experimental.query_engine import PandasQueryEngine
    HAS_PANDAS_ENGINE = True
except ImportError:
    HAS_PANDAS_ENGINE = False
    logging.getLogger(__name__).warning(
        "llama-index-experimental not installed. PandasQueryEngine unavailable."
    )

# Configure logging
logger = logging.getLogger(__name__)


class ChatService:
    """Service for handling RAG-based chat interactions with intent routing"""
    
    def __init__(self):
        """
        Initialize ChatService:
        - Initialize LlamaIndex Settings (LLM & Embeddings)
        - Connect to MongoDB (university_db.chat_sessions)
        - Connect to Qdrant and load university_knowledge index
        - Initialize Advanced RAG components (Hybrid Search + Reranking)
        """
        # Load configuration
        self.settings = get_settings()
        
        # Initialize LlamaIndex settings
        init_settings()
        
        # Connect to MongoDB for chat history
        self.mongo_client = MongoClient(os.getenv("MONGO_URI"))
        self.db = self.mongo_client["university_db"]
        self.chat_sessions = self.db["chat_sessions"]
        
        # Initialize dynamic prompt service
        self._prompt_service = get_prompt_service()

        # Connect to Qdrant for vector search
        self.qdrant_client = QdrantClient(url=os.getenv("QDRANT_URL"))
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME", "university_knowledge")
        
        # Initialize vector store and index
        self._index = None
        self._query_engine = None  # Kept for fallback
        self._index_lock = threading.Lock()  # Lock for thread-safe index initialization
        
        # Advanced RAG Components
        self._hybrid_retriever: Optional[HybridRetriever] = None
        self._reranker: Optional[CrossEncoderReranker] = None
        self._metadata_filter: Optional[MetadataFilterService] = None
        self._query_rewriter: Optional[QueryRewriter] = None
        self._all_nodes: List[Any] = []  # Cache for BM25 index
        
        # Structured data directory for CSV + metadata files
        self.structured_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "structured"
        )
        
        # Initialize Advanced RAG if enabled
        self._init_advanced_rag()
        
        # Pandas Query Engines for structured data (CSV)
        self._diem_chuan_engine = None
        self._hoc_phi_engine = None
        self._init_pandas_engines()
        
        # Startup diagnostics for Pandas engines
        if self._diem_chuan_engine:
            print("✅ PandasQueryEngine [Điểm chuẩn] sẵn sàng")
        else:
            print("⚠️ PandasQueryEngine [Điểm chuẩn] KHÔNG khả dụng — câu hỏi điểm chuẩn sẽ fallback sang RAG")
        if self._hoc_phi_engine:
            print("✅ PandasQueryEngine [Học phí] sẵn sàng")
        else:
            print("⚠️ PandasQueryEngine [Học phí] KHÔNG khả dụng — câu hỏi học phí sẽ fallback sang RAG")
        
        logger.info("✅ ChatService initialized")
        print("✅ ChatService initialized")

    def _get_intent_prompt(self, intent: str) -> str:
        """
        Get intent-specific prompt template from dynamic PromptService.
        Falls back to hardcoded prompts if service is unavailable.
        
        Args:
            intent: Intent name (e.g., "general", "diem_chuan")
            
        Returns:
            Prompt template string
        """
        try:
            return self._prompt_service.get_intent_prompt(intent)
        except Exception as e:
            logger.warning(f"Failed to get dynamic prompt for '{intent}': {e}")
            # Fallback to hardcoded
            from app.service.prompts.intent_prompts import INTENT_PROMPTS
            return INTENT_PROMPTS.get(intent, INTENT_PROMPTS.get("general", ""))

    def _init_advanced_rag(self):
        """
        Initialize Advanced RAG components:
        - Metadata Filter Service
        - Cross-Encoder Reranker
        - Hybrid Retriever (initialized lazily when nodes are available)
        """
        retrieval_config = self.settings.retrieval
        
        # Initialize Metadata Filter
        if retrieval_config.enable_metadata_filter:
            self._metadata_filter = MetadataFilterService(
                default_year=retrieval_config.default_year
            )
            logger.info("✅ MetadataFilterService initialized")
        
        # Initialize Query Rewriter
        if retrieval_config.enable_query_rewrite:
            self._query_rewriter = QueryRewriter(
                enable_rewrite=retrieval_config.enable_query_rewrite,
                enable_expansion=retrieval_config.enable_query_expansion,
                enable_keywords=retrieval_config.enable_keyword_extraction,
                max_expanded_queries=retrieval_config.max_expanded_queries,
            )
            logger.info("✅ QueryRewriter initialized")
        
        # Initialize Reranker
        if retrieval_config.enable_reranking:
            try:
                self._reranker = CrossEncoderReranker(
                    model_name=retrieval_config.rerank_model,
                    top_n=retrieval_config.rerank_top_n,
                )
                logger.info(f"Reranker initialized: {retrieval_config.rerank_model}")
            except Exception as e:
                logger.warning(f"Failed to initialize reranker: {e}")
                self._reranker = None
    
    def _get_index(self) -> Optional[VectorStoreIndex]:
        """Get or create the VectorStoreIndex from Qdrant (thread-safe)"""
        # First check without lock (fast path)
        if self._index is not None:
            return self._index
        
        # Acquire lock for initialization (slow path)
        with self._index_lock:
            # Double-check after acquiring lock to prevent race condition
            if self._index is not None:
                return self._index
            
            try:
                logger.info("Initializing VectorStoreIndex from Qdrant...")
                vector_store = QdrantVectorStore(
                    client=self.qdrant_client,
                    collection_name=self.collection_name
                )
                self._index = VectorStoreIndex.from_vector_store(vector_store)
                logger.info(f"Loaded index from Qdrant collection: {self.collection_name}")
                print(f"Loaded index from Qdrant collection: {self.collection_name}")
                
                # Initialize Hybrid Retriever after index is loaded
                self._init_hybrid_retriever()
                
            except Exception as e:
                logger.error(f"Could not load index from Qdrant: {e}")
                print(f"Could not load index from Qdrant: {e}")
                return None
        
        return self._index
    
    def _init_hybrid_retriever(self):
        """
        Initialize Hybrid Retriever after index is loaded.
        Loads all nodes from Qdrant for BM25 index.
        """
        if not self.settings.retrieval.enable_hybrid_search:
            logger.info("Hybrid search disabled in config")
            return
        
        if self._index is None:
            return
        
        try:
            # Load all nodes from Qdrant for BM25
            # When using from_vector_store(), docstore is empty, so we fetch from Qdrant
            self._all_nodes = self._load_nodes_from_qdrant()
            
            if self._all_nodes:
                retrieval_config = self.settings.retrieval
                self._hybrid_retriever = HybridRetriever(
                    vector_index=self._index,
                    nodes=self._all_nodes,
                    alpha=retrieval_config.hybrid_alpha,
                    dense_top_k=retrieval_config.dense_top_k,
                    sparse_top_k=retrieval_config.sparse_top_k,
                    final_top_k=retrieval_config.dense_top_k,  # Before reranking
                )
                logger.info("HybridRetriever initialized")
            else:
                logger.warning("No nodes available for Hybrid Retriever")
                
        except Exception as e:
            logger.error(f"Failed to initialize HybridRetriever: {e}")
            self._hybrid_retriever = None
    
    def _load_nodes_from_qdrant(self) -> List[Any]:
        """
        Load all text nodes from Qdrant for BM25 indexing.
        
        Returns:
            List of TextNode objects for BM25
        """
        from llama_index.core.schema import TextNode
        import json
        
        try:
            # Scroll through all points in Qdrant collection
            all_nodes = []
            offset = None
            batch_size = 100
            
            while True:
                # Fetch batch of points with payload
                results = self.qdrant_client.scroll(
                    collection_name=self.collection_name,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,  # We don't need vectors for BM25
                )
                
                points, next_offset = results
                
                if not points:
                    break
                
                # Convert Qdrant points to TextNode objects
                for point in points:
                    payload = point.payload or {}
                    text = ""
                    inner_metadata = {}
                    
                    # Parse _node_content JSON (LlamaIndex stores nodes this way)
                    node_content = payload.get('_node_content')
                    if node_content:
                        try:
                            content_dict = json.loads(node_content)
                            text = content_dict.get('text', '')
                            inner_metadata = content_dict.get('metadata', {})
                        except (json.JSONDecodeError, TypeError):
                            text = str(node_content)
                    
                    # Fallback to direct text field
                    if not text:
                        text = payload.get('text', '')
                    
                    if text:
                        # Build metadata from payload (top-level) and inner metadata
                        metadata = {
                            'doc_uuid': payload.get('doc_uuid', inner_metadata.get('doc_uuid', '')),
                            'filename': payload.get('filename', inner_metadata.get('filename', '')),
                            'file_name': inner_metadata.get('file_name', ''),
                            'year': payload.get('year', inner_metadata.get('year')),
                            'category': payload.get('category', inner_metadata.get('category', '')),
                            'section_context': inner_metadata.get('section_context', ''),
                        }
                        
                        # Create TextNode
                        node = TextNode(
                            text=text,
                            id_=str(point.id),
                            metadata=metadata,
                        )
                        all_nodes.append(node)
                
                offset = next_offset
                if offset is None:
                    break
            
            logger.info(f"📚 Loaded {len(all_nodes)} nodes from Qdrant for BM25")
            return all_nodes
            
        except Exception as e:
            logger.error(f"Failed to load nodes from Qdrant: {e}")
            return []
    
    def _get_query_engine(self):
        """Get or create the query engine with similarity_top_k=3 and system prompt (FALLBACK)"""
        if self._query_engine is None:
            index = self._get_index()
            if index:
                self._query_engine = index.as_query_engine(
                    similarity_top_k=5,
                    response_mode="compact",
                    system_prompt=RAG_SYSTEM_PROMPT
                )
        return self._query_engine
    
    def _classify_intent(self, message: str) -> str:
        """
        Classify user message intent using multi-factor analysis.
        
        Priority (highest first):
        1. Score-specific indicators → QUERY_SCORES
        2. Fee-specific indicators → QUERY_FEES
        3. Career advice indicators → CAREER_ADVICE
        4. General query indicators → QUERY_DOCS
        5. Message length (long = QUERY_DOCS)
        6. Chitchat keywords (short msgs only) → CHITCHAT
        7. Default → QUERY_DOCS
        
        Args:
            message: User's message
            
        Returns:
            One of: "CHITCHAT", "QUERY_DOCS", "QUERY_SCORES", "QUERY_FEES", "CAREER_ADVICE"
        """
        message_lower = message.lower().strip()
        words = message_lower.split()
        word_count = len(words)
        
        # Priority 1: Check for SCORE-specific indicators
        for indicator in SCORE_INDICATORS:
            if indicator in message_lower:
                logger.debug(f"Score indicator found: '{indicator}' → QUERY_SCORES")
                return "QUERY_SCORES"
        
        # Priority 2: Check for FEE-specific indicators
        for indicator in FEE_INDICATORS:
            if indicator in message_lower:
                logger.debug(f"Fee indicator found: '{indicator}' → QUERY_FEES")
                return "QUERY_FEES"
        
        # Priority 3: Check for CAREER_ADVICE indicators
        for indicator in CAREER_INDICATORS:
            if indicator in message_lower:
                logger.debug(f"Career indicator found: '{indicator}' → CAREER_ADVICE")
                return "CAREER_ADVICE"
        
        # Priority 4: Check for general query indicators
        for indicator in QUERY_INDICATORS:
            if indicator in message_lower:
                logger.debug(f"Query indicator found: '{indicator}' → QUERY_DOCS")
                return "QUERY_DOCS"
        
        # Priority 4: Long messages are typically queries
        if word_count > CHITCHAT_MAX_WORDS:
            return "QUERY_DOCS"
        
        # Priority 5: Only classify as CHITCHAT if message is short AND has chitchat keyword
        for keyword in CHITCHAT_KEYWORDS:
            pattern = rf'\b{re.escape(keyword)}\b'
            if re.search(pattern, message_lower):
                logger.debug(f"Chitchat keyword found: '{keyword}' (words={word_count}) → CHITCHAT")
                return "CHITCHAT"
        
        # Default: treat as knowledge query
        return "QUERY_DOCS"
    
    def _load_chat_history(self, session_id: str, limit: int = 5) -> List[ChatMessage]:
        """
        Load the last N messages from MongoDB and convert to LlamaIndex ChatMessage objects.
        
        Args:
            session_id: The chat session ID
            limit: Maximum number of messages to retrieve (default: 5)
            
        Returns:
            List of ChatMessage objects for LlamaIndex
        """
        try:
            session = self.chat_sessions.find_one({"session_id": session_id})
            if not session or "messages" not in session:
                return []
            
            # Get the last N messages
            messages = session["messages"][-limit:]
            
            # Convert to LlamaIndex ChatMessage objects
            chat_messages = []
            for msg in messages:
                role = MessageRole.USER if msg["role"] == "user" else MessageRole.ASSISTANT
                chat_messages.append(ChatMessage(role=role, content=msg["content"]))
            
            return chat_messages
            
        except Exception as e:
            print(f"Could not load chat history: {e}")
            return []

    async def _resolve_coreferences(
        self, message: str, history: List[ChatMessage]
    ) -> str:
        """
        Resolve coreferences (anaphora) in user message using chat history.
        
        When users refer to previous context with pronouns or demonstratives
        like "2 ngành này", "ngành đó", "trường này", this method rewrites 
        the message into a self-contained query.
        
        Args:
            message: Current user message (may contain unresolved references)
            history: Recent chat history for context
            
        Returns:
            Self-contained message with references resolved, or original if 
            no resolution needed.
        """
        if not history:
            return message
        
        # Quick check: skip if message likely has no unresolved references
        coreference_indicators = [
            "này", "đó", "trên", "kia", "ấy",
            "nó", "chúng", "họ",
            "2 ngành", "hai ngành", "các ngành",
            "ngành đó", "ngành này", "trường đó", "trường này",
            "mấy ngành", "những ngành",
        ]
        message_lower = message.lower()
        has_coreference = any(ind in message_lower for ind in coreference_indicators)
        if not has_coreference:
            return message
        
        try:
            # Build conversation context from history
            history_text = ""
            for msg in history[-6:]:  # Last 6 messages (3 turns)
                role_label = "User" if msg.role == MessageRole.USER else "Bot"
                history_text += f"{role_label}: {msg.content}\n"
            
            resolve_prompt = (
                "Bạn là chuyên gia xử lý ngôn ngữ tự nhiên.\n"
                "Nhiệm vụ: Viết lại câu hỏi hiện tại thành câu hỏi ĐỘC LẬP, TỰ ĐẦY ĐỦ ngữ cảnh.\n\n"
                "Quy tắc:\n"
                "1. Thay thế đại từ chỉ thị (này, đó, ấy, kia) bằng thực thể cụ thể từ lịch sử hội thoại\n"
                "2. Giữ nguyên ý nghĩa và intent của câu hỏi gốc\n"
                "3. Nếu câu hỏi đã đủ rõ ràng, trả về nguyên văn\n"
                "4. CHỈ trả về câu hỏi đã viết lại, KHÔNG giải thích\n\n"
                "Ví dụ:\n"
                "Lịch sử: User hỏi về ngành CNTT và KTPM\n"
                "Câu hỏi: 'điểm chuẩn 2 ngành này năm trước'\n"
                "→ 'điểm chuẩn ngành Công nghệ thông tin và Kỹ thuật phần mềm năm trước'"
            )
            
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=resolve_prompt),
                ChatMessage(
                    role=MessageRole.USER,
                    content=(
                        f"Lịch sử hội thoại gần đây:\n{history_text}\n"
                        f"Câu hỏi hiện tại: {message}\n\n"
                        f"Viết lại câu hỏi (chỉ trả về câu hỏi đã viết lại):"
                    ),
                ),
            ]
            
            response = await Settings.llm.achat(messages)
            resolved = response.message.content.strip().strip('"\'')
            resolved = ' '.join(resolved.split())
            
            if resolved and len(resolved) >= 3:
                logger.info(f"🔗 Coreference resolved: '{message}' → '{resolved}'")
                return resolved
            
            return message
            
        except Exception as e:
            logger.warning(f"Coreference resolution failed: {e}")
            return message

    def _save_to_history(
        self, 
        session_id: str, 
        role: str, 
        content: str, 
        sources: Optional[List[str]] = None
    ):
        """
        Save a message to MongoDB chat history.
        
        Args:
            session_id: The chat session ID
            role: "user" or "assistant"
            content: Message content
            sources: Optional list of source filenames (for assistant RAG responses)
        """
        try:
            message_doc = {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow()
            }
            
            # Add sources if provided (for RAG responses)
            if sources:
                message_doc["sources"] = sources
            
            # Update or create session document
            self.chat_sessions.update_one(
                {"session_id": session_id},
                {
                    "$push": {"messages": message_doc},
                    "$set": {"last_activity": datetime.utcnow()},
                    "$setOnInsert": {"created_at": datetime.utcnow()}
                },
                upsert=True
            )
            
        except Exception as e:
            print(f"Could not save to history: {e}")
    
    async def process_message(self, session_id: str, message: str) -> Dict:
        """
        Process a user message with 4-way intent routing.
        
        Workflow:
        1. Load last 5 messages from history
        2. Classify intent (CHITCHAT, QUERY_DOCS, QUERY_SCORES, QUERY_FEES)
        3. Execute appropriate handler
        4. Save user message and assistant response to history
        5. Return response with metadata
        
        Args:
            session_id: Unique session identifier
            message: User's message
            
        Returns:
            Dict with keys: response, sources, intent
        """
        print(f"Processing message: {message[:50]}...")
        print(f"Session ID: {session_id}")
        
        try:
            # Step 1: Load chat history (last 5 messages)
            history = self._load_chat_history(session_id, limit=5)
            print(f"Loaded {len(history)} messages from history")
            
            # Step 2: Classify intent
            intent = self._classify_intent(message)
            print(f"Intent classified as: {intent}")
            
            # Initialize response variables
            response_text = ""
            sources = []
            
            # Step 3: Execute based on intent
            if intent == "CHITCHAT":
                response_text = await self._handle_chitchat(history, message)
                
            elif intent == "QUERY_SCORES" and self._diem_chuan_engine:
                resolved_message = await self._resolve_coreferences(message, history)
                response_text, sources = await self._handle_pandas_query(
                    self._diem_chuan_engine, resolved_message, "Bảng điểm chuẩn", intent="diem_chuan"
                )
                
            elif intent == "QUERY_FEES" and self._hoc_phi_engine:
                resolved_message = await self._resolve_coreferences(message, history)
                response_text, sources = await self._handle_pandas_query(
                    self._hoc_phi_engine, resolved_message, "Bảng học phí", intent="hoc_phi"
                )
                
            elif intent == "CAREER_ADVICE":
                response_text = await self._handle_career_advice(history, message)
                sources = ["Tư vấn từ chuyên gia AI - Khoa CNTT"]
                
            else:  # QUERY_DOCS or fallback when CSV engine unavailable
                resolved_message = await self._resolve_coreferences(message, history)
                response_text, sources = await self._handle_rag_query(resolved_message)
            
            # Step 4: Save to history
            self._save_to_history(session_id, "user", message)
            self._save_to_history(
                session_id, 
                "assistant", 
                response_text, 
                sources if sources else None
            )
            
            # Step 5: Return response
            return {
                "response": response_text,
                "sources": sources,
                "intent": intent
            }
            
        except Exception as e:
            print(f"Error processing message: {e}")
            return {
                "response": "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại sau.",
                "sources": [],
                "intent": "ERROR",
                "error": str(e)
            }
    
    async def process_message_stream(
        self, session_id: str, message: str
    ) -> AsyncGenerator[str, None]:
        """
        Process a user message with 4-way intent routing and stream the response.
        Yields text chunks as they arrive from the LLM.
        After streaming completes, saves the full response to MongoDB.

        Args:
            session_id: Unique session identifier
            message: User's message

        Yields:
            str chunks of the response
        """
        print(f"[STREAM] Processing message: {message[:50]}...")
        print(f"[STREAM] Session ID: {session_id}")

        full_response = ""
        sources: List[str] = []
        intent = "UNKNOWN"

        try:
            # Step 1: Load chat history
            history = self._load_chat_history(session_id, limit=5)
            print(f"[STREAM] Loaded {len(history)} messages from history")

            # Step 2: Classify intent (non-streaming, fast)
            intent = self._classify_intent(message)
            print(f"[STREAM] Intent classified as: {intent}")

            # Step 3: Save user message to history immediately
            self._save_to_history(session_id, "user", message)

            # Step 4: Stream based on intent (4-way routing)
            if intent == "CHITCHAT":
                async for chunk in self._handle_chitchat_stream(history, message):
                    full_response += chunk
                    yield chunk
                    
            elif intent == "QUERY_SCORES" and self._diem_chuan_engine:
                # Resolve coreferences before pandas query
                resolved_message = await self._resolve_coreferences(message, history)
                # Pandas-based score query
                async for chunk in self._handle_pandas_query_stream(
                    self._diem_chuan_engine, resolved_message, "Bảng điểm chuẩn", intent="diem_chuan"
                ):
                    full_response += chunk
                    yield chunk
                sources = ["Truy xuất từ Bảng điểm chuẩn"]
                    
            elif intent == "QUERY_FEES" and self._hoc_phi_engine:
                # Resolve coreferences before pandas query
                resolved_message = await self._resolve_coreferences(message, history)
                # Pandas-based fee query
                async for chunk in self._handle_pandas_query_stream(
                    self._hoc_phi_engine, resolved_message, "Bảng học phí", intent="hoc_phi"
                ):
                    full_response += chunk
                    yield chunk
                sources = ["Truy xuất từ Bảng học phí"]

            elif intent == "CAREER_ADVICE":
                # Career advice: use LLM base knowledge, no Qdrant retrieval
                async for chunk in self._handle_career_advice_stream(history, message):
                    full_response += chunk
                    yield chunk
                sources = ["Tư vấn từ chuyên gia AI - Khoa CNTT"]
                    
            else:  # QUERY_DOCS or fallback
                # Resolve coreferences before retrieval
                resolved_message = await self._resolve_coreferences(message, history)
                # Retrieval & Reranking (non-streaming)
                nodes, sources = await self._retrieve_and_rerank(resolved_message)

                if not nodes:
                    fallback = (
                        "Tôi không tìm thấy thông tin phù hợp trong cơ sở dữ liệu. "
                        "Vui lòng thử lại với câu hỏi khác hoặc liên hệ phòng Tuyển sinh."
                    )
                    full_response = fallback
                    yield fallback
                else:
                    # Stream the LLM generation step
                    async for chunk in self._synthesize_response_stream(
                        resolved_message, nodes
                    ):
                        full_response += chunk
                        yield chunk

            # Step 5: Save full assistant response to MongoDB after stream completes
            self._save_to_history(
                session_id,
                "assistant",
                full_response,
                sources if sources else None,
            )
            print(f"[STREAM] Saved full response ({len(full_response)} chars) to DB")

        except Exception as e:
            logger.error(f"[STREAM] Error: {e}")
            error_msg = "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại sau."
            if not full_response:
                yield error_msg
            # Still save partial response if any
            if full_response:
                self._save_to_history(
                    session_id, "assistant", full_response,
                    sources if sources else None
                )

    async def _retrieve_and_rerank(
        self, message: str
    ) -> tuple[List[NodeWithScore], List[str]]:
        """
        Execute the retrieval + reranking pipeline (non-streaming).
        Extracted from _handle_advanced_rag_query for reuse.

        Returns:
            Tuple of (final_nodes, source_strings)
        """
        retrieval_config = self.settings.retrieval

        # Ensure index is loaded
        index = self._get_index()
        if index is None:
            return [], []

        # Step 1: Query Rewriting
        search_query = message
        rewritten_result = None

        if self._query_rewriter:
            try:
                rewritten_result = await self._query_rewriter.rewrite(message)
                search_query = rewritten_result.rewritten
                logger.info(f"Query rewritten: '{message[:30]}...' → '{search_query[:30]}...'")
            except Exception as e:
                logger.warning(f"Query rewriting failed: {e}")
                search_query = message

        # Step 2: Extract metadata filters
        filters = {}
        if self._metadata_filter:
            filters = self._metadata_filter.extract_filters(message)
            if filters:
                logger.info(f"Extracted filters: {filters}")

        # Step 3: Hybrid Retrieval
        if self._hybrid_retriever:
            logger.info("🔍 Using Hybrid Retrieval (Dense + BM25)")
            retrieved_nodes = await asyncio.to_thread(
                self._hybrid_retriever.retrieve, search_query
            )
        else:
            logger.info("🔍 Using Dense-only Retrieval")
            retriever = index.as_retriever(
                similarity_top_k=retrieval_config.dense_top_k
            )
            retrieved_nodes = await asyncio.to_thread(
                retriever.retrieve, search_query
            )

        logger.info(f"Retrieved {len(retrieved_nodes)} nodes")

        # Step 4: Reranking
        if self._reranker and retrieved_nodes:
            reranked_nodes = await self._reranker.rerank(
                query=message, nodes=retrieved_nodes
            )
        else:
            reranked_nodes = retrieved_nodes[:retrieval_config.rerank_top_n]

        # Step 5: Post-filtering
        if filters and self._metadata_filter:
            final_nodes = self._metadata_filter.apply_post_filters(
                reranked_nodes, filters, strict=False
            )
        else:
            final_nodes = reranked_nodes

        logger.info(f"Final nodes for synthesis: {len(final_nodes)}")

        sources = self._extract_sources(final_nodes) if final_nodes else []
        return final_nodes, sources

    async def _handle_chitchat_stream(
        self, history: List[ChatMessage], message: str
    ) -> AsyncGenerator[str, None]:
        """
        Handle chitchat messages using streaming LLM.

        Yields:
            Text chunks from the LLM
        """
        try:
            messages = [
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=CHITCHAT_SYSTEM_PROMPT,
                )
            ]
            messages.extend(history)
            messages.append(ChatMessage(role=MessageRole.USER, content=message))

            # Use streaming chat
            response = await Settings.llm.astream_chat(messages)
            async for chunk in response:
                # chunk.delta contains the incremental text
                if hasattr(chunk, 'delta') and chunk.delta:
                    yield chunk.delta

        except Exception as e:
            logger.error(f"Chitchat stream error: {e}")
            yield "Xin chào! Tôi là Trợ lý Tuyển sinh. Tôi có thể giúp gì cho bạn?"

    async def _handle_career_advice(
        self, history: List[ChatMessage], message: str
    ) -> str:
        """
        Handle career advice using LLM base knowledge (no Qdrant retrieval).

        Args:
            history: Chat history
            message: User's message

        Returns:
            Full response text
        """
        try:
            career_prompt = self._get_intent_prompt("career_advice")
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=career_prompt),
            ]
            messages.extend(history)
            messages.append(ChatMessage(role=MessageRole.USER, content=message))

            response = await Settings.llm.achat(messages)
            return response.message.content

        except Exception as e:
            logger.error(f"Career advice error: {e}")
            return (
                "Xin lỗi, tôi chưa thể tư vấn hướng nghiệp lúc này. "
                "Vui lòng thử lại sau hoặc liên hệ Khoa CNTT - ĐH An Giang."
            )

    async def _handle_career_advice_stream(
        self, history: List[ChatMessage], message: str
    ) -> AsyncGenerator[str, None]:
        """
        Handle career advice messages using streaming LLM (no Qdrant retrieval).
        Uses LLM base knowledge with career_advice prompt.

        Args:
            history: Chat history
            message: User's message

        Yields:
            Text chunks from the LLM
        """
        try:
            career_prompt = self._get_intent_prompt("career_advice")
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=career_prompt),
            ]
            messages.extend(history)
            messages.append(ChatMessage(role=MessageRole.USER, content=message))

            response = await Settings.llm.astream_chat(messages)
            async for chunk in response:
                if hasattr(chunk, 'delta') and chunk.delta:
                    yield chunk.delta

        except Exception as e:
            logger.error(f"Career advice stream error: {e}")
            yield (
                "Xin lỗi, tôi chưa thể tư vấn hướng nghiệp lúc này. "
                "Vui lòng thử lại sau hoặc liên hệ Khoa CNTT - ĐH An Giang."
            )

    async def _synthesize_response_stream(
        self,
        query: str,
        nodes: List[NodeWithScore],
        intent: str = "general",
    ) -> AsyncGenerator[str, None]:
        """
        Stream the LLM synthesis step for RAG responses.

        Yields:
            Text chunks from the LLM
        """
        try:
            if Settings.llm is None:
                yield "Xin lỗi, hệ thống LLM chưa được khởi tạo."
                return

            # Build context from nodes
            context_parts = []
            for i, node in enumerate(nodes, 1):
                try:
                    node_text = node.node.get_content()
                    metadata = node.node.metadata or {}
                    source = metadata.get('filename', metadata.get('file_name', 'Unknown'))
                    year = metadata.get('year', '')

                    context_header = f"[Nguồn {i}: {source}"
                    if year:
                        context_header += f" - Năm {year}"
                    context_header += "]"
                    context_parts.append(f"{context_header}\n{node_text}")
                except Exception as node_err:
                    logger.warning(f"Error extracting node {i}: {node_err}")
                    continue

            if not context_parts:
                yield "Không thể trích xuất thông tin từ cơ sở dữ liệu."
                return

            context = "\n\n---\n\n".join(context_parts)

            intent_prompt = self._get_intent_prompt(intent)

            prompt = f"""{RAG_SYSTEM_PROMPT}
            {intent_prompt}
            ## Ngữ cảnh (Context):
            {context}

            ## Câu hỏi của người dùng:
            {query}

            ## Trả lời:"""

            messages = [
                ChatMessage(role=MessageRole.USER, content=prompt)
            ]

            # Stream from LLM
            response = await Settings.llm.astream_chat(messages)
            async for chunk in response:
                if hasattr(chunk, 'delta') and chunk.delta:
                    yield chunk.delta

        except Exception as e:
            logger.error(f"Response stream synthesis error: {e}")
            yield "Xin lỗi, đã có lỗi khi tổng hợp câu trả lời."

    async def _handle_chitchat(self, history: List[ChatMessage], message: str) -> str:
        """
        Handle chitchat messages using LLM with conversation history.
        
        Args:
            history: Previous chat messages
            message: Current user message
            
        Returns:
            LLM response text
        """
        try:
            # Build messages list with system prompt
            messages = [
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=CHITCHAT_SYSTEM_PROMPT
                )
            ]
            
            # Add conversation history
            messages.extend(history)
            
            # Add current user message
            messages.append(ChatMessage(role=MessageRole.USER, content=message))
            
            # Call LLM
            response = await Settings.llm.achat(messages)
            
            return response.message.content
            
        except Exception as e:
            print(f"Chitchat error: {e}")
            return "Xin chào! Tôi là Trợ lý Tuyển sinh. Tôi có thể giúp gì cho bạn về thông tin tuyển sinh, điểm chuẩn, học phí?"
    
    # ============================================
    # PANDAS QUERY ENGINE METHODS
    # ============================================
    
    def _read_metadata_file(self, filename: str) -> str:
        """Đọc nội dung file metadata (.txt) nếu tồn tại"""
        filepath = os.path.join(self.structured_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                logger.info(f"📝 Loaded dynamic metadata from {filename} ({len(content)} chars)")
                return content
        logger.info(f"📝 No metadata file found: {filename}")
        return ""
    
    def _detect_latest_year(self, prefix: str) -> int | None:
        """
        Auto-detect the latest academic year from CSV filenames in structured_dir.
        Scans for files matching `{prefix}_*.csv` and extracts the max year.
        
        Returns:
            The latest year found, or None if no files exist.
        """
        import re
        pattern = os.path.join(self.structured_dir, f"{prefix}_*.csv")
        csv_files = glob.glob(pattern)
        years = []
        for f in csv_files:
            match = re.search(rf"{prefix}_(\d{{4}})", os.path.basename(f))
            if match:
                years.append(int(match.group(1)))
        return max(years) if years else None

    def _init_pandas_engines(self, year: int | None = None):
        """
        Initialize PandasQueryEngine instances for structured CSV data.
        Reads dynamic metadata from .txt files generated by Ingestion Pipeline.
        
        Args:
            year: Academic year for file naming. If None, auto-detects
                  the latest year from existing CSV filenames.
        """
        if not HAS_PANDAS_ENGINE:
            logger.warning("PandasQueryEngine not available. Skipping CSV engine init.")
            return
        
        if not os.path.isdir(self.structured_dir):
            logger.info(f"Structured data dir not found: {self.structured_dir}")
            return
        
        # --- 1. ENGINE ĐIỂM CHUẨN ---
        dc_year = year or self._detect_latest_year("diem_chuan")
        if dc_year:
            diem_chuan_meta = self._read_metadata_file(f"diem_chuan_{dc_year}_metadata.txt")
            self._diem_chuan_engine = self._load_csv_engine(
                self.structured_dir, "diem_chuan",
                "Dữ liệu điểm chuẩn tuyển sinh Đại học An Giang",
                dynamic_notes=diem_chuan_meta
            )
            logger.info(f"📊 Điểm chuẩn engine initialized for year {dc_year}")
        else:
            logger.info("📊 No điểm chuẩn CSV files found — skipping engine init")
        
        # --- 2. ENGINE HỌC PHÍ ---
        hp_year = year or self._detect_latest_year("hoc_phi")
        if hp_year:
            hoc_phi_meta = self._read_metadata_file(f"hoc_phi_{hp_year}_metadata.txt")
            self._hoc_phi_engine = self._load_multi_csv_engine(
                self.structured_dir, "hoc_phi",
                "Dữ liệu học phí Đại học An Giang",
                dynamic_notes=hoc_phi_meta
            )
            logger.info(f"📊 Học phí engine initialized for year {hp_year}")
        else:
            logger.info("📊 No học phí CSV files found — skipping engine init")
    
    def _load_csv_engine(self, directory: str, prefix: str, description: str, dynamic_notes: str = ""):
        """
        Load the latest CSV file matching a prefix and create a PandasQueryEngine.
        Uses dynamic metadata notes from .txt files instead of hardcoded dictionary.
        
        Args:
            directory: Path to the structured data directory
            prefix: Filename prefix (e.g. "diem_chuan", "hoc_phi")
            description: Description of the data for LLM context
            dynamic_notes: Dynamic metadata/notes from ingestion pipeline
            
        Returns:
            PandasQueryEngine or None
        """
        try:
            pattern = os.path.join(directory, f"{prefix}_*.csv")
            csv_files = sorted(glob.glob(pattern), reverse=True)  # Latest first
            
            if not csv_files:
                logger.info(f"No CSV files found for prefix: {prefix}")
                return None
            
            latest_csv = csv_files[0]
            df = pd.read_csv(latest_csv, encoding='utf-8-sig')
            
            if df.empty:
                logger.warning(f"Empty CSV file: {latest_csv}")
                return None
            
            # Build instruction with Dynamic Metadata + Schema
            columns_str = ", ".join(df.columns.tolist())
            notes_section = ""
            if dynamic_notes:
                notes_section = (
                    f"--- CHÚ THÍCH & TỪ ĐIỂN DỮ LIỆU (trích từ tài liệu gốc) ---\n"
                    f"{dynamic_notes}\n\n"
                )
            
            instruction_str = (
                f"Bạn là chuyên gia phân tích dữ liệu tuyển sinh. "
                f"Hãy viết code Pandas (df) để tìm câu trả lời chính xác.\n\n"
                f"{notes_section}"
                f"--- DYNAMIC SCHEMA ---\n"
                f"DataFrame 'df' có {len(df)} dòng với các cột: [{columns_str}]\n"
                f"Mô tả: {description}\n\n"
                f"QUAN TRỌNG: Output CHỈ là raw executable Python code.\n"
                f"KHÔNG được bọc code trong markdown code blocks (``` hoặc ```python).\n"
                f"KHÔNG thêm giải thích hay comment. CHỈ code thuần.\n"
                f"Biến DataFrame tên là 'df'.\n"
                f"KHÔNG dùng print(). Dòng cuối cùng PHẢI là một expression trả về kết quả (ví dụ: df[df['NganhHoc'] == 'X'] hoặc result).\n"
                f"Khi dùng str.contains(), LUÔN thêm na=False để tránh lỗi NaN. Ví dụ: df[df['NganhHoc'].str.contains('keyword', case=False, na=False)]\n"
            )
            
            engine = PandasQueryEngine(
                df=df,
                verbose=True,
                synthesize_response=False,
                instruction_str=instruction_str,
            )
            
            logger.info(f"📊 Loaded PandasQueryEngine from {latest_csv} ({len(df)} rows, cols={columns_str}, metadata={'yes' if dynamic_notes else 'no'})")
            print(f"📊 Loaded PandasQueryEngine from {latest_csv} ({len(df)} rows, metadata={'yes' if dynamic_notes else 'no'})")
            return engine
            
        except Exception as e:
            logger.error(f"❌ Failed to load CSV engine for {prefix}: {e}")
            print(f"❌ Failed to load CSV engine for {prefix}: {e}")
            return None
    
    def _load_multi_csv_engine(self, directory: str, prefix: str, description: str, dynamic_notes: str = ""):
        """
        Load multiple CSV files matching a prefix, tag each with a source label,
        and create a single PandasQueryEngine over the merged DataFrame.
        Uses dynamic metadata notes from .txt files instead of hardcoded dictionary.
        
        Used for Học phí where DH26 and DH25 tables have different schemas
        and are stored as separate CSV files (hoc_phi_bang_1_YYYY, hoc_phi_bang_2_YYYY).
        Falls back to _load_csv_engine if only one file is found.
        
        Args:
            directory: Path to the structured data directory
            prefix: Filename prefix (e.g. "hoc_phi")
            description: Description of the data for LLM context
            dynamic_notes: Dynamic metadata/notes from ingestion pipeline
            
        Returns:
            PandasQueryEngine or None
        """
        try:
            pattern = os.path.join(directory, f"{prefix}_*.csv")
            csv_files = sorted(glob.glob(pattern))
            
            if not csv_files:
                logger.info(f"No CSV files found for prefix: {prefix}")
                return None
            
            # If only one file, fall back to simple loader
            if len(csv_files) == 1:
                return self._load_csv_engine(directory, prefix, description, dynamic_notes=dynamic_notes)
            
            # Load each CSV, tag with source table name
            frames = []
            for csv_path in csv_files:
                try:
                    df = pd.read_csv(csv_path, encoding='utf-8-sig')
                    if not df.empty:
                        # Extract table label from filename (e.g. "bang_1", "bang_2")
                        basename = os.path.basename(csv_path).replace('.csv', '')
                        df['bang'] = basename  # Tag source table
                        frames.append(df)
                        logger.info(f"📊 Loaded {len(df)} rows from {csv_path}")
                except Exception as e:
                    logger.warning(f"Could not load {csv_path}: {e}")
            
            if not frames:
                return None
            
            # Concat all frames (different schemas → NaN for missing columns)
            merged_df = pd.concat(frames, ignore_index=True)
            
            # Build instruction with Dynamic Metadata + Schema
            columns_str = ", ".join(merged_df.columns.tolist())
            notes_section = ""
            if dynamic_notes:
                notes_section = (
                    f"--- CHÚ THÍCH & TỪ ĐIỂN DỮ LIỆU (trích từ tài liệu gốc) ---\n"
                    f"{dynamic_notes}\n\n"
                )
            
            instruction_str = (
                f"Bạn là chuyên gia phân tích dữ liệu tuyển sinh. "
                f"Hãy viết code Pandas (df) để tìm câu trả lời chính xác.\n\n"
                f"{notes_section}"
                f"--- DYNAMIC SCHEMA ---\n"
                f"DataFrame 'df' có {len(merged_df)} dòng (merged từ {len(frames)} bảng) với các cột: [{columns_str}]\n"
                f"Cột 'bang' cho biết dòng thuộc bảng nào (ví dụ: hoc_phi_bang_1_2025 = Khóa Mới DH26).\n"
                f"Mô tả: {description}\n\n"
                f"QUAN TRỌNG: Output CHỈ là raw executable Python code.\n"
                f"KHÔNG được bọc code trong markdown code blocks (``` hoặc ```python).\n"
                f"KHÔNG thêm giải thích hay comment. CHỈ code thuần.\n"
                f"Biến DataFrame tên là 'df'.\n"
                f"KHÔNG dùng print(). Dòng cuối cùng PHẢI là một expression trả về kết quả (ví dụ: df[df['col'] == 'X'] hoặc result).\n"
                f"Khi dùng str.contains(), LUÔN thêm na=False để tránh lỗi NaN.\n"
                f"Ví dụ đúng:\n"
                f"  filtered = df[df['NganhHoc'].str.contains('keyword', case=False, na=False)]\n"
                f"  filtered[['MaNganh', 'NganhHoc', 'ToHopMonXetTuyen', 'PT1_DT2_3', 'PT2', 'PT3_Nhom1']]"
            )
            
            engine = PandasQueryEngine(
                df=merged_df,
                verbose=True,
                synthesize_response=False,
                instruction_str=instruction_str,
            )
            
            logger.info(f"📊 Loaded multi-CSV PandasQueryEngine for {prefix} ({len(merged_df)} total rows from {len(frames)} files, metadata={'yes' if dynamic_notes else 'no'})")
            print(f"📊 Loaded multi-CSV PandasQueryEngine for {prefix} ({len(merged_df)} total rows from {len(frames)} files, metadata={'yes' if dynamic_notes else 'no'})")
            return engine
            
        except Exception as e:
            logger.error(f"❌ Failed to load multi-CSV engine for {prefix}: {e}")
            print(f"❌ Failed to load multi-CSV engine for {prefix}: {e}")
            return None
    
    async def _handle_pandas_query(
        self, engine, message: str, source_label: str, intent: str = "general"
    ) -> tuple[str, List[str]]:
        """
        Handle a query using PandasQueryEngine (sync, non-streaming).
        Queries the DataFrame, then formats the raw output through LLM.
        
        Args:
            engine: PandasQueryEngine instance
            message: User's question
            source_label: Label for the data source
            intent: Intent key for INTENT_PROMPTS (e.g. "diem_chuan", "hoc_phi")
            
        Returns:
            Tuple of (formatted_response, [source_label])
        """
        try:
            # Query pandas (sync, run in thread to avoid blocking)
            pandas_response = await asyncio.to_thread(engine.query, message)
            raw_output = str(pandas_response)
            
            # Safety net: if str(response) is "None", try metadata
            if raw_output in ("None", "", "none", "null"):
                meta = getattr(pandas_response, 'metadata', {}) or {}
                raw_pandas = meta.get('raw_pandas_output')
                if raw_pandas is not None:
                    raw_output = str(raw_pandas)
                    logger.info(f"[FIX] Recovered output from metadata: {raw_output[:200]}...")
                else:
                    logger.warning(f"Pandas query returned None with no metadata fallback")
            
            logger.info(f"Pandas query result ({source_label}): {raw_output[:200]}...")
            
            # If still None/empty, fallback to RAG
            if raw_output in ("None", "", "none", "null"):
                logger.warning(f"Pandas output is empty/None — falling back to RAG")
                return await self._handle_rag_query(message)
            
            # Get intent-specific formatting instructions
            intent_prompt = self._get_intent_prompt(intent)
            
            # Format through LLM with intent-specific prompt
            format_prompt = f"""{intent_prompt}

Dựa trên kết quả truy vấn từ {source_label}:

{raw_output}

Hãy format kết quả trên thành câu trả lời cho câu hỏi: "{message}"
- Sử dụng tiếng Việt
- Trình bày dạng bảng markdown theo cấu trúc đã quy định
- Giữ nguyên số liệu chính xác"""
            
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=RAG_SYSTEM_PROMPT),
                ChatMessage(role=MessageRole.USER, content=format_prompt),
            ]
            
            response = await Settings.llm.achat(messages)
            return response.message.content, [f"Truy xuất từ {source_label}"]
            
        except Exception as e:
            logger.error(f"Pandas query error ({source_label}): {e}")
            # Fallback to RAG
            logger.info("Falling back to RAG pipeline...")
            return await self._handle_rag_query(message)
    
    async def _handle_pandas_query_stream(
        self, engine, message: str, source_label: str, intent: str = "general"
    ) -> AsyncGenerator[str, None]:
        """
        Handle a query using PandasQueryEngine with SSE-compatible streaming.
        Queries the DataFrame, then streams the formatted response through LLM.
        
        Args:
            engine: PandasQueryEngine instance
            message: User's question
            source_label: Label for the data source
            intent: Intent key for INTENT_PROMPTS (e.g. "diem_chuan", "hoc_phi")
            
        Yields:
            str chunks of the formatted response
        """
        try:
            # Query pandas (sync, run in thread to avoid blocking)
            pandas_response = await asyncio.to_thread(engine.query, message)
            raw_output = str(pandas_response)
            
            # Safety net: if str(response) is "None", try metadata
            if raw_output in ("None", "", "none", "null"):
                meta = getattr(pandas_response, 'metadata', {}) or {}
                raw_pandas = meta.get('raw_pandas_output')
                if raw_pandas is not None:
                    raw_output = str(raw_pandas)
                    logger.info(f"[STREAM][FIX] Recovered output from metadata: {raw_output[:200]}...")
                else:
                    logger.warning(f"[STREAM] Pandas query returned None with no metadata fallback")
            
            logger.info(f"[STREAM] Pandas query result ({source_label}): {raw_output[:200]}...")
            
            # If still None/empty, yield error
            if raw_output in ("None", "", "none", "null"):
                logger.warning(f"[STREAM] Pandas output is empty/None")
                yield f"Không thể truy xuất dữ liệu từ {source_label}. Vui lòng thử lại."
                return
            
            # Get intent-specific formatting instructions
            intent_prompt = self._get_intent_prompt(intent)
            
            # Format through LLM with intent-specific prompt + streaming
            format_prompt = f"""{intent_prompt}

Dựa trên kết quả truy vấn từ {source_label}:

{raw_output}

Hãy format kết quả trên thành câu trả lời cho câu hỏi: "{message}"
- Sử dụng tiếng Việt
- Trình bày dạng bảng markdown theo cấu trúc đã quy định
- Giữ nguyên số liệu chính xác"""
            
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=RAG_SYSTEM_PROMPT),
                ChatMessage(role=MessageRole.USER, content=format_prompt),
            ]
            
            # Stream via astream_chat
            response_stream = await Settings.llm.astream_chat(messages)
            async for token in response_stream:
                yield token.delta
                
        except Exception as e:
            logger.error(f"[STREAM] Pandas query error ({source_label}): {e}")
            # Fallback: yield error message
            yield f"Không thể truy xuất dữ liệu từ {source_label}. Đang chuyển sang tìm kiếm thông thường..."
    
    # ============================================
    # RAG QUERY METHODS
    # ============================================
    
    async def _handle_rag_query(self, message: str) -> tuple[str, List[str]]:
        """
        Handle knowledge-base queries using Advanced RAG.
        
        Pipeline:
        1. Extract metadata filters from query (year, category)
        2. Hybrid Retrieval (Dense + BM25 with RRF fusion)
        3. Cross-Encoder Reranking
        4. Post-filtering (if needed)
        5. Response synthesis with LLM
        
        Falls back to basic query engine if advanced components unavailable.
        
        Args:
            message: User's question
            
        Returns:
            Tuple of (response_text, list of source filenames)
        """
        retrieval_config = self.settings.retrieval
        
        # Try Advanced RAG first
        if self._hybrid_retriever or self._reranker:
            try:
                return await self._handle_advanced_rag_query(message)
            except Exception as e:
                logger.error(f"Advanced RAG failed, falling back to basic: {e}")
        
        # Fallback to basic RAG
        return await self._handle_basic_rag_query(message)
    
    async def _handle_advanced_rag_query(self, message: str) -> tuple[str, List[str]]:
        """
        Handle queries using Advanced RAG pipeline.
        
        Pipeline:
        1. Query Rewriting (clarification & expansion)
        2. Extract metadata filters from query (year, category)
        3. Hybrid Retrieval (Dense + BM25 with RRF fusion)
        4. Cross-Encoder Reranking
        5. Post-filtering (if needed)
        6. Response synthesis with LLM
        
        Args:
            message: User's question
            
        Returns:
            Tuple of (response_text, list of source filenames)
        """
        logger.info(f"Advanced RAG query: {message[:50]}...")
        
        # Ensure index is loaded
        index = self._get_index()
        if index is None:
            return (
                "Xin lỗi, hệ thống Knowledge Base chưa được khởi tạo. "
                "Vui lòng liên hệ Admin để nạp dữ liệu.",
                []
            )
        
        # Step 1: Query Rewriting
        search_query = message  # Default to original
        rewritten_result = None
        
        if self._query_rewriter:
            try:
                rewritten_result = await self._query_rewriter.rewrite(message)
                search_query = rewritten_result.rewritten
                logger.info(f"Query rewritten: '{message[:30]}...' → '{search_query[:30]}...'")
                
                # Log keywords if extracted
                if rewritten_result.extracted_keywords:
                    logger.info(f"Keywords: {rewritten_result.extracted_keywords}")
            except Exception as e:
                logger.warning(f"Query rewriting failed: {e}")
                search_query = message
        
        # Step 2: Extract metadata filters (from original message for accuracy)
        filters = {}
        if self._metadata_filter:
            filters = self._metadata_filter.extract_filters(message)
            if filters:
                logger.info(f"Extracted filters: {filters}")
        
        # Step 3: Hybrid Retrieval (using rewritten query)
        # Wrap sync retrieval in asyncio.to_thread to avoid blocking event loop
        if self._hybrid_retriever:
            logger.info("🔍 Using Hybrid Retrieval (Dense + BM25)")
            retrieved_nodes = await asyncio.to_thread(
                self._hybrid_retriever.retrieve, search_query
            )
        else:
            # Fallback to dense-only retrieval
            logger.info("🔍 Using Dense-only Retrieval (Hybrid not available)")
            retriever = index.as_retriever(
                similarity_top_k=self.settings.retrieval.dense_top_k
            )
            retrieved_nodes = await asyncio.to_thread(retriever.retrieve, search_query)
        
        logger.info(f"Retrieved {len(retrieved_nodes)} nodes")
        
        # Step 4: Reranking (use ORIGINAL message for relevance scoring)
        if self._reranker and retrieved_nodes:
            logger.info("Reranking with Cross-Encoder")
            reranked_nodes = await self._reranker.rerank(
                query=message,  # Use original for accurate relevance
                nodes=retrieved_nodes,
            )
            logger.info(f"Reranked to {len(reranked_nodes)} nodes")
        else:
            reranked_nodes = retrieved_nodes[:self.settings.retrieval.rerank_top_n]
        
        # Step 5: Post-filtering (if filters extracted)
        if filters and self._metadata_filter:
            final_nodes = self._metadata_filter.apply_post_filters(
                reranked_nodes,
                filters,
                strict=False  # Fallback to all if no matches
            )
        else:
            final_nodes = reranked_nodes
        
        logger.info(f"Final nodes for synthesis: {len(final_nodes)}")
        
        # Step 6: Response synthesis with intent-specific prompt
        if not final_nodes:
            return (
                "Tôi không tìm thấy thông tin phù hợp trong cơ sở dữ liệu. "
                "Vui lòng thử lại với câu hỏi khác hoặc liên hệ phòng Tuyển sinh.",
                []
            )
        
        # Get detected intent from query rewriting
        detected_intent = "general"
        if rewritten_result and hasattr(rewritten_result, 'detected_intent'):
            detected_intent = rewritten_result.detected_intent
            logger.info(f"Using intent-specific prompt: {detected_intent}")
        
        response_text = await self._synthesize_response(message, final_nodes, detected_intent)
        sources = self._extract_sources(final_nodes)
        
        return response_text, sources
    
    async def _handle_basic_rag_query(self, message: str) -> tuple[str, List[str]]:
        """
        Handle queries using basic RAG (fallback method).
        
        Args:
            message: User's question
            
        Returns:
            Tuple of (response_text, list of source filenames)
        """
        try:
            query_engine = self._get_query_engine()
            
            if query_engine is None:
                return (
                    "Xin lỗi, hệ thống Knowledge Base chưa được khởi tạo. "
                    "Vui lòng liên hệ Admin để nạp dữ liệu.",
                    []
                )
            
            # Query the knowledge base (wrap in asyncio.to_thread to avoid blocking)
            response = await asyncio.to_thread(query_engine.query, message)
            
            # Extract sources from response
            sources = []
            if hasattr(response, 'source_nodes'):
                sources = self._extract_sources(response.source_nodes)
            
            return str(response), sources
            
        except Exception as e:
            logger.error(f"Basic RAG query error: {e}")
            return (
                "Xin lỗi, không thể truy vấn cơ sở dữ liệu. Vui lòng thử lại sau.",
                []
            )
    
    async def _synthesize_response(
        self,
        query: str,
        nodes: List[NodeWithScore],
        intent: str = "general"
    ) -> str:
        """
        Synthesize final response from retrieved nodes using LLM.
        Uses intent-specific prompts for better response quality.
        
        Args:
            query: User's question
            nodes: Retrieved and reranked nodes
            intent: Detected intent for specialized prompting
            
        Returns:
            Synthesized response text
        """
        try:
            # Validate LLM is initialized
            if Settings.llm is None:
                logger.error("LLM not initialized in Settings")
                return "Xin lỗi, hệ thống LLM chưa được khởi tạo. Vui lòng thử lại sau."
            
            # Build context from nodes
            context_parts = []
            for i, node in enumerate(nodes, 1):
                try:
                    node_text = node.node.get_content()
                    metadata = node.node.metadata or {}
                    source = metadata.get('filename', metadata.get('file_name', 'Unknown'))
                    year = metadata.get('year', '')
                    
                    context_header = f"[Nguồn {i}: {source}"
                    if year:
                        context_header += f" - Năm {year}"
                    context_header += "]"
                    
                    context_parts.append(f"{context_header}\n{node_text}")
                except Exception as node_err:
                    logger.warning(f"Error extracting node {i} content: {node_err}")
                    continue
            
            if not context_parts:
                logger.warning("No valid context parts extracted from nodes")
                return "Không thể trích xuất thông tin từ cơ sở dữ liệu. Vui lòng thử lại."
            
            context = "\n\n---\n\n".join(context_parts)
            
            # Get intent-specific prompt
            intent_prompt = self._get_intent_prompt(intent)
            
            # Build prompt with context and intent-specific instructions
            prompt = f"""{RAG_SYSTEM_PROMPT}
{intent_prompt}
## Ngữ cảnh (Context):
{context}

## Câu hỏi của người dùng:
{query}

## Trả lời:"""
            
            # Call LLM with proper error handling
            messages = [
                ChatMessage(role=MessageRole.USER, content=prompt)
            ]
            
            # Try async first, fallback to sync if not supported
            try:
                if hasattr(Settings.llm, 'achat'):
                    response = await Settings.llm.achat(messages)
                else:
                    # Fallback to sync chat wrapped in asyncio.to_thread
                    logger.info("Using sync chat (achat not available)")
                    response = await asyncio.to_thread(Settings.llm.chat, messages)
            except AttributeError as attr_err:
                logger.warning(f"achat not available, using sync: {attr_err}")
                response = await asyncio.to_thread(Settings.llm.chat, messages)
            
            # Extract response content
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                return response.message.content
            elif hasattr(response, 'content'):
                return response.content
            else:
                logger.error(f"Unexpected response format: {type(response)}")
                return str(response)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Response synthesis error: {e}\n{error_details}")
            print(f"Response synthesis error: {e}\n{error_details}")
            return f"Xin lỗi, đã có lỗi khi tổng hợp câu trả lời. Vui lòng thử lại."
    
    def _extract_sources(self, nodes: List[NodeWithScore]) -> List[str]:
        """
        Extract source information from nodes.
        
        Args:
            nodes: List of NodeWithScore
            
        Returns:
            List of formatted source strings
        """
        sources = []
        for node in nodes:
            metadata = node.node.metadata if hasattr(node.node, 'metadata') else {}
            filename = metadata.get('file_name', metadata.get('filename', 'Unknown'))
            page = metadata.get('page_label', metadata.get('page', ''))
            year = metadata.get('year', '')
            
            source_str = filename
            if year:
                source_str += f" ({year})"
            if page:
                source_str += f" - trang {page}"
            
            if source_str not in sources:
                sources.append(source_str)
        
        return sources
    
    def get_session_history(self, session_id: str) -> List[Dict]:
        """
        Get full conversation history for a session.
        
        Args:
            session_id: The chat session ID
            
        Returns:
            List of message dictionaries
        """
        try:
            session = self.chat_sessions.find_one({"session_id": session_id})
            if session:
                return session.get("messages", [])
            return []
        except Exception as e:
            print(f"Could not get session history: {e}")
            return []
    
    def clear_session(self, session_id: str) -> bool:
        try:
            result = self.chat_sessions.delete_one({"session_id": session_id})
            return result.deleted_count > 0
        except Exception as e:
            print(f"Could not clear session: {e}")
            return False
    
    def get_all_sessions(self, limit: int = 20) -> List[Dict]:
        try:
            sessions = self.chat_sessions.find(
                {},
                {"session_id": 1, "created_at": 1, "last_activity": 1, "messages": {"$slice": -1}}
            ).sort("last_activity", -1).limit(limit)
            
            return list(sessions)
        except Exception as e:
            print(f"Could not get sessions: {e}")
            return []
    
    def clear_cache(self) -> Dict[str, Any]:
        """
        Clear all in-memory caches and reinitialize components.
        This should be called after deleting/uploading documents to ensure
        the RAG system uses fresh data from Qdrant and CSV files.
        
        Returns:
            Dict with cache clear status
        """
        try:
            old_nodes_count = len(self._all_nodes) if self._all_nodes else 0
            had_hybrid = self._hybrid_retriever is not None
            had_index = self._index is not None
            had_diem_chuan = self._diem_chuan_engine is not None
            had_hoc_phi = self._hoc_phi_engine is not None
            
            # Clear all caches
            self._index = None
            self._query_engine = None
            self._hybrid_retriever = None
            self._all_nodes = []
            self._diem_chuan_engine = None
            self._hoc_phi_engine = None
            
            logger.info("Cleared in-memory caches")
            print("Cleared in-memory caches")
            
            # Also clear dynamic prompt cache
            try:
                self._prompt_service.invalidate_cache()
                logger.info("Cleared prompt cache")
            except Exception as prompt_err:
                logger.warning(f"Failed to invalidate prompt cache: {prompt_err}")
            
            # Reinitialize index and hybrid retriever
            self._get_index()
            
            # Reinitialize pandas engines from CSV files
            self._init_pandas_engines()
            
            new_nodes_count = len(self._all_nodes) if self._all_nodes else 0
            
            result = {
                "status": "success",
                "cleared": {
                    "index": had_index,
                    "hybrid_retriever": had_hybrid,
                    "nodes_before": old_nodes_count,
                    "diem_chuan_engine": had_diem_chuan,
                    "hoc_phi_engine": had_hoc_phi,
                },
                "reloaded": {
                    "index": self._index is not None,
                    "hybrid_retriever": self._hybrid_retriever is not None,
                    "nodes_after": new_nodes_count,
                    "diem_chuan_engine": self._diem_chuan_engine is not None,
                    "hoc_phi_engine": self._hoc_phi_engine is not None,
                }
            }
            
            logger.info(f"Cache cleared and reloaded: {old_nodes_count} → {new_nodes_count} nodes")
            print(f"Cache cleared and reloaded: {old_nodes_count} → {new_nodes_count} nodes")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            print(f"Failed to clear cache: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
