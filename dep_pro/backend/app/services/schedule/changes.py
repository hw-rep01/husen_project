import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import role_has_permission
from app.models import (
    ChangeType,
    Course,
    Enrollment,
    LectureOccurrence,
    NotificationType,
    Room,
    ScheduleChangeLog,
    ScheduleSlotType,
    TimeSlot,
    User,
)
from app.services.access import ensure_course_access
from app.services.common.timeutil import as_utc, local_day_bounds, local_to_utc, local_tz, utc_now
from app.services.errors import AccessDeniedError, BusinessRuleError, NotFoundError
from app.services.notify.service import notify_section
from app.services.schedule.conflicts import BusyBlock, find_conflicts
from app.services.schedule.snapshot import instructor_ids_by_course, load_snapshot, relevant_course_ids


def describe(occ: LectureOccurrence, course_name: str, room_code: str | None) -> str:
    local = as_utc(occ.starts_at).astimezone(local_tz())
    return f"{course_name} يوم {local:%Y-%m-%d} الساعة {local:%H:%M} في القاعة {room_code or 'غير محددة'}"


def record_change(
    db: Session,
    occ: LectureOccurrence,
    actor: User,
    change_type: ChangeType,
    old: dict,
    new: dict,
) -> None:
    db.add(
        ScheduleChangeLog(
            occurrence_id=occ.id,
            changed_by_user_id=actor.id,
            change_type=change_type,
            old_value=json.dumps(old, ensure_ascii=False, default=str),
            new_value=json.dumps(new, ensure_ascii=False, default=str),
        )
    )


def notify_schedule_change(db: Session, occ: LectureOccurrence, enrollment: Enrollment, title: str, body: str) -> None:
    notify_section(
        db,
        enrollment.section_id,
        notification_type=NotificationType.SCHEDULE_CHANGE,
        title=title,
        body=body,
        scheduled_for=utc_now(),
        occurrence_id=occ.id,
    )


def _course_name(db: Session, enrollment: Enrollment) -> str:
    return db.get(Course, enrollment.course_id).name_ar


def _room_code(db: Session, room_id: int | None) -> str | None:
    room = db.get(Room, room_id) if room_id else None
    return room.code if room else None


def authorize_edit(db: Session, actor: User, occurrence_id: int) -> tuple[LectureOccurrence, Enrollment]:
    occ = db.get(LectureOccurrence, occurrence_id)
    if occ is None:
        raise NotFoundError("المحاضرة غير موجودة")
    enrollment = db.get(Enrollment, occ.enrollment_id)
    allowed = role_has_permission(actor.role, "schedule:edit_own_course") or role_has_permission(
        actor.role, "schedule:edit_department"
    )
    if not allowed:
        raise AccessDeniedError("ليست لديك صلاحية تعديل الجدول")
    ensure_course_access(db, actor, enrollment.course_id)
    return occ, enrollment


def require_available_room(db: Session, room_id: int | None) -> Room | None:
    if room_id is None:
        return None
    room = db.get(Room, room_id)
    if room is None or not room.is_available:
        raise BusinessRuleError("القاعة غير موجودة أو غير متاحة")
    return room


def assert_free(
    db: Session,
    enrollment: Enrollment,
    occurrence_id: int | None,
    starts,
    ends,
    room_id: int | None,
) -> None:
    instructors = instructor_ids_by_course(db, [enrollment.course_id]).get(enrollment.course_id, frozenset())
    local_day = as_utc(starts).astimezone(local_tz()).date()
    day_start, day_end = local_day_bounds(local_day)
    snapshot = load_snapshot(
        db,
        day_start,
        day_end,
        section_id=enrollment.section_id,
        course_ids=relevant_course_ids(db, enrollment.course_id),
        instructor_ids=instructors,
        room_ids=[room_id] if room_id else [],
    )
    proposed = BusyBlock(
        occurrence_id=occurrence_id,
        local_date=local_day,
        starts_at=starts,
        ends_at=ends,
        room_id=room_id,
        section_id=enrollment.section_id,
        instructor_ids=instructors,
    )
    conflicts = find_conflicts(proposed, snapshot)
    if conflicts:
        raise BusinessRuleError("؛ ".join(conflicts))


def change_room(db: Session, actor: User, occurrence_id: int, room_id: int, note: str | None = None) -> LectureOccurrence:
    occ, enrollment = authorize_edit(db, actor, occurrence_id)
    if occ.is_cancelled:
        raise BusinessRuleError("لا يمكن تغيير قاعة محاضرة ملغاة")
    room = require_available_room(db, room_id)

    assert_free(db, enrollment, occ.id, as_utc(occ.starts_at), as_utc(occ.ends_at), room.id)

    old_room = occ.room_id
    occ.room_id = room.id
    occ.note = note or occ.note
    occ.version += 1

    record_change(
        db, occ, actor, ChangeType.ROOM_CHANGE,
        {"room_id": old_room, "room_code": _room_code(db, old_room)},
        {"room_id": room.id, "room_code": room.code},
    )
    notify_schedule_change(
        db, occ, enrollment, "تغيير قاعة محاضرة",
        describe(occ, _course_name(db, enrollment), room.code),
    )
    db.commit()
    return occ


def reschedule(
    db: Session,
    actor: User,
    occurrence_id: int,
    *,
    new_date,
    time_slot_id: int,
    room_id: int | None = None,
    note: str | None = None,
) -> LectureOccurrence:
    occ, enrollment = authorize_edit(db, actor, occurrence_id)
    if occ.is_cancelled:
        raise BusinessRuleError("لا يمكن نقل محاضرة ملغاة، أعد جدولتها كتعويض بدلاً من ذلك")

    slot = db.get(TimeSlot, time_slot_id)
    if slot is None:
        raise NotFoundError("الفترة الزمنية غير موجودة")

    starts = local_to_utc(new_date, slot.starts_at)
    ends = local_to_utc(new_date, slot.ends_at)
    target_room_id = room_id if room_id is not None else occ.room_id
    require_available_room(db, target_room_id)

    if occ.weekly_entry_id is not None:
        clash = db.scalar(
            select(LectureOccurrence.id).where(
                LectureOccurrence.weekly_entry_id == occ.weekly_entry_id,
                LectureOccurrence.occurrence_date == new_date,
                LectureOccurrence.id != occ.id,
            )
        )
        if clash is not None:
            raise BusinessRuleError("توجد محاضرة من القالب نفسه في هذا اليوم")

    assert_free(db, enrollment, occ.id, starts, ends, target_room_id)

    old = {"date": occ.occurrence_date.isoformat(), "starts_at": as_utc(occ.starts_at).isoformat()}
    occ.occurrence_date = new_date
    occ.starts_at = starts
    occ.ends_at = ends
    occ.room_id = target_room_id
    occ.note = note or occ.note
    occ.version += 1
    new = {"date": new_date.isoformat(), "starts_at": starts.isoformat()}

    record_change(db, occ, actor, ChangeType.TIME_CHANGE, old, new)
    notify_schedule_change(
        db, occ, enrollment, "تغيير موعد محاضرة",
        describe(occ, _course_name(db, enrollment), _room_code(db, occ.room_id)),
    )
    db.commit()
    return occ


def cancel_occurrence(
    db: Session,
    actor: User,
    occurrence_id: int,
    *,
    as_postponement: bool,
    note: str | None = None,
) -> LectureOccurrence:
    occ, enrollment = authorize_edit(db, actor, occurrence_id)
    if occ.is_cancelled:
        raise BusinessRuleError("المحاضرة ملغاة مسبقاً")

    occ.is_cancelled = True
    occ.slot_type = ScheduleSlotType.POSTPONED if as_postponement else ScheduleSlotType.CANCELLED
    occ.note = note or occ.note
    occ.version += 1

    change_type = ChangeType.POSTPONEMENT if as_postponement else ChangeType.CANCELLATION
    record_change(
        db, occ, actor, change_type,
        {"is_cancelled": False},
        {"is_cancelled": True, "slot_type": occ.slot_type.value},
    )

    title = "تأجيل محاضرة" if as_postponement else "إلغاء محاضرة"
    body = describe(occ, _course_name(db, enrollment), _room_code(db, occ.room_id))
    if note:
        body = f"{body}. ملاحظة: {note}"
    notify_schedule_change(db, occ, enrollment, title, body)
    db.commit()
    return occ