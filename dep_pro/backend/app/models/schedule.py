from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ChangeType, ScheduleSlotType, Weekday


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (UniqueConstraint("department_id", "code", name="uq_room_code_per_dept"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(255))
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    is_available: Mapped[bool] = mapped_column(default=True)


class TimeSlot(Base):
    __tablename__ = "time_slots"
    __table_args__ = (UniqueConstraint("starts_at", "ends_at", name="uq_time_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    label: Mapped[str] = mapped_column(String(32))


class WeeklyScheduleEntry(Base):
    __tablename__ = "weekly_schedule_entries"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "weekday", "time_slot_id", name="uq_weekly_entry"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True, index=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slots.id", ondelete="RESTRICT"), index=True)
    weekday: Mapped[Weekday] = mapped_column(Enum(Weekday, native_enum=False, length=16))

    enrollment: Mapped["Enrollment"] = relationship()
    room: Mapped["Room | None"] = relationship()
    time_slot: Mapped["TimeSlot"] = relationship()


class LectureOccurrence(Base):
    __tablename__ = "lecture_occurrences"
    __table_args__ = (
        UniqueConstraint("weekly_entry_id", "occurrence_date", name="uq_occurrence_per_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    weekly_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_schedule_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), index=True)
    occurrence_date: Mapped[date] = mapped_column(Date, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True, index=True)
    slot_type: Mapped[ScheduleSlotType] = mapped_column(
        Enum(ScheduleSlotType, native_enum=False, length=16), default=ScheduleSlotType.REGULAR
    )
    is_cancelled: Mapped[bool] = mapped_column(default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    enrollment: Mapped["Enrollment"] = relationship()
    room: Mapped["Room | None"] = relationship()
    change_logs: Mapped[list["ScheduleChangeLog"]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )


class ScheduleChangeLog(Base):
    __tablename__ = "schedule_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurrence_id: Mapped[int] = mapped_column(ForeignKey("lecture_occurrences.id", ondelete="CASCADE"), index=True)
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    change_type: Mapped[ChangeType] = mapped_column(Enum(ChangeType, native_enum=False, length=32))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    occurrence: Mapped["LectureOccurrence"] = relationship(back_populates="change_logs")


class MakeupSuggestion(Base):
    __tablename__ = "makeup_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id", ondelete="CASCADE"), index=True)
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    suggested_date: Mapped[date] = mapped_column(Date)
    suggested_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    suggested_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    suggested_room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(default=0.0)
    is_accepted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Absence(Base):
    __tablename__ = "absences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=True, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)