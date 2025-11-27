# -*- coding: utf-8 -*-
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid


class RequestStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class LLMRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    service: str  # ollama, openai, vllm, etc.
    model: str
    prompt: str
    status: RequestStatus = RequestStatus.QUEUED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    response: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class RequestAction(BaseModel):
    action: str  # "kill"
    request_id: str


class DashboardStats(BaseModel):
    queue_count: int
    processing_count: int
    completed_count: int
    failed_count: int
    killed_count: int

