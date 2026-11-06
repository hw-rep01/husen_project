from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Absence, CourseInstructor, Enrollment, LectureOccurrence
from app.services.common.timeutil import as_utc
from app.services.schedule.conflicts import AbsenceBlock, BusyBlock, ScheduleSnapshot


def instructor_ids_by_course(db: Session, course_ids: Iterable[int]) -> dict[int, frozenset[int]]:
    ids = list(course_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(CourseInstructor.course_id, CourseInstructor.instructor_id).where(
            CourseInstructor.course_id.in_(ids)
        )
    ).all()
    grouped: dict[int, set[int]] = {}
    for course_id, instructor_id in rows:
        grouped.setdefault(course_id, set()).add(instructor_id)
    return {course_id: frozenset(values) for course_id, values in grouped.items()}


def relevant_course_ids(db: Session, course_id: int) -> frozenset[int]:
    """
    المادة نفسها مع كل المواد التي يدرّسها أساتذتها، لأن تعارض الدكتور
    يمتد عبر جميع المواد التي يدرّسها، لا المادة الحالية فقط.
    """
    instructor_ids = list(
        db.scalars(select(CourseInstructor.instructor_id).where(CourseInstructor.course_id == course_id)).all()
    )
    if not instructor_ids:
        return frozenset({course_id})
    others = db.scalars(
        select(CourseInstructor.course_id).where(CourseInstructor.instructor_id.in_(instructor_ids))
    ).all()
    return frozenset(others) | {course_id}


def load_snapshot(
    db: Session,
    start: datetime,
    end: datetime,
    *,
    section_id: int,
    course_ids: Iterable[int],
    instructor_ids: Iterable[int],
    room_ids: Iterable[int],
) -> ScheduleSnapshot:
    course_list = list(course_ids)
    instructor_list = list(instructor_ids)
    room_list = list(room_ids)

    scope = [Enrollment.section_id == section_id]
    if course_list:
        scope.append(Enrollment.course_id.in_(course_list))
    if room_list:
        scope.append(LectureOccurrence.room_id.in_(room_list))

    rows = db.execute(
        select(
            LectureOccurrence.id,
            LectureOccurrence.occurrence_date,
            LectureOccurrence.starts_at,
            LectureOccurrence.ends_at,
            LectureOccurrence.room_id,
            Enrollment.section_id,
            Enrollment.course_id,
        )
        .join(Enrollment, Enrollment.id == LectureOccurrence.enrollment_id)
        .where(
            LectureOccurrence.is_cancelled.is_(False),
            LectureOccurrence.starts_at < end,
            LectureOccurrence.ends_at > start,
            or_(*scope),
        )
    ).all()

    owners = instructor_ids_by_course(db, {row.course_id for row in rows})
    busy = tuple(
        BusyBlock(
            occurrence_id=row.id,
            local_date=row.occurrence_date,
            starts_at=as_utc(row.starts_at),
            ends_at=as_utc(row.ends_at),
            room_id=row.room_id,
            section_id=row.section_id,
            instructor_ids=owners.get(row.course_id, frozenset()),
        )
        for row in rows
    )

    absence_scope = []
    if instructor_list:
        absence_scope.append(Absence.user_id.in_(instructor_list))
    if room_list:
        absence_scope.append(Absence.room_id.in_(room_list))

    absences: tuple[AbsenceBlock, ...] = ()
    if absence_scope:
        absence_rows = db.scalars(
            select(Absence).where(
                Absence.starts_at < end,
                Absence.ends_at > start,
                or_(*absence_scope),
            )
        ).all()
        absences = tuple(
            AbsenceBlock(
                starts_at=as_utc(a.starts_at),
                ends_at=as_utc(a.ends_at),
                user_id=a.user_id,
                room_id=a.room_id,
            )
            for a in absence_rows
        )

    return ScheduleSnapshot(busy=busy, absences=absences)