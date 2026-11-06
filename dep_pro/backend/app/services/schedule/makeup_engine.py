from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta

from app.services.common.timeutil import local_to_utc
from app.services.schedule.conflicts import BusyBlock, ScheduleSnapshot, find_conflicts


@dataclass(frozen=True)
class SlotSpec:
    slot_id: int
    start: time
    end: time
    order: int


@dataclass(frozen=True)
class RoomSpec:
    room_id: int
    code: str
    capacity: int
    preferred: bool = False


@dataclass(frozen=True)
class MakeupQuery:
    section_id: int
    section_size: int
    instructor_ids: frozenset[int]
    from_date: date
    days_ahead: int
    reference_date: date
    excluded_weekdays: frozenset[int]


@dataclass(frozen=True)
class MakeupCandidate:
    local_date: date
    slot_id: int
    starts_at: datetime
    ends_at: datetime
    room_id: int
    room_code: str
    score: float


def find_makeup_candidates(
    query: MakeupQuery,
    slots: list[SlotSpec],
    rooms: list[RoomSpec],
    snapshot: ScheduleSnapshot,
    limit: int,
) -> list[MakeupCandidate]:
    """
    القيود الصلبة: لا تعارض مع الشعبة أو الدكتور أو القاعة أو الغياب، ولا يوم مستثنى.
    الترتيب (الأقل درجة أفضل):
      - القرب من تاريخ المحاضرة الأصلية (كل يوم = 1)
      - الفترة المبكرة في اليوم أولى قليلاً
      - ملاءمة السعة: قاعة أقرب إلى حجم الشعبة أفضل، وتُقص الزيادة عند 5 أضعاف
      - القاعة المعتادة للمادة تحصل على مكافأة صغيرة
    لكل فترة تُختار أفضل قاعة متاحة فقط، فتتنوع الاقتراحات في الأوقات.
    """
    ordered_rooms = sorted(rooms, key=lambda r: (not r.preferred, r.capacity, r.room_id))
    size = max(query.section_size, 1)
    candidates: list[MakeupCandidate] = []

    for offset in range(query.days_ahead + 1):
        day = query.from_date + timedelta(days=offset)
        if day.weekday() in query.excluded_weekdays:
            continue

        for slot in sorted(slots, key=lambda s: s.order):
            base = BusyBlock(
                occurrence_id=None,
                local_date=day,
                starts_at=local_to_utc(day, slot.start),
                ends_at=local_to_utc(day, slot.end),
                room_id=None,
                section_id=query.section_id,
                instructor_ids=query.instructor_ids,
            )
            if find_conflicts(base, snapshot):
                continue

            for room in ordered_rooms:
                proposed = replace(base, room_id=room.room_id)
                if find_conflicts(proposed, snapshot):
                    continue
                slack = min((room.capacity - query.section_size) / size, 5.0)
                score = (
                    abs((day - query.reference_date).days)
                    + slot.order * 0.1
                    + slack * 0.5
                    - (0.5 if room.preferred else 0.0)
                )
                candidates.append(
                    MakeupCandidate(
                        local_date=day,
                        slot_id=slot.slot_id,
                        starts_at=proposed.starts_at,
                        ends_at=proposed.ends_at,
                        room_id=room.room_id,
                        room_code=room.code,
                        score=round(score, 3),
                    )
                )
                break

    candidates.sort(key=lambda c: (c.score, c.local_date, c.starts_at))
    return candidates[:limit]