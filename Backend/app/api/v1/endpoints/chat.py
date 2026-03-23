import json
import uuid
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Import ChatService (from refactored package)
from app.service.chat import ChatService

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)

# ============================================
# PYDANTIC MODELS
# ============================================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None

    def get_session_id(self) -> Optional[str]:
        return self.session_id or self.conversation_id


class SourceInfo(BaseModel):
    content: str
    score: Optional[float] = None
    metadata: Optional[dict] = None


class ChatResponse(BaseModel):
    response: str
    sources: List[str] = []
    session_id: str
    intent: str


class ResetResponse(BaseModel):
    success: bool
    message: str
    conversation_id: str


# ============================================
# DEPENDENCIES
# ============================================

# Singleton instance
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service


# ============================================
# ENDPOINTS
# ============================================


async def _sse_generator(chat_service: ChatService, session_id: str, message: str):
    try:
        logger.info(
            f"[CHAT_STREAM] Start session={session_id} message_len={len(message)}"
        )
        # Detect intent before streaming
        intent = await chat_service._intent_classifier.classify(message)
        logger.info(f"[CHAT_STREAM] Intent detected: {intent} | session={session_id}")
        sources: List[str] = []

        # Send metadata (session_id, intent) as the first event
        meta = json.dumps({
            "session_id": session_id,
            "intent": intent,
        }, ensure_ascii=False)
        yield f"event: metadata\ndata: {meta}\n\n"

        # Route based on intent
        if intent == "QUERY_DOCS":
            # Standard RAG: load history, resolve coreferences, retrieve, send sources
            history = chat_service._history_manager.load_history(session_id, limit=5)
            resolved_msg = await chat_service._coreference.resolve(message, history)
            nodes, sources = await chat_service._retrieve_and_rerank(resolved_msg)
            if sources:
                sources_json = json.dumps(sources, ensure_ascii=False)
                yield f"event: sources\ndata: {sources_json}\n\n"

        elif intent in {"QUERY_SCORES", "QUERY_FEES"}:
            # Sources for score/fee are emitted only when grounded retrieval succeeds
            # inside the main processing pipeline.
            pass

        elif intent == "CAREER_ADVICE":
            # Career advice: LLM base knowledge, no Qdrant retrieval
            sources = ["Tư vấn từ chuyên gia AI - Khoa CNTT"]
            sources_json = json.dumps(sources, ensure_ascii=False)
            yield f"event: sources\ndata: {sources_json}\n\n"

        # Stream token chunks (process_message_stream handles all routing internally)
        async for chunk in chat_service.process_message_stream(session_id, message):
            # Escape newlines for SSE data field
            escaped = chunk.replace("\n", "\ndata: ")
            yield f"event: token\ndata: {escaped}\n\n"

        # Signal completion
        logger.info(f"[CHAT_STREAM] Completed session={session_id}")
        yield f"event: done\ndata: [DONE]\n\n"

    except Exception as e:
        logger.exception(f"[CHAT_STREAM] Failed session={session_id}: {e}")
        error_json = json.dumps({"error": str(e)}, ensure_ascii=False)
        yield f"event: error\ndata: {error_json}\n\n"


@router.post("/stream")
@router.post("/stream/")
async def chat_stream(request: ChatRequest):
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    chat_service = get_chat_service()
    session_id = request.get_session_id() or str(uuid.uuid4())
    logger.info(f"[CHAT_STREAM] Incoming request session={session_id}")

    return StreamingResponse(
        _sse_generator(chat_service, session_id, request.message.strip()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post("", response_model=ChatResponse)
@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.message or not request.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )
    
    try:
        import uuid
        chat_service = get_chat_service()
        
        # Generate session_id if not provided
        session_id = request.get_session_id() or str(uuid.uuid4())
        logger.info(f"[CHAT] Incoming request session={session_id}")
        
        result = await chat_service.process_message(
            session_id=session_id,
            message=request.message.strip()
        )
        logger.info(
            f"[CHAT] Completed session={session_id} intent={result.get('intent', 'UNKNOWN')}"
        )
        
        return ChatResponse(
            response=result["response"],
            sources=result.get("sources", []),
            session_id=session_id,
            intent=result.get("intent", "UNKNOWN")
        )
        
    except Exception as e:
        logger.exception(f"[CHAT] Failed request: {e}")
        raise HTTPException(
            status_code=500,
            detail={"message": f"Error processing chat: {str(e)}"}
        )


@router.post("/reset", response_model=ResetResponse)
async def reset_conversation(session_id: str):
    try:
        chat_service = get_chat_service()
        success = chat_service.clear_session(session_id)
        
        return ResetResponse(
            success=success,
            message="Session cleared successfully" if success else "Session not found",
            conversation_id=session_id
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error resetting conversation: {str(e)}"
        )


@router.delete("/{session_id}", response_model=ResetResponse)
@router.delete("/{session_id}/", response_model=ResetResponse)
async def delete_conversation(session_id: str):
    try:
        chat_service = get_chat_service()
        success = chat_service.clear_session(session_id)

        return ResetResponse(
            success=success,
            message="Session deleted successfully" if success else "Session not found",
            conversation_id=session_id,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting conversation: {str(e)}"
        )


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    try:
        chat_service = get_chat_service()
        messages = chat_service.get_session_history(session_id)
        
        return {
            "session_id": session_id,
            "messages": messages
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting history: {str(e)}"
        )
