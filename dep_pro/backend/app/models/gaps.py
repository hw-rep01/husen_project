from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base
from app.db.types import VectorType
from app.models.enums import ClusterSource, GapAlertStatus

EMBEDDING_DIM = get_settings().embedding_dimension


class TopicCluster(Base):
    """مجموعة من الأسئلة/الأخطاء المتشابهة دلالياً ضمن مادة وشعبة في فصل معين. تُعاد حسابها في كل تشغيل."""

    __tablename__ = "topic_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(255))
    centroid: Mapped[list[float] | None] = mapped_column(VectorType(EMBEDDING_DIM), nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    distinct_student_count: Mapped[int] = mapped_column(Integer, default=0)
    section_student_total: Mapped[int] = mapped_column(Integer, default=0)
    affected_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    members: Mapped[list["TopicClusterMember"]] = relationship(back_populates="cluster", cascade="all, delete-orphan")


class TopicClusterMember(Base):
    __tablename__ = "topic_cluster_members"
    __table_args__ = (UniqueConstraint("cluster_id", "source", "source_id", name="uq_cluster_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("topic_clusters.id", ondelete="CASCADE"), index=True)
    source: Mapped[ClusterSource] = mapped_column(Enum(ClusterSource, native_enum=False, length=32))
    source_id: Mapped[int] = mapped_column(Integer)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    similarity: Mapped[float] = mapped_column(Float, default=0.0)

    cluster: Mapped["TopicCluster"] = relationship(back_populates="members")


class GapAlert(Base):
    """
    تنبيه للدكتور عن موضوع تجاوز نسبة الطلاب المتأثرين الحد المحدد.
    يحمل لقطته الخاصة (الموضوع، المركز، الإحصاءات) فلا يتأثر بإعادة حساب العناقيد.
    """

    __tablename__ = "gap_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), index=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("topic_clusters.id", ondelete="SET NULL"), nullable=True
    )
    topic_label: Mapped[str] = mapped_column(String(255))
    centroid: Mapped[list[float] | None] = mapped_column(VectorType(EMBEDDING_DIM), nullable=True)
    distinct_student_count: Mapped[int] = mapped_column(Integer, default=0)
    section_student_total: Mapped[int] = mapped_column(Integer, default=0)
    affected_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[GapAlertStatus] = mapped_column(
        Enum(GapAlertStatus, native_enum=False, length=16), default=GapAlertStatus.OPEN
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
