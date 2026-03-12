"""
Unit tests for HybridRetriever.update_bm25_index:
- Runs rebuild in background (run_in_executor)
- asyncio.Lock prevents concurrent rebuilds
- Atomic swap of bm25_retriever
- Empty nodes warning
"""
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import pytest_asyncio

from llama_index.core.schema import NodeWithScore, TextNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hybrid_retriever(nodes=None):
    """Create a HybridRetriever with mocked dependencies."""
    from app.service.retrieval.hybrid_retriever import HybridRetriever

    with patch.object(HybridRetriever, "__init__", lambda self, **kw: None):
        hr = HybridRetriever()

    hr.alpha = 0.5
    hr.dense_top_k = 10
    hr.sparse_top_k = 10
    hr.final_top_k = 10
    hr.bm25_retriever = MagicMock() if nodes else None
    hr.vector_retriever = MagicMock()
    # Need the lock
    hr._bm25_rebuild_lock = asyncio.Lock()

    return hr


# ---------------------------------------------------------------------------
# update_bm25_index
# ---------------------------------------------------------------------------

class TestUpdateBM25Index:

    @pytest.mark.asyncio
    async def test_rebuild_swaps_retriever(self):
        """After update, bm25_retriever should be the new instance."""
        hr = _make_hybrid_retriever(nodes=["existing"])
        old_retriever = hr.bm25_retriever

        fake_new_retriever = MagicMock(name="new_bm25")

        with patch(
            "app.service.retrieval.hybrid_retriever.BM25Retriever"
        ) as MockBM25:
            MockBM25.from_defaults.return_value = fake_new_retriever
            fake_nodes = [TextNode(text="new doc")]
            await hr.update_bm25_index(fake_nodes)

        assert hr.bm25_retriever is fake_new_retriever
        assert hr.bm25_retriever is not old_retriever

    @pytest.mark.asyncio
    async def test_empty_nodes_skipped(self):
        """Empty node list should not trigger rebuild."""
        hr = _make_hybrid_retriever(nodes=["existing"])
        old_retriever = hr.bm25_retriever

        await hr.update_bm25_index([])

        assert hr.bm25_retriever is old_retriever  # unchanged

    @pytest.mark.asyncio
    async def test_none_nodes_skipped(self):
        """None node list should not trigger rebuild."""
        hr = _make_hybrid_retriever(nodes=["existing"])
        old_retriever = hr.bm25_retriever

        await hr.update_bm25_index(None)

        assert hr.bm25_retriever is old_retriever

    @pytest.mark.asyncio
    async def test_uses_executor(self):
        """BM25 rebuild should be dispatched to run_in_executor."""
        hr = _make_hybrid_retriever(nodes=["existing"])

        fake_retriever = MagicMock()

        with patch(
            "app.service.retrieval.hybrid_retriever.BM25Retriever"
        ) as MockBM25:
            MockBM25.from_defaults.return_value = fake_retriever

            with patch("asyncio.get_event_loop") as mock_get_loop:
                mock_loop = MagicMock()
                mock_get_loop.return_value = mock_loop

                async def fake_run_in_executor(executor, fn):
                    assert executor is None  # should use default executor
                    return fn()

                mock_loop.run_in_executor = fake_run_in_executor

                await hr.update_bm25_index([TextNode(text="doc")])

        MockBM25.from_defaults.assert_called_once()
        assert hr.bm25_retriever is fake_retriever

    @pytest.mark.asyncio
    async def test_lock_prevents_concurrent_rebuilds(self):
        """Only one rebuild should run at a time."""
        hr = _make_hybrid_retriever(nodes=["existing"])
        rebuild_order = []

        fake_retriever_1 = MagicMock(name="retriever_1")
        fake_retriever_2 = MagicMock(name="retriever_2")
        call_count = 0

        with patch(
            "app.service.retrieval.hybrid_retriever.BM25Retriever"
        ) as MockBM25:
            def make_retriever(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    rebuild_order.append("build_1")
                    return fake_retriever_1
                else:
                    rebuild_order.append("build_2")
                    return fake_retriever_2

            MockBM25.from_defaults.side_effect = make_retriever

            nodes = [TextNode(text="doc")]
            # Run two updates; lock should serialize them
            await asyncio.gather(
                hr.update_bm25_index(nodes),
                hr.update_bm25_index(nodes),
            )

        assert len(rebuild_order) == 2
        # Final retriever should be from the second build
        assert hr.bm25_retriever is fake_retriever_2

    @pytest.mark.asyncio
    async def test_passes_sparse_top_k(self):
        """from_defaults should receive the correct sparse_top_k."""
        hr = _make_hybrid_retriever(nodes=["existing"])
        hr.sparse_top_k = 7

        with patch(
            "app.service.retrieval.hybrid_retriever.BM25Retriever"
        ) as MockBM25:
            MockBM25.from_defaults.return_value = MagicMock()
            await hr.update_bm25_index([TextNode(text="doc")])

        _, kwargs = MockBM25.from_defaults.call_args
        assert kwargs["similarity_top_k"] == 7
