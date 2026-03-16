import logging
from typing import List

from llama_index.core import Settings
from llama_index.core.llms import ChatMessage, MessageRole

logger = logging.getLogger(__name__)

# Indicators that suggest the message may contain unresolved references
COREFERENCE_INDICATORS = [
    "này", "đó", "trên", "kia", "ấy",
    "nó", "chúng", "họ",
    "2 ngành", "hai ngành", "các ngành",
    "ngành đó", "ngành này", "trường đó", "trường này",
    "mấy ngành", "những ngành",
]

RESOLVE_SYSTEM_PROMPT = (
    "Bạn là chuyên gia xử lý ngôn ngữ tự nhiên.\n"
    "Nhiệm vụ: Viết lại câu hỏi hiện tại thành câu hỏi ĐỘC LẬP, TỰ ĐẦY ĐỦ ngữ cảnh.\n\n"
    "Quy tắc:\n"
    "1. Thay thế đại từ chỉ thị (này, đó, ấy, kia) bằng thực thể cụ thể từ lịch sử hội thoại\n"
    "2. Giữ nguyên ý nghĩa và intent của câu hỏi gốc\n"
    "3. Nếu câu hỏi đã đủ rõ ràng, trả về nguyên văn\n"
    "3.1 KHÔNG tự thêm ngành mới nếu lịch sử hội thoại không nêu\n"
    "4. CHỈ trả về câu hỏi đã viết lại, KHÔNG giải thích\n\n"
    "Ví dụ:\n"
    "Lịch sử: User hỏi về ngành Kế toán và Quản trị kinh doanh\n"
    "Câu hỏi: 'điểm chuẩn 2 ngành này năm trước'\n"
    "→ 'điểm chuẩn ngành Kế toán và Quản trị kinh doanh năm trước'"
)


class CoreferenceResolver:
    """Resolves coreferences in user messages using LLM + chat history."""

    async def resolve(self, message: str, history: List[ChatMessage]) -> str:
        if not history:
            return message

        # Quick check: skip if message likely has no unresolved references
        message_lower = message.lower()
        has_coreference = any(ind in message_lower for ind in COREFERENCE_INDICATORS)
        if not has_coreference:
            return message

        try:
            # Build conversation context from history
            history_text = ""
            for msg in history[-6:]:  # Last 6 messages (3 turns)
                role_label = "User" if msg.role == MessageRole.USER else "Bot"
                history_text += f"{role_label}: {msg.content}\n"

            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=RESOLVE_SYSTEM_PROMPT),
                ChatMessage(
                    role=MessageRole.USER,
                    content=(
                        f"Lịch sử hội thoại gần đây:\n{history_text}\n"
                        f"Câu hỏi hiện tại: {message}\n\n"
                        f"Viết lại câu hỏi (chỉ trả về câu hỏi đã viết lại):"
                    ),
                ),
            ]

            response = await Settings.llm.achat(messages)
            resolved = response.message.content.strip().strip("\"'")
            resolved = " ".join(resolved.split())

            if resolved and len(resolved) >= 3:
                logger.info(f"🔗 Coreference resolved: '{message}' → '{resolved}'")
                return resolved

            return message

        except Exception as e:
            logger.warning(f"Coreference resolution failed: {e}")
            return message
