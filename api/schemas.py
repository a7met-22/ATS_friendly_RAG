

"""Strict Pydantic v2 request and response contracts for the RAG Resume API."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------
# Shared Error Contract
# --------------------------------------------------

class ErrorResponse(BaseModel):
    error_code: str
    message: str
    request_id: str | None = None


# --------------------------------------------------
# Authentication Contracts
# --------------------------------------------------

class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    email: str
    roles: list[str]


# --------------------------------------------------
# Document Management Contracts
# --------------------------------------------------

class DocumentUploadResponse(BaseModel):
    document_id: int
    filename: str
    content_hash: str
    chunk_count: int
    reused: bool


class SessionDocumentItem(BaseModel):
    document_id: int
    filename: str


class SessionDocumentsResponse(BaseModel):
    upload_session_id: str
    documents: list[SessionDocumentItem]


class DeleteDocumentResponse(BaseModel):
    deleted: bool
    document_id: int


# --------------------------------------------------
# RAG Question Answering Contracts
# --------------------------------------------------

class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(..., min_length=1, max_length=1000)
    retrieval_mode: Literal["hybrid", "semantic", "keyword"] = "hybrid"
    top_k: int = Field(default=5, ge=1, le=15)
    include_session_uploads: bool = Field(
        default=False,
        description="For authorized users: include current-session PDFs alongside system documents. Always True for guests.",
    )


class CitationItem(BaseModel):
    document_title: str
    chunk_id: str | int


class SourceItem(BaseModel):
    document_id: int
    document_title: str
    chunk_id: str | int
    section: str | None = None


class AnswerResponse(BaseModel):
    answer: str
    citations: list[CitationItem]
    sources: list[SourceItem]
    retrieval_mode: Literal["hybrid", "semantic", "keyword"]
    documents_searched: int
    prompt_access_level: Literal["system", "guest"]


# --------------------------------------------------
# Admin & Health Contracts
# --------------------------------------------------

class SyncTriggerResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    message: str


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    database: Literal["connected", "disconnected"]
