from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


FileType = Literal["pdf", "pptx", "txt", "md", "csv"]


class Source(BaseModel):
    text: str
    location: str
    score: float | None = None


class AskRequest(BaseModel):
    document_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1, max_length=4000)


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    file_type: FileType
    chunks_stored: int


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    confidence: float | None = None
    raw_model_output: str | None = None


class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    file_type: FileType
    chunks_stored: int
    size_bytes: int = 0
    uploaded_at: datetime


class HistoryItem(BaseModel):
    question: str
    answer: str
    sources: list[Source] = []
    created_at: datetime


class ErrorResponse(BaseModel):
    detail: str | dict[str, Any]
