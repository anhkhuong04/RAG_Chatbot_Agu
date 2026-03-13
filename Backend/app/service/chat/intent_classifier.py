"""
Intent Classification module.

Classifies user messages into one of:
  CHITCHAT, QUERY_DOCS, QUERY_SCORES, QUERY_FEES, CAREER_ADVICE

Extracted from ChatService._classify_intent and ChatService._check_future_year_query.
"""
import re
import logging

from app.service.prompts import (
    CHITCHAT_KEYWORDS,
    QUERY_INDICATORS,
    SCORE_INDICATORS,
    FEE_INDICATORS,
    CAREER_INDICATORS,
    CHITCHAT_MAX_WORDS,
)

logger = logging.getLogger(__name__)


class IntentClassifier:
    """Stateless intent classifier using keyword / indicator matching."""

    def classify(self, message: str) -> str:
        """
        Classify user message intent using multi-factor analysis.

        Priority (highest first):
        1. Score-specific indicators → QUERY_SCORES
        2. Fee-specific indicators → QUERY_FEES
        3. Career advice indicators → CAREER_ADVICE
        4. General query indicators → QUERY_DOCS
        5. Message length (long = QUERY_DOCS)
        6. Chitchat keywords (short msgs only) → CHITCHAT
        7. Default → QUERY_DOCS

        Args:
            message: User's message

        Returns:
            One of: "CHITCHAT", "QUERY_DOCS", "QUERY_SCORES", "QUERY_FEES", "CAREER_ADVICE"
        """
        message_lower = message.lower().strip()
        words = message_lower.split()
        word_count = len(words)

        # Priority 1: Check for SCORE-specific indicators
        for indicator in SCORE_INDICATORS:
            if indicator in message_lower:
                logger.debug(f"Score indicator found: '{indicator}' → QUERY_SCORES")
                return "QUERY_SCORES"

        # Priority 2: Check for FEE-specific indicators
        # Exception: "dự kiến" → force QUERY_DOCS (RAG) vì dữ liệu CSV chỉ có số chính thức
        if "dự kiến" not in message_lower:
            for indicator in FEE_INDICATORS:
                if indicator in message_lower:
                    logger.debug(f"Fee indicator found: '{indicator}' → QUERY_FEES")
                    return "QUERY_FEES"

        # Priority 3: Check for CAREER_ADVICE indicators
        for indicator in CAREER_INDICATORS:
            if indicator in message_lower:
                logger.debug(f"Career indicator found: '{indicator}' → CAREER_ADVICE")
                return "CAREER_ADVICE"

        # Priority 4: Check for general query indicators
        for indicator in QUERY_INDICATORS:
            if indicator in message_lower:
                logger.debug(f"Query indicator found: '{indicator}' → QUERY_DOCS")
                return "QUERY_DOCS"

        # Priority 5: Long messages are typically queries
        if word_count > CHITCHAT_MAX_WORDS:
            return "QUERY_DOCS"

        # Priority 6: Only classify as CHITCHAT if message is short AND has chitchat keyword
        for keyword in CHITCHAT_KEYWORDS:
            pattern = rf'\b{re.escape(keyword)}\b'
            if re.search(pattern, message_lower):
                logger.debug(f"Chitchat keyword found: '{keyword}' (words={word_count}) → CHITCHAT")
                return "CHITCHAT"

        # Default: treat as knowledge query
        return "QUERY_DOCS"

    @staticmethod
    def check_future_year(
        message: str,
        intent: str,
        latest_diem_chuan_year: int | None,
        latest_hoc_phi_year: int | None,
    ) -> str | None:
        """
        Check if user is asking about a year that has no data yet.
        Returns a polite correction message if so, otherwise None.
        """
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
