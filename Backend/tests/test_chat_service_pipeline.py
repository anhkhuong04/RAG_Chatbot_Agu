"""
Tests for the new Multi-Query Retrieval pipeline and ChatService improvements.

Covers:
  - _retrieve_and_rerank: multi-query parallelism, deduplication
  - _refresh_latest_years: MongoDB aggregation → correct year assignment
  - reranker score threshold: returns empty when top score < threshold
  - _handle_basic_rag_query: uses ResponseHandler (consistent format)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llama_index.core.schema import NodeWithScore, TextNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(node_id: str, score: float = 0.9, text: str = "test") -> NodeWithScore:
    node = TextNode(text=text, id_=node_id)
    return NodeWithScore(node=node, score=score)


def _make_chat_service_shell():
    """Return a ChatService instance with all external dependencies mocked out."""
    with patch("app.service.chat.chat_service.init_settings"), \
         patch("app.service.chat.chat_service.get_prompt_service"), \
         patch("app.service.chat.chat_service.get_chat_sessions_collection"), \
         patch("app.service.chat.chat_service.get_qdrant_client"), \
         patch("app.service.chat.chat_service.get_database"), \
         patch("app.service.chat.chat_service.IntentClassifier"), \
         patch("app.service.chat.chat_service.ChatHistoryManager"), \
         patch("app.service.chat.chat_service.CoreferenceResolver"), \
         patch("app.service.chat.chat_service.ResponseHandler"), \
         patch.object(
             __import__("app.service.chat.chat_service", fromlist=["ChatService"]).ChatService,
             "_init_advanced_rag",
         ), \
         patch.object(
             __import__("app.service.chat.chat_service", fromlist=["ChatService"]).ChatService,
             "_refresh_latest_years",
         ):
        from app.service.chat.chat_service import ChatService
        svc = ChatService()
        return svc


# ---------------------------------------------------------------------------
# Tests: _refresh_latest_years
# ---------------------------------------------------------------------------

class TestRefreshLatestYears:

    def test_sets_scores_and_fees_year_from_mongo(self):
        from app.service.chat.chat_service import ChatService

        mock_aggregate_result = [
            {"_id": "Điểm chuẩn", "max_year": 2024},
            {"_id": "Học phí", "max_year": 2023},
        ]

        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = iter(mock_aggregate_result)

        with patch("app.service.chat.chat_service.init_settings"), \
             patch("app.service.chat.chat_service.get_prompt_service"), \
             patch("app.service.chat.chat_service.get_chat_sessions_collection"), \
             patch("app.service.chat.chat_service.get_qdrant_client"), \
             patch("app.service.chat.chat_service.get_database") as mock_get_db, \
             patch("app.service.chat.chat_service.IntentClassifier"), \
             patch("app.service.chat.chat_service.ChatHistoryManager"), \
             patch("app.service.chat.chat_service.CoreferenceResolver"), \
             patch("app.service.chat.chat_service.ResponseHandler"), \
             patch.object(
                 ChatService, "_init_advanced_rag",
             ):
            mock_get_db.return_value.__getitem__.return_value = mock_collection
            svc = ChatService()

        svc._refresh_latest_years()

        # Manually trigger with the mock
        mock_collection.aggregate.return_value = iter(mock_aggregate_result)
        svc._doc_collection = mock_collection
        svc._latest_scores_year = None
        svc._latest_fees_year = None
        svc._refresh_latest_years()

        assert svc._latest_scores_year == 2024
        assert svc._latest_fees_year == 2023

    def test_handles_mongo_failure_gracefully(self):
        svc = _make_chat_service_shell()

        mock_collection = MagicMock()
        mock_collection.aggregate.side_effect = Exception("Mongo connection error")
        svc._doc_collection = mock_collection

        # Should not raise
        svc._refresh_latest_years()

        # Stays None on failure
        assert svc._latest_scores_year is None
        assert svc._latest_fees_year is None


# ---------------------------------------------------------------------------
# Tests: _retrieve_and_rerank — Multi-Query Retrieval
# ---------------------------------------------------------------------------

class TestMultiQueryRetrieval:

    @pytest.mark.asyncio
    async def test_single_query_when_no_expansion(self):
        """Without expanded_queries, only 1 retrieval call is made."""
        svc = _make_chat_service_shell()

        # No query rewriter → uses raw message
        svc._query_rewriter = None
        svc._metadata_filter = None
        svc._reranker = None
        svc._hybrid_retriever = None

        mock_node = _make_node("n1")
        mock_index = MagicMock()
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [mock_node]
        mock_index.as_retriever.return_value = mock_retriever
        svc._index = mock_index

        svc._response_handler.extract_sources.return_value = []

        nodes, sources = await svc._retrieve_and_rerank("test query")

        assert mock_retriever.retrieve.call_count == 1
        assert len(nodes) == 1

    @pytest.mark.asyncio
    async def test_multiple_queries_parallel_retrieval(self):
        """Expanded queries cause multiple parallel retrieval calls."""
        svc = _make_chat_service_shell()

        # Mock query rewriter that returns 2 expanded variants
        mock_rewritten = MagicMock()
        mock_rewritten.rewritten = "rewritten query"
        mock_rewritten.expanded_queries = ["variant 1", "variant 2"]
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite = AsyncMock(return_value=mock_rewritten)
        svc._query_rewriter = mock_rewriter
        svc._metadata_filter = None
        svc._reranker = None
        svc._hybrid_retriever = None

        call_log = []

        def fake_retrieve(query):
            call_log.append(query)
            return [_make_node(f"node_{query[:6]}")]

        mock_index = MagicMock()
        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = fake_retrieve
        mock_index.as_retriever.return_value = mock_retriever
        svc._index = mock_index
        svc._response_handler.extract_sources.return_value = []

        nodes, _ = await svc._retrieve_and_rerank("original")

        # 3 unique queries: rewritten + 2 variants → 3 retrieval calls
        assert len(call_log) == 3
        assert "rewritten query" in call_log
        assert "variant 1" in call_log
        assert "variant 2" in call_log

    @pytest.mark.asyncio
    async def test_deduplication_of_nodes(self):
        """Nodes with the same node_id from different queries are deduplicated."""
        svc = _make_chat_service_shell()

        mock_rewritten = MagicMock()
        mock_rewritten.rewritten = "q1"
        mock_rewritten.expanded_queries = ["q2"]
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite = AsyncMock(return_value=mock_rewritten)
        svc._query_rewriter = mock_rewriter
        svc._metadata_filter = None
        svc._reranker = None
        svc._hybrid_retriever = None

        shared_node = _make_node("shared_id", score=0.9)

        def fake_retrieve(query):
            # Both queries return the same node_id
            return [shared_node, _make_node(f"unique_{query}")]

        mock_index = MagicMock()
        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = fake_retrieve
        mock_index.as_retriever.return_value = mock_retriever
        svc._index = mock_index
        svc._response_handler.extract_sources.return_value = []

        nodes, _ = await svc._retrieve_and_rerank("test")

        # shared_node appears once, 2 unique nodes → total 3
        node_ids = [n.node.node_id for n in nodes]
        assert node_ids.count("shared_id") == 1
        assert len(nodes) == 3


# ---------------------------------------------------------------------------
# Tests: Reranker Score Threshold
# ---------------------------------------------------------------------------

class TestRerankerScoreThreshold:

    @pytest.mark.asyncio
    async def test_returns_empty_when_top_score_below_threshold(self):
        """When reranker top score < threshold, returns ([], []) to trigger fallback."""
        svc = _make_chat_service_shell()
        svc._query_rewriter = None
        svc._metadata_filter = None
        svc._hybrid_retriever = None

        # Score is -10.0 — below default threshold of -5.0
        low_score_node = _make_node("n1", score=-10.0)

        mock_reranker = MagicMock()
        mock_reranker.rerank = AsyncMock(return_value=[low_score_node])
        svc._reranker = mock_reranker

        mock_index = MagicMock()
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [low_score_node]
        mock_index.as_retriever.return_value = mock_retriever
        svc._index = mock_index

        nodes, sources = await svc._retrieve_and_rerank("any query")

        assert nodes == []
        assert sources == []

    @pytest.mark.asyncio
    async def test_returns_nodes_when_score_above_threshold(self):
        """When reranker top score >= threshold, nodes are returned normally."""
        svc = _make_chat_service_shell()
        svc._query_rewriter = None
        svc._metadata_filter = None
        svc._hybrid_retriever = None

        good_node = _make_node("n1", score=2.0)  # Above -5.0 threshold

        mock_reranker = MagicMock()
        mock_reranker.rerank = AsyncMock(return_value=[good_node])
        svc._reranker = mock_reranker

        mock_index = MagicMock()
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [good_node]
        mock_index.as_retriever.return_value = mock_retriever
        svc._index = mock_index
        svc._response_handler.extract_sources.return_value = ["source.pdf"]

        nodes, sources = await svc._retrieve_and_rerank("any query")

        assert len(nodes) == 1
        assert sources == ["source.pdf"]

    @pytest.mark.asyncio
    async def test_keeps_low_score_results_when_metadata_filters_present(self):
        """Low reranker scores should not force empty when user explicitly constrains metadata."""
        svc = _make_chat_service_shell()
        svc._query_rewriter = None
        svc._hybrid_retriever = None

        low_score_node = _make_node("n1", score=-10.0)

        mock_reranker = MagicMock()
        mock_reranker.rerank = AsyncMock(return_value=[low_score_node])
        svc._reranker = mock_reranker

        mock_index = MagicMock()
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [low_score_node]
        mock_index.as_retriever.return_value = mock_retriever
        svc._index = mock_index

        mock_filter = MagicMock()
        mock_filter.extract_filters.return_value = {"year": 2024}
        mock_filter.build_qdrant_filters.return_value = object()
        mock_filter.apply_post_filters.side_effect = lambda nodes, *_args, **_kwargs: nodes
        svc._metadata_filter = mock_filter

        svc._response_handler.extract_sources.return_value = ["source.pdf"]

        nodes, sources = await svc._retrieve_and_rerank("điểm chuẩn năm 2024")

        assert len(nodes) == 1
        assert sources == ["source.pdf"]


# ---------------------------------------------------------------------------
# Tests: Metadata-filter retrieval safety + category extraction robustness
# ---------------------------------------------------------------------------

class TestMetadataFilterSafety:

    @pytest.mark.asyncio
    async def test_uses_vector_prefilter_when_filters_exist_even_with_hybrid(self):
        """When metadata filters exist, retrieval must bypass hybrid and use vector pre-filter."""
        svc = _make_chat_service_shell()

        svc._query_rewriter = None
        svc._reranker = None

        mock_filter = MagicMock()
        mock_filter.extract_filters.return_value = {"year": 2024, "category": "Điểm chuẩn"}
        mock_qdrant_filters = object()
        mock_filter.build_qdrant_filters.return_value = mock_qdrant_filters
        mock_filter.apply_post_filters.side_effect = lambda nodes, *_args, **_kwargs: nodes
        svc._metadata_filter = mock_filter

        svc._hybrid_retriever = MagicMock()
        svc._hybrid_retriever.retrieve.return_value = [_make_node("hybrid_path")]

        vector_node = _make_node("vector_prefilter_path")
        mock_index = MagicMock()
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [vector_node]
        mock_index.as_retriever.return_value = mock_retriever
        svc._index = mock_index
        svc._response_handler.extract_sources.return_value = []

        nodes, _ = await svc._retrieve_and_rerank("diem chuan cntt nam 2024")

        svc._hybrid_retriever.retrieve.assert_not_called()
        assert mock_index.as_retriever.call_count == 1
        retriever_kwargs = mock_index.as_retriever.call_args.kwargs
        assert retriever_kwargs.get("filters") is mock_qdrant_filters
        assert [n.node.node_id for n in nodes] == ["vector_prefilter_path"]


class TestMetadataFilterExtraction:

    def test_extracts_score_category_from_non_accented_query(self):
        from app.service.retrieval.metadata_filter import MetadataFilterService

        svc = MetadataFilterService()
        filters = svc.extract_filters("diem chuan nganh cntt nam 2024")

        assert filters.get("year") == 2024
        assert filters.get("category") == "Điểm chuẩn"
