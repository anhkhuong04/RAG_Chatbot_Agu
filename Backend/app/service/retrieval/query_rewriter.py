import asyncio
import logging
from typing import List, Any
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
2. Chuẩn hóa thuật ngữ nếu người dùng đã nêu rõ (VD: "CNTT" → "Công nghệ thông tin")
3. Thêm context nếu câu hỏi mơ hồ
4. Loại bỏ từ thừa, giữ keywords quan trọng
5. Nếu có năm cụ thể, giữ nguyên năm đó
6. Nếu không có năm, KHÔNG thêm năm vào
7. KHÔNG tự thêm ngành cụ thể nếu câu gốc không nêu ngành (đặc biệt không tự chèn "Công nghệ thông tin"/"CNTT")
8. Với câu hỏi chính sách chung của trường (học bổng, miễn giảm, quy chế, điều kiện), giữ phạm vi toàn trường, không thu hẹp về 1 ngành

Ví dụ:
- "điểm cntt" → "Điểm chuẩn ngành Công nghệ thông tin"
- "học phí bao nhiêu" → "Mức học phí các ngành đào tạo"
- "đăng ký xét tuyển như nào" → "Quy trình đăng ký xét tuyển đại học"
- "học bổng có không" → "Chính sách học bổng tuyển sinh của trường"
"""

    # Prevent rewrite from injecting specific major when original query is generic.
    _CNTT_TERMS = [
        "cntt",
        "công nghệ thông tin",
        "cong nghe thong tin",
        "it",
    ]

    _GENERAL_POLICY_TERMS = [
        "học bổng",
        "hoc bong",
        "miễn giảm",
        "mien giam",
        "quy chế",
        "quy che",
        "quy định",
        "quy dinh",
        "điều kiện",
        "dieu kien",
        "tuyển sinh",
        "tuyen sinh",
    ]

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
        enable_hyde: bool = False,
    ):
        self.enable_rewrite = enable_rewrite
        self.enable_expansion = enable_expansion
        self.enable_keywords = enable_keywords
        self.max_expanded_queries = max_expanded_queries
        self._hyde_expander = HyDEQueryExpander(enabled=enable_hyde)
        
        logger.info(
            f"QueryRewriter initialized "
            f"(rewrite={enable_rewrite}, expand={enable_expansion}, "
            f"keywords={enable_keywords}, hyde={enable_hyde})"
        )
    
    async def rewrite(self, query: str) -> RewrittenQuery:
        logger.info(f"Rewriting query: {query[:50]}...")
        
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
            tasks: dict[str, Any] = {}
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

            if self._hyde_expander.enabled:
                task_keys.append("hyde")
                coros.append(self._hyde_expander.generate_hypothetical_document(query))

            # Run all LLM tasks in parallel
            if coros:
                results = await asyncio.gather(*coros, return_exceptions=True)
                for key, res in zip(task_keys, results):
                    tasks[key] = res

            # Process rewrite result
            if "rewrite" in tasks:
                if isinstance(tasks["rewrite"], Exception):
                    logger.warning(f"Rewrite task failed: {tasks['rewrite']}")
                else:
                    result.rewritten = tasks["rewrite"]
                    logger.debug(f"   Rewritten: {result.rewritten}")

            # If expansion was run on the original query, and we got a rewrite,
            # the expansion already ran in parallel on the original query which is acceptable.
            if "expand" in tasks:
                if isinstance(tasks["expand"], Exception):
                    logger.warning(f"Expand task failed: {tasks['expand']}")
                else:
                    result.expanded_queries = tasks["expand"]
                    logger.debug(f"   Expanded: {len(result.expanded_queries)} queries")

            # Process keywords result
            if "keywords" in tasks:
                if isinstance(tasks["keywords"], Exception):
                    logger.warning(f"Keywords task failed: {tasks['keywords']}")
                else:
                    result.extracted_keywords = tasks["keywords"]
                    logger.debug(f"   Keywords: {result.extracted_keywords}")

            # Process HyDE result — append hypothetical doc as extra query variant
            if "hyde" in tasks:
                if isinstance(tasks["hyde"], Exception):
                    logger.warning(f"HyDE task failed: {tasks['hyde']}")
                elif tasks["hyde"]:
                    hyde_doc = tasks["hyde"]
                    result.expanded_queries.append(hyde_doc)
                    logger.debug(f"   HyDE doc appended ({len(hyde_doc)} chars)")
            
            logger.info(
                f"Query rewritten: '{query[:30]}...' → '{result.rewritten[:30]}...' "
                f"(+{len(result.expanded_queries)} variants, {len(result.extracted_keywords)} keywords)"
            )
            log_msg = f"\n[QueryRewriter]\n   ↳ Gốc     : '{query}'\n   ↳ Viết lại: '{result.rewritten}'"
            if result.expanded_queries:
                log_msg += f"\n   ↳ Mở rộng : {result.expanded_queries}"
            logger.info(log_msg)
            
        except Exception as e:
            logger.error(f"Query rewrite error: {e}")
            # Return original query on error
        
        return result
    
    async def _rewrite_query(self, query: str) -> str:
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

        # Guardrail: do not allow overly-specific major injection for generic questions.
        if self._is_over_specific_rewrite(query, rewritten):
            logger.info("Rewrite guard triggered: keeping original query to avoid major overfitting")
            return query
        
        return rewritten

    @staticmethod
    def _contains_any(text: str, terms: List[str]) -> bool:
        return any(term in text for term in terms)

    def _is_over_specific_rewrite(self, original: str, rewritten: str) -> bool:
        o = original.lower()
        r = rewritten.lower()

        original_has_cntt = self._contains_any(o, self._CNTT_TERMS)
        rewritten_has_cntt = self._contains_any(r, self._CNTT_TERMS)
        original_is_general_policy = self._contains_any(o, self._GENERAL_POLICY_TERMS)

        return (not original_has_cntt) and rewritten_has_cntt and original_is_general_policy
    
    async def _expand_query(self, query: str) -> List[str]:
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
        self.enabled = enabled
        logger.info(f"HyDEQueryExpander initialized (enabled={enabled})")
    
    async def generate_hypothetical_document(self, query: str) -> str:
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
