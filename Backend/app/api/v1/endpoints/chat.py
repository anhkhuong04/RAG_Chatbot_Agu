"""
Chat API Endpoints
"""
import json
import uuid
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Import ChatService (from refactored package)
from app.service.chat import ChatService
from app.service.chat.intent_classifier import IntentClassifier

router = APIRouter(prefix="/chat", tags=["Chat"])

# ============================================
# PYDANTIC MODELS
# ============================================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None

    def get_session_id(self) -> Optional[str]:
        """Return session_id or conversation_id (frontend compat)"""
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
    """Get ChatService singleton instance"""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service


# ============================================
# ENDPOINTS
# ============================================


async def _sse_generator(chat_service: ChatService, session_id: str, message: str):
    """
    SSE event generator. Wraps the ChatService stream into SSE format.
    
    Event types:
    - "token": a text chunk from the LLM
    - "sources": JSON array of source strings (sent once after retrieval)
    - "metadata": session info and detected intent
    - "done": signals stream completion
    - "error": signals an error
    """
    try:
        # Detect intent before streaming
        intent = chat_service._intent_classifier.classify(message)
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

        elif intent == "QUERY_SCORES":
            # Pandas route: sources are sent after streaming
            sources = ["Truy xuất từ Bảng điểm chuẩn"]
            sources_json = json.dumps(sources, ensure_ascii=False)
            yield f"event: sources\ndata: {sources_json}\n\n"

        elif intent == "QUERY_FEES":
            # Pandas route: sources are sent after streaming
            sources = ["Truy xuất từ Bảng học phí"]
            sources_json = json.dumps(sources, ensure_ascii=False)
            yield f"event: sources\ndata: {sources_json}\n\n"

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
        yield f"event: done\ndata: [DONE]\n\n"

    except Exception as e:
        error_json = json.dumps({"error": str(e)}, ensure_ascii=False)
        yield f"event: error\ndata: {error_json}\n\n"


@router.post("/stream")
@router.post("/stream/")
async def chat_stream(request: ChatRequest):
    """
    Stream a chat response using Server-Sent Events (SSE).
    
    - **message**: User's question
    - **session_id**: Optional ID to continue existing conversation
    
    Returns SSE stream with events: metadata, sources, token, done, error
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    chat_service = get_chat_service()
    session_id = request.get_session_id() or str(uuid.uuid4())

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
    """
    Send a message to the chatbot and get a RAG-based response.
    
    - **message**: User's question
    - **conversation_id**: Optional ID to continue existing conversation
    
    Returns:
    - **response**: AI-generated answer based on knowledge base
    - **sources**: List of source documents used
    - **conversation_id**: ID for continuing the conversation
    """
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
        
        result = await chat_service.process_message(
            session_id=session_id,
            message=request.message.strip()
        )
        
        return ChatResponse(
            response=result["response"],
            sources=result.get("sources", []),
            session_id=session_id,
            intent=result.get("intent", "UNKNOWN")
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"message": f"Error processing chat: {str(e)}"}
        )


@router.post("/reset", response_model=ResetResponse)
async def reset_conversation(session_id: str):
    """
    Reset/delete a chat session.
    
    - **session_id**: ID of the session to reset
    """
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


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """
    Get chat session history by ID.
    
    - **session_id**: ID of the session
    """
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
