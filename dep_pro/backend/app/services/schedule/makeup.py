from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import role_has_permission
from app.models import (
    ChangeType,
    Course,
    CourseInstructor,
    Enrollment,
    LectureOccurrence,
    MakeupSuggestion,
    Room,
    ScheduleSlotType,
    Section,
    TimeSlot,
    User,
    WeeklyScheduleEntry,
)
from app.services.access import ensure_course_access
from app.services.common.timeutil import as_utc, local_day_bounds, local_today, utc_now
from app.services.errors import AccessDeniedError, BusinessRuleError, NotFoundError
from app.services.notify.service import STUDENT_ROLES
from app.services.schedule.changes import (
    assert_free,
    describe,
    notify_schedule_change,
    record_change,
    require_available_room,
)
from app.services.schedule.makeup_engine import MakeupQuery, RoomSpec, SlotSpec, find_makeup_candidates
from app.services.schedule.snapshot import instructor_ids_by_course, load_snapshot, relevant_course_ids


def suggest_makeup(
    db: Session,
    actor: User,
    *,
    enrollment_id: int,
    from_date,
    days_ahead: int,
    limit: int,
) -> list[MakeupSuggestion]:
    settings = get_settings()
    if not role_has_permission(actor.role, "schedule:suggest_slots"):
        raise AccessDeniedError("ليست لديك صلاحية اقتراح أوقات تعويضية")

    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError("التسجيل غير موجود")
    ensure_course_access(db, actor, enrollment.course_id)
    section = db.get(Section, enrollment.section_id)

    days_ahead = min(days_ahead, settings.makeup_search_days)
    start_day = max(from_date, local_today())

    instructor_ids = instructor_ids_by_course(db, [enrollment.course_id]).get(enrollment.course_id, frozenset())
    if not instructor_ids:
        raise BusinessRuleError("لا يوجد دكتور مسجل لهذه المادة")

    section_size = int(
        db.scalar(
            select(func.count(User.id)).where(
                User.section_id == section.id,
                User.role.in_(STUDENT_ROLES),
                User.is_active.is_(True),
            )
        )
        or 0
    )

    preferred_room_id = db.scalar(
        select(WeeklyScheduleEntry.room_id)
        .where(WeeklyScheduleEntry.enrollment_id == enrollment.id, WeeklyScheduleEntry.room_id.is_not(None))
        .limit(1)
    )
    room_rows = db.scalars(
        select(Room).where(
            Room.is_available.is_(True),
            or_(Room.department_id.is_(None), Room.department_id == section.department_id),
        )
    ).all()
    # القاعات بلا سعة مسجلة (0) تُستبعد لأن سعتها مجهولة
    rooms = [
        RoomSpec(r.id, r.code, r.capacity, preferred=(r.id == preferred_room_id))
        for r in room_rows
        if r.capacity >= section_size
    ]
    slots = [
        SlotSpec(t.id, t.starts_at, t.ends_at, index)
        for index, t in enumerate(db.scalars(select(TimeSlot).order_by(TimeSlot.starts_at)).all())
    ]
    if not rooms or not slots:
        return []

    course_ids = relevant_course_ids(db, enrollment.course_id)
    snapshot = load_snapshot(
        db,
        local_day_bounds(start_day)[0],
        local_day_bounds(start_day + timedelta(days=days_ahead))[1],
        section_id=section.id,
        course_ids=course_ids,
        instructor_ids=instructor_ids,
        room_ids=[r.room_id for r in rooms],
    )

    query = MakeupQuery(
        section_id=section.id,
        section_size=section_size,
        instructor_ids=instructor_ids,
        from_date=start_day,
        days_ahead=days_ahead,
        reference_date=from_date,
        excluded_weekdays=settings.excluded_weekdays,
    )
    candidates = find_makeup_candidates(query, slots, rooms, snapshot, min(limit, settings.makeup_max_suggestions))

    created: list[MakeupSuggestion] = []
    for c in candidates:
        suggestion = MakeupSuggestion(
            enrollment_id=enrollment.id,
            requested_by_user_id=actor.id,
            suggested_date=c.local_date,
            suggested_starts_at=c.starts_at,
            suggested_ends_at=c.ends_at,
            suggested_room_id=c.room_id,
            score=c.score,
            is_accepted=False,
        )
        db.add(suggestion)
        created.append(suggestion)
    db.commit()
    return created


def accept_makeup(db: Session, actor: User, suggestion_id: int) -> LectureOccurrence:
    if not role_has_permission(actor.role, "schedule:suggest_slots"):
        raise AccessDeniedError("ليست لديك صلاحية اعتماد التعويضات")

    suggestion = db.get(MakeupSuggestion, suggestion_id)
    if suggestion is None:
        raise NotFoundError("الاقتراح غير موجود")
    if suggestion.is_accepted:
        raise BusinessRuleError("تم اعتماد هذا الاقتراح مسبقاً")

    enrollment = db.get(Enrollment, suggestion.enrollment_id)
    ensure_course_access(db, actor, enrollment.course_id)

    starts = as_utc(suggestion.suggested_starts_at)
    ends = as_utc(suggestion.suggested_ends_at)
    if starts <= utc_now():
        raise BusinessRuleError("الموعد المقترح مضى، اطلب اقتراحاً جديداً")

    room = require_available_room(db, suggestion.suggested_room_id)
    # إعادة الفحص عند الاعتماد لأن الجدول قد تغير منذ الاقتراح
    assert_free(db, enrollment, None, starts, ends, room.id)

    occ = LectureOccurrence(
        weekly_entry_id=None,
        enrollment_id=enrollment.id,
        occurrence_date=suggestion.suggested_date,
        starts_at=starts,
        ends_at=ends,
        room_id=room.id,
        slot_type=ScheduleSlotType.MAKEUP,
    )
    db.add(occ)
    db.flush()
    suggestion.is_accepted = True

    record_change(
        db, occ, actor, ChangeType.MAKEUP_ADDED,
        {},
        {"date": suggestion.suggested_date.isoformat(), "room_id": room.id},
    )
    course_name = db.get(Course, enrollment.course_id).name_ar
    notify_schedule_change(
        db, occ, enrollment, "محاضرة تعويضية",
        f"تمت جدولة محاضرة تعويضية: {describe(occ, course_name, room.code)}",
    )
    db.commit()
    return occ
