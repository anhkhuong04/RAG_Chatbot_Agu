"""
Pydantic models for Dynamic Prompt Management.
Stored in MongoDB collection: 'prompts'

Schema:
  - intent_name: Unique intent identifier (e.g., 'general', 'diem_chuan', 'hoc_phi')
  - system_prompt: System-level prompt (reserved for future use)
  - user_template: The actual prompt template with {context_str} placeholder
  - description: Human-readable description for admin UI
  - is_active: Whether this prompt is active
  - updated_at / created_at: Timestamps
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PromptRecord(BaseModel):
    """Full schema for a prompt document in MongoDB 'prompts' collection."""

    intent_name: str = Field(
        ...,
        description="Unique intent identifier (e.g., 'general', 'diem_chuan', 'hoc_phi', 'career_advice')"
    )
    system_prompt: str = Field(
        default="",
        description="System-level prompt (reserved for future use)"
    )
    user_template: str = Field(
        default="",
        description="User-facing template with intent-specific formatting instructions"
    )
    description: str = Field(
        default="",
        description="Human-readable description of this intent prompt"
    )
    is_active: bool = Field(
        default=True,
        description="Whether this prompt is currently active"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp"
    )

    class Config:
        from_attributes = True


class PromptUpdate(BaseModel):
    """Schema for updating a prompt via PUT endpoint. Only non-None fields are applied."""

    system_prompt: Optional[str] = None
    user_template: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PromptResponse(BaseModel):
    """Response model for prompt API endpoints."""

    intent_name: str
    system_prompt: str
    user_template: str
    description: str
    is_active: bool
    updated_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
