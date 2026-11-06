import logging
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Course,
    Enrollment,
    LectureOccurrence,
    Notification,
    NotificationStatus,
    NotificationType,
    Room,
    Semester,
    User,
)
from app.services.common.timeutil import as_utc, local_today, local_tz
from app.services.notify.service import STUDENT_ROLES, enqueue, section_member_ids

logger = logging.getLogger(__name__)


class InAppChannel:
    """
    التسليم داخل التطبيق: يصبح الإشعار مرئياً في GET /api/notifications/mine
    بعد تحويله إلى SENT. أي قناة خارجية (Push أو SMS) تُضاف بتنفيذ دالة deliver.
    """

    name = "in_app"

    def deliver(self, notification: Notification) -> None:
        return None


DEFAULT_CHANNEL = InAppChannel()


def course_room_rows(db: Session, extra_where: list) -> list:
    """صفوف المحاضرات مع الشعبة واسم المادة ورمز القاعة، للفصل الدراسي النشط فقط."""
    stmt = (
        select(LectureOccurrence, Enrollment.section_id, Course.name_ar, Room.code)
        .join(Enrollment, Enrollment.id == LectureOccurrence.enrollment_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Semester, Semester.id == Enrollment.semester_id)
        .outerjoin(Room, Room.id == LectureOccurrence.room_id)
        .where(
            Semester.is_active.is_(True),
            LectureOccurrence.is_cancelled.is_(False),
            *extra_where,
        )
        .order_by(LectureOccurrence.starts_at)
    )
    return db.execute(stmt).all()


def _reminder_body(occ: LectureOccurrence, course_name: str, room_code: str | None, minutes: int) -> str:
    start_local = as_utc(occ.starts_at).astimezone(local_tz())
    place = f"القاعة {room_code}" if room_code else "القاعة لم تحدد بعد"
    return f"محاضرة {course_name} تبدأ الساعة {start_local:%H:%M} بعد {minutes} دقيقة، في {place}."


def plan_pre_lecture_reminders(db: Session, now: datetime) -> int:
    """
    ينشئ تذكيرات للمحاضرات التي تبدأ خلال النافذة. النافذة أوسع من مهلة التذكير
    حتى لا تفوت أي محاضرة إذا تأخرت المهمة لدقائق. التكرار محمي بمقارنة الموعد المتوقع.
    """
    settings = get_settings()
    lead = timedelta(minutes=settings.lecture_reminder_minutes)
    rows = course_room_rows(
        db,
        [
            LectureOccurrence.starts_at >= now + timedelta(minutes=1),
            LectureOccurrence.starts_at < now + lead + timedelta(minutes=5),
        ],
    )

    members_cache: dict[int, list[int]] = {}
    created = 0
    for occ, section_id, course_name, room_code in rows:
        expected = as_utc(occ.starts_at) - lead
        existing = db.scalars(
            select(Notification).where(
                Notification.lecture_occurrence_id == occ.id,
                Notification.notification_type == NotificationType.PRE_LECTURE_REMINDER,
            )
        ).all()

        covered: set[int] = set()
        for n in existing:
            if as_utc(n.scheduled_for) == expected and n.status != NotificationStatus.CANCELLED:
                covered.add(n.recipient_user_id)
            elif n.status == NotificationStatus.PENDING:
                # تذكير قديم لموعد تغيّر: يُلغى ويُعاد تخطيطه بالموعد الجديد
                n.status = NotificationStatus.CANCELLED

        if section_id not in members_cache:
            members_cache[section_id] = section_member_ids(db, section_id)
        missing = [uid for uid in members_cache[section_id] if uid not in covered]
        if missing:
            created += enqueue(
                db,
                missing,
                notification_type=NotificationType.PRE_LECTURE_REMINDER,
                title=f"تذكير: محاضرة بعد {settings.lecture_reminder_minutes} دقيقة",
                body=_reminder_body(occ, course_name, room_code, settings.lecture_reminder_minutes),
                scheduled_for=expected,
                occurrence_id=occ.id,
            )
    return created


def plan_morning_digests(db: Session, now: datetime) -> int:
    """
    ينشئ ملخص جدول اليوم لكل طالب عند ساعة الصباح المحددة. إذا تجاوزنا الساعة
    بأكثر من ساعتين لا يُنشأ ملخص اليوم، لتجنب إرسال متأخر.
    """
    settings = get_settings()
    tz = local_tz()
    today = local_today()
    digest_at = datetime.combine(today, time(settings.morning_digest_hour), tzinfo=tz).astimezone(UTC)
    if now > digest_at + timedelta(hours=2):
        return 0

    already = set(
        db.scalars(
            select(Notification.recipient_user_id).where(
                Notification.notification_type == NotificationType.MORNING_DIGEST,
                Notification.scheduled_for == digest_at,
            )
        ).all()
    )

    lines_by_section: dict[int, list[str]] = defaultdict(list)
    for occ, section_id, course_name, room_code in course_room_rows(
        db, [LectureOccurrence.occurrence_date == today]
    ):
        start_local = as_utc(occ.starts_at).astimezone(tz)
        end_local = as_utc(occ.ends_at).astimezone(tz)
        place = room_code or "غير محددة"
        lines_by_section[section_id].append(
            f"{start_local:%H:%M} - {end_local:%H:%M}: {course_name} (القاعة: {place})"
        )

    students = db.execute(
        select(User.id, User.section_id).where(
            User.role.in_(STUDENT_ROLES),
            User.is_active.is_(True),
            User.section_id.is_not(None),
        )
    ).all()

    created = 0
    for user_id, section_id in students:
        if user_id in already:
            continue
        lines = lines_by_section.get(section_id, [])
        body = "\n".join(lines) if lines else "لا توجد محاضرات مجدولة لك اليوم."
        created += enqueue(
            db,
            [user_id],
            notification_type=NotificationType.MORNING_DIGEST,
            title=f"جدول اليوم: {len(lines)} محاضرة",
            body=body,
            scheduled_for=digest_at,
        )
    return created


def dispatch_due_notifications(
    db: Session,
    now: datetime,
    channel=DEFAULT_CHANNEL,
    batch_size: int = 500,
) -> dict[str, int]:
    settings = get_settings()
    lead = timedelta(minutes=settings.lecture_reminder_minutes)
    due = db.scalars(
        select(Notification)
        .where(Notification.status == NotificationStatus.PENDING, Notification.scheduled_for <= now)
        .order_by(Notification.scheduled_for, Notification.id)
        .limit(batch_size)
    ).all()

    counts = {"sent": 0, "cancelled": 0, "failed": 0}
    for n in due:
        try:
            if n.notification_type == NotificationType.PRE_LECTURE_REMINDER:
                occ = db.get(LectureOccurrence, n.lecture_occurrence_id) if n.lecture_occurrence_id else None
                if occ is None or occ.is_cancelled or as_utc(occ.starts_at) - lead != as_utc(n.scheduled_for):
                    n.status = NotificationStatus.CANCELLED
                    counts["cancelled"] += 1
                    continue
                rows = course_room_rows(db, [LectureOccurrence.id == occ.id])
                if rows:
                    _, _, course_name, room_code = rows[0]
                    n.body = _reminder_body(occ, course_name, room_code, settings.lecture_reminder_minutes)

            channel.deliver(n)
            n.status = NotificationStatus.SENT
            n.sent_at = now
            counts["sent"] += 1
        except Exception as exc:
            logger.exception("فشل تسليم الإشعار %s", n.id)
            n.status = NotificationStatus.FAILED
            n.error_message = str(exc)[:1000]
            counts["failed"] += 1

    db.commit()
    return counts