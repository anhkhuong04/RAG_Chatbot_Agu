from fastapi import APIRouter, HTTPException, status
from app.schemas.chat import (
    ChatRequest, 
    ChatResponse, 
    ResetConversationRequest,
    ResetConversationResponse,
    ConversationInfo,
    ErrorResponse
)
from app.core.engine import chat_with_session, get_engine_factory
from app.core.session import get_session_manager
from app.core.exceptions import (
    RAGChatbotError,
    SessionNotFoundError,
    EmptyQueryError
)
from app.core.logger import get_logger, LogContext, RequestLogger
from app.core.metrics import track_rag_operation
from typing import List
import time

router = APIRouter()
logger = get_logger(__name__)
req_logger = RequestLogger(logger)


# Initialize engine factory on startup (loads vector store once)
@router.on_event("startup")
async def startup_event():
    """Pre-initialize engine factory"""
    try:
        logger.info("Pre-initializing engine factory...")
        get_engine_factory()
        logger.info("Engine factory initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize engine factory: {e}")


@router.post(
    "/chat", 
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"}
    }
)
async def chat(request: ChatRequest):
    """
    Chat endpoint với session management
    
    - Nếu không có conversation_id: tạo session mới
    - Nếu có conversation_id: tiếp tục cuộc hội thoại cũ
    """
    start_time = time.time()
    
    with LogContext(logger, "chat_endpoint", 
                   message=request.message,
                   conversation_id=request.conversation_id):
        try:
            # Validate message
            if not request.message or not request.message.strip():
                raise EmptyQueryError()
            
            # Chat with session management
            response, conversation_id, source_nodes = chat_with_session(
                message=request.message,
                conversation_id=request.conversation_id
            )
            
            # Extract sources
            source_texts = []
            for node in source_nodes:
                file_name = node.metadata.get("file_name", "Tài liệu không tên")
                category = node.metadata.get("category", "Chung")
                source_texts.append(f"{file_name} ({category})")
            
            # Remove duplicates
            source_texts = list(set(source_texts))
            
            # Track metrics
            duration_ms = (time.time() - start_time) * 1000
            track_rag_operation(
                "api_endpoint", 
                duration_ms,
                endpoint="/chat",
                num_sources=len(source_texts),
                conversation_id=conversation_id
            )
            
            logger.info(
                "Chat request completed",
                context={
                    "duration_ms": round(duration_ms, 2),
                    "num_sources": len(source_texts),
                    "conversation_id": conversation_id
                }
            )

            return ChatResponse(
                response=str(response),
                sources=source_texts,
                conversation_id=conversation_id
            )
            
        except RAGChatbotError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.warning(
                "Chat request failed with known error",
                context={
                    "error_code": e.error_code,
                    "message": e.message,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.to_dict()
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Chat request failed",
                context={
                    "error": str(e),
                    "duration_ms": round(duration_ms, 2)
                }
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error_code": "INTERNAL_ERROR",
                    "message": "Đã xảy ra lỗi khi xử lý câu hỏi.",
                    "details": {"error": str(e)} if logger.logger.level <= 10 else {}
                }
            )


@router.post(
    "/chat/reset",
    response_model=ResetConversationResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"}
    }
)
async def reset_conversation(request: ResetConversationRequest):
    """
    Reset conversation history (clear chat memory)
    """
    session_manager = get_session_manager()
    
    success = session_manager.reset_session(request.conversation_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SESSION_NOT_FOUND",
                "message": f"Conversation not found: {request.conversation_id}"
            }
        )
    
    logger.info(f"Conversation reset: {request.conversation_id}")
    
    return ResetConversationResponse(
        success=True,
        message="Conversation history has been reset",
        conversation_id=request.conversation_id
    )


@router.delete(
    "/chat/{conversation_id}",
    response_model=ResetConversationResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"}
    }
)
async def delete_conversation(conversation_id: str):
    """
    Delete a conversation session
    """
    session_manager = get_session_manager()
    
    success = session_manager.delete_session(conversation_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SESSION_NOT_FOUND",
                "message": f"Conversation not found: {conversation_id}"
            }
        )
    
    logger.info(f"Conversation deleted: {conversation_id}")
    
    return ResetConversationResponse(
        success=True,
        message="Conversation has been deleted",
        conversation_id=conversation_id
    )


@router.get(
    "/chat/{conversation_id}",
    response_model=ConversationInfo,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"}
    }
)
async def get_conversation_info(conversation_id: str):
    """
    Get information about a conversation session
    """
    session_manager = get_session_manager()
    
    info = session_manager.get_session_info(conversation_id)
    
    if not info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SESSION_NOT_FOUND",
                "message": f"Conversation not found: {conversation_id}"
            }
        )
    
    return ConversationInfo(
        conversation_id=info["conversation_id"],
        created_at=info["created_at"],
        last_accessed=info["last_accessed"],
        is_active=not info["is_expired"]
    )


@router.get("/sessions/count")
async def get_session_count():
    """
    Get number of active sessions (for monitoring)
    """
    session_manager = get_session_manager()
    count = session_manager.get_session_count()
    
    return {
        "active_sessions": count
    }