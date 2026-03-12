import asyncio
import logging
import re
from difflib import SequenceMatcher
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from llama_index.core import Settings
from llama_index.core.llms import ChatMessage, MessageRole

logger = logging.getLogger(__name__)


@dataclass
class RewrittenQuery:
    """Container for rewritten query results"""
    original: str
    rewritten: str
    expanded_queries: List[str]
    extracted_keywords: List[str]
    detected_intent: str


class QueryRewriter:
    # System prompt for query rewriting
    REWRITE_SYSTEM_PROMPT = """Bạn là chuyên gia xử lý ngôn ngữ tự nhiên cho hệ thống tư vấn tuyển sinh đại học.

Nhiệm vụ: Phân tích và viết lại câu hỏi của người dùng để tối ưu cho việc tìm kiếm thông tin.

Quy tắc:
1. Giữ nguyên ý nghĩa gốc của câu hỏi
2. Chuẩn hóa thuật ngữ (VD: "CNTT" → "Công nghệ thông tin")
3. Thêm context nếu câu hỏi mơ hồ
4. Loại bỏ từ thừa, giữ keywords quan trọng
5. Nếu có năm cụ thể, giữ nguyên năm đó
6. Nếu không có năm, KHÔNG thêm năm vào

Ví dụ:
- "điểm cntt" → "Điểm chuẩn ngành Công nghệ thông tin"
- "học phí bao nhiêu" → "Mức học phí các ngành đào tạo"
- "đăng ký xét tuyển như nào" → "Quy trình đăng ký xét tuyển đại học"
"""

    EXPAND_SYSTEM_PROMPT = """Bạn là chuyên gia tìm kiếm thông tin tuyển sinh đại học.

Nhiệm vụ: Từ câu hỏi gốc, sinh ra 2-3 câu hỏi tương đương khác nhau để mở rộng phạm vi tìm kiếm.

Quy tắc:
1. Mỗi câu hỏi phải khác nhau về cách diễn đạt nhưng cùng ý nghĩa
2. Sử dụng từ đồng nghĩa, cách nói khác
3. Giữ nguyên các thông tin cụ thể (năm, tên ngành, mã ngành)
4. Output mỗi câu trên 1 dòng, không đánh số

Ví dụ input: "Điểm chuẩn ngành CNTT năm 2025"
Output:
Điểm trúng tuyển Công nghệ thông tin 2025
Điểm đỗ ngành CNTT năm 2025
Điểm xét tuyển ngành Công nghệ thông tin 2025
"""

    KEYWORD_SYSTEM_PROMPT = """Trích xuất các từ khóa quan trọng từ câu hỏi tuyển sinh đại học.

Quy tắc:
1. Chỉ trả về từ khóa, mỗi từ khóa cách nhau bằng dấu phẩy
2. Ưu tiên: tên ngành, mã ngành, năm, loại thông tin (điểm chuẩn, học phí, etc.)
3. Chuẩn hóa viết tắt thành đầy đủ
4. Không thêm từ khóa không có trong câu hỏi gốc
"""

    def __init__(
        self,
        enable_rewrite: bool = True,
        enable_expansion: bool = True,
        enable_keywords: bool = True,
        max_expanded_queries: int = 3,
    ):
        """
        Initialize Query Rewriter.
        
        Args:
            enable_rewrite: Enable query rewriting/clarification
            enable_expansion: Enable multi-query expansion
            enable_keywords: Enable keyword extraction
            max_expanded_queries: Maximum number of expanded queries
        """
        self.enable_rewrite = enable_rewrite
        self.enable_expansion = enable_expansion
        self.enable_keywords = enable_keywords
        self.max_expanded_queries = max_expanded_queries
        
        logger.info(
            f"✅ QueryRewriter initialized "
            f"(rewrite={enable_rewrite}, expand={enable_expansion}, keywords={enable_keywords})"
        )
    
    async def rewrite(self, query: str) -> RewrittenQuery:
        """
        Full query rewriting pipeline.
        Runs rewrite, expansion, and keyword extraction in parallel via asyncio.gather().
        
        Args:
            query: Original user query
            
        Returns:
            RewrittenQuery with all enhancements
        """
        logger.info(f"📝 Rewriting query: {query[:50]}...")
        
        # Initialize result
        result = RewrittenQuery(
            original=query,
            rewritten=query,
            expanded_queries=[],
            extracted_keywords=[],
            detected_intent="general"
        )
        
        try:
            # Build coroutine list for parallel execution
            tasks: Dict[str, Any] = {}
            coros = []
            task_keys = []

            if self.enable_rewrite:
                task_keys.append("rewrite")
                coros.append(self._rewrite_query(query))

            if self.enable_expansion:
                task_keys.append("expand")
                coros.append(self._expand_query(query))

            if self.enable_keywords:
                task_keys.append("keywords")
                coros.append(self._extract_keywords(query))

            # Run all LLM tasks in parallel
            if coros:
                results = await asyncio.gather(*coros, return_exceptions=True)
                for key, res in zip(task_keys, results):
                    tasks[key] = res

            # Process rewrite result
            if "rewrite" in tasks:
                if isinstance(tasks["rewrite"], Exception):
                    logger.warning(f"⚠️ Rewrite task failed: {tasks['rewrite']}")
                else:
                    result.rewritten = tasks["rewrite"]
                    logger.debug(f"   Rewritten: {result.rewritten}")

            # If expansion was run on the original query, and we got a rewrite,
            # the expansion already ran in parallel on the original query which is acceptable.
            if "expand" in tasks:
                if isinstance(tasks["expand"], Exception):
                    logger.warning(f"⚠️ Expand task failed: {tasks['expand']}")
                else:
                    result.expanded_queries = tasks["expand"]
                    logger.debug(f"   Expanded: {len(result.expanded_queries)} queries")

            # Process keywords result
            if "keywords" in tasks:
                if isinstance(tasks["keywords"], Exception):
                    logger.warning(f"⚠️ Keywords task failed: {tasks['keywords']}")
                else:
                    result.extracted_keywords = tasks["keywords"]
                    logger.debug(f"   Keywords: {result.extracted_keywords}")

            # Detect intent (sync, lightweight — no need to parallelize)
            result.detected_intent = self._detect_intent(query)
            
            logger.info(
                f"✅ Query rewritten: '{query[:30]}...' → '{result.rewritten[:30]}...' "
                f"(+{len(result.expanded_queries)} variants, {len(result.extracted_keywords)} keywords)"
            )
            
        except Exception as e:
            logger.error(f"❌ Query rewrite error: {e}")
            # Return original query on error
        
        return result
    
    async def rewrite_simple(self, query: str) -> str:
        """
        Simple query rewriting - just returns the rewritten query.
        
        Args:
            query: Original user query
            
        Returns:
            Rewritten query string
        """
        if not self.enable_rewrite:
            return query
        
        try:
            return await self._rewrite_query(query)
        except Exception as e:
            logger.error(f"❌ Simple rewrite error: {e}")
            return query
    
    async def _rewrite_query(self, query: str) -> str:
        """
        Rewrite query using LLM for clarification and normalization.
        """
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=self.REWRITE_SYSTEM_PROMPT),
            ChatMessage(
                role=MessageRole.USER,
                content=f"Viết lại câu hỏi sau (chỉ trả về câu hỏi đã viết lại, không giải thích):\n\n{query}"
            )
        ]
        
        response = await Settings.llm.achat(messages)
        rewritten = response.message.content.strip()
        
        # Clean up response (remove quotes, extra whitespace)
        rewritten = rewritten.strip('"\'')
        rewritten = ' '.join(rewritten.split())
        
        # Fallback to original if response is empty or too different
        if not rewritten or len(rewritten) < 3:
            return query
        
        return rewritten
    
    async def _expand_query(self, query: str) -> List[str]:
        """
        Generate alternative phrasings of the query.
        """
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=self.EXPAND_SYSTEM_PROMPT),
            ChatMessage(
                role=MessageRole.USER,
                content=f"Câu hỏi gốc: {query}"
            )
        ]
        
        response = await Settings.llm.achat(messages)
        
        # Parse response - each line is a query variant
        expanded = []
        for line in response.message.content.strip().split('\n'):
            line = line.strip()
            # Skip empty lines and numbered items
            if line and not line[0].isdigit():
                # Clean up
                line = line.strip('-•*').strip()
                if line and line != query:
                    expanded.append(line)
        
        return expanded[:self.max_expanded_queries]
    
    async def _extract_keywords(self, query: str) -> List[str]:
        """
        Extract important keywords from query for BM25 boost.
        """
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=self.KEYWORD_SYSTEM_PROMPT),
            ChatMessage(role=MessageRole.USER, content=query)
        ]
        
        response = await Settings.llm.achat(messages)
        
        # Parse comma-separated keywords
        keywords = []
        for kw in response.message.content.split(','):
            kw = kw.strip().lower()
            if kw and len(kw) > 1:
                keywords.append(kw)
        
        return keywords
    
    # Similarity threshold for fuzzy matching (0.0 – 1.0)
    _FUZZY_THRESHOLD = 0.75

    # Pre-compiled regex patterns per intent (word-boundary aware)
    _INTENT_PATTERNS: Dict[str, re.Pattern] = {
        "diem_chuan": re.compile(
            r"\b(điểm\s*chuẩn|diem\s*chuan|điểm\s*trúng\s*tuyển|diem\s*trung\s*tuyen"
            r"|điểm\s*đỗ|diem\s*do|điểm\s*đậu|diem\s*dau|điểm\s*xét\s*tuyển|diem\s*xet\s*tuyen)\b",
            re.IGNORECASE,
        ),
        "hoc_phi": re.compile(
            r"\b(học\s*phí|hoc\s*phi|chi\s*phí|chi\s*phi|tiền\s*học|tien\s*hoc"
            r"|lệ\s*phí|le\s*phi|học\s*bổng|hoc\s*bong|miễn\s*giảm|mien\s*giam)\b",
            re.IGNORECASE,
        ),
        "tuyen_sinh": re.compile(
            r"\b(tuyển\s*sinh|tuyen\s*sinh|xét\s*tuyển|xet\s*tuyen|đăng\s*ký|dang\s*ky"
            r"|nộp\s*hồ\s*sơ|nop\s*ho\s*so|nguyện\s*vọng|nguyen\s*vong|chỉ\s*tiêu|chi\s*tieu)\b",
            re.IGNORECASE,
        ),
        "nganh_hoc": re.compile(
            r"\b(ngành|nganh|chuyên\s*ngành|chuyen\s*nganh|chương\s*trình|chuong\s*trinh"
            r"|đào\s*tạo|dao\s*tao|mã\s*ngành|ma\s*nganh)\b",
            re.IGNORECASE,
        ),
        "quy_che": re.compile(
            r"\b(quy\s*chế|quy\s*che|quy\s*định|quy\s*dinh|điều\s*kiện|dieu\s*kien"
            r"|yêu\s*cầu|yeu\s*cau|tiêu\s*chuẩn|tieu\s*chuan)\b",
            re.IGNORECASE,
        ),
    }

    # Canonical keyword list per intent – used for fuzzy fallback
    _INTENT_KEYWORDS: Dict[str, List[str]] = {
        "diem_chuan": ["điểm chuẩn", "điểm trúng tuyển", "điểm đỗ", "điểm đậu", "điểm xét tuyển"],
        "hoc_phi": ["học phí", "chi phí", "tiền học", "lệ phí", "học bổng", "miễn giảm"],
        "tuyen_sinh": ["tuyển sinh", "xét tuyển", "đăng ký", "nộp hồ sơ", "nguyện vọng", "chỉ tiêu"],
        "nganh_hoc": ["ngành", "chuyên ngành", "chương trình", "đào tạo", "mã ngành"],
        "quy_che": ["quy chế", "quy định", "điều kiện", "yêu cầu", "tiêu chuẩn"],
    }

    def _detect_intent(self, query: str) -> str:
        """
        Intent detection using regex with word boundaries, falling back to
        fuzzy matching (difflib) to handle typos and no-diacritics input.
        """
        # 1. Fast path – regex match (handles exact, no-diacritics, extra spaces)
        for intent, pattern in self._INTENT_PATTERNS.items():
            if pattern.search(query):
                return intent

        # 2. Slow path – fuzzy matching for light typos
        query_lower = query.lower()
        best_intent = "general"
        best_score = 0.0

        for intent, keywords in self._INTENT_KEYWORDS.items():
            for kw in keywords:
                score = SequenceMatcher(None, query_lower, kw.lower()).ratio()
                if score > best_score:
                    best_score = score
                    best_intent = intent

            # Also try matching each word-window of the query against each keyword
            words = query_lower.split()
            for kw in keywords:
                kw_lower = kw.lower()
                kw_word_count = len(kw_lower.split())
                for i in range(len(words) - kw_word_count + 1):
                    window = " ".join(words[i : i + kw_word_count])
                    score = SequenceMatcher(None, window, kw_lower).ratio()
                    if score > best_score:
                        best_score = score
                        best_intent = intent

        if best_score >= self._FUZZY_THRESHOLD:
            return best_intent

        return "general"
    
    async def get_all_queries(self, query: str) -> List[str]:
        """
        Get all query variants for multi-query retrieval.
        
        Returns original + rewritten + expanded queries (deduplicated).
        
        Args:
            query: Original user query
            
        Returns:
            List of unique query variants
        """
        result = await self.rewrite(query)
        
        # Collect all unique queries
        all_queries = [result.original]
        
        if result.rewritten != result.original:
            all_queries.append(result.rewritten)
        
        for expanded in result.expanded_queries:
            if expanded not in all_queries:
                all_queries.append(expanded)
        
        return all_queries


class HyDEQueryExpander: 
    HYDE_SYSTEM_PROMPT = """Bạn là chuyên gia tư vấn tuyển sinh đại học.
    Nhiệm vụ: Viết một đoạn văn ngắn (2-3 câu) trả lời câu hỏi của người dùng như thể bạn đang trích dẫn từ tài liệu chính thức của trường.

    Quy tắc:
    1. Viết như thể đây là thông tin thật từ tài liệu
    2. Sử dụng ngôn ngữ trang trọng, chính thức
    3. Bao gồm các chi tiết cụ thể (số liệu giả định hợp lý nếu cần)
    4. Không viết "Tôi không biết" hay "Xin lỗi"
    """
    
    def __init__(self, enabled: bool = False):
        """
        Initialize HyDE Expander.
        
        Args:
            enabled: Whether HyDE expansion is enabled (disabled by default as it's experimental)
        """
        self.enabled = enabled
        logger.info(f"HyDEQueryExpander initialized (enabled={enabled})")
    
    async def generate_hypothetical_document(self, query: str) -> str:
        """
        Generate a hypothetical document that would answer the query.
        
        Args:
            query: User's question
            
        Returns:
            Hypothetical document text
        """
        if not self.enabled:
            return ""
        
        try:
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=self.HYDE_SYSTEM_PROMPT),
                ChatMessage(role=MessageRole.USER, content=query)
            ]
            
            response = await Settings.llm.achat(messages)
            return response.message.content.strip()
            
        except Exception as e:
            logger.error(f"HyDE generation error: {e}")
            return ""
