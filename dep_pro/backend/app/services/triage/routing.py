from enum import Enum

from app.models import RequestCategory, RequestStatus, RoutingStage, UserRole
from app.services.errors import AccessDeniedError, BusinessRuleError


class Action(str, Enum):
    FORWARD = "forward"
    APPROVE = "approve"
    REJECT = "reject"
    RESOLVE = "resolve"


_DECISIONS: frozenset[Action] = frozenset({Action.APPROVE, Action.REJECT, Action.RESOLVE})

DECISION_STATUS: dict[Action, RequestStatus] = {
    Action.APPROVE: RequestStatus.APPROVED,
    Action.REJECT: RequestStatus.REJECTED,
    Action.RESOLVE: RequestStatus.RESOLVED,
}

TERMINAL_STATUSES: frozenset[RequestStatus] = frozenset({
    RequestStatus.APPROVED,
    RequestStatus.REJECTED,
    RequestStatus.RESOLVED,
    RequestStatus.CLOSED,
})

PATHS: dict[RequestCategory, tuple[RoutingStage, ...]] = {
    RequestCategory.ACADEMIC: (
        RoutingStage.CLASS_REPRESENTATIVE,
        RoutingStage.INSTRUCTOR,
    ),
    RequestCategory.ADMINISTRATIVE: (
        RoutingStage.CLASS_REPRESENTATIVE,
        RoutingStage.DEPARTMENT_COORDINATOR,
        RoutingStage.DEPARTMENT_HEAD,
    ),
}

ALLOWED_ACTIONS: dict[tuple[RequestCategory, RoutingStage], frozenset[Action]] = {
    (RequestCategory.ACADEMIC, RoutingStage.CLASS_REPRESENTATIVE): frozenset({Action.FORWARD}),
    (RequestCategory.ACADEMIC, RoutingStage.INSTRUCTOR): _DECISIONS,
    (RequestCategory.ADMINISTRATIVE, RoutingStage.CLASS_REPRESENTATIVE): frozenset({Action.FORWARD}),
    (RequestCategory.ADMINISTRATIVE, RoutingStage.DEPARTMENT_COORDINATOR): frozenset({Action.FORWARD}) | _DECISIONS,
    (RequestCategory.ADMINISTRATIVE, RoutingStage.DEPARTMENT_HEAD): _DECISIONS,
}

STAGE_ROLE: dict[RoutingStage, UserRole] = {
    RoutingStage.CLASS_REPRESENTATIVE: UserRole.CLASS_REPRESENTATIVE,
    RoutingStage.INSTRUCTOR: UserRole.INSTRUCTOR,
    RoutingStage.DEPARTMENT_COORDINATOR: UserRole.DEPARTMENT_COORDINATOR,
    RoutingStage.DEPARTMENT_HEAD: UserRole.DEPARTMENT_HEAD,
}

_PERMISSION_BY_STAGE: dict[RoutingStage, dict[Action, str]] = {
    RoutingStage.CLASS_REPRESENTATIVE: {Action.FORWARD: "request:forward"},
    RoutingStage.INSTRUCTOR: {action: "request:decide_academic" for action in _DECISIONS},
    RoutingStage.DEPARTMENT_COORDINATOR: {
        Action.FORWARD: "request:decide_administrative",
        **{action: "request:decide_administrative" for action in _DECISIONS},
    },
    RoutingStage.DEPARTMENT_HEAD: {action: "request:decide_final" for action in _DECISIONS},
}


def next_stage(category: RequestCategory, stage: RoutingStage) -> RoutingStage | None:
    path = PATHS[category]
    index = path.index(stage)
    return path[index + 1] if index + 1 < len(path) else None


def validate_action(category: RequestCategory, stage: RoutingStage, action: Action) -> None:
    if action not in ALLOWED_ACTIONS.get((category, stage), frozenset()):
        raise BusinessRuleError("هذا الإجراء غير متاح في المرحلة الحالية للطلب")


def permission_for(stage: RoutingStage, action: Action) -> str:
    try:
        return _PERMISSION_BY_STAGE[stage][action]
    except KeyError as exc:
        raise AccessDeniedError("الإجراء غير متاح لهذه المرحلة") from exc