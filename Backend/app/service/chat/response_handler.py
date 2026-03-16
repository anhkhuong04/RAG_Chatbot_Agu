"""
Response Handler module.

Handles LLM response generation for different intent types:
  - Chitchat (sync + stream)
  - Career advice (sync + stream)
  - RAG synthesis (sync + stream)
  - Source extraction

Extracted from ChatService chitchat/career/synthesis methods.
"""
import asyncio
import logging
import traceback
from typing import List, AsyncGenerator

from llama_index.core import Settings
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.schema import NodeWithScore

from app.service.prompts import CHITCHAT_SYSTEM_PROMPT, RAG_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ResponseHandler:
    """Handles LLM response generation for all intent types."""

    def __init__(self, get_intent_prompt_fn):
        self._get_intent_prompt = get_intent_prompt_fn

    # ------------------------------------------------------------------
    # Chitchat
    # ------------------------------------------------------------------

    async def handle_chitchat(self, history: List[ChatMessage], message: str) -> str:
        try:
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=CHITCHAT_SYSTEM_PROMPT)
            ]
            messages.extend(history)
            messages.append(ChatMessage(role=MessageRole.USER, content=message))

            response = await Settings.llm.achat(messages)
            return response.message.content

        except Exception as e:
            logger.error(f"Chitchat error: {e}")
            return (
                "Xin chào! Tôi là Trợ lý Tuyển sinh. "
                "Tôi có thể giúp gì cho bạn về thông tin tuyển sinh, điểm chuẩn, học phí?"
            )

    async def handle_chitchat_stream(
        self, history: List[ChatMessage], message: str
    ) -> AsyncGenerator[str, None]:
        try:
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=CHITCHAT_SYSTEM_PROMPT)
            ]
            messages.extend(history)
            messages.append(ChatMessage(role=MessageRole.USER, content=message))

            response = await Settings.llm.astream_chat(messages)
            async for chunk in response:
                if hasattr(chunk, "delta") and chunk.delta:
                    yield chunk.delta

        except Exception as e:
            logger.error(f"Chitchat stream error: {e}")
            yield "Xin chào! Tôi là Trợ lý Tuyển sinh. Tôi có thể giúp gì cho bạn?"

    # ------------------------------------------------------------------
    # Career advice
    # ------------------------------------------------------------------

    async def handle_career_advice(
        self, history: List[ChatMessage], message: str
    ) -> str:
        try:
            career_prompt = self._get_intent_prompt("career_advice")
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=career_prompt),
            ]
            messages.extend(history)
            messages.append(ChatMessage(role=MessageRole.USER, content=message))

            response = await Settings.llm.achat(messages)
            return response.message.content

        except Exception as e:
            logger.error(f"Career advice error: {e}")
            return (
                "Xin lỗi, tôi chưa thể tư vấn hướng nghiệp lúc này. "
                "Vui lòng thử lại sau hoặc liên hệ Khoa CNTT - ĐH An Giang."
            )

    async def handle_career_advice_stream(
        self, history: List[ChatMessage], message: str
    ) -> AsyncGenerator[str, None]:
        try:
            career_prompt = self._get_intent_prompt("career_advice")
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=career_prompt),
            ]
            messages.extend(history)
            messages.append(ChatMessage(role=MessageRole.USER, content=message))

            response = await Settings.llm.astream_chat(messages)
            async for chunk in response:
                if hasattr(chunk, "delta") and chunk.delta:
                    yield chunk.delta

        except Exception as e:
            logger.error(f"Career advice stream error: {e}")
            yield (
                "Xin lỗi, tôi chưa thể tư vấn hướng nghiệp lúc này. "
                "Vui lòng thử lại sau hoặc liên hệ Khoa CNTT - ĐH An Giang."
            )

    # ------------------------------------------------------------------
    # RAG response synthesis
    # ------------------------------------------------------------------

    async def synthesize_response(
        self,
        query: str,
        nodes: List[NodeWithScore],
        intent: str = "general",
    ) -> str:
        try:
            if Settings.llm is None:
                logger.error("LLM not initialized in Settings")
                return "Xin lỗi, hệ thống LLM chưa được khởi tạo. Vui lòng thử lại sau."

            context = self._build_context(nodes)
            if not context:
                return "Không thể trích xuất thông tin từ cơ sở dữ liệu. Vui lòng thử lại."

            intent_prompt = self._get_intent_prompt(intent)
            prompt = f"""{RAG_SYSTEM_PROMPT}
{intent_prompt}
## Ngữ cảnh (Context):
{context}

## Câu hỏi của người dùng:
{query}

## Trả lời:"""

            messages = [ChatMessage(role=MessageRole.USER, content=prompt)]

            try:
                if hasattr(Settings.llm, "achat"):
                    response = await Settings.llm.achat(messages)
                else:
                    logger.info("Using sync chat (achat not available)")
                    response = await asyncio.to_thread(Settings.llm.chat, messages)
            except AttributeError as attr_err:
                logger.warning(f"achat not available, using sync: {attr_err}")
                response = await asyncio.to_thread(Settings.llm.chat, messages)

            if hasattr(response, "message") and hasattr(response.message, "content"):
                return response.message.content
            elif hasattr(response, "content"):
                return response.content
            else:
                logger.error(f"Unexpected response format: {type(response)}")
                return str(response)

        except Exception as e:
            error_details = traceback.format_exc()
            logger.error(f"Response synthesis error: {e}\n{error_details}")
            return "Xin lỗi, đã có lỗi khi tổng hợp câu trả lời. Vui lòng thử lại."

    async def synthesize_response_stream(
        self,
        query: str,
        nodes: List[NodeWithScore],
        intent: str = "general",
    ) -> AsyncGenerator[str, None]:
        try:
            if Settings.llm is None:
                yield "Xin lỗi, hệ thống LLM chưa được khởi tạo."
                return

            context = self._build_context(nodes)
            if not context:
                yield "Không thể trích xuất thông tin từ cơ sở dữ liệu."
                return

            intent_prompt = self._get_intent_prompt(intent)
            prompt = f"""{RAG_SYSTEM_PROMPT}
            {intent_prompt}
            ## Ngữ cảnh (Context):
            {context}

            ## Câu hỏi của người dùng:
            {query}

            ## Trả lời:"""

            messages = [ChatMessage(role=MessageRole.USER, content=prompt)]

            response = await Settings.llm.astream_chat(messages)
            async for chunk in response:
                if hasattr(chunk, "delta") and chunk.delta:
                    yield chunk.delta

        except Exception as e:
            logger.error(f"Response stream synthesis error: {e}")
            yield "Xin lỗi, đã có lỗi khi tổng hợp câu trả lời."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context(nodes: List[NodeWithScore]) -> str | None:
        context_parts = []
        for i, node in enumerate(nodes, 1):
            try:
                node_text = node.node.get_content()
                metadata = node.node.metadata or {}
                source = metadata.get("filename", metadata.get("file_name", "Unknown"))
                year = metadata.get("year", "")

                context_header = f"[Nguồn {i}: {source}"
                if year:
                    context_header += f" - Năm {year}"
                context_header += "]"
                context_parts.append(f"{context_header}\n{node_text}")
            except Exception as node_err:
                logger.warning(f"Error extracting node {i} content: {node_err}")
                continue

        if not context_parts:
            logger.warning("No valid context parts extracted from nodes")
            return None

        return "\n\n---\n\n".join(context_parts)

    @staticmethod
    def extract_sources(nodes: List[NodeWithScore]) -> List[str]:
        sources = []
        for node in nodes:
            metadata = node.node.metadata if hasattr(node.node, "metadata") else {}
            filename = metadata.get("file_name", metadata.get("filename", "Unknown"))
            page = metadata.get("page_label", metadata.get("page", ""))
            year = metadata.get("year", "")

            source_str = filename
            if year:
                source_str += f" ({year})"
            if page:
                source_str += f" - trang {page}"

            if source_str not in sources:
                sources.append(source_str)

        return sources
