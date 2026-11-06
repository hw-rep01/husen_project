from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import role_has_permission
from app.models import (
    CourseInstructor,
    RequestBatch,
    RequestCategory,
    RequestStatus,
    RoutingStage,
    Section,
    StudentRequest,
    User,
    UserRole,
)
from app.services.access import ensure_course_access
from app.services.errors import AccessDeniedError, BusinessRuleError, NotFoundError
from app.services.triage.deduplication import attach_on_submit, consolidate_section, refresh_batch_summary
from app.services.triage.events import record_event
from app.services.triage.notify import notify_stage, notify_students
from app.services.triage.routing import (
    STAGE_ROLE,
    TERMINAL_STATUSES,
    Action,
    DECISION_STATUS,
    next_stage,
    permission_for,
    validate_action,
)

REP = RoutingStage.CLASS_REPRESENTATIVE
INSTRUCTOR = RoutingStage.INSTRUCTOR
COORDINATOR = RoutingStage.DEPARTMENT_COORDINATOR
HEAD = RoutingStage.DEPARTMENT_HEAD

STAGE_LABELS: dict[RoutingStage, str] = {
    REP: "ممثل الشعبة",
    INSTRUCTOR: "أستاذ المادة",
    COORDINATOR: "مقرر القسم",
    HEAD: "رئيس القسم",
}

DECISION_LABELS: dict[RequestStatus, str] = {
    RequestStatus.APPROVED: "موافقة",
    RequestStatus.REJECTED: "رفض",
    RequestStatus.RESOLVED: "تمت المعالجة",
}


@dataclass
class Unit:
    """الوحدة المُعالَجة: إما بطاقة موحدة وأعضاؤها، وإما طلب منفرد."""

    batch: RequestBatch | None
    requests: list[StudentRequest]

    @property
    def section_id(self) -> int:
        return self.requests[0].section_id

    @property
    def category(self) -> RequestCategory | None:
        return self.batch.category if self.batch is not None else self.requests[0].category

    @property
    def course_id(self) -> int | None:
        return self.batch.course_id if self.batch is not None else self.requests[0].course_id

    @property
    def stage(self) -> RoutingStage:
        return self.batch.current_stage if self.batch is not None else self.requests[0].current_stage

    @property
    def status(self) -> RequestStatus:
        return self.batch.status if self.batch is not None else self.requests[0].status

    @property
    def title(self) -> str:
        return self.batch.title if self.batch is not None else self.requests[0].subject

    @property
    def summary(self) -> str:
        return self.batch.formal_summary if self.batch is not None else self.requests[0].body

    def set_course(self, course_id: int) -> None:
        if self.batch is not None:
            self.batch.course_id = course_id
        for request in self.requests:
            request.course_id = course_id

    def set_position(self, stage: RoutingStage, status: RequestStatus) -> None:
        if self.batch is not None:
            self.batch.current_stage = stage
            self.batch.status = status
        for request in self.requests:
            request.current_stage = stage
            request.status = status


def load_unit(db: Session, *, request_id: int | None = None, batch_id: int | None = None) -> Unit:
    if batch_id is not None:
        batch = db.get(RequestBatch, batch_id)
        if batch is None:
            raise NotFoundError("البطاقة الموحدة غير موجودة")
        members = list(
            db.scalars(
                select(StudentRequest)
                .where(StudentRequest.batch_id == batch.id)
                .order_by(StudentRequest.id)
            ).all()
        )
        if not members:
            raise NotFoundError("البطاقة الموحدة لا تحتوي على طلبات")
        return Unit(batch=batch, requests=members)

    request = db.get(StudentRequest, request_id)
    if request is None:
        raise NotFoundError("الطلب غير موجود")
    if request.batch_id is not None:
        raise BusinessRuleError("هذا الطلب ضمن بطاقة موحدة، أجرِ الإجراء على البطاقة")
    return Unit(batch=None, requests=[request])


def _assert_actor(actor: User, stage: RoutingStage, action: Action) -> None:
    if actor.role != STAGE_ROLE[stage]:
        raise AccessDeniedError("هذه المرحلة لا تخص دورك")
    if not role_has_permission(actor.role, permission_for(stage, action)):
        raise AccessDeniedError("ليست لديك صلاحية لهذا الإجراء")


def _assert_scope(db: Session, actor: User, unit: Unit) -> None:
    stage = unit.stage
    if stage == REP:
        allowed = actor.section_id is not None and actor.section_id == unit.section_id
    elif stage == INSTRUCTOR:
        allowed = unit.course_id is not None and db.scalar(
            select(CourseInstructor.id).where(
                CourseInstructor.course_id == unit.course_id,
                CourseInstructor.instructor_id == actor.id,
            )
        ) is not None
    else:
        section = db.get(Section, unit.section_id)
        allowed = section is not None and actor.department_id is not None and (
            actor.department_id == section.department_id
        )
    if not allowed:
        raise AccessDeniedError("الطلب خارج نطاق صلاحياتك")


def _log(
    db: Session,
    unit: Unit,
    *,
    actor_id: int,
    action: str,
    from_stage: RoutingStage,
    to_stage: RoutingStage,
    note: str | None,
) -> None:
    batch_id = unit.batch.id if unit.batch is not None else None
    for request in unit.requests:
        record_event(
            db,
            action=action,
            actor_user_id=actor_id,
            request_id=request.id,
            batch_id=batch_id,
            from_stage=from_stage,
            to_stage=to_stage,
            note=note,
        )
    if batch_id is not None:
        record_event(
            db,
            action=action,
            actor_user_id=actor_id,
            batch_id=batch_id,
            from_stage=from_stage,
            to_stage=to_stage,
            note=note,
        )


def perform_action(
    db: Session,
    actor: User,
    *,
    action: Action,
    request_id: int | None = None,
    batch_id: int | None = None,
    course_id: int | None = None,
    note: str | None = None,
) -> Unit:
    unit = load_unit(db, request_id=request_id, batch_id=batch_id)

    category = unit.category
    if category is None:
        raise BusinessRuleError("يجب تصنيف الطلب قبل إجراء أي خطوة عليه")
    if unit.status in TERMINAL_STATUSES:
        raise BusinessRuleError("الطلب مغلق ولا يقبل إجراءات جديدة")

    stage = unit.stage
    validate_action(category, stage, action)
    _assert_actor(actor, stage, action)
    _assert_scope(db, actor, unit)

    now = datetime.now(timezone.utc)

    if action == Action.FORWARD:
        target = next_stage(category, stage)
        if target is None:
            raise BusinessRuleError("لا توجد مرحلة تالية لهذا الطلب")

        if category == RequestCategory.ACADEMIC and stage == REP:
            chosen_course = course_id if course_id is not None else unit.course_id
            if chosen_course is None:
                raise BusinessRuleError("حدد المادة قبل إحالة الطلب الأكاديمي إلى الدكتور")
            ensure_course_access(db, actor, chosen_course)
            unit.set_course(chosen_course)

        new_status = RequestStatus.FORWARDED if stage == REP else RequestStatus.IN_REVIEW
        unit.set_position(target, new_status)
        _log(db, unit, actor_id=actor.id, action="forwarded", from_stage=stage, to_stage=target, note=note)

        notify_stage(
            db,
            target,
            unit.section_id,
            unit.course_id,
            title="طلب جديد بانتظار مراجعتك",
            body=f"{unit.title}" + (f" ({len(unit.requests)} طلباً)" if unit.batch is not None else ""),
            now=now,
        )
        notify_students(
            db,
            {r.student_id for r in unit.requests},
            title="تم تحديث حالة طلبك",
            body=f"تم رفع طلبك إلى: {STAGE_LABELS[target]}",
            now=now,
        )
    else:
        status = DECISION_STATUS[action]
        unit.set_position(stage, status)
        _log(db, unit, actor_id=actor.id, action=action.value, from_stage=stage, to_stage=stage, note=note)

        decision_text = DECISION_LABELS[status]
        notify_students(
            db,
            {r.student_id for r in unit.requests},
            title="تم البت في طلبك",
            body=f"القرار: {decision_text}" + (f". ملاحظة: {note}" if note else ""),
            now=now,
        )

    db.commit()
    return unit


def classify_by_representative(
    db: Session,
    actor: User,
    *,
    request_id: int,
    category: RequestCategory,
) -> StudentRequest:
    request = db.get(StudentRequest, request_id)
    if request is None:
        raise NotFoundError("الطلب غير موجود")
    if actor.role != UserRole.CLASS_REPRESENTATIVE or not role_has_permission(actor.role, "request:merge_review"):
        raise AccessDeniedError("ليست لديك صلاحية تصنيف الطلبات")
    if actor.section_id != request.section_id:
        raise AccessDeniedError("الطلب خارج شعبتك")
    if request.batch_id is not None:
        raise BusinessRuleError("لا يمكن تغيير تصنيف طلب ضمن بطاقة موحدة")
    if request.current_stage != REP or request.status in TERMINAL_STATUSES:
        raise BusinessRuleError("لا يمكن تصنيف الطلب في مرحلته الحالية")

    previous = request.category.value if request.category else "none"
    request.category = category
    record_event(
        db,
        action="classified",
        actor_user_id=actor.id,
        request_id=request.id,
        from_stage=REP,
        to_stage=REP,
        note=f"{previous} -> {category.value}",
    )
    db.flush()
    attach_on_submit(db, request, actor.id)
    db.commit()
    db.refresh(request)
    return request


def consolidate_for_representative(db: Session, actor: User) -> int:
    if actor.role != UserRole.CLASS_REPRESENTATIVE or actor.section_id is None:
        raise AccessDeniedError("هذا الإجراء لممثل الشعبة فقط")
    return consolidate_section(db, actor.section_id, actor.id)


def refresh_for_representative(db: Session, actor: User, batch_id: int) -> Unit:
    unit = load_unit(db, batch_id=batch_id)
    if actor.role != UserRole.CLASS_REPRESENTATIVE or actor.section_id != unit.section_id:
        raise AccessDeniedError("الطلب خارج شعبتك")
    if unit.stage != REP:
        raise BusinessRuleError("لا يمكن تحديث ملخص بطاقة أُحيلت بالفعل")
    refresh_batch_summary(db, unit.batch)
    return load_unit(db, batch_id=batch_id)