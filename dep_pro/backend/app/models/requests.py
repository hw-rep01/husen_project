from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base
from app.db.types import VectorType
from app.models.enums import RequestCategory, RequestStatus, RoutingStage

EMBEDDING_DIM = get_settings().embedding_dimension


class RequestBatch(Base):
    """بطاقة موحدة تجمع طلبات متشابهة دلالياً وتُلخَّص بصياغة رسمية."""

    __tablename__ = "request_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True)
    category: Mapped[RequestCategory] = mapped_column(Enum(RequestCategory, native_enum=False, length=16))
    title: Mapped[str] = mapped_column(String(255))
    formal_summary: Mapped[str] = mapped_column(Text)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    centroid: Mapped[list[float] | None] = mapped_column(VectorType(EMBEDDING_DIM), nullable=True)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, native_enum=False, length=32), default=RequestStatus.IN_SECTION_REVIEW
    )
    current_stage: Mapped[RoutingStage] = mapped_column(
        Enum(RoutingStage, native_enum=False, length=32), default=RoutingStage.CLASS_REPRESENTATIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    requests: Mapped[list["StudentRequest"]] = relationship(back_populates="batch", foreign_keys="StudentRequest.batch_id")
    events: Mapped[list["RequestEvent"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class StudentRequest(Base):
    """الطلب أو الشكوى الموحدة التي يكتبها الطالب."""

    __tablename__ = "student_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[RequestCategory | None] = mapped_column(
        Enum(RequestCategory, native_enum=False, length=16), nullable=True
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, native_enum=False, length=32), default=RequestStatus.SUBMITTED, index=True
    )
    current_stage: Mapped[RoutingStage] = mapped_column(
        Enum(RoutingStage, native_enum=False, length=32), default=RoutingStage.CLASS_REPRESENTATIVE
    )
    embedding: Mapped[list[float] | None] = mapped_column(VectorType(EMBEDDING_DIM), nullable=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("request_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    batch: Mapped["RequestBatch | None"] = relationship(back_populates="requests", foreign_keys=[batch_id])
    events: Mapped[list["RequestEvent"]] = relationship(back_populates="request", cascade="all, delete-orphan")


class RequestEvent(Base):
    """سجل مسار الطلب: من تصرف، ومن أي مرحلة إلى أي مرحلة، ومع أي ملاحظة."""

    __tablename__ = "request_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_requests.id", ondelete="CASCADE"), nullable=True, index=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("request_batches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    from_stage: Mapped[RoutingStage | None] = mapped_column(
        Enum(RoutingStage, native_enum=False, length=32), nullable=True
    )
    to_stage: Mapped[RoutingStage | None] = mapped_column(
        Enum(RoutingStage, native_enum=False, length=32), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    request: Mapped["StudentRequest | None"] = relationship(back_populates="events")
    batch: Mapped["RequestBatch | None"] = relationship(back_populates="events")