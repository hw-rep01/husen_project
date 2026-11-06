from datetime import date, time

import pytest

from app.core.permissions import role_has_permission
from app.models import RequestCategory, RoutingStage, UserRole
from app.services.common.timeutil import local_day_bounds, local_to_utc
from app.services.errors import AccessDeniedError, BusinessRuleError
from app.services.schedule.conflicts import AbsenceBlock, BusyBlock, ScheduleSnapshot, find_conflicts, overlaps
from app.services.schedule.makeup_engine import MakeupQuery, RoomSpec, SlotSpec, find_makeup_candidates
from app.services.triage.routing import Action, next_stage, permission_for, validate_action
from app.services.triage.classifier import classify_request
from app.services.triage.summarizer import summarize_batch

DAY = date(2030, 1, 7)  # يوم اثنين


def _block(occ_id, start, end, room, section=1, instructors=frozenset({10})):
    return BusyBlock(occ_id, DAY, local_to_utc(DAY, start), local_to_utc(DAY, end), room, section, instructors)


# ---------- الصلاحيات والمسارات ----------

def test_academic_path_ends_at_instructor():
    assert next_stage(RequestCategory.ACADEMIC, RoutingStage.CLASS_REPRESENTATIVE) == RoutingStage.INSTRUCTOR
    assert next_stage(RequestCategory.ACADEMIC, RoutingStage.INSTRUCTOR) is None


def test_administrative_path_goes_through_coordinator_to_head():
    adm = RequestCategory.ADMINISTRATIVE
    assert next_stage(adm, RoutingStage.CLASS_REPRESENTATIVE) == RoutingStage.DEPARTMENT_COORDINATOR
    assert next_stage(adm, RoutingStage.DEPARTMENT_COORDINATOR) == RoutingStage.DEPARTMENT_HEAD
    assert next_stage(adm, RoutingStage.DEPARTMENT_HEAD) is None


def test_representative_cannot_decide_academic():
    with pytest.raises(BusinessRuleError):
        validate_action(RequestCategory.ACADEMIC, RoutingStage.CLASS_REPRESENTATIVE, Action.APPROVE)


def test_instructor_cannot_forward_academic():
    with pytest.raises(BusinessRuleError):
        validate_action(RequestCategory.ACADEMIC, RoutingStage.INSTRUCTOR, Action.FORWARD)


def test_head_cannot_forward_administrative():
    with pytest.raises(BusinessRuleError):
        validate_action(RequestCategory.ADMINISTRATIVE, RoutingStage.DEPARTMENT_HEAD, Action.FORWARD)


def test_coordinator_can_forward_and_decide():
    validate_action(RequestCategory.ADMINISTRATIVE, RoutingStage.DEPARTMENT_COORDINATOR, Action.FORWARD)
    validate_action(RequestCategory.ADMINISTRATIVE, RoutingStage.DEPARTMENT_COORDINATOR, Action.APPROVE)


def test_permission_mapping_per_stage():
    assert permission_for(RoutingStage.CLASS_REPRESENTATIVE, Action.FORWARD) == "request:forward"
    assert permission_for(RoutingStage.INSTRUCTOR, Action.APPROVE) == "request:decide_academic"
    assert permission_for(RoutingStage.DEPARTMENT_HEAD, Action.REJECT) == "request:decide_final"
    with pytest.raises(AccessDeniedError):
        permission_for(RoutingStage.INSTRUCTOR, Action.FORWARD)


@pytest.mark.parametrize(
    "role, permission, expected",
    [
        (UserRole.STUDENT, "request:merge_review", False),
        (UserRole.STUDENT, "request:create", True),
        (UserRole.CLASS_REPRESENTATIVE, "request:merge_review", True),
        (UserRole.CLASS_REPRESENTATIVE, "request:decide_academic", False),
        (UserRole.INSTRUCTOR, "request:decide_academic", True),
        (UserRole.DEPARTMENT_COORDINATOR, "request:decide_final", False),
        (UserRole.DEPARTMENT_HEAD, "request:decide_final", True),
    ],
)
def test_role_permission_matrix(role, permission, expected):
    assert role_has_permission(role, permission) is expected


# ---------- التصنيف والتلخيص بلا مفتاح نموذج ----------

def test_classifier_returns_none_without_llm_key():
    assert classify_request("تأجيل الكويز", "نرجو تأجيل الكويز الثاني") is None


def test_summary_falls_back_without_llm_key():
    summary = summarize_batch(["تأجيل الكويز الأول", "تأجيل الكويز الأول أرجو"], RequestCategory.ACADEMIC, 2)
    assert "2" in summary.formal_summary
    assert len(summary.title) >= 3


# ---------- التعارض والتعويض ----------

def test_adjacent_lectures_do_not_conflict():
    snap = ScheduleSnapshot(busy=(_block(1, time(8), time(9, 30), room=5),))
    assert find_conflicts(_block(None, time(9, 30), time(11), room=5), snap) == []


def test_overlap_reports_section_room_and_instructor():
    snap = ScheduleSnapshot(busy=(_block(1, time(8), time(9, 30), room=5),))
    reasons = find_conflicts(_block(None, time(8, 30), time(10), room=5), snap)
    assert len(reasons) == 3


def test_moving_an_occurrence_ignores_itself():
    snap = ScheduleSnapshot(busy=(_block(7, time(8), time(9, 30), room=5),))
    assert find_conflicts(_block(7, time(8), time(9, 30), room=5), snap) == []


def test_instructor_absence_blocks_slot():
    snap = ScheduleSnapshot(
        absences=(AbsenceBlock(local_to_utc(DAY, time(8)), local_to_utc(DAY, time(12)), user_id=10, room_id=None),)
    )
    assert "الدكتور في غياب معلن" in find_conflicts(_block(None, time(9), time(10), room=5), snap)


def test_overlaps_is_strict_at_boundaries():
    a = local_to_utc(DAY, time(8))
    b = local_to_utc(DAY, time(9))
    c = local_to_utc(DAY, time(10))
    assert overlaps(a, b, b, c) is False
    assert overlaps(a, c, b, c) is True


def test_makeup_skips_busy_slots_and_prefers_preferred_room():
    snap = ScheduleSnapshot(busy=(_block(1, time(8), time(9, 30), room=6, section=1),))
    slots = [SlotSpec(1, time(8), time(9, 30), 0), SlotSpec(2, time(9, 30), time(11), 1)]
    rooms = [RoomSpec(5, "B-203", 60, preferred=True), RoomSpec(6, "B-101", 40)]
    query = MakeupQuery(1, 30, frozenset({10}), DAY, 1, DAY, frozenset({4}))
    candidates = find_makeup_candidates(query, slots, rooms, snap, limit=10)
    assert candidates
    assert not any(c.local_date == DAY and c.slot_id == 1 for c in candidates)
    assert candidates[0].slot_id == 2
    assert candidates[0].room_id == 5


def test_makeup_respects_excluded_weekdays():
    slots = [SlotSpec(1, time(8), time(9, 30), 0)]
    rooms = [RoomSpec(5, "B-203", 60)]
    query = MakeupQuery(1, 30, frozenset({10}), DAY, 1, DAY, frozenset({0}))
    candidates = find_makeup_candidates(query, slots, rooms, ScheduleSnapshot(), limit=10)
    assert all(c.local_date != DAY for c in candidates)


# ---------- التوقيت ----------

def test_local_baghdad_time_converts_to_utc():
    # بغداد UTC+3 بلا توقيت صيفي
    assert local_to_utc(date(2030, 1, 7), time(8, 0)).hour == 5


def test_local_day_bounds_span_24_hours():
    start, end = local_day_bounds(date(2030, 1, 7))
    assert (end - start).total_seconds() == 24 * 3600
