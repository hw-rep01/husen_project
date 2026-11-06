from app.models.enums import UserRole

ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.STUDENT: frozenset({
        "rag:ask",
        "quiz:take",
        "request:create",
        "request:view_own",
        "schedule:view",
        "broadcast:view",
        "notification:view_own",
    }),
    UserRole.CLASS_REPRESENTATIVE: frozenset({
        "rag:ask",
        "quiz:take",
        "request:create",
        "request:view_own",
        "request:view_section",
        "request:merge_review",
        "request:forward",
        "schedule:view",
        "broadcast:view",
        "broadcast:send_section",
        "notification:view_own",
    }),
    UserRole.INSTRUCTOR: frozenset({
        "rag:ask",
        "rag:manage_material",
        "quiz:create",
        "quiz:view_results",
        "request:view_course",
        "request:decide_academic",
        "schedule:view",
        "schedule:edit_own_course",
        "schedule:suggest_slots",
        "broadcast:view",
        "broadcast:send_course",
        "gaps:view_course",
        "notification:view_own",
    }),
    UserRole.DEPARTMENT_COORDINATOR: frozenset({
        "request:view_department",
        "request:decide_administrative",
        "schedule:view",
        "schedule:edit_department",
        "schedule:suggest_slots",
        "broadcast:view",
        "broadcast:send_department",
        "gaps:view_department",
        "notification:view_own",
    }),
    UserRole.DEPARTMENT_HEAD: frozenset({
        "request:view_department",
        "request:decide_final",
        "schedule:view",
        "schedule:edit_department",
        "broadcast:view",
        "broadcast:send_department",
        "gaps:view_department",
        "notification:view_own",
    }),
}


def role_has_permission(role: UserRole, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())