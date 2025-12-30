"""Chat data models."""

from pydantic import BaseModel
from typing import List, Optional


class ChatMessage(BaseModel):
    """Chat message model."""
    message: str


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    sources: Optional[List[str]] = None
