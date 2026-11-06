from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Notification, NotificationStatus, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: int
    notification_type: str
    title: str
    body: str
    lecture_occurrence_id: int | None
    sent_at: datetime | None


@router.get("/mine", response_model=list[NotificationOut])
def my_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NotificationOut]:
    rows = db.scalars(
        select(Notification)
        .where(
            Notification.recipient_user_id == user.id,
            Notification.status == NotificationStatus.SENT,
        )
        .order_by(Notification.sent_at.desc())
        .limit(100)
    ).all()
    return [
        NotificationOut(
            id=n.id,
            notification_type=n.notification_type.value,
            title=n.title,
            body=n.body,
            lecture_occurrence_id=n.lecture_occurrence_id,
            sent_at=n.sent_at,
        )
        for n in rows
    ]