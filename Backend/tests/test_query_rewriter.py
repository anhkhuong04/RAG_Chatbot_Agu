"""
Unit tests for QueryRewriter:
- asyncio.gather() parallel execution in rewrite()
- Fault tolerance (one task failing doesn't crash the pipeline)
- _detect_intent() with regex (có dấu, không dấu) and fuzzy matching (typos)
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
# _detect_intent — regex & fuzzy
# ---------------------------------------------------------------------------

class TestDetectIntent:
    """Tests for the regex + fuzzy _detect_intent method."""

    def setup_method(self):
        self.qr = QueryRewriter(
            enable_rewrite=False, enable_expansion=False, enable_keywords=False
        )

    # --- Exact match (có dấu) ---
    @pytest.mark.parametrize("query, expected", [
        ("Điểm chuẩn ngành CNTT", "diem_chuan"),
        ("Điểm trúng tuyển năm 2025", "diem_chuan"),
        ("Điểm đỗ đại học", "diem_chuan"),
        ("Học phí ngành kinh tế", "hoc_phi"),
        ("Chi phí đào tạo", "hoc_phi"),
        ("Học bổng tài năng", "hoc_phi"),
        ("Tuyển sinh đại học 2025", "tuyen_sinh"),
        ("Xét tuyển nguyện vọng 1", "tuyen_sinh"),
        ("Đăng ký nộp hồ sơ", "tuyen_sinh"),
        ("Ngành công nghệ thông tin", "nganh_hoc"),
        ("Mã ngành kinh tế", "nganh_hoc"),
        ("Chương trình đào tạo", "nganh_hoc"),
        ("Quy chế thi", "quy_che"),
        ("Điều kiện tốt nghiệp", "quy_che"),
        ("Yêu cầu đầu vào", "quy_che"),
    ])
    def test_exact_vietnamese(self, query, expected):
        assert self.qr._detect_intent(query) == expected

    # --- Không dấu (no diacritics) — should be caught by regex ---
    @pytest.mark.parametrize("query, expected", [
        ("diem chuan nganh CNTT", "diem_chuan"),
        ("diem trung tuyen 2025", "diem_chuan"),
        ("hoc phi nganh kinh te", "hoc_phi"),
        ("tuyen sinh dai hoc", "tuyen_sinh"),
        ("xet tuyen nguyen vong", "tuyen_sinh"),
        ("dang ky ho so", "tuyen_sinh"),
        ("nganh cong nghe thong tin", "nganh_hoc"),
        ("ma nganh", "nganh_hoc"),
        ("quy che thi", "quy_che"),
        ("dieu kien tot nghiep", "quy_che"),
    ])
    def test_no_diacritics(self, query, expected):
        assert self.qr._detect_intent(query) == expected

    # --- Fuzzy matching (light typos) ---
    @pytest.mark.parametrize("query, expected", [
        ("diểm chuẫn", "diem_chuan"),   # sai dấu nhẹ
        ("hoc phí bao nhieu", "hoc_phi"),  # thiếu dấu 1 phần
    ])
    def test_fuzzy_typos(self, query, expected):
        assert self.qr._detect_intent(query) == expected

    # --- Unknown intent ---
    def test_general_fallback(self):
        assert self.qr._detect_intent("thời tiết hôm nay") == "general"
        assert self.qr._detect_intent("hello world") == "general"


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
    async def test_intent_always_detected(self):
        """Intent detection should run even when LLM tasks are disabled."""
        qr = QueryRewriter(
            enable_rewrite=False, enable_expansion=False, enable_keywords=False
        )

        with patch("app.service.retrieval.query_rewriter.Settings"):
            result = await qr.rewrite("điểm chuẩn ngành CNTT")

        assert result.detected_intent == "diem_chuan"
