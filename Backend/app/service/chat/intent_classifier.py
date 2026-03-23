import re
import logging
from difflib import SequenceMatcher
from typing import Dict, List, Optional
from llama_index.core import Settings
from llama_index.core.llms import ChatMessage, MessageRole

from app.service.prompts import (
    CHITCHAT_KEYWORDS,
    QUERY_INDICATORS,
    SCORE_INDICATORS,
    FEE_INDICATORS,
    CAREER_INDICATORS,
    CHITCHAT_MAX_WORDS,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# LLM classification prompt
# --------------------------------------------------------------------------

INTENT_CLASSIFY_PROMPT = """\
Bạn là bộ phân loại ý định (intent classifier) cho Chatbot tư vấn tuyển sinh Đại học An Giang.

Phân loại câu hỏi của người dùng vào **đúng 1** trong các loại sau:
- QUERY_SCORES — hỏi về điểm chuẩn, điểm trúng tuyển, điểm đầu vào, điểm đỗ
- QUERY_FEES — hỏi về học phí, chi phí, lệ phí, tín chỉ, 
- CAREER_ADVICE — hỏi về cơ hội việc làm, hướng nghiệp, nghề nghiệp, ra trường làm gì
- CHITCHAT — chào hỏi, cảm ơn, tạm biệt, small talk
- QUERY_DOCS — tất cả câu hỏi khác về tuyển sinh, ngành học, quy chế, thông tin chung, học bổng, miễn giảm

Quy tắc:
1. Chỉ trả lời DUY NHẤT 1 từ: QUERY_SCORES hoặc QUERY_FEES hoặc CAREER_ADVICE hoặc CHITCHAT hoặc QUERY_DOCS
2. Không giải thích, không thêm bất kỳ ký tự nào khác
3. Khi câu hỏi mơ hồ, ưu tiên QUERY_DOCS"""

# Canonical keyword list per intent — used for fuzzy fallback
_FUZZY_KEYWORDS: Dict[str, List[str]] = {
    "QUERY_SCORES": ["điểm chuẩn", "điểm trúng tuyển", "điểm đỗ", "điểm đậu", "điểm xét tuyển"],
    "QUERY_FEES": ["học phí", "chi phí", "tiền học", "lệ phí"],
    "CAREER_ADVICE": ["cơ hội việc làm", "hướng nghiệp", "nghề nghiệp", "ra trường", "việc làm"],
    "QUERY_DOCS": [
        "tuyển sinh", "xét tuyển", "đăng ký", "nộp hồ sơ", "nguyện vọng", "chỉ tiêu",
        "ngành", "chuyên ngành", "chương trình", "đào tạo", "mã ngành",
        "quy chế", "quy định", "điều kiện", "yêu cầu",  "học bổng", "miễn giảm"
    ],
}

_FUZZY_THRESHOLD = 0.75

# Map from the fine-grained intent names (used by QueryRewriter/prompt system)
# to the routing intent names used by ChatService.
FINE_TO_ROUTING: Dict[str, str] = {
    "diem_chuan": "QUERY_SCORES",
    "hoc_phi": "QUERY_FEES",
    "tuyen_sinh": "QUERY_DOCS",
    "nganh_hoc": "QUERY_DOCS",
    "quy_che": "QUERY_DOCS",
    "career_advice": "CAREER_ADVICE",
    "general": "QUERY_DOCS",
}

# Reverse: routing intent → fine-grained intent (for prompt selection)
ROUTING_TO_FINE: Dict[str, str] = {
    "QUERY_SCORES": "diem_chuan",
    "QUERY_FEES": "hoc_phi",
    "CAREER_ADVICE": "career_advice",
    "QUERY_DOCS": "general",
    "CHITCHAT": "general",
}

# --------------------------------------------------------------------------
# Valid intents returned by LLM
# --------------------------------------------------------------------------

_VALID_INTENTS = {"CHITCHAT", "QUERY_DOCS", "QUERY_SCORES", "QUERY_FEES", "CAREER_ADVICE"}


class IntentClassifier:
    """Hybrid intent classifier: keyword → regex/fuzzy → LLM fallback."""

    async def classify(self, message: str) -> str:
        keyword_result = self._classify_by_keywords(message)
        if keyword_result is not None:
            logger.info(f"🎯 [IntentClassifier] Phân loại bằng Keywords: {keyword_result}")
            return keyword_result

        # Step 2: Regex + fuzzy matching (instant)
        regex_result = self._classify_by_regex_fuzzy(message)
        if regex_result is not None:
            logger.info(f"🎯 [IntentClassifier] Phân loại bằng Fuzzy/Regex: {regex_result}")
            return regex_result

        # Step 3: LLM fallback (async)
        llm_result = await self._classify_by_llm(message)
        logger.info(f"🎯 [IntentClassifier] Phân loại bởi LLM: {llm_result} cho '{message[:50]}...'")
        return llm_result

    # ------------------------------------------------------------------
    # Step 1: Keyword fast-path
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_by_keywords(message: str) -> Optional[str]:
        message_lower = message.lower().strip()
        words = message_lower.split()
        word_count = len(words)

        # Priority 1: Aggressive Score-specific indicators intercept
        # Prevents queries about scores from falling into standard RAG
        if (
            ("điểm" in message_lower or "diem" in message_lower)
            and any(
                sub in message_lower
                for sub in [
                    "chuẩn", "trúng", "đậu", "đỗ", "xét", "đầu vào", "thi", "đánh giá", "năng lực",
                    "chuan", "trung", "dau", "xet", "dau vao", "danh gia", "nang luc",
                    "cntt", "ktpm", "bao nhiêu", "bao nhieu",
                ]
            )
        ):
            return "QUERY_SCORES"
            
        for indicator in SCORE_INDICATORS:
            if indicator in message_lower:
                return "QUERY_SCORES"

        # Priority 2: Fee-specific indicators
        # Exception: "dự kiến" → force QUERY_DOCS (RAG) vì dữ liệu CSV chỉ có số chính thức
        if "dự kiến" not in message_lower:
            for indicator in FEE_INDICATORS:
                if indicator in message_lower:
                    return "QUERY_FEES"

        # Priority 3: Career advice indicators
        for indicator in CAREER_INDICATORS:
            if indicator in message_lower:
                return "CAREER_ADVICE"

        # Priority 4: General query indicators
        for indicator in QUERY_INDICATORS:
            if indicator in message_lower:
                return "QUERY_DOCS"

        # Priority 5: Long messages are typically queries
        if word_count > CHITCHAT_MAX_WORDS:
            return "QUERY_DOCS"

        # Priority 6: Chitchat for short messages with chitchat keywords
        for keyword in CHITCHAT_KEYWORDS:
            pattern = rf'\b{re.escape(keyword)}\b'
            if re.search(pattern, message_lower):
                return "CHITCHAT"

        # No confident match — return None to trigger next step
        return None

    # ------------------------------------------------------------------
    # Step 2: Regex + fuzzy matching
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_by_regex_fuzzy(message: str) -> Optional[str]:
        message_lower = message.lower()

        # 2b. Fuzzy matching for light typos
        best_intent = None
        best_score = 0.0

        for intent, keywords in _FUZZY_KEYWORDS.items():
            for kw in keywords:
                score = SequenceMatcher(None, message_lower, kw.lower()).ratio()
                if score > best_score:
                    best_score = score
                    best_intent = intent

            # Also try matching each word-window of the query against each keyword
            words = message_lower.split()
            for kw in keywords:
                kw_lower = kw.lower()
                kw_word_count = len(kw_lower.split())
                for i in range(len(words) - kw_word_count + 1):
                    window = " ".join(words[i: i + kw_word_count])
                    score = SequenceMatcher(None, window, kw_lower).ratio()
                    if score > best_score:
                        best_score = score
                        best_intent = intent

        if best_score >= _FUZZY_THRESHOLD and best_intent is not None:
            return best_intent

        return None

    # ------------------------------------------------------------------
    # Step 3: LLM fallback
    # ------------------------------------------------------------------

    @staticmethod
    async def _classify_by_llm(message: str) -> str:
        try:
            if Settings.llm is None:
                logger.warning("LLM not available for intent classification, defaulting to QUERY_DOCS")
                return "QUERY_DOCS"

            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=INTENT_CLASSIFY_PROMPT),
                ChatMessage(role=MessageRole.USER, content=message),
            ]

            response = await Settings.llm.achat(messages)
            raw = response.message.content.strip().upper()

            # Parse — the LLM should return exactly one of the valid intents
            if raw in _VALID_INTENTS:
                return raw

            # Try to extract a valid intent from a longer response
            for valid in _VALID_INTENTS:
                if valid in raw:
                    return valid

            logger.warning(f"LLM returned unexpected intent: '{raw}', defaulting to QUERY_DOCS")
            return "QUERY_DOCS"

        except Exception as e:
            logger.warning(f"LLM intent classification failed: {e}, defaulting to QUERY_DOCS")
            return "QUERY_DOCS"

    # ------------------------------------------------------------------
    # Utility: get fine-grained intent for prompt selection
    # ------------------------------------------------------------------

    @staticmethod
    def get_fine_intent(routing_intent: str) -> str:
        return ROUTING_TO_FINE.get(routing_intent, "general")

    # ------------------------------------------------------------------
    # Future year check (unchanged)
    # ------------------------------------------------------------------

    @staticmethod
    def check_future_year(
        message: str,
        intent: str,
        latest_diem_chuan_year: int | None,
        latest_hoc_phi_year: int | None,
    ) -> str | None:
        years_mentioned = re.findall(r'\b(20[2-9][0-9])\b', message)
        if not years_mentioned:
            return None

        if intent == "QUERY_SCORES" and latest_diem_chuan_year:
            for y in years_mentioned:
                if int(y) > latest_diem_chuan_year:
                    return (
                        f"Hiện tại trường Đại học An Giang chưa công bố dữ liệu điểm chuẩn "
                        f"của năm {y}. Bạn có muốn tham khảo thông tin điểm chuẩn "
                        f"của năm gần nhất là {latest_diem_chuan_year} không?"
                    )

        if intent == "QUERY_FEES" and latest_hoc_phi_year:
            for y in years_mentioned:
                if int(y) > latest_hoc_phi_year:
                    return (
                        f"Hiện tại trường Đại học An Giang chưa công bố dữ liệu học phí "
                        f"của năm {y}. Bạn có muốn tham khảo thông tin học phí "
                        f"của năm gần nhất là {latest_hoc_phi_year} không?"
                    )

        return None
