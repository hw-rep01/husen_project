from datetime import timedelta

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models import (
    Course,
    Enrollment,
    LectureOccurrence,
    Room,
    ScheduleChangeLog,
    Section,
    Semester,
    User,
    UserRole,
)
from app.services.common.timeutil import local_day_bounds
from app.services.triage.visibility import taught_course_ids


def visible_enrollment_clause(db: Session, user: User):
    """ما يراه كل دور من الجدول: الطالب شعبته، والدكتور موادّه، والمقرر والرئيس قسمهما."""
    if user.role in (UserRole.STUDENT, UserRole.CLASS_REPRESENTATIVE):
        return Enrollment.section_id == user.section_id if user.section_id is not None else false()
    if user.role == UserRole.INSTRUCTOR:
        ids = taught_course_ids(db, user)
        return Enrollment.course_id.in_(ids) if ids else false()
    if user.role in (UserRole.DEPARTMENT_COORDINATOR, UserRole.DEPARTMENT_HEAD):
        if user.department_id is None:
            return false()
        return Enrollment.section_id.in_(select(Section.id).where(Section.department_id == user.department_id))
    return false()


def _base_select():
    return (
        select(LectureOccurrence, Enrollment, Course, Room.code)
        .join(Enrollment, Enrollment.id == LectureOccurrence.enrollment_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Semester, Semester.id == Enrollment.semester_id)
        .outerjoin(Room, Room.id == LectureOccurrence.room_id)
        .where(Semester.is_active.is_(True))
    )


def occurrence_view(db: Session, occurrence_id: int):
    return db.execute(_base_select().where(LectureOccurrence.id == occurrence_id)).one()


def week_rows(db: Session, user: User, day):
    start, _ = local_day_bounds(day)
    _, end = local_day_bounds(day + timedelta(days=6))
    return db.execute(
        _base_select()
        .where(
            visible_enrollment_clause(db, user),
            LectureOccurrence.starts_at >= start,
            LectureOccurrence.starts_at < end,
        )
        .order_by(LectureOccurrence.starts_at)
    ).all()


def changes_since(db: Session, user: User, after_id: int, limit: int = 100) -> list[ScheduleChangeLog]:
    stmt = (
        select(ScheduleChangeLog)
        .join(LectureOccurrence, LectureOccurrence.id == ScheduleChangeLog.occurrence_id)
        .join(Enrollment, Enrollment.id == LectureOccurrence.enrollment_id)
        .join(Semester, Semester.id == Enrollment.semester_id)
        .where(
            Semester.is_active.is_(True),
            ScheduleChangeLog.id > after_id,
            visible_enrollment_clause(db, user),
        )
        .order_by(ScheduleChangeLog.id)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())