from dataclasses import asdict
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import RequestBatch, RequestCategory, RequestEvent, StudentRequest, User
from app.services.errors import AccessDeniedError, NotFoundError
from app.services.triage.routing import Action
from app.services.triage.submission import submit_request
from app.services.triage.visibility import (
    build_unit_views,
    can_view_request,
    inbox_requests,
    section_requests,
    student_requests,
    view_of_unit,
)
from app.services.triage.workflow import (
    classify_by_representative,
    consolidate_for_representative,
    load_unit,
    perform_action,
    refresh_for_representative,
)

router = APIRouter(prefix="/api", tags=["requests"])


class RequestCreateIn(BaseModel):
    course_id: int | None = None
    subject: str = Field(min_length=3, max_length=255)
    body: str = Field(min_length=10, max_length=5000)


class ClassifyIn(BaseModel):
    category: Literal["academic", "administrative"]


class ActionIn(BaseModel):
    action: Literal["forward", "approve", "reject", "resolve"]
    course_id: int | None = None
    note: str | None = Field(default=None, max_length=1000)


class RequestOut(BaseModel):
    id: int
    course_id: int | None
    subject: str
    body: str
    category: str | None
    classification_confidence: float | None
    status: str
    current_stage: str
    batch_id: int | None
    created_at: datetime


class UnitOut(BaseModel):
    kind: str
    id: int
    section_id: int
    category: str | None
    course_id: int | None
    title: str
    summary: str
    request_count: int
    status: str
    current_stage: str
    created_at: datetime


class EventOut(BaseModel):
    action: str
    from_stage: str | None
    to_stage: str | None
    actor_user_id: int | None
    note: str | None
    created_at: datetime


def _request_out(request: StudentRequest) -> RequestOut:
    return RequestOut(
        id=request.id,
        course_id=request.course_id,
        subject=request.subject,
        body=request.body,
        category=request.category.value if request.category else None,
        classification_confidence=request.classification_confidence,
        status=request.status.value,
        current_stage=request.current_stage.value,
        batch_id=request.batch_id,
        created_at=request.created_at,
    )


def _unit_out(batch: RequestBatch | None, requests: list[StudentRequest]) -> UnitOut:
    return UnitOut(**asdict(view_of_unit(batch, requests)))


@router.post("/requests", response_model=RequestOut, status_code=201)
def create_request(
    payload: RequestCreateIn,
    user: User = Depends(require_permission("request:create")),
    db: Session = Depends(get_db),
) -> RequestOut:
    request = submit_request(
        db,
        user,
        subject=payload.subject,
        body=payload.body,
        course_id=payload.course_id,
    )
    return _request_out(request)


@router.get("/requests/mine", response_model=list[RequestOut])
def my_requests(
    user: User = Depends(require_permission("request:view_own")),
    db: Session = Depends(get_db),
) -> list[RequestOut]:
    return [_request_out(r) for r in student_requests(db, user)]


@router.get("/requests/section", response_model=list[UnitOut])
def list_section_requests(
    user: User = Depends(require_permission("request:view_section")),
    db: Session = Depends(get_db),
) -> list[UnitOut]:
    return [UnitOut(**asdict(v)) for v in build_unit_views(db, section_requests(db, user))]


@router.get("/requests/inbox", response_model=list[UnitOut])
def list_inbox(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UnitOut]:
    return [UnitOut(**asdict(v)) for v in build_unit_views(db, inbox_requests(db, user))]


@router.get("/requests/{request_id}", response_model=RequestOut)
def get_request(
    request_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RequestOut:
    request = db.get(StudentRequest, request_id)
    if request is None:
        raise NotFoundError("الطلب غير موجود")
    if not can_view_request(db, user, request):
        raise AccessDeniedError("لا تملك صلاحية عرض هذا الطلب")
    return _request_out(request)


@router.get("/requests/{request_id}/timeline", response_model=list[EventOut])
def request_timeline(
    request_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EventOut]:
    request = db.get(StudentRequest, request_id)
    if request is None:
        raise NotFoundError("الطلب غير موجود")
    if not can_view_request(db, user, request):
        raise AccessDeniedError("لا تملك صلاحية عرض سجل هذا الطلب")
    events = db.scalars(
        select(RequestEvent)
        .where(RequestEvent.request_id == request_id)
        .order_by(RequestEvent.created_at, RequestEvent.id)
    ).all()
    return [
        EventOut(
            action=e.action,
            from_stage=e.from_stage.value if e.from_stage else None,
            to_stage=e.to_stage.value if e.to_stage else None,
            actor_user_id=e.actor_user_id,
            note=e.note,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.post("/requests/{request_id}/classify", response_model=RequestOut)
def classify_request_route(
    request_id: int,
    payload: ClassifyIn,
    user: User = Depends(require_permission("request:merge_review")),
    db: Session = Depends(get_db),
) -> RequestOut:
    request = classify_by_representative(
        db,
        user,
        request_id=request_id,
        category=RequestCategory(payload.category),
    )
    return _request_out(request)


@router.post("/requests/{request_id}/actions", response_model=UnitOut)
def act_on_request(
    request_id: int,
    payload: ActionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnitOut:
    unit = perform_action(
        db,
        user,
        action=Action(payload.action),
        request_id=request_id,
        course_id=payload.course_id,
        note=payload.note,
    )
    return _unit_out(unit.batch, unit.requests)


@router.post("/batches/{batch_id}/actions", response_model=UnitOut)
def act_on_batch(
    batch_id: int,
    payload: ActionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnitOut:
    unit = perform_action(
        db,
        user,
        action=Action(payload.action),
        batch_id=batch_id,
        course_id=payload.course_id,
        note=payload.note,
    )
    return _unit_out(unit.batch, unit.requests)


@router.get("/batches/{batch_id}", response_model=UnitOut)
def get_batch(
    batch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnitOut:
    unit = load_unit(db, batch_id=batch_id)
    if not can_view_request(db, user, unit.requests[0]):
        raise AccessDeniedError("لا تملك صلاحية عرض هذه البطاقة")
    return _unit_out(unit.batch, unit.requests)


@router.post("/sections/consolidate")
def consolidate_section_route(
    user: User = Depends(require_permission("request:merge_review")),
    db: Session = Depends(get_db),
) -> dict:
    created = consolidate_for_representative(db, user)
    return {"batches_created": created}


@router.post("/batches/{batch_id}/refresh-summary", response_model=UnitOut)
def refresh_batch_summary_route(
    batch_id: int,
    user: User = Depends(require_permission("request:merge_review")),
    db: Session = Depends(get_db),
) -> UnitOut:
    unit = refresh_for_representative(db, user, batch_id)
    return _unit_out(unit.batch, unit.requests)