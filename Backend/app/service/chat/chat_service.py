"""
ChatService — Orchestrator for RAG-based chat interactions.

This is the main entry point that coordinates:
  - Intent classification
  - Chat history management
  - Coreference resolution
  - CSV query engines (điểm chuẩn, học phí)
  - RAG retrieval pipeline
  - Response synthesis

Refactored from the original monolithic chat_service.py (~2000 lines)
into this ~300-line orchestrator that delegates to focused modules.
"""
import os
import json
import logging
import asyncio
import threading
from typing import Optional, List, Dict, Any, AsyncGenerator

from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.llms import ChatMessage
from llama_index.core.schema import TextNode, NodeWithScore
from llama_index.vector_stores.qdrant import QdrantVectorStore

from app.core.config import get_settings
from app.db import get_chat_sessions_collection, get_qdrant_client
from app.service.llm_factory import init_settings
from app.service.prompt_service import get_prompt_service
from app.service.prompts import RAG_SYSTEM_PROMPT

# Retrieval components (unchanged)
from app.service.retrieval import (
    HybridRetriever,
    CrossEncoderReranker,
    MetadataFilterService,
    QueryRewriter,
)

# Extracted modules
from app.service.chat.intent_classifier import IntentClassifier
from app.service.chat.history_manager import ChatHistoryManager
from app.service.chat.coreference import CoreferenceResolver
from app.service.chat.csv_query_engine import CSVQueryEngine
from app.service.chat.response_handler import ResponseHandler

logger = logging.getLogger(__name__)


class ChatService:
    """Service for handling RAG-based chat interactions with intent routing."""

    def __init__(self):
        """
        Initialize ChatService:
        - Initialize LlamaIndex Settings (LLM & Embeddings)
        - Set up all sub-modules (intent, history, coreference, CSV, response)
        - Connect to Qdrant and initialize Advanced RAG components
        """
        # Load configuration
        self.settings = get_settings()

        # Initialize LlamaIndex settings
        init_settings()

        # Initialize dynamic prompt service
        self._prompt_service = get_prompt_service()

        # --- Sub-modules ---
        self._intent_classifier = IntentClassifier()
        self._history_manager = ChatHistoryManager(get_chat_sessions_collection())
        self._coreference = CoreferenceResolver()
        self._response_handler = ResponseHandler(self._get_intent_prompt)

        # Connect to Qdrant for vector search
        self.qdrant_client = get_qdrant_client()
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME", "university_knowledge")

        # Vector index (lazy initialized)
        self._index = None
        self._query_engine = None
        self._index_lock = threading.Lock()

        # Advanced RAG Components
        self._hybrid_retriever: Optional[HybridRetriever] = None
        self._reranker: Optional[CrossEncoderReranker] = None
        self._metadata_filter: Optional[MetadataFilterService] = None
        self._query_rewriter: Optional[QueryRewriter] = None
        self._all_nodes: List[Any] = []

        # Initialize Advanced RAG if enabled
        self._init_advanced_rag()

        # CSV Query Engines
        # Calculate path to data/structured
        # current file: app/service/chat/chat_service.py
        # root: app/service/chat/ -> app/service/ -> app/ -> Backend/
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        structured_dir = os.path.join(backend_dir, "data", "structured")
        
        self._csv_engine = CSVQueryEngine(structured_dir, self._get_intent_prompt)

        logger.info("✅ ChatService initialized")
        print("✅ ChatService initialized")

    # ------------------------------------------------------------------
    # Prompt helper
    # ------------------------------------------------------------------

    def _get_intent_prompt(self, intent: str) -> str:
        """Get intent-specific prompt template from dynamic PromptService."""
        try:
            return self._prompt_service.get_intent_prompt(intent)
        except Exception as e:
            logger.warning(f"Failed to get dynamic prompt for '{intent}': {e}")
            from app.service.prompts.intent_prompts import INTENT_PROMPTS
            return INTENT_PROMPTS.get(intent, INTENT_PROMPTS.get("general", ""))

    # ------------------------------------------------------------------
    # Advanced RAG initialization (kept in orchestrator)
    # ------------------------------------------------------------------

    def _init_advanced_rag(self):
        """Initialize Advanced RAG components."""
        rc = self.settings.retrieval

        if rc.enable_metadata_filter:
            self._metadata_filter = MetadataFilterService(default_year=rc.default_year)
            logger.info("✅ MetadataFilterService initialized")

        if rc.enable_query_rewrite:
            self._query_rewriter = QueryRewriter(
                enable_rewrite=rc.enable_query_rewrite,
                enable_expansion=rc.enable_query_expansion,
                enable_keywords=rc.enable_keyword_extraction,
                max_expanded_queries=rc.max_expanded_queries,
            )
            logger.info("✅ QueryRewriter initialized")

        if rc.enable_reranking:
            try:
                self._reranker = CrossEncoderReranker(
                    model_name=rc.rerank_model, top_n=rc.rerank_top_n,
                )
                logger.info(f"Reranker initialized: {rc.rerank_model}")
            except Exception as e:
                logger.warning(f"Failed to initialize reranker: {e}")
                self._reranker = None

    def _get_index(self) -> Optional[VectorStoreIndex]:
        """Get or create the VectorStoreIndex from Qdrant (thread-safe)."""
        if self._index is not None:
            return self._index

        with self._index_lock:
            if self._index is not None:
                return self._index
            try:
                logger.info("Initializing VectorStoreIndex from Qdrant...")
                vector_store = QdrantVectorStore(
                    client=self.qdrant_client, collection_name=self.collection_name,
                )
                self._index = VectorStoreIndex.from_vector_store(vector_store)
                logger.info(f"Loaded index from Qdrant collection: {self.collection_name}")
                self._init_hybrid_retriever()
            except Exception as e:
                logger.error(f"Could not load index from Qdrant: {e}")
                return None

        return self._index

    def _init_hybrid_retriever(self):
        """Initialize Hybrid Retriever after index is loaded."""
        if not self.settings.retrieval.enable_hybrid_search or self._index is None:
            return

        try:
            self._all_nodes = self._load_nodes_from_qdrant()
            if self._all_nodes:
                rc = self.settings.retrieval
                self._hybrid_retriever = HybridRetriever(
                    vector_index=self._index, nodes=self._all_nodes,
                    alpha=rc.hybrid_alpha, dense_top_k=rc.dense_top_k,
                    sparse_top_k=rc.sparse_top_k, final_top_k=rc.dense_top_k,
                )
                logger.info("HybridRetriever initialized")
            else:
                logger.warning("No nodes available for Hybrid Retriever")
        except Exception as e:
            logger.error(f"Failed to initialize HybridRetriever: {e}")
            self._hybrid_retriever = None

    def _load_nodes_from_qdrant(self) -> List[Any]:
        """Load all text nodes from Qdrant for BM25 indexing."""
        try:
            all_nodes = []
            offset = None
            batch_size = 100

            while True:
                results = self.qdrant_client.scroll(
                    collection_name=self.collection_name,
                    limit=batch_size, offset=offset,
                    with_payload=True, with_vectors=False,
                )
                points, next_offset = results
                if not points:
                    break

                for point in points:
                    payload = point.payload or {}
                    text = ""
                    inner_metadata = {}

                    node_content = payload.get("_node_content")
                    if node_content:
                        try:
                            content_dict = json.loads(node_content)
                            text = content_dict.get("text", "")
                            inner_metadata = content_dict.get("metadata", {})
                        except (json.JSONDecodeError, TypeError):
                            text = str(node_content)

                    if not text:
                        text = payload.get("text", "")

                    if text:
                        metadata = {
                            "doc_uuid": payload.get("doc_uuid", inner_metadata.get("doc_uuid", "")),
                            "filename": payload.get("filename", inner_metadata.get("filename", "")),
                            "file_name": inner_metadata.get("file_name", ""),
                            "year": payload.get("year", inner_metadata.get("year")),
                            "category": payload.get("category", inner_metadata.get("category", "")),
                            "section_context": inner_metadata.get("section_context", ""),
                        }
                        node = TextNode(text=text, id_=str(point.id), metadata=metadata)
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
        """Get or create the query engine (FALLBACK)."""
        if self._query_engine is None:
            index = self._get_index()
            if index:
                self._query_engine = index.as_query_engine(
                    similarity_top_k=5, response_mode="compact",
                    system_prompt=RAG_SYSTEM_PROMPT,
                )
        return self._query_engine

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    async def process_message(self, session_id: str, message: str) -> Dict:
        """Process a user message with 4-way intent routing."""
        print(f"Processing message: {message[:50]}...")

        try:
            history = self._history_manager.load_history(session_id, limit=5)
            intent = self._intent_classifier.classify(message)
            print(f"Intent classified as: {intent}")

            # Check for future year queries
            future_check = IntentClassifier.check_future_year(
                message, intent,
                self._csv_engine.latest_diem_chuan_year,
                self._csv_engine.latest_hoc_phi_year,
            )
            if future_check is not None:
                self._history_manager.save_message(session_id, "user", message)
                self._history_manager.save_message(session_id, "assistant", future_check)
                return {"response": future_check, "sources": [], "intent": intent}

            response_text = ""
            sources = []

            if intent == "CHITCHAT":
                response_text = await self._response_handler.handle_chitchat(history, message)

            elif intent == "QUERY_SCORES" and self._csv_engine.diem_chuan_engine:
                resolved = await self._coreference.resolve(message, history)
                result = await self._csv_engine.handle_query(
                    self._csv_engine.diem_chuan_engine, resolved, "Bảng điểm chuẩn", intent="diem_chuan",
                )
                if result[0] is not None:
                    response_text, sources = result
                else:
                    resolved = await self._coreference.resolve(message, history)
                    response_text, sources = await self._handle_rag_query(resolved)

            elif intent == "QUERY_FEES" and self._csv_engine.hoc_phi_engine:
                resolved = await self._coreference.resolve(message, history)
                result = await self._csv_engine.handle_query(
                    self._csv_engine.hoc_phi_engine, resolved, "Bảng học phí", intent="hoc_phi",
                )
                if result[0] is not None:
                    response_text, sources = result
                else:
                    resolved = await self._coreference.resolve(message, history)
                    response_text, sources = await self._handle_rag_query(resolved)

            elif intent == "CAREER_ADVICE":
                response_text = await self._response_handler.handle_career_advice(history, message)
                sources = ["Tư vấn từ chuyên gia AI - Khoa CNTT"]

            else:  # QUERY_DOCS or fallback
                resolved = await self._coreference.resolve(message, history)
                response_text, sources = await self._handle_rag_query(resolved)

            # Save to history
            self._history_manager.save_message(session_id, "user", message)
            self._history_manager.save_message(session_id, "assistant", response_text, sources or None)

            return {"response": response_text, "sources": sources, "intent": intent}

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return {
                "response": "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại sau.",
                "sources": [], "intent": "ERROR", "error": str(e),
            }

    async def process_message_stream(
        self, session_id: str, message: str
    ) -> AsyncGenerator[str, None]:
        """Process a user message with streaming response."""
        print(f"[STREAM] Processing message: {message[:50]}...")

        full_response = ""
        sources: List[str] = []
        intent = "UNKNOWN"

        try:
            history = self._history_manager.load_history(session_id, limit=5)
            intent = self._intent_classifier.classify(message)
            print(f"[STREAM] Intent classified as: {intent}")

            # Check for future year queries
            future_check = IntentClassifier.check_future_year(
                message, intent,
                self._csv_engine.latest_diem_chuan_year,
                self._csv_engine.latest_hoc_phi_year,
            )
            if future_check is not None:
                self._history_manager.save_message(session_id, "user", message)
                self._history_manager.save_message(session_id, "assistant", future_check)
                yield future_check
                return

            self._history_manager.save_message(session_id, "user", message)

            if intent == "CHITCHAT":
                async for chunk in self._response_handler.handle_chitchat_stream(history, message):
                    full_response += chunk
                    yield chunk

            elif intent == "QUERY_SCORES" and self._csv_engine.diem_chuan_engine:
                resolved = await self._coreference.resolve(message, history)
                async for chunk in self._csv_engine.handle_query_stream(
                    self._csv_engine.diem_chuan_engine, resolved, "Bảng điểm chuẩn", intent="diem_chuan",
                ):
                    full_response += chunk
                    yield chunk
                sources = ["Truy xuất từ Bảng điểm chuẩn"]

            elif intent == "QUERY_FEES" and self._csv_engine.hoc_phi_engine:
                resolved = await self._coreference.resolve(message, history)
                async for chunk in self._csv_engine.handle_query_stream(
                    self._csv_engine.hoc_phi_engine, resolved, "Bảng học phí", intent="hoc_phi",
                ):
                    full_response += chunk
                    yield chunk
                sources = ["Truy xuất từ Bảng học phí"]

            elif intent == "CAREER_ADVICE":
                async for chunk in self._response_handler.handle_career_advice_stream(history, message):
                    full_response += chunk
                    yield chunk
                sources = ["Tư vấn từ chuyên gia AI - Khoa CNTT"]

            else:
                resolved = await self._coreference.resolve(message, history)
                nodes, sources = await self._retrieve_and_rerank(resolved)

                if not nodes:
                    fallback = (
                        "Tôi không tìm thấy thông tin phù hợp trong cơ sở dữ liệu. "
                        "Vui lòng thử lại với câu hỏi khác hoặc liên hệ phòng Tuyển sinh."
                    )
                    full_response = fallback
                    yield fallback
                else:
                    async for chunk in self._response_handler.synthesize_response_stream(
                        resolved, nodes
                    ):
                        full_response += chunk
                        yield chunk

            self._history_manager.save_message(
                session_id, "assistant", full_response, sources or None,
            )
            print(f"[STREAM] Saved full response ({len(full_response)} chars) to DB")

        except Exception as e:
            logger.error(f"[STREAM] Error: {e}")
            error_msg = "Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại sau."
            if not full_response:
                yield error_msg
            if full_response:
                self._history_manager.save_message(
                    session_id, "assistant", full_response, sources or None,
                )

    # ------------------------------------------------------------------
    # RAG pipeline
    # ------------------------------------------------------------------

    async def _retrieve_and_rerank(self, message: str) -> tuple[List[NodeWithScore], List[str]]:
        """Execute the retrieval + reranking pipeline."""
        rc = self.settings.retrieval
        index = self._get_index()
        if index is None:
            return [], []

        # Step 1: Query Rewriting
        search_query = message
        if self._query_rewriter:
            try:
                rewritten_result = await self._query_rewriter.rewrite(message)
                search_query = rewritten_result.rewritten
                logger.info(f"Query rewritten: '{message[:30]}...' → '{search_query[:30]}...'")
            except Exception as e:
                logger.warning(f"Query rewriting failed: {e}")

        # Step 2: Extract metadata filters
        filters = {}
        if self._metadata_filter:
            filters = self._metadata_filter.extract_filters(message)

        # Step 3: Hybrid Retrieval
        if self._hybrid_retriever:
            retrieved_nodes = await asyncio.to_thread(
                self._hybrid_retriever.retrieve, search_query,
            )
        else:
            retriever = index.as_retriever(similarity_top_k=rc.dense_top_k)
            retrieved_nodes = await asyncio.to_thread(retriever.retrieve, search_query)

        # Step 4: Reranking
        if self._reranker and retrieved_nodes:
            reranked_nodes = await self._reranker.rerank(query=message, nodes=retrieved_nodes)
        else:
            reranked_nodes = retrieved_nodes[:rc.rerank_top_n]

        # Step 5: Post-filtering
        if filters and self._metadata_filter:
            final_nodes = self._metadata_filter.apply_post_filters(reranked_nodes, filters, strict=False)
        else:
            final_nodes = reranked_nodes

        sources = self._response_handler.extract_sources(final_nodes) if final_nodes else []
        return final_nodes, sources

    async def _handle_rag_query(self, message: str) -> tuple[str, List[str]]:
        """Handle knowledge-base queries using Advanced RAG."""
        if self._hybrid_retriever or self._reranker:
            try:
                return await self._handle_advanced_rag_query(message)
            except Exception as e:
                logger.error(f"Advanced RAG failed, falling back to basic: {e}")
        return await self._handle_basic_rag_query(message)

    async def _handle_advanced_rag_query(self, message: str) -> tuple[str, List[str]]:
        """Handle queries using Advanced RAG pipeline."""
        index = self._get_index()
        if index is None:
            return (
                "Xin lỗi, hệ thống Knowledge Base chưa được khởi tạo. "
                "Vui lòng liên hệ Admin để nạp dữ liệu.", [],
            )

        # Query Rewriting
        search_query = message
        rewritten_result = None
        if self._query_rewriter:
            try:
                rewritten_result = await self._query_rewriter.rewrite(message)
                search_query = rewritten_result.rewritten
            except Exception as e:
                logger.warning(f"Query rewriting failed: {e}")

        # Metadata filters
        filters = {}
        if self._metadata_filter:
            filters = self._metadata_filter.extract_filters(message)

        # Hybrid Retrieval
        if self._hybrid_retriever:
            retrieved_nodes = await asyncio.to_thread(
                self._hybrid_retriever.retrieve, search_query,
            )
        else:
            retriever = index.as_retriever(
                similarity_top_k=self.settings.retrieval.dense_top_k,
            )
            retrieved_nodes = await asyncio.to_thread(retriever.retrieve, search_query)

        # Reranking
        if self._reranker and retrieved_nodes:
            reranked_nodes = await self._reranker.rerank(query=message, nodes=retrieved_nodes)
        else:
            reranked_nodes = retrieved_nodes[:self.settings.retrieval.rerank_top_n]

        # Post-filtering
        if filters and self._metadata_filter:
            final_nodes = self._metadata_filter.apply_post_filters(reranked_nodes, filters, strict=False)
        else:
            final_nodes = reranked_nodes

        if not final_nodes:
            return (
                "Tôi không tìm thấy thông tin phù hợp trong cơ sở dữ liệu. "
                "Vui lòng thử lại với câu hỏi khác hoặc liên hệ phòng Tuyển sinh.", [],
            )

        detected_intent = "general"
        if rewritten_result and hasattr(rewritten_result, "detected_intent"):
            detected_intent = rewritten_result.detected_intent

        response_text = await self._response_handler.synthesize_response(message, final_nodes, detected_intent)
        sources = self._response_handler.extract_sources(final_nodes)
        return response_text, sources

    async def _handle_basic_rag_query(self, message: str) -> tuple[str, List[str]]:
        """Handle queries using basic RAG (fallback method)."""
        try:
            query_engine = self._get_query_engine()
            if query_engine is None:
                return (
                    "Xin lỗi, hệ thống Knowledge Base chưa được khởi tạo. "
                    "Vui lòng liên hệ Admin để nạp dữ liệu.", [],
                )

            response = await asyncio.to_thread(query_engine.query, message)
            sources = []
            if hasattr(response, "source_nodes"):
                sources = self._response_handler.extract_sources(response.source_nodes)
            return str(response), sources

        except Exception as e:
            logger.error(f"Basic RAG query error: {e}")
            return ("Xin lỗi, không thể truy vấn cơ sở dữ liệu. Vui lòng thử lại sau.", [])

    # ------------------------------------------------------------------
    # Delegation to sub-modules
    # ------------------------------------------------------------------

    def get_session_history(self, session_id: str) -> List[Dict]:
        return self._history_manager.get_session_history(session_id)

    def clear_session(self, session_id: str) -> bool:
        return self._history_manager.clear_session(session_id)

    def get_all_sessions(self, limit: int = 20) -> List[Dict]:
        return self._history_manager.get_all_sessions(limit)

    def clear_cache(self) -> Dict[str, Any]:
        """Clear all in-memory caches and reinitialize components."""
        try:
            old_nodes_count = len(self._all_nodes) if self._all_nodes else 0
            had_hybrid = self._hybrid_retriever is not None
            had_index = self._index is not None

            # Clear RAG caches
            self._index = None
            self._query_engine = None
            self._hybrid_retriever = None
            self._all_nodes = []

            # Clear CSV engine caches
            self._csv_engine.clear()

            # Clear prompt cache
            try:
                self._prompt_service.invalidate_cache()
            except Exception as prompt_err:
                logger.warning(f"Failed to invalidate prompt cache: {prompt_err}")

            # Reinitialize
            self._get_index()
            self._csv_engine.init_engines()

            new_nodes_count = len(self._all_nodes) if self._all_nodes else 0

            result = {
                "status": "success",
                "cleared": {
                    "index": had_index,
                    "hybrid_retriever": had_hybrid,
                    "nodes_before": old_nodes_count,
                    "diem_chuan_engine": True,
                    "hoc_phi_engine": True,
                },
                "reloaded": {
                    "index": self._index is not None,
                    "hybrid_retriever": self._hybrid_retriever is not None,
                    "nodes_after": new_nodes_count,
                    "diem_chuan_engine": self._csv_engine.diem_chuan_engine is not None,
                    "hoc_phi_engine": self._csv_engine.hoc_phi_engine is not None,
                },
            }

            logger.info(f"Cache cleared and reloaded: {old_nodes_count} → {new_nodes_count} nodes")
            return result

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return {"status": "error", "error": str(e)}
