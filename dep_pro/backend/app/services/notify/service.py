from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification, NotificationStatus, NotificationType, User, UserRole

STUDENT_ROLES = (UserRole.STUDENT, UserRole.CLASS_REPRESENTATIVE)


def section_member_ids(db: Session, section_id: int) -> list[int]:
    return list(
        db.scalars(
            select(User.id).where(
                User.section_id == section_id,
                User.role.in_(STUDENT_ROLES),
                User.is_active.is_(True),
            )
        ).all()
    )


def enqueue(
    db: Session,
    recipient_ids,
    *,
    notification_type: NotificationType,
    title: str,
    body: str,
    scheduled_for: datetime,
    occurrence_id: int | None = None,
) -> int:
    count = 0
    for user_id in sorted(set(recipient_ids)):
        db.add(
            Notification(
                recipient_user_id=user_id,
                notification_type=notification_type,
                title=title[:255],
                body=body,
                lecture_occurrence_id=occurrence_id,
                scheduled_for=scheduled_for,
                status=NotificationStatus.PENDING,
            )
        )
        count += 1
    return count


def notify_section(
    db: Session,
    section_id: int,
    *,
    notification_type: NotificationType,
    title: str,
    body: str,
    scheduled_for: datetime,
    occurrence_id: int | None = None,
) -> int:
    return enqueue(
        db,
        section_member_ids(db, section_id),
        notification_type=notification_type,
        title=title,
        body=body,
        scheduled_for=scheduled_for,
        occurrence_id=occurrence_id,
    )