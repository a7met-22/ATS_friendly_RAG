


"""Session-scoped PDF document management router (Upload, List, Delete)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from api.dependencies import (
    get_client_ip,
    get_current_principal,
    get_document_parser,
    get_upload_session_id,
)
from api.schemas import (
    DeleteDocumentResponse,
    DocumentUploadResponse,
    ErrorResponse,
    SessionDocumentItem,
    SessionDocumentsResponse,
)
from api.security import upload_rate_limiter
from application.services.document_scope import get_session_upload_ids
from application.services.upload_service import MAX_PDF_SIZE_BYTES, process_uploaded_pdf
from database_utilities.database_connection import get_connection
from security.authorization import Principal

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])

MAX_FILES_PER_SESSION = 10
_READ_CHUNK_SIZE = 1024 * 1024  # 1 MB streaming read buffer


async def _enforce_upload_rate_limit(
    request: Request,
    principal: Principal | None = Depends(get_current_principal),
) -> None:
    key = principal.email if principal is not None else get_client_ip(request)
    await upload_rate_limiter.check(key)


async def _read_bounded_pdf_bytes(upload: UploadFile) -> bytes:
    """Read uploaded stream in 1MB chunks and abort immediately if it exceeds MAX_PDF_SIZE_BYTES."""
    if not upload.filename or not upload.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files (.pdf) are supported.",
        )

    chunks: list[bytes] = []
    total_bytes = 0

    while True:
        chunk = await upload.read(_READ_CHUNK_SIZE)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > MAX_PDF_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Uploaded PDF exceeds the maximum allowed size of 20 MB.",
            )
        chunks.append(chunk)

    if total_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded PDF file is empty.",
        )

    return b"".join(chunks)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_enforce_upload_rate_limit)],
    responses={
        400: {"model": ErrorResponse, "description": "Invalid PDF or session limit reached"},
        413: {"model": ErrorResponse, "description": "File exceeds 20 MB limit"},
        429: {"model": ErrorResponse, "description": "Upload rate limit exceeded"},
    },
    summary="Upload and index a PDF document for the current session",
)
async def upload_session_document(
    file: UploadFile = File(...),
    upload_session_id: str = Depends(get_upload_session_id),
    parser=Depends(get_document_parser),
) -> DocumentUploadResponse:
    """Ingest a PDF into the isolated current session for both Guests and Authenticated Users."""
    existing_ids = await get_session_upload_ids(upload_session_id)
    if len(existing_ids) >= MAX_FILES_PER_SESSION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum limit of {MAX_FILES_PER_SESSION} documents per session reached.",
        )

    pdf_bytes = await _read_bounded_pdf_bytes(file)

    try:
        result = await process_uploaded_pdf(
            pdf_bytes=pdf_bytes,
            filename=file.filename or "uploaded.pdf",
            upload_session_id=upload_session_id,
            parser=parser,
            source_type="session_upload",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return DocumentUploadResponse(**result)


@router.get(
    "/session",
    response_model=SessionDocumentsResponse,
    summary="List all processed PDFs uploaded in the current session",
)
async def list_session_documents(
    upload_session_id: str = Depends(get_upload_session_id),
) -> SessionDocumentsResponse:
    """Return documents scoped strictly to the caller's X-Session-ID."""
    upload_ids = await get_session_upload_ids(upload_session_id)
    if not upload_ids:
        return SessionDocumentsResponse(upload_session_id=upload_session_id, documents=[])

    async with await get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id, filename
                FROM public.documents
                WHERE id = ANY(%s::bigint[])
                ORDER BY created_at, id
                """,
                (upload_ids,),
            )
            rows = await cur.fetchall()

    items = [SessionDocumentItem(document_id=row[0], filename=row[1]) for row in rows]
    return SessionDocumentsResponse(upload_session_id=upload_session_id, documents=items)


@router.delete(
    "/session/{document_id}",
    response_model=DeleteDocumentResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Document not found in current session"},
    },
    summary="Delete a specific document from the current session",
)
async def delete_session_document(
    document_id: int,
    upload_session_id: str = Depends(get_upload_session_id),
) -> DeleteDocumentResponse:
    """Delete a session document strictly verifying ownership via X-Session-ID (IDOR-safe)."""
    async with await get_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    DELETE FROM public.documents
                    WHERE id = %s
                      AND drive_file_id IS NULL
                      AND metadata->>'source_type' IN ('session_upload', 'streamlit_upload')
                      AND metadata->>'upload_session_id' = %s
                    RETURNING id
                    """,
                    (document_id, upload_session_id),
                )
                deleted_row = await cur.fetchone()

    if deleted_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in your current session.",
        )

    return DeleteDocumentResponse(deleted=True, document_id=document_id)
