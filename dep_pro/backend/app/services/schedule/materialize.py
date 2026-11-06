from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Enrollment,
    LectureOccurrence,
    ScheduleSlotType,
    Section,
    Semester,
    TimeSlot,
    WeeklyScheduleEntry,
)
from app.services.common.timeutil import as_utc, local_to_utc, local_tz


def materialize_occurrences(
    db: Session,
    *,
    semester: Semester,
    start: date,
    end: date,
    department_id: int | None,
) -> int:
    """
    يولّد المحاضرات الفعلية من القالب الأسبوعي لفترة معينة. آمن للتكرار:
    أي محاضرة موجودة مسبقاً (نفس القالب واليوم) تُتجاوز.
    """
    sem_start = as_utc(semester.starts_on).astimezone(local_tz()).date()
    sem_end = as_utc(semester.ends_on).astimezone(local_tz()).date()
    start = max(start, sem_start)
    end = min(end, sem_end)
    if start > end:
        return 0

    stmt = (
        select(WeeklyScheduleEntry, TimeSlot, Enrollment)
        .join(Enrollment, Enrollment.id == WeeklyScheduleEntry.enrollment_id)
        .join(TimeSlot, TimeSlot.id == WeeklyScheduleEntry.time_slot_id)
        .join(Section, Section.id == Enrollment.section_id)
        .where(Enrollment.semester_id == semester.id)
    )
    if department_id is not None:
        stmt = stmt.where(Section.department_id == department_id)
    entries = db.execute(stmt).all()

    existing = {
        (row[0], row[1])
        for row in db.execute(
            select(LectureOccurrence.weekly_entry_id, LectureOccurrence.occurrence_date).where(
                LectureOccurrence.weekly_entry_id.is_not(None),
                LectureOccurrence.occurrence_date >= start,
                LectureOccurrence.occurrence_date <= end,
            )
        ).all()
    }

    created = 0
    for entry, slot, enrollment in entries:
        day = start
        while day <= end:
            if day.weekday() == entry.weekday.value and (entry.id, day) not in existing:
                db.add(
                    LectureOccurrence(
                        weekly_entry_id=entry.id,
                        enrollment_id=enrollment.id,
                        occurrence_date=day,
                        starts_at=local_to_utc(day, slot.starts_at),
                        ends_at=local_to_utc(day, slot.ends_at),
                        room_id=entry.room_id,
                        slot_type=ScheduleSlotType.REGULAR,
                    )
                )
                created += 1
            day += timedelta(days=1)

    db.commit()
    return created