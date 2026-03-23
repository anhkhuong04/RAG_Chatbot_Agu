import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.service.retrieval.query_rewriter import QueryRewriter


def _make_chat_response(content: str):
    msg = MagicMock()
    msg.content = content
    resp = MagicMock()
    resp.message = msg
    return resp


class TestHyDEIntegration:

    @pytest.mark.asyncio
    async def test_hyde_disabled_by_default(self):
        """HyDE generate_hypothetical_document is NOT called when enable_hyde=False."""
        qr = QueryRewriter(
            enable_rewrite=False, enable_expansion=False,
            enable_keywords=False, enable_hyde=False,
        )
        assert not qr._hyde_expander.enabled

        mock_llm = MagicMock()
        mock_llm.achat = AsyncMock(return_value=_make_chat_response(""))

        with patch("app.service.retrieval.query_rewriter.Settings") as s:
            s.llm = mock_llm
            result = await qr.rewrite("học phí là bao nhiêu?")

        # HyDE produces no extra expanded query
        assert result.expanded_queries == []
        mock_llm.achat.assert_not_called()

    @pytest.mark.asyncio
    async def test_hyde_enabled_appends_to_expanded_queries(self):
        """HyDE document is appended to expanded_queries when enable_hyde=True."""
        qr = QueryRewriter(
            enable_rewrite=False, enable_expansion=False,
            enable_keywords=False, enable_hyde=True,
        )
        assert qr._hyde_expander.enabled

        hyde_doc = "Học phí tại Đại học An Giang năm 2025 là 15 triệu đồng mỗi năm."

        async def mock_achat(messages):
            return _make_chat_response(hyde_doc)

        mock_llm = MagicMock()
        mock_llm.achat = mock_achat

        with patch("app.service.retrieval.query_rewriter.Settings") as s:
            s.llm = mock_llm
            result = await qr.rewrite("học phí là bao nhiêu?")

        assert hyde_doc in result.expanded_queries

    @pytest.mark.asyncio
    async def test_hyde_and_expansion_both_append(self):
        """Both regular expansion AND HyDE append to expanded_queries."""
        qr = QueryRewriter(
            enable_rewrite=False, enable_expansion=True,
            enable_keywords=False, enable_hyde=True,
        )

        expand_lines = "Mức học phí hàng năm\nChi phí đào tạo đại học"
        hyde_doc = "Học phí trường An Giang là 12 triệu."

        call_count = 0

        async def mock_achat(messages):
            nonlocal call_count
            call_count += 1
            content = messages[-1].content
            if "Câu hỏi gốc" in content:
                return _make_chat_response(expand_lines)
            # HyDE system prompt contains "Viết một đoạn văn ngắn"
            return _make_chat_response(hyde_doc)

        mock_llm = MagicMock()
        mock_llm.achat = mock_achat

        with patch("app.service.retrieval.query_rewriter.Settings") as s:
            s.llm = mock_llm
            result = await qr.rewrite("học phí là bao nhiêu?")

        # Expansion gives 2 lines; HyDE gives 1 more
        assert hyde_doc in result.expanded_queries
        assert call_count == 2  # expand + hyde called in parallel

    @pytest.mark.asyncio
    async def test_hyde_failure_does_not_crash(self):
        """If HyDE LLM call fails, pipeline continues and expanded_queries stays intact."""
        qr = QueryRewriter(
            enable_rewrite=False, enable_expansion=False,
            enable_keywords=False, enable_hyde=True,
        )

        async def mock_achat(messages):
            raise RuntimeError("HyDE LLM error")

        mock_llm = MagicMock()
        mock_llm.achat = mock_achat

        with patch("app.service.retrieval.query_rewriter.Settings") as s:
            s.llm = mock_llm
            result = await qr.rewrite("test")  # Should not raise

        # No expansion appended but original query preserved
        assert result.original == "test"
        assert result.expanded_queries == []
