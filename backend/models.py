from pydantic import BaseModel
from typing import List, Optional

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    session_id: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    retrieval_mode: Optional[str] = "hybrid"
    top_k: Optional[int] = 5

class ChatResponse(BaseModel):
    answer: str
    response_time: float
    retrieved_chunks: Optional[List[str]] = None
    amap_called: bool = False
    map_link: Optional[str] = None

class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str

class MessageOut(BaseModel):
    role: str
    content: str
    timestamp: str