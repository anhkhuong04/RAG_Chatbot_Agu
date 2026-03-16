import asyncio
from unittest.mock import MagicMock, patch, PropertyMock
import numpy as np

import pytest
import pytest_asyncio

from llama_index.core.schema import NodeWithScore, TextNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_nodes(texts: list[str], scores: list[float] | None = None) -> list[NodeWithScore]:
    if scores is None:
        scores = [1.0] * len(texts)
    return [
        NodeWithScore(node=TextNode(text=t), score=s)
        for t, s in zip(texts, scores)
    ]


def _make_reranker(predict_scores):
    from app.service.retrieval.reranker import CrossEncoderReranker

    with patch.object(CrossEncoderReranker, "__init__", lambda self, **kw: None):
        reranker = CrossEncoderReranker()

    reranker.model_name = "mock-model"
    reranker.top_n = 3

    mock_model = MagicMock()
    mock_model.predict = MagicMock(return_value=np.array(predict_scores))
    reranker.model = mock_model

    return reranker


# ---------------------------------------------------------------------------
# rerank()
# ---------------------------------------------------------------------------

class TestRerank:

    @pytest.mark.asyncio
    async def test_rerank_returns_sorted_nodes(self):
        nodes = _make_nodes(["doc A", "doc B", "doc C"], [0.5, 0.5, 0.5])
        # Model scores: C > A > B
        reranker = _make_reranker([0.2, 0.1, 0.9])

        result = await reranker.rerank("query", nodes, top_n=3)

        assert len(result) == 3
        assert all(isinstance(n, NodeWithScore) for n in result)
        # Highest score first
        assert result[0].score == pytest.approx(0.9)
        assert result[0].node.text == "doc C"
        assert result[1].score == pytest.approx(0.2)
        assert result[2].score == pytest.approx(0.1)

    @pytest.mark.asyncio
    async def test_rerank_respects_top_n(self):
        nodes = _make_nodes(["a", "b", "c", "d", "e"])
        reranker = _make_reranker([0.5, 0.3, 0.9, 0.1, 0.7])

        result = await reranker.rerank("q", nodes, top_n=2)

        assert len(result) == 2
        assert result[0].node.text == "c"  # score 0.9
        assert result[1].node.text == "e"  # score 0.7

    @pytest.mark.asyncio
    async def test_rerank_empty_nodes(self):
        reranker = _make_reranker([])
        result = await reranker.rerank("query", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_rerank_predict_uses_executor(self):
        nodes = _make_nodes(["doc"])
        reranker = _make_reranker([0.5])

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            # Make run_in_executor return a coroutine that yields the scores
            async def fake_executor(executor, fn):
                return fn()

            mock_loop.run_in_executor = fake_executor

            result = await reranker.rerank("q", nodes)

        assert len(result) == 1
        reranker.model.predict.assert_called_once()

    @pytest.mark.asyncio
    async def test_rerank_fallback_on_predict_error(self):
        nodes = _make_nodes(["a", "b", "c"])
        reranker = _make_reranker([])
        reranker.model.predict = MagicMock(side_effect=RuntimeError("CUDA OOM"))

        result = await reranker.rerank("q", nodes, top_n=2)

        # Should fallback to first 2 original nodes
        assert len(result) == 2
        assert result[0].node.text == "a"
        assert result[1].node.text == "b"

    @pytest.mark.asyncio
    async def test_rerank_truncates_long_text(self):
        long_text = "x" * 2000
        nodes = _make_nodes([long_text])
        reranker = _make_reranker([0.5])

        await reranker.rerank("q", nodes)

        call_args = reranker.model.predict.call_args
        pairs = call_args[0][0]  # first positional arg
        assert len(pairs[0][1]) < 2000  # truncated


# ---------------------------------------------------------------------------
# rerank_with_scores()
# ---------------------------------------------------------------------------

class TestRerankWithScores:

    @pytest.mark.asyncio
    async def test_returns_tuples_with_both_scores(self):
        nodes = _make_nodes(["a", "b"], scores=[0.8, 0.6])
        reranker = _make_reranker([0.3, 0.7])

        result = await reranker.rerank_with_scores("q", nodes)

        assert len(result) == 2
        # Sorted by reranker score descending, so "b" first
        node, orig, rerank_s = result[0]
        assert node.node.text == "b"
        assert orig == pytest.approx(0.6)
        assert rerank_s == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_empty_input(self):
        reranker = _make_reranker([])
        assert await reranker.rerank_with_scores("q", []) == []
