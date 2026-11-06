from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CourseInstructor,
    Department,
    Notification,
    NotificationStatus,
    NotificationType,
    RoutingStage,
    Section,
    User,
    UserRole,
)


def _enqueue(db: Session, recipient_ids: list[int] | set[int], title: str, body: str, now: datetime) -> None:
    for user_id in sorted(set(recipient_ids)):
        db.add(
            Notification(
                recipient_user_id=user_id,
                notification_type=NotificationType.REQUEST_UPDATE,
                title=title[:255],
                body=body,
                scheduled_for=now,
                status=NotificationStatus.PENDING,
            )
        )


def recipients_for_stage(
    db: Session,
    stage: RoutingStage,
    section_id: int,
    course_id: int | None,
) -> list[int]:
    if stage == RoutingStage.CLASS_REPRESENTATIVE:
        return list(
            db.scalars(
                select(User.id).where(
                    User.role == UserRole.CLASS_REPRESENTATIVE,
                    User.section_id == section_id,
                    User.is_active.is_(True),
                )
            ).all()
        )

    if stage == RoutingStage.INSTRUCTOR:
        if course_id is None:
            return []
        return list(
            db.scalars(
                select(CourseInstructor.instructor_id).where(CourseInstructor.course_id == course_id)
            ).all()
        )

    section = db.get(Section, section_id)
    department = db.get(Department, section.department_id) if section else None
    if department is None:
        return []
    if stage == RoutingStage.DEPARTMENT_COORDINATOR:
        return [department.coordinator_user_id] if department.coordinator_user_id else []
    return [department.head_user_id] if department.head_user_id else []


def notify_stage(
    db: Session,
    stage: RoutingStage,
    section_id: int,
    course_id: int | None,
    *,
    title: str,
    body: str,
    now: datetime,
) -> None:
    _enqueue(db, recipients_for_stage(db, stage, section_id, course_id), title, body, now)


def notify_students(db: Session, student_ids: set[int], *, title: str, body: str, now: datetime) -> None:
    _enqueue(db, student_ids, title, body, now)