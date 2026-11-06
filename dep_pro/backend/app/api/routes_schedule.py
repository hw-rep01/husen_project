from datetime import date, datetime
from time import monotonic, sleep

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.config import get_settings
from app.db.session import SessionLocal, get_db
from app.models import MakeupSuggestion, Room, ScheduleChangeLog, Semester, User
from app.services.common.timeutil import as_utc, local_today
from app.services.errors import BusinessRuleError, NotFoundError
from app.services.schedule.changes import cancel_occurrence, change_room, reschedule
from app.services.schedule.makeup import accept_makeup, suggest_makeup
from app.services.schedule.materialize import materialize_occurrences
from app.services.schedule.read import changes_since, occurrence_view, week_rows

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


class OccurrenceOut(BaseModel):
    id: int
    enrollment_id: int
    section_id: int
    course_id: int
    course_code: str
    course_name: str
    occurrence_date: date
    starts_at: datetime
    ends_at: datetime
    room_id: int | None
    room_code: str | None
    slot_type: str
    is_cancelled: bool
    note: str | None
    version: int


class RoomChangeIn(BaseModel):
    room_id: int
    note: str | None = Field(default=None, max_length=1000)


class RescheduleIn(BaseModel):
    new_date: date
    time_slot_id: int
    room_id: int | None = None
    note: str | None = Field(default=None, max_length=1000)


class CancelIn(BaseModel):
    as_postponement: bool = False
    note: str | None = Field(default=None, max_length=1000)


class MakeupSuggestIn(BaseModel):
    enrollment_id: int
    from_date: date | None = None
    days_ahead: int = Field(default=14, ge=1, le=30)
    limit: int = Field(default=5, ge=1, le=10)


class SuggestionOut(BaseModel):
    id: int
    enrollment_id: int
    suggested_date: date
    starts_at: datetime
    ends_at: datetime
    room_id: int
    room_code: str
    score: float
    is_accepted: bool


class MaterializeIn(BaseModel):
    from_date: date
    to_date: date


class ChangeOut(BaseModel):
    id: int
    occurrence_id: int
    change_type: str
    changed_by_user_id: int | None
    old_value: str | None
    new_value: str | None
    created_at: datetime


def _occ_out(row) -> OccurrenceOut:
    occ, enrollment, course, room_code = row
    return OccurrenceOut(
        id=occ.id,
        enrollment_id=enrollment.id,
        section_id=enrollment.section_id,
        course_id=course.id,
        course_code=course.code,
        course_name=course.name_ar,
        occurrence_date=occ.occurrence_date,
        starts_at=as_utc(occ.starts_at),
        ends_at=as_utc(occ.ends_at),
        room_id=occ.room_id,
        room_code=room_code,
        slot_type=occ.slot_type.value,
        is_cancelled=occ.is_cancelled,
        note=occ.note,
        version=occ.version,
    )


def _change_out(c: ScheduleChangeLog) -> ChangeOut:
    return ChangeOut(
        id=c.id,
        occurrence_id=c.occurrence_id,
        change_type=c.change_type.value,
        changed_by_user_id=c.changed_by_user_id,
        old_value=c.old_value,
        new_value=c.new_value,
        created_at=c.created_at,
    )


def _suggestion_out(db: Session, s: MakeupSuggestion) -> SuggestionOut:
    room = db.get(Room, s.suggested_room_id)
    return SuggestionOut(
        id=s.id,
        enrollment_id=s.enrollment_id,
        suggested_date=s.suggested_date,
        starts_at=as_utc(s.suggested_starts_at),
        ends_at=as_utc(s.suggested_ends_at),
        room_id=s.suggested_room_id,
        room_code=room.code if room else "",
        score=s.score,
        is_accepted=s.is_accepted,
    )


@router.get("/week", response_model=list[OccurrenceOut])
def week(
    day: date | None = None,
    user: User = Depends(require_permission("schedule:view")),
    db: Session = Depends(get_db),
) -> list[OccurrenceOut]:
    return [_occ_out(row) for row in week_rows(db, user, day or local_today())]


@router.get("/changes", response_model=list[ChangeOut])
def changes(
    after_id: int = 0,
    user: User = Depends(require_permission("schedule:view")),
    db: Session = Depends(get_db),
) -> list[ChangeOut]:
    return [_change_out(c) for c in changes_since(db, user, after_id)]


@router.get("/stream")
def stream_changes(
    after_id: int = -1,
    user: User = Depends(require_permission("schedule:view")),
):
    """
    بث أحداث الجدول عبر Server-Sent Events.
    after_id = -1 يعني "ابدأ من آخر تغيير موجود"، فلا يُعاد تشغيل التاريخ كله.
    كل اتصال يُغلق بعد مدة محددة، والعميل يعيد الاتصال بآخر معرّف استلمه.
    """
    settings = get_settings()
    user_id = user.id

    def events():
        with SessionLocal() as db:
            if after_id >= 0:
                last_id = after_id
            else:
                last_id = db.scalar(select(func.max(ScheduleChangeLog.id))) or 0

        deadline = monotonic() + settings.schedule_stream_max_seconds
        while monotonic() < deadline:
            with SessionLocal() as db:
                current = db.get(User, user_id)
                if current is None or not current.is_active:
                    return
                items = [_change_out(c) for c in changes_since(db, current, last_id)]
            for item in items:
                last_id = item.id
                yield f"id: {item.id}\nevent: schedule_change\ndata: {item.model_dump_json()}\n\n"
            if not items:
                yield ": keep-alive\n\n"
            sleep(settings.schedule_stream_poll_seconds)
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/occurrences/{occurrence_id}/room", response_model=OccurrenceOut)
def change_room_route(
    occurrence_id: int,
    payload: RoomChangeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    change_room(db, user, occurrence_id, payload.room_id, payload.note)
    return _occ_out(occurrence_view(db, occurrence_id))


@router.post("/occurrences/{occurrence_id}/reschedule", response_model=OccurrenceOut)
def reschedule_route(
    occurrence_id: int,
    payload: RescheduleIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    reschedule(
        db, user, occurrence_id,
        new_date=payload.new_date,
        time_slot_id=payload.time_slot_id,
        room_id=payload.room_id,
        note=payload.note,
    )
    return _occ_out(occurrence_view(db, occurrence_id))


@router.post("/occurrences/{occurrence_id}/cancel", response_model=OccurrenceOut)
def cancel_route(
    occurrence_id: int,
    payload: CancelIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    cancel_occurrence(db, user, occurrence_id, as_postponement=payload.as_postponement, note=payload.note)
    return _occ_out(occurrence_view(db, occurrence_id))


@router.post("/makeup/suggest", response_model=list[SuggestionOut])
def suggest_route(
    payload: MakeupSuggestIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SuggestionOut]:
    suggestions = suggest_makeup(
        db,
        user,
        enrollment_id=payload.enrollment_id,
        from_date=payload.from_date or local_today(),
        days_ahead=payload.days_ahead,
        limit=payload.limit,
    )
    return [_suggestion_out(db, s) for s in suggestions]


@router.post("/makeup/suggestions/{suggestion_id}/accept", response_model=OccurrenceOut)
def accept_route(
    suggestion_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occ = accept_makeup(db, user, suggestion_id)
    return _occ_out(occurrence_view(db, occ.id))


@router.post("/semesters/{semester_id}/materialize")
def materialize_route(
    semester_id: int,
    payload: MaterializeIn,
    user: User = Depends(require_permission("schedule:edit_department")),
    db: Session = Depends(get_db),
) -> dict:
    semester = db.get(Semester, semester_id)
    if semester is None:
        raise NotFoundError("الفصل الدراسي غير موجود")
    if payload.to_date < payload.from_date or (payload.to_date - payload.from_date).days > 200:
        raise BusinessRuleError("نطاق التواريخ غير صالح (الحد الأقصى 200 يوم)")
    if user.department_id is None:
        raise BusinessRuleError("الحساب غير مرتبط بقسم")
    created = materialize_occurrences(
        db,
        semester=semester,
        start=payload.from_date,
        end=payload.to_date,
        department_id=user.department_id,
    )
    return {"created": created}