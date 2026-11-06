import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    ClusterSource,
    CourseInstructor,
    Enrollment,
    GapAlert,
    GapAlertStatus,
    Notification,
    NotificationStatus,
    NotificationType,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizQuestion,
    Semester,
    StudentQuestion,
    TopicCluster,
    TopicClusterMember,
    User,
    UserRole,
)
from app.services.common.vector_math import cosine_similarity, normalize_rows, to_matrix
from app.services.errors import NotFoundError
from app.services.gaps.clustering import centroid_of, cluster_embeddings, most_central_index

logger = logging.getLogger(__name__)

STUDENT_ROLES = [UserRole.STUDENT, UserRole.CLASS_REPRESENTATIVE]


@dataclass(frozen=True)
class ClusterItem:
    source: ClusterSource
    source_id: int
    student_id: int
    text: str
    embedding: list[float]


@dataclass(frozen=True)
class RadarRunResult:
    course_id: int
    section_id: int
    semester_id: int
    section_student_total: int
    item_count: int
    cluster_count: int
    alerts_created: int
    alerts_updated: int


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _section_student_total(db: Session, section_id: int) -> int:
    total = db.scalar(
        select(func.count(User.id)).where(
            User.section_id == section_id,
            User.role.in_(STUDENT_ROLES),
            User.is_active.is_(True),
        )
    )
    return int(total or 0)


def _collect_items(db: Session, course_id: int, section_id: int, semester: Semester) -> list[ClusterItem]:
    start = _as_aware(semester.starts_on)
    end = _as_aware(semester.ends_on)
    items: list[ClusterItem] = []

    question_rows = db.execute(
        select(
            StudentQuestion.id,
            StudentQuestion.student_id,
            StudentQuestion.question_text,
            StudentQuestion.embedding,
        ).where(
            StudentQuestion.course_id == course_id,
            StudentQuestion.section_id == section_id,
            StudentQuestion.created_at >= start,
            StudentQuestion.created_at <= end,
            StudentQuestion.embedding.is_not(None),
        )
    ).all()
    for item_id, student_id, text, embedding in question_rows:
        items.append(ClusterItem(ClusterSource.STUDENT_QUESTION, item_id, student_id, text, embedding))

    mistake_rows = db.execute(
        select(
            QuizAnswer.id,
            QuizAttempt.student_id,
            QuizQuestion.question_text,
            QuizQuestion.embedding,
        )
        .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
        .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
        .join(Quiz, Quiz.id == QuizQuestion.quiz_id)
        .join(User, User.id == QuizAttempt.student_id)
        .where(
            Quiz.course_id == course_id,
            User.section_id == section_id,
            QuizAnswer.is_correct.is_(False),
            QuizAttempt.submitted_at >= start,
            QuizAttempt.submitted_at <= end,
            QuizQuestion.embedding.is_not(None),
        )
    ).all()
    for answer_id, student_id, text, embedding in mistake_rows:
        items.append(ClusterItem(ClusterSource.QUIZ_MISTAKE, answer_id, student_id, text, embedding))

    return items


def build_alert_summary(label: str, distinct: int, total: int, ratio: float) -> str:
    return (
        f"تم رصد موضوع تكرر في أسئلة أو أخطاء {distinct} طالباً من أصل {total} طالباً في الشعبة "
        f"(بنسبة {ratio:.0%}): «{label}». يُنصح بمراجعة هذا الموضوع في المحاضرة القادمة."
    )


def _upsert_gap_alert(
    db: Session,
    *,
    course_id: int,
    section_id: int,
    semester_id: int,
    instructor_id: int,
    cluster_id: int,
    label: str,
    centroid: list[float],
    distinct: int,
    total: int,
    ratio: float,
    now: datetime,
) -> str:
    """
    يحدّث تنبيهاً قائماً إذا كان الموضوع نفسه (تشابه المركز أعلى من الحد)،
    وإلا ينشئ تنبيهاً جديداً ويرسل إشعاراً للدكتور.
    """
    settings = get_settings()
    open_alerts = db.scalars(
        select(GapAlert).where(
            GapAlert.course_id == course_id,
            GapAlert.section_id == section_id,
            GapAlert.semester_id == semester_id,
            GapAlert.instructor_id == instructor_id,
            GapAlert.status != GapAlertStatus.RESOLVED,
            GapAlert.centroid.is_not(None),
        )
    ).all()

    best: GapAlert | None = None
    best_similarity = settings.gap_alert_merge_similarity
    for alert in open_alerts:
        similarity = cosine_similarity(alert.centroid, centroid)
        if similarity >= best_similarity:
            best, best_similarity = alert, similarity

    summary = build_alert_summary(label, distinct, total, ratio)

    if best is not None:
        best.cluster_id = cluster_id
        best.topic_label = label
        best.centroid = centroid
        best.distinct_student_count = distinct
        best.section_student_total = total
        best.affected_ratio = round(ratio, 4)
        best.summary = summary
        return "alerts_updated"

    db.add(
        GapAlert(
            course_id=course_id,
            section_id=section_id,
            semester_id=semester_id,
            instructor_id=instructor_id,
            cluster_id=cluster_id,
            topic_label=label,
            centroid=centroid,
            distinct_student_count=distinct,
            section_student_total=total,
            affected_ratio=round(ratio, 4),
            summary=summary,
            status=GapAlertStatus.OPEN,
        )
    )
    db.add(
        Notification(
            recipient_user_id=instructor_id,
            notification_type=NotificationType.GAP_ALERT,
            title="تنبيه: موضوع يحتاج مراجعة",
            body=summary,
            scheduled_for=now,
            status=NotificationStatus.PENDING,
        )
    )
    return "alerts_created"


def run_radar_for_scope(db: Session, course_id: int, section_id: int, semester_id: int) -> RadarRunResult:
    settings = get_settings()
    semester = db.get(Semester, semester_id)
    if semester is None:
        raise NotFoundError("الفصل الدراسي غير موجود")

    section_total = _section_student_total(db, section_id)

    # العناقيد تُعاد حسابها بالكامل لهذا النطاق، أما التنبيهات فمستقلة ولا تُمسح
    db.execute(
        delete(TopicCluster).where(
            TopicCluster.course_id == course_id,
            TopicCluster.section_id == section_id,
            TopicCluster.semester_id == semester_id,
        )
    )

    items = [item for item in _collect_items(db, course_id, section_id, semester) if item.embedding]
    cluster_count = 0
    alerts_created = 0
    alerts_updated = 0

    if section_total > 0 and len(items) >= settings.gap_min_members:
        vectors = to_matrix([item.embedding for item in items])
        labels = cluster_embeddings(vectors, settings.gap_cluster_similarity)
        instructor_ids = list(
            db.scalars(select(CourseInstructor.instructor_id).where(CourseInstructor.course_id == course_id))
        )
        now = datetime.now(timezone.utc)

        for label in sorted(set(labels.tolist())):
            indices = np.flatnonzero(labels == label)
            group = [items[int(i)] for i in indices]
            group_vectors = vectors[indices]

            distinct = len({member.student_id for member in group})
            ratio = distinct / section_total
            centroid = centroid_of(group_vectors)
            representative = group[most_central_index(group_vectors, centroid)]

            cluster = TopicCluster(
                course_id=course_id,
                section_id=section_id,
                semester_id=semester_id,
                label=representative.text[:255],
                centroid=centroid.tolist(),
                member_count=len(group),
                distinct_student_count=distinct,
                section_student_total=section_total,
                affected_ratio=round(ratio, 4),
            )
            db.add(cluster)
            db.flush()

            similarities = normalize_rows(group_vectors) @ centroid
            for member, similarity in zip(group, similarities.tolist()):
                db.add(
                    TopicClusterMember(
                        cluster_id=cluster.id,
                        source=member.source,
                        source_id=member.source_id,
                        student_id=member.student_id,
                        similarity=round(float(similarity), 4),
                    )
                )
            cluster_count += 1

            if ratio > settings.gap_alert_threshold and distinct >= settings.gap_min_members:
                for instructor_id in instructor_ids:
                    outcome = _upsert_gap_alert(
                        db,
                        course_id=course_id,
                        section_id=section_id,
                        semester_id=semester_id,
                        instructor_id=instructor_id,
                        cluster_id=cluster.id,
                        label=cluster.label,
                        centroid=cluster.centroid,
                        distinct=distinct,
                        total=section_total,
                        ratio=ratio,
                        now=now,
                    )
                    if outcome == "alerts_created":
                        alerts_created += 1
                    else:
                        alerts_updated += 1

    db.commit()
    return RadarRunResult(
        course_id=course_id,
        section_id=section_id,
        semester_id=semester_id,
        section_student_total=section_total,
        item_count=len(items),
        cluster_count=cluster_count,
        alerts_created=alerts_created,
        alerts_updated=alerts_updated,
    )


def _active_scopes(db: Session, course_id: int | None = None) -> set[tuple[int, int, int]]:
    stmt = (
        select(Enrollment.course_id, Enrollment.section_id, Enrollment.semester_id)
        .join(Semester, Semester.id == Enrollment.semester_id)
        .where(Semester.is_active.is_(True))
    )
    if course_id is not None:
        stmt = stmt.where(Enrollment.course_id == course_id)
    return {(int(c), int(s), int(m)) for c, s, m in db.execute(stmt).all()}


def run_radar_for_course(db: Session, course_id: int) -> list[RadarRunResult]:
    return [
        run_radar_for_scope(db, c, s, m)
        for c, s, m in sorted(_active_scopes(db, course_id))
    ]


def run_radar_all_active(db: Session) -> list[RadarRunResult]:
    results: list[RadarRunResult] = []
    for course_id, section_id, semester_id in sorted(_active_scopes(db)):
        try:
            results.append(run_radar_for_scope(db, course_id, section_id, semester_id))
        except Exception:
            db.rollback()
            logger.exception(
                "فشل تشغيل الرادار للنطاق course=%s section=%s semester=%s",
                course_id, section_id, semester_id,
            )
    return results