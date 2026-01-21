from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str = Field(
        ..., 
        description="Câu hỏi của người dùng", 
        example="Học phí ngành CNTT là bao nhiêu?",
        min_length=1,
        max_length=4000
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="ID cuộc hội thoại. Nếu không có sẽ tạo mới.",
        example="550e8400-e29b-41d4-a716-446655440000"
    )


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    response: str = Field(..., description="Câu trả lời từ AI")
    sources: List[str] = Field(
        default=[], 
        description="Danh sách tài liệu tham khảo (để hiển thị trích dẫn)"
    )
    conversation_id: str = Field(
        ...,
        description="ID cuộc hội thoại để tiếp tục chat"
    )


class ConversationInfo(BaseModel):
    """Information about a conversation/session"""
    conversation_id: str
    created_at: datetime
    last_accessed: datetime
    is_active: bool = True


class ResetConversationRequest(BaseModel):
    """Request to reset a conversation"""
    conversation_id: str = Field(..., description="ID cuộc hội thoại cần reset")


class ResetConversationResponse(BaseModel):
    """Response for reset conversation"""
    success: bool
    message: str
    conversation_id: str


class ErrorResponse(BaseModel):
    """Standard error response"""
    error_code: str
    message: str
    details: Optional[dict] = None