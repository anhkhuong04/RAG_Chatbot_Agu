import time
import json
import logging
import asyncio
import threading
from typing import Optional, List, Dict, Any, AsyncGenerator
from llama_index.core import VectorStoreIndex
from llama_index.core.schema import TextNode, NodeWithScore
from llama_index.vector_stores.qdrant import QdrantVectorStore

from app.core.config import get_settings
from app.db import get_chat_sessions_collection, get_qdrant_client, get_database
from app.service.llm_factory import init_settings
from app.service.prompt_service import get_prompt_service

# Retrieval components
from app.service.retrieval import (
    HybridRetriever,
    CrossEncoderReranker,
    MetadataFilterService,
    QueryRewriter,
)

# Chat sub-modules
from app.service.chat.intent_classifier import IntentClassifier
from app.service.chat.history_manager import ChatHistoryManager
from app.service.chat.coreference import CoreferenceResolver
from app.service.chat.response_handler import ResponseHandler


logger = logging.getLogger(__name__)

# Legacy static fallback kept only as a last-resort safety net.
_NO_CONTEXT_MSG = (
    "Hiện tại tôi chưa tìm thấy thông tin phù hợp trong dữ liệu nội bộ. "
    "Bạn vui lòng liên hệ Phòng Tuyển sinh qua hotline 0794 2222 45 "
    "hoặc website tuyensinh.agu.edu.vn để được hỗ trợ chính xác hơn."
)


class ChatService:
    """Service for handling RAG-based chat interactions with intent routing."""

    def __init__(self):
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
        self.collection_name = self.settings.database.qdrant_collection_name

        # MongoDB documents collection (for latest-year lookup)
        self._doc_collection = get_database()["documents"]

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

        # Latest available data years (populated from MongoDB)
        self._latest_scores_year: Optional[int] = None
        self._latest_fees_year: Optional[int] = None
        self._refresh_latest_years()

        # Initialize Advanced RAG if enabled
        self._init_advanced_rag()

        logger.info("ChatService initialized")

    # ------------------------------------------------------------------
    # Prompt helper
    # ------------------------------------------------------------------

    def _get_intent_prompt(self, intent: str) -> str:
        try:
            return self._prompt_service.get_intent_prompt(intent)
        except Exception as e:
            logger.warning(f"Failed to get dynamic prompt for '{intent}': {e}")
            from app.service.prompts.intent_prompts import INTENT_PROMPTS
            return INTENT_PROMPTS.get(intent, INTENT_PROMPTS.get("general", ""))

    # ------------------------------------------------------------------
    # Latest data years (fixes check_future_year always receiving None)
    # ------------------------------------------------------------------

    def _refresh_latest_years(self) -> None:
        """Query MongoDB to find the latest indexed year per category."""
        try:
            pipeline = [
                {"$match": {"status": "INDEXED", "metadata.year": {"$ne": None}}},
                {"$group": {
                    "_id": "$metadata.category",
                    "max_year": {"$max": {"$toInt": "$metadata.year"}},
                }},
            ]
            for doc in self._doc_collection.aggregate(pipeline):
                cat = (doc.get("_id") or "").lower()
                year = doc.get("max_year")
                if not year:
                    continue
                if "điểm chuẩn" in cat or "diem chuan" in cat:
                    self._latest_scores_year = year
                elif "học phí" in cat or "hoc phi" in cat:
                    self._latest_fees_year = year

            logger.info(
                f"Latest data years — scores: {self._latest_scores_year}, "
                f"fees: {self._latest_fees_year}"
            )
        except Exception as e:
            logger.warning(f"Could not refresh latest data years: {e}")

    # ------------------------------------------------------------------
    # Advanced RAG initialization
    # ------------------------------------------------------------------

    def _init_advanced_rag(self):
        rc = self.settings.retrieval

        if rc.enable_metadata_filter:
            self._metadata_filter = MetadataFilterService(default_year=rc.default_year)
            logger.info("MetadataFilterService initialized")

        if rc.enable_query_rewrite:
            self._query_rewriter = QueryRewriter(
                enable_rewrite=rc.enable_query_rewrite,
                enable_expansion=rc.enable_query_expansion,
                enable_keywords=rc.enable_keyword_extraction,
                max_expanded_queries=rc.max_expanded_queries,
                enable_hyde=rc.enable_hyde,
            )
            logger.info(" QueryRewriter initialized")

        if rc.enable_reranking:
            try:
                self._reranker = CrossEncoderReranker(
                    model_name=rc.rerank_model, top_n=rc.rerank_top_n,
                )
                logger.info(f"Reranker initialized: {rc.rerank_model}")
            except Exception as e:
                logger.warning(f"Failed to initialize reranker: {e}")
                self._reranker = None

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()

    def _intent_category_guard(
        self,
        intent: str,
        nodes: List[NodeWithScore],
    ) -> bool:
        """
        Defense-in-depth guard against grounded-but-wrong answers.
        For score/fee intents, require at least one retrieved node to carry
        matching category metadata; otherwise force no-context fallback.
        """
        if intent not in {"QUERY_SCORES", "QUERY_FEES"}:
            return True

        if not nodes:
            return False

        expected_tokens = (
            ["điểmchuẩn", "diemchuan"]
            if intent == "QUERY_SCORES"
            else ["họcphí", "hocphi"]
        )

        for item in nodes:
            metadata = item.node.metadata or {}
            category_raw = metadata.get("category", "")
            category_norm = (
                self._normalize_text(category_raw)
                .replace(" ", "")
                .replace("_", "")
            )
            if any(token in category_norm for token in expected_tokens):
                return True

        logger.warning(
            "Intent-category guard blocked response: intent=%s, nodes=%d, categories=%s",
            intent,
            len(nodes),
            list({self._normalize_text((n.node.metadata or {}).get('category', '')) for n in nodes}),
        )
        return False

    def _get_index(self) -> Optional[VectorStoreIndex]:
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

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    async def process_message(self, session_id: str, message: str) -> Dict:
        logger.info(f"Processing message: {message[:50]}...")

        try:
            history = self._history_manager.load_history(session_id, limit=5)
            intent = await self._intent_classifier.classify(message)
            logger.info(f"Intent classified as: {intent}")

            # Check for future year queries (now with real years from MongoDB)
            future_check = IntentClassifier.check_future_year(
                message, intent,
                self._latest_scores_year,
                self._latest_fees_year,
            )
            if future_check is not None:
                self._history_manager.save_message(session_id, "user", message)
                self._history_manager.save_message(session_id, "assistant", future_check)
                return {"response": future_check, "sources": [], "intent": intent}

            response_text = ""
            sources = []

            if intent == "CHITCHAT":
                response_text = await self._response_handler.handle_chitchat(history, message)

            elif intent == "CAREER_ADVICE":
                response_text = await self._response_handler.handle_career_advice(history, message)
                sources = ["Tư vấn từ chuyên gia AI - Khoa CNTT"]

            else:  # QUERY_SCORES, QUERY_FEES, QUERY_DOCS
                resolved = await self._coreference.resolve(message, history)
                response_text, sources = await self._handle_rag_query(resolved, intent)

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
        logger.info(f"[STREAM] Processing message: {message[:50]}...")

        full_response = ""
        sources: List[str] = []
        intent = "UNKNOWN"

        try:
            history = self._history_manager.load_history(session_id, limit=5)
            intent = await self._intent_classifier.classify(message)
            logger.info(f"[STREAM] Intent classified as: {intent}")

            # Check for future year queries (now with real years from MongoDB)
            future_check = IntentClassifier.check_future_year(
                message, intent,
                self._latest_scores_year,
                self._latest_fees_year,
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

            elif intent == "CAREER_ADVICE":
                async for chunk in self._response_handler.handle_career_advice_stream(history, message):
                    full_response += chunk
                    yield chunk
                sources = ["Tư vấn từ chuyên gia AI - Khoa CNTT"]

            else:  # QUERY_SCORES, QUERY_FEES, QUERY_DOCS
                resolved = await self._coreference.resolve(message, history)
                nodes, sources = await self._retrieve_and_rerank(resolved)

                if not nodes or not self._intent_category_guard(intent, nodes):
                    fine_intent = IntentClassifier.get_fine_intent(intent)
                    full_response = await self._response_handler.synthesize_no_context_response(
                        resolved, fine_intent
                    )
                    if not full_response:
                        full_response = _NO_CONTEXT_MSG
                    yield full_response
                else:
                    fine_intent = IntentClassifier.get_fine_intent(intent)
                    async for chunk in self._response_handler.synthesize_response_stream(
                        resolved, nodes, fine_intent
                    ):
                        full_response += chunk
                        yield chunk

            self._history_manager.save_message(
                session_id, "assistant", full_response, sources or None,
            )
            logger.info(f"[STREAM] Saved full response ({len(full_response)} chars) to DB")

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
    # RAG pipeline — single unified method
    # ------------------------------------------------------------------

    async def _retrieve_and_rerank(
        self, message: str
    ) -> tuple[List[NodeWithScore], List[str]]:
        """
        Unified 5-step Advanced RAG pipeline:
          1. Query Rewriting (+ optional expansion/HyDE)
          2. Metadata filter extraction
          3. Multi-Query Hybrid Retrieval (parallel variants)
          4. Cross-Encoder Reranking with score threshold
          5. Post-filtering by metadata
        """
        rc = self.settings.retrieval
        index = self._get_index()
        if index is None:
            return [], []

        t_total = time.perf_counter()

        # ── Step 1: Query Rewriting ─────────────────────────────────────
        t0 = time.perf_counter()
        search_query = message
        all_query_variants: List[str] = []

        if self._query_rewriter:
            try:
                rewritten_result = await self._query_rewriter.rewrite(message)
                search_query = rewritten_result.rewritten
                all_query_variants = rewritten_result.expanded_queries
                logger.info(
                    f"Query rewritten: '{message[:30]}...' → '{search_query[:30]}...' "
                    f"(+{len(all_query_variants)} variants)"
                )
            except Exception as e:
                logger.warning(f"Query rewriting failed: {e}")

        t_rewrite = time.perf_counter() - t0

        # ── Step 2: Metadata filter extraction ─────────────────────────
        filters = {}
        qdrant_filters = None
        if self._metadata_filter:
            filters = self._metadata_filter.extract_filters(message)
            qdrant_filters = self._metadata_filter.build_qdrant_filters(filters)

        # ── Step 3: Multi-Query Retrieval ───────────────────────────────
        t0 = time.perf_counter()

        # Collect all unique queries: rewritten + expansion variants
        unique_queries: List[str] = [search_query]
        for q in all_query_variants:
            if q and q != search_query and q not in unique_queries:
                unique_queries.append(q)

        async def _retrieve_single(query: str) -> List[NodeWithScore]:
            """Retrieve nodes for a single query."""
            try:
                # Important: when metadata filters are present, enforce vector
                # pre-filter retrieval. HybridRetriever currently has no
                # filter-aware path and can miss year/category-constrained docs.
                if self._hybrid_retriever and not qdrant_filters:
                    return await asyncio.to_thread(
                        self._hybrid_retriever.retrieve, query,
                    )
                else:
                    # Pure vector retrieval with optional pre-filter
                    retriever_kwargs: Dict[str, Any] = {
                        "similarity_top_k": rc.dense_top_k,
                    }
                    if qdrant_filters:
                        retriever_kwargs["filters"] = qdrant_filters
                    retriever = index.as_retriever(**retriever_kwargs)
                    return await asyncio.to_thread(retriever.retrieve, query)
            except Exception as e:
                logger.warning(f"Retrieval failed for query '{query[:30]}...': {e}")
                return []

        # Run all query variants in parallel
        if len(unique_queries) > 1:
            results_per_query = await asyncio.gather(*[_retrieve_single(q) for q in unique_queries])
        else:
            results_per_query = [await _retrieve_single(unique_queries[0])]

        # Merge + deduplicate by node_id (first occurrence wins)
        seen_ids: set = set()
        retrieved_nodes: List[NodeWithScore] = []
        for nodes_list in results_per_query:
            for node in nodes_list:
                nid = node.node.node_id
                if nid not in seen_ids:
                    seen_ids.add(nid)
                    retrieved_nodes.append(node)

        logger.info(
            f"Multi-query retrieval: {len(unique_queries)} queries → "
            f"{len(retrieved_nodes)} unique nodes merged"
        )
        t_retrieval = time.perf_counter() - t0

        # ── Step 4: Cross-Encoder Reranking with score threshold ────────
        t0 = time.perf_counter()
        if self._reranker and retrieved_nodes:
            reranked_nodes = await self._reranker.rerank(query=message, nodes=retrieved_nodes)
        else:
            reranked_nodes = retrieved_nodes[:rc.rerank_top_n]

        # Score threshold: reject low-confidence results to avoid hallucination
        if reranked_nodes and self._reranker and not filters:
            top_score = reranked_nodes[0].score if reranked_nodes[0].score is not None else 0.0
            if top_score < rc.rerank_score_threshold:
                logger.warning(
                    f"Top reranker score {top_score:.3f} < threshold {rc.rerank_score_threshold}. "
                    "Returning empty to trigger fallback."
                )
                return [], []

        t_rerank = time.perf_counter() - t0

        # ── Step 5: Post-filtering by metadata ──────────────────────────
        t0 = time.perf_counter()
        if filters and self._metadata_filter:
            final_nodes = self._metadata_filter.apply_post_filters(
                reranked_nodes, filters, strict=False
            )
        else:
            final_nodes = reranked_nodes

        t_postfilter = time.perf_counter() - t0

        # ── Timing summary ───────────────────────────────────────────────
        t_pipeline = time.perf_counter() - t_total
        logger.info(
            f"[TIMING] pipeline={t_pipeline*1000:.0f}ms | "
            f"rewrite={t_rewrite*1000:.0f}ms | "
            f"retrieval={t_retrieval*1000:.0f}ms | "
            f"rerank={t_rerank*1000:.0f}ms | "
            f"postfilter={t_postfilter*1000:.0f}ms | "
            f"final_nodes={len(final_nodes)}"
        )

        sources = self._response_handler.extract_sources(final_nodes) if final_nodes else []
        return final_nodes, sources

    # ------------------------------------------------------------------
    # RAG query handler (sync path)
    # ------------------------------------------------------------------

    async def _handle_rag_query(
        self, message: str, intent: str = "QUERY_DOCS"
    ) -> tuple[str, List[str]]:
        """Unified RAG handler: retrieve → rerank → synthesize."""
        index = self._get_index()
        if index is None:
            return (
                "Xin lỗi, hệ thống Knowledge Base chưa được khởi tạo. "
                "Vui lòng liên hệ Admin để nạp dữ liệu.", [],
            )

        try:
            nodes, sources = await self._retrieve_and_rerank(message)
        except Exception as e:
            logger.error(f"Retrieval pipeline failed, falling back to basic: {e}")
            return await self._handle_basic_rag_query(message)

        if not nodes:
            fine_intent = IntentClassifier.get_fine_intent(intent)
            no_context_text = await self._response_handler.synthesize_no_context_response(
                message, fine_intent
            )
            return no_context_text or _NO_CONTEXT_MSG, []

        if not self._intent_category_guard(intent, nodes):
            fine_intent = IntentClassifier.get_fine_intent(intent)
            no_context_text = await self._response_handler.synthesize_no_context_response(
                message, fine_intent
            )
            return no_context_text or _NO_CONTEXT_MSG, []

        fine_intent = IntentClassifier.get_fine_intent(intent)
        response_text = await self._response_handler.synthesize_response(
            message, nodes, fine_intent
        )
        return response_text, sources

    async def _handle_basic_rag_query(self, message: str) -> tuple[str, List[str]]:
        """
        Pure vector fallback — used if the Advanced RAG pipeline throws.
        Uses ResponseHandler.synthesize_response() to keep response format consistent.
        """
        try:
            index = self._get_index()
            if index is None:
                return (
                    "Xin lỗi, hệ thống Knowledge Base chưa được khởi tạo. "
                    "Vui lòng liên hệ Admin để nạp dữ liệu.", [],
                )
            retriever = index.as_retriever(
                similarity_top_k=self.settings.retrieval.dense_top_k
            )
            nodes = await asyncio.to_thread(retriever.retrieve, message)
            if not nodes:
                no_context_text = await self._response_handler.synthesize_no_context_response(
                    message, "general"
                )
                return no_context_text or _NO_CONTEXT_MSG, []

            sources = self._response_handler.extract_sources(nodes)
            response_text = await self._response_handler.synthesize_response(
                message, nodes, "general"
            )
            return response_text, sources

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
        try:
            old_nodes_count = len(self._all_nodes) if self._all_nodes else 0
            had_hybrid = self._hybrid_retriever is not None
            had_index = self._index is not None

            # Clear RAG caches
            self._index = None
            self._query_engine = None
            self._hybrid_retriever = None
            self._all_nodes = []

            # Clear prompt cache
            try:
                self._prompt_service.invalidate_cache()
            except Exception as prompt_err:
                logger.warning(f"Failed to invalidate prompt cache: {prompt_err}")

            # Refresh latest years from MongoDB
            self._refresh_latest_years()

            # Reinitialize
            self._get_index()

            new_nodes_count = len(self._all_nodes) if self._all_nodes else 0

            result = {
                "status": "success",
                "cleared": {
                    "index": had_index,
                    "hybrid_retriever": had_hybrid,
                    "nodes_before": old_nodes_count,
                },
                "reloaded": {
                    "index": self._index is not None,
                    "hybrid_retriever": self._hybrid_retriever is not None,
                    "nodes_after": new_nodes_count,
                },
                "latest_years": {
                    "scores": self._latest_scores_year,
                    "fees": self._latest_fees_year,
                },
            }

            logger.info(f"Cache cleared and reloaded: {old_nodes_count} → {new_nodes_count} nodes")
            return result

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return {"status": "error", "error": str(e)}
