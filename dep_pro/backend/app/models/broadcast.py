from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import BroadcastScope


class BroadcastChannel(Base):
    """قناة تبليغ رسمية: قسم كامل أو مادة محددة."""

    __tablename__ = "broadcast_channels"
    __table_args__ = (UniqueConstraint("scope", "department_id", "course_id", name="uq_channel_scope_target"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[BroadcastScope] = mapped_column(Enum(BroadcastScope, native_enum=False, length=16))
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    broadcasts: Mapped[list["Broadcast"]] = relationship(back_populates="channel", cascade="all, delete-orphan")


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("broadcast_channels.id", ondelete="CASCADE"), index=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    audience_count: Mapped[int] = mapped_column(Integer, default=0)
    seen_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    channel: Mapped["BroadcastChannel"] = relationship(back_populates="broadcasts")
    reads: Mapped[list["BroadcastRead"]] = relationship(back_populates="broadcast", cascade="all, delete-orphan")


class BroadcastRead(Base):
    """سجل القراءة الفردي: من قرأ التبليغ ومتى، ليظهر في عداد القراءة."""

    __tablename__ = "broadcast_reads"
    __table_args__ = (UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_read_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    broadcast: Mapped["Broadcast"] = relationship(back_populates="reads")