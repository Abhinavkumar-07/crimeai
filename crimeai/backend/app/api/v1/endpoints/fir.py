"""
FIR (First Information Report) endpoints.
Upload text or file → queue NLP processing → return extracted entities.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies.auth import CurrentUser, require_role
from app.core.exceptions import AlreadyExistsError
from app.core.security import UserRole
from app.db.session import get_db
from app.repositories.fir_repository import FIRRepository
from app.schemas.fir import FIRCreateRequest, FIRListResponse, FIRResponse
from app.workers.tasks.nlp_tasks import process_fir

router = APIRouter()

ALLOWED_FILE_TYPES = {"application/pdf", "text/plain", "image/jpeg", "image/png"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.get("/", response_model=FIRListResponse, summary="List FIR reports")
async def list_firs(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    db: Annotated[AsyncSession, Depends(get_db)],
    nlp_status: str | None = Query(None),
    my_reports: bool = Query(False, description="Only show my submitted FIRs"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> FIRListResponse:
    repo = FIRRepository(db)
    submitted_by = current_user.user_id if my_reports else None
    items, total = await repo.list_firs(
        nlp_status=nlp_status,
        submitted_by=submitted_by,
        limit=limit,
        offset=offset,
    )
    return FIRListResponse(
        items=[FIRResponse.model_validate(f) for f in items],
        total=total,
    )


@router.post(
    "/",
    response_model=FIRResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit FIR text for NLP processing",
)
async def submit_fir(
    body: FIRCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FIRResponse:
    repo = FIRRepository(db)

    existing = await repo.get_by_fir_number(body.fir_number)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"FIR number '{body.fir_number}' already registered",
        )

    fir = await repo.create(
        fir_number=body.fir_number,
        raw_text=body.raw_text,
        crime_id=body.crime_id,
        submitted_by=current_user.user_id,
        nlp_status="pending",
    )

    # Queue async NLP processing — does not block the response
    process_fir.apply_async(args=[str(fir.id)], queue="nlp")

    return FIRResponse.model_validate(fir)


@router.post(
    "/upload",
    response_model=FIRResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload FIR document (PDF/image) for OCR + NLP",
)
async def upload_fir(
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    db: Annotated[AsyncSession, Depends(get_db)],
    fir_number: str = Form(...),
    file: UploadFile = File(...),
    crime_id: str | None = Form(None),
) -> FIRResponse:
    # Validate file type and size
    if file.content_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{file.content_type}' not supported. "
                   f"Allowed: {', '.join(ALLOWED_FILE_TYPES)}",
        )
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 10 MB limit",
        )

    repo = FIRRepository(db)
    existing = await repo.get_by_fir_number(fir_number)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"FIR number '{fir_number}' already registered",
        )

    # TODO Step 6: upload to Supabase storage and extract text via OCR
    # For now store placeholder
    fir = await repo.create(
        fir_number=fir_number,
        raw_text=f"[File upload: {file.filename}] — NLP extraction pending",
        crime_id=uuid.UUID(crime_id) if crime_id else None,
        submitted_by=current_user.user_id,
        file_url=f"/pending/{file.filename}",
        file_type=file.content_type,
        nlp_status="pending",
    )
    process_fir.apply_async(args=[str(fir.id)], queue="nlp")
    return FIRResponse.model_validate(fir)


@router.get("/{fir_id}", response_model=FIRResponse, summary="Get FIR with extracted entities")
async def get_fir(
    fir_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FIRResponse:
    repo = FIRRepository(db)
    fir = await repo.get_by_id(fir_id)
    if not fir:
        raise HTTPException(status_code=404, detail="FIR not found")
    return FIRResponse.model_validate(fir)


@router.post(
    "/{fir_id}/reprocess",
    summary="Re-run NLP pipeline on existing FIR (Analyst)",
)
async def reprocess_fir(
    fir_id: uuid.UUID,
    current_user: Annotated[CurrentUser, Depends(require_role(UserRole.ANALYST))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    repo = FIRRepository(db)
    fir = await repo.get_by_id(fir_id)
    if not fir:
        raise HTTPException(status_code=404, detail="FIR not found")
    await repo.set_nlp_status(fir_id, "pending")
    task = process_fir.apply_async(args=[str(fir_id)], queue="nlp")
    return {"message": "NLP reprocessing queued", "task_id": task.id}
