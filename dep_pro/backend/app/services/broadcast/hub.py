from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.permissions import role_has_permission
from app.models import (
    Broadcast,
    BroadcastChannel,
    BroadcastRead,
    BroadcastScope,
    Course,
    Department,
    Enrollment,
    NotificationType,
    Semester,
    User,
    UserRole,
)
from app.services.access import ensure_course_access
from app.services.common.timeutil import utc_now
from app.services.errors import AccessDeniedError, BusinessRuleError, NotFoundError
from app.services.notify.service import STUDENT_ROLES, enqueue


def get_or_create_department_channel(db: Session, department: Department) -> BroadcastChannel:
    channel = db.scalar(
        select(BroadcastChannel).where(
            BroadcastChannel.scope == BroadcastScope.DEPARTMENT,
            BroadcastChannel.department_id == department.id,
        )
    )
    if channel is None:
        channel = BroadcastChannel(
            scope=BroadcastScope.DEPARTMENT,
            department_id=department.id,
            course_id=None,
            name=f"تبليغات {department.name_ar}"[:255],
        )
        db.add(channel)
        db.flush()
    return channel


def get_or_create_course_channel(db: Session, course: Course) -> BroadcastChannel:
    channel = db.scalar(
        select(BroadcastChannel).where(
            BroadcastChannel.scope == BroadcastScope.COURSE,
            BroadcastChannel.course_id == course.id,
        )
    )
    if channel is None:
        channel = BroadcastChannel(
            scope=BroadcastScope.COURSE,
            department_id=course.department_id,
            course_id=course.id,
            name=f"تبليغات مادة {course.name_ar}"[:255],
        )
        db.add(channel)
        db.flush()
    return channel


def audience_user_ids(db: Session, channel: BroadcastChannel) -> list[int]:
    if channel.scope == BroadcastScope.DEPARTMENT:
        stmt = select(User.id).where(
            User.department_id == channel.department_id,
            User.role.in_(STUDENT_ROLES),
            User.is_active.is_(True),
        )
    else:
        stmt = (
            select(User.id)
            .join(Enrollment, Enrollment.section_id == User.section_id)
            .join(Semester, Semester.id == Enrollment.semester_id)
            .where(
                Enrollment.course_id == channel.course_id,
                Semester.is_active.is_(True),
                User.role.in_(STUDENT_ROLES),
                User.is_active.is_(True),
            )
            .distinct()
        )
    return list(db.scalars(stmt).all())


def is_in_audience(db: Session, user: User, channel: BroadcastChannel) -> bool:
    if user.role not in STUDENT_ROLES or not user.is_active:
        return False
    if channel.scope == BroadcastScope.DEPARTMENT:
        return user.department_id == channel.department_id
    if user.section_id is None:
        return False
    return db.scalar(
        select(Enrollment.id)
        .join(Semester, Semester.id == Enrollment.semester_id)
        .where(
            Enrollment.section_id == user.section_id,
            Enrollment.course_id == channel.course_id,
            Semester.is_active.is_(True),
        )
        .limit(1)
    ) is not None


def can_view(db: Session, user: User, channel: BroadcastChannel) -> bool:
    if user.role in STUDENT_ROLES:
        return is_in_audience(db, user, channel)
    if channel.scope == BroadcastScope.DEPARTMENT:
        return user.department_id == channel.department_id
    try:
        ensure_course_access(db, user, channel.course_id)
        return True
    except (AccessDeniedError, NotFoundError):
        return False


def _can_manage(db: Session, actor: User, broadcast: Broadcast, channel: BroadcastChannel) -> bool:
    if actor.id == broadcast.author_user_id:
        return True
    if channel.scope == BroadcastScope.DEPARTMENT:
        return actor.role in (UserRole.DEPARTMENT_COORDINATOR, UserRole.DEPARTMENT_HEAD) and (
            actor.department_id == channel.department_id
        )
    if actor.role != UserRole.INSTRUCTOR:
        return False
    try:
        ensure_course_access(db, actor, channel.course_id)
        return True
    except AccessDeniedError:
        return False


def post_broadcast(
    db: Session,
    actor: User,
    *,
    scope: BroadcastScope,
    course_id: int | None,
    title: str,
    body: str,
    is_pinned: bool = False,
) -> tuple[Broadcast, BroadcastChannel]:
    settings = get_settings()

    if scope == BroadcastScope.DEPARTMENT:
        if not role_has_permission(actor.role, "broadcast:send_department") or actor.department_id is None:
            raise AccessDeniedError("ليست لديك صلاحية نشر تبليغات القسم")
        department = db.get(Department, actor.department_id)
        if department is None:
            raise NotFoundError("القسم غير موجود")
        channel = get_or_create_department_channel(db, department)
    else:
        if not role_has_permission(actor.role, "broadcast:send_course"):
            raise AccessDeniedError("ليست لديك صلاحية نشر تبليغات المواد")
        if course_id is None:
            raise BusinessRuleError("حدد المادة لنشر التبليغ فيها")
        course = db.get(Course, course_id)
        if course is None:
            raise NotFoundError("المادة غير موجودة")
        ensure_course_access(db, actor, course.id)
        channel = get_or_create_course_channel(db, course)

    audience = audience_user_ids(db, channel)
    broadcast = Broadcast(
        channel_id=channel.id,
        author_user_id=actor.id,
        title=title.strip()[:255],
        body=body.strip()[: settings.broadcast_body_max_chars],
        is_pinned=is_pinned,
        audience_count=len(audience),
    )
    db.add(broadcast)
    db.flush()

    enqueue(
        db,
        audience,
        notification_type=NotificationType.BROADCAST,
        title=f"تبليغ: {broadcast.title}"[:255],
        body=broadcast.body[:500],
        scheduled_for=utc_now(),
    )
    db.commit()
    db.refresh(broadcast)
    return broadcast, channel


def visible_broadcasts(db: Session, user: User, limit: int = 200) -> list[tuple[Broadcast, BroadcastChannel]]:
    rows = db.execute(
        select(Broadcast, BroadcastChannel)
        .join(BroadcastChannel, BroadcastChannel.id == Broadcast.channel_id)
        .order_by(Broadcast.is_pinned.desc(), Broadcast.created_at.desc())
        .limit(limit)
    ).all()
    return [(b, c) for b, c in rows if can_view(db, user, c)]


def mark_read(db: Session, user: User, broadcast_id: int) -> Broadcast:
    broadcast = db.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise NotFoundError("التبليغ غير موجود")
    if user.role not in STUDENT_ROLES:
        raise AccessDeniedError("قراءة التبليغات تُسجَّل للطلاب فقط")
    channel = db.get(BroadcastChannel, broadcast.channel_id)
    if not is_in_audience(db, user, channel):
        raise AccessDeniedError("هذا التبليغ ليس موجهاً إليك")

    already = db.scalar(
        select(BroadcastRead.id).where(
            BroadcastRead.broadcast_id == broadcast.id,
            BroadcastRead.user_id == user.id,
        )
    )
    if already is not None:
        return broadcast

    try:
        db.add(BroadcastRead(broadcast_id=broadcast.id, user_id=user.id))
        db.flush()
        # زيادة ذرية للعداد، فلا تتأثر بالتزامن بين الطلاب
        db.execute(
            update(Broadcast)
            .where(Broadcast.id == broadcast.id)
            .values(seen_count=Broadcast.seen_count + 1)
        )
        db.commit()
    except IntegrityError:
        # قراءة متزامنة من الجهاز نفسه: السجل موجود بالفعل
        db.rollback()

    db.refresh(broadcast)
    return broadcast


def list_readers(db: Session, actor: User, broadcast_id: int) -> list[tuple[str, object]]:
    broadcast = db.get(Broadcast, broadcast_id)
    if broadcast is None:
        raise NotFoundError("التبليغ غير موجود")
    channel = db.get(BroadcastChannel, broadcast.channel_id)
    if not _can_manage(db, actor, broadcast, channel):
        raise AccessDeniedError("لا تملك صلاحية عرض قائمة القراءة")

    rows = db.execute(
        select(User.full_name, BroadcastRead.read_at)
        .join(User, User.id == BroadcastRead.user_id)
        .where(BroadcastRead.broadcast_id == broadcast.id)
        .order_by(BroadcastRead.read_at)
    ).all()
    return [(name, read_at) for name, read_at in rows]