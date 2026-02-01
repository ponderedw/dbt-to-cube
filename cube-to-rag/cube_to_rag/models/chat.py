"""Chat data models."""

from pydantic import BaseModel
from typing import List, Optional


class ChatMessage(BaseModel):
    """Chat message model."""
    message: str


class ContextUpload(BaseModel):
    """Context upload model for persistent context."""
    content: str
    name: Optional[str] = None  # Optional name/label for the context


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    sources: Optional[List[str]] = None
