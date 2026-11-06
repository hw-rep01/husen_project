from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class BusyBlock:
    occurrence_id: int | None
    local_date: date
    starts_at: datetime
    ends_at: datetime
    room_id: int | None
    section_id: int
    instructor_ids: frozenset[int]


@dataclass(frozen=True)
class AbsenceBlock:
    starts_at: datetime
    ends_at: datetime
    user_id: int | None
    room_id: int | None


@dataclass(frozen=True)
class ScheduleSnapshot:
    busy: tuple[BusyBlock, ...] = ()
    absences: tuple[AbsenceBlock, ...] = ()


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """فترتان تتعارضان إذا تداخلتا فعلاً. الحصة التي تنتهي 09:30 لا تتعارض مع التي تبدأ 09:30."""
    return a_start < b_end and b_start < a_end


def find_conflicts(proposed: BusyBlock, snapshot: ScheduleSnapshot) -> list[str]:
    reasons: set[str] = set()

    for block in snapshot.busy:
        if proposed.occurrence_id is not None and block.occurrence_id == proposed.occurrence_id:
            continue
        if not overlaps(proposed.starts_at, proposed.ends_at, block.starts_at, block.ends_at):
            continue
        if block.section_id == proposed.section_id:
            reasons.add("الشعبة لديها محاضرة أخرى في هذا الوقت")
        if proposed.room_id is not None and block.room_id == proposed.room_id:
            reasons.add("القاعة مشغولة في هذا الوقت")
        if proposed.instructor_ids & block.instructor_ids:
            reasons.add("الدكتور لديه محاضرة أخرى في هذا الوقت")

    for absence in snapshot.absences:
        if not overlaps(proposed.starts_at, proposed.ends_at, absence.starts_at, absence.ends_at):
            continue
        if absence.room_id is not None and absence.room_id == proposed.room_id:
            reasons.add("القاعة معطلة بسبب صيانة أو غياب معلن")
        if absence.user_id is not None and absence.user_id in proposed.instructor_ids:
            reasons.add("الدكتور في غياب معلن")

    return sorted(reasons)