"""
Unit tests for QueryRewriter:
- asyncio.gather() parallel execution in rewrite()
- Fault tolerance (one task failing doesn't crash the pipeline)

Note: _detect_intent tests are now in test_intent_classifier.py
"""
import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.service.retrieval.query_rewriter import QueryRewriter, RewrittenQuery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chat_response(content: str):
    """Create a mock LLM chat response."""
    msg = MagicMock()
    msg.content = content
    resp = MagicMock()
    resp.message = msg
    return resp


# ---------------------------------------------------------------------------
# rewrite() — parallel execution & fault tolerance
# ---------------------------------------------------------------------------

class TestRewriteParallel:
    """Tests for the async rewrite() pipeline."""

    def setup_method(self):
        self.qr = QueryRewriter(
            enable_rewrite=True, enable_expansion=True, enable_keywords=True
        )

    @pytest.mark.asyncio
    async def test_all_tasks_run_in_parallel(self):
        """All 3 LLM tasks should complete and results should be populated."""
        rewrite_resp = _make_chat_response("Điểm chuẩn ngành Công nghệ thông tin")
        expand_resp = _make_chat_response(
            "Điểm trúng tuyển CNTT\nĐiểm đỗ ngành Công nghệ thông tin"
        )
        keyword_resp = _make_chat_response("điểm chuẩn, công nghệ thông tin")

        call_count = 0
        async def mock_achat(messages):
            nonlocal call_count
            call_count += 1
            content = messages[-1].content
            if "Viết lại" in content:
                return rewrite_resp
            elif "Câu hỏi gốc" in content:
                return expand_resp
            else:
                return keyword_resp

        mock_llm = MagicMock()
        mock_llm.achat = mock_achat

        with patch("app.service.retrieval.query_rewriter.Settings") as mock_settings:
            mock_settings.llm = mock_llm
            result = await self.qr.rewrite("điểm cntt")

        assert isinstance(result, RewrittenQuery)
        assert result.rewritten == "Điểm chuẩn ngành Công nghệ thông tin"
        assert len(result.expanded_queries) == 2
        assert "điểm chuẩn" in result.extracted_keywords
        assert call_count == 3  # All 3 tasks called

    @pytest.mark.asyncio
    async def test_keyword_failure_does_not_crash(self):
        """If keyword extraction fails, rewrite & expand should still succeed."""
        rewrite_resp = _make_chat_response("Học phí đại học")
        expand_resp = _make_chat_response("Chi phí học tập")

        async def mock_achat(messages):
            content = messages[-1].content
            if "Viết lại" in content:
                return rewrite_resp
            elif "Câu hỏi gốc" in content:
                return expand_resp
            else:
                raise RuntimeError("Keyword extraction error")

        mock_llm = MagicMock()
        mock_llm.achat = mock_achat

        with patch("app.service.retrieval.query_rewriter.Settings") as mock_settings:
            mock_settings.llm = mock_llm
            result = await self.qr.rewrite("học phí")

        assert result.rewritten == "Học phí đại học"
        assert len(result.expanded_queries) == 1
        assert result.extracted_keywords == []  # Failed gracefully

    @pytest.mark.asyncio
    async def test_rewrite_failure_keeps_original(self):
        """If rewrite task fails, original query is kept."""
        expand_resp = _make_chat_response("Câu hỏi mở rộng")
        keyword_resp = _make_chat_response("keyword1")

        async def mock_achat(messages):
            content = messages[-1].content
            if "Viết lại" in content:
                raise RuntimeError("Rewrite error")
            elif "Câu hỏi gốc" in content:
                return expand_resp
            else:
                return keyword_resp

        mock_llm = MagicMock()
        mock_llm.achat = mock_achat

        with patch("app.service.retrieval.query_rewriter.Settings") as mock_settings:
            mock_settings.llm = mock_llm
            result = await self.qr.rewrite("test query")

        assert result.rewritten == "test query"  # Kept original
        assert result.original == "test query"

    @pytest.mark.asyncio
    async def test_rewrite_guard_blocks_cntt_injection_for_general_policy_query(self):
        """Generic policy query should not be rewritten into CNTT-specific query."""
        rewrite_resp = _make_chat_response("Học bổng ngành Công nghệ thông tin như thế nào")

        async def mock_achat(messages):
            content = messages[-1].content
            if "Viết lại" in content:
                return rewrite_resp
            return _make_chat_response("")

        qr = QueryRewriter(enable_rewrite=True, enable_expansion=False, enable_keywords=False)

        mock_llm = MagicMock()
        mock_llm.achat = mock_achat

        with patch("app.service.retrieval.query_rewriter.Settings") as mock_settings:
            mock_settings.llm = mock_llm
            result = await qr.rewrite("trường có học bổng không")

        assert result.rewritten == "trường có học bổng không"

    @pytest.mark.asyncio
    async def test_disabled_tasks_not_called(self):
        """Disabled tasks should not generate LLM calls."""
        qr = QueryRewriter(
            enable_rewrite=False, enable_expansion=False, enable_keywords=False
        )

        mock_llm = MagicMock()
        mock_llm.achat = AsyncMock()

        with patch("app.service.retrieval.query_rewriter.Settings") as mock_settings:
            mock_settings.llm = mock_llm
            result = await qr.rewrite("test")

        mock_llm.achat.assert_not_called()
        assert result.rewritten == "test"
        assert result.expanded_queries == []
        assert result.extracted_keywords == []

    @pytest.mark.asyncio
    async def test_detected_intent_defaults_to_general(self):
        """Intent detection is no longer done in QueryRewriter; field should default to 'general'."""
        qr = QueryRewriter(
            enable_rewrite=False, enable_expansion=False, enable_keywords=False
        )

        with patch("app.service.retrieval.query_rewriter.Settings"):
            result = await qr.rewrite("điểm chuẩn ngành CNTT")

        # QueryRewriter no longer detects intent — always defaults to general
        assert result.detected_intent == "general"

